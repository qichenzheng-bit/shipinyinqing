"""Multi-provider API library: encrypted keys, exact versions, job pinning."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from weiguang_backend.main import create_app
from weiguang_backend.model_hub import (
    CATALOG_MAP, HubClient, ModelHubError, decrypt_key, validate_base_url,
)
from weiguang_backend.models import (
    AiJobSelection, AiProvider, AiTaskSelection, Job, Lesson,
)


@pytest.fixture
def studio(tmp_path,monkeypatch):
    monkeypatch.setenv("WEIGUANG_MODEL_MASTER_KEY",Fernet.generate_key().decode())
    monkeypatch.delenv("WEIGUANG_ALLOW_PRIVATE_MODEL_ENDPOINTS",raising=False)
    app=create_app(data_dir=tmp_path/"ai-config",local_dev=True,eager=False)
    import weiguang_backend.worker as worker
    dispatched=[]
    monkeypatch.setattr(
        worker.celery_app,"send_task",
        lambda name,args=None,**kwargs:dispatched.append((name,args)),
    )
    return TestClient(app),dispatched


def save_provider(client,*,name="Claude 模型组",protocol="anthropic_messages",
                  preset="anthropic",base_url="https://api.anthropic.com/v1",
                  api_key="secret-key-never-echo"):
    result=client.post("/api/v1/ai/providers",json={
        "name":name,"preset":preset,"protocol":protocol,
        "base_url":base_url,"api_key":api_key,"json_mode":False,
    })
    assert result.status_code==201,result.text
    return result.json()


def test_catalog_and_secret_encryption_never_return_plaintext(studio):
    client,_=studio
    catalog=client.get("/api/v1/ai/catalog")
    assert catalog.status_code==200
    providers={x["id"]:x for x in catalog.json()["providers"]}
    for name in ("openai","anthropic","gemini","deepseek","qwen",
                 "zhipu","openrouter","ollama","custom"):
        assert name in providers
    assert client.get("/api/v1/ai/status").json()["secret_store_ready"] is True
    row=save_provider(client)
    assert row["has_key"] is True
    assert "api_key" not in row and "encrypted_key" not in row
    with client.app.state.SessionLocal() as db:
        saved=db.get(AiProvider,row["id"])
        assert "secret-key-never-echo" not in saved.encrypted_key
        assert decrypt_key(saved.encrypted_key)=="secret-key-never-echo"
    listed=client.get("/api/v1/ai/providers")
    assert listed.status_code==200
    assert "secret-key-never-echo" not in listed.text
    assert "encrypted_key" not in listed.text
    original_version=row["revision"]
    edited=client.patch("/api/v1/ai/providers/"+row["id"],json={
        "name":"Claude 新配置",
    })
    assert edited.status_code==200
    assert edited.json()["revision"]==original_version+1
    with client.app.state.SessionLocal() as db:
        assert decrypt_key(db.get(AiProvider,row["id"]).encrypted_key)==(
            "secret-key-never-echo"
        )


def test_dynamic_model_discovery_three_protocols_and_manual_fallback(monkeypatch):
    def upstream(client,suffix,body=None,timeout=90):
        if client.protocol=="openai_chat":
            return {"data":[
                {"id":"family-2026-01"},{"id":"family-2026-11"},
            ]}
        if client.protocol=="anthropic_messages":
            return {"data":[{"id":"claude-rev-A"},{"id":"claude-rev-B"}]}
        return {"models":[
            {"name":"models/gemini-release-001",
             "displayName":"Gemini stable",
             "supportedGenerationMethods":["generateContent"]},
            {"name":"models/gemini-image","supportedGenerationMethods":["embedContent"]},
        ]}
    monkeypatch.setattr(HubClient,"_request",upstream)
    settings=[
        ("openai_chat","https://api.openai.com/v1",
         ("family-2026-01","family-2026-11")),
        ("anthropic_messages","https://api.anthropic.com/v1",
         ("claude-rev-A","claude-rev-B")),
        ("gemini_generate","https://generativelanguage.googleapis.com/v1beta",
         ("gemini-release-001",)),
    ]
    for protocol,base_url,expected in settings:
        model=HubClient(protocol=protocol,base_url=base_url,
                        api_key="test-key",model_id=expected[0])
        found=model.models()
        assert found["source"]=="live"
        assert {m["id"] for m in found["models"]}==set(expected)
    def denied(*args,**kwargs):
        raise ModelHubError("MODEL_UPSTREAM_HTTP_404")
    monkeypatch.setattr(HubClient,"_request",denied)
    missing=HubClient(protocol="openai_chat",base_url="https://api.openai.com/v1",
                      api_key="key",model_id="manual-id").models()
    assert missing["source"]=="manual"
    assert missing["manual_allowed"] is True
    assert missing["models"]==[]


def test_native_generation_json_transport_and_version_identity(monkeypatch):
    calls=[]
    def upstream(client,suffix,body=None,timeout=90):
        calls.append((client.protocol,client.model_id,suffix,body))
        if client.protocol=="openai_chat":
            return {"choices":[{"message":{"content":'{"ok":true}'}}]}
        if client.protocol=="anthropic_messages":
            return {"content":[{"type":"text","text":'{"ok":true}'}]}
        return {"candidates":[{"content":{"parts":[{"text":'{"ok":true}'}]}}]}
    monkeypatch.setattr(HubClient,"_request",upstream)
    for protocol,url in [
        ("openai_chat","https://api.openai.com/v1"),
        ("anthropic_messages","https://api.anthropic.com/v1"),
        ("gemini_generate","https://generativelanguage.googleapis.com/v1beta"),
    ]:
        model=HubClient(protocol=protocol,base_url=url,api_key="test",
                        model_id="family-revision-2026-11")
        assert model.probe()["status"]=="connected"
    assert calls[0][3]["model"]=="family-revision-2026-11"
    assert calls[1][2]=="/messages"
    assert calls[2][2]=="/models/family-revision-2026-11:generateContent"
    assert calls[2][3]["systemInstruction"]["parts"]


def test_atomic_shared_or_independent_task_bindings_and_job_pin(studio):
    client,dispatched=studio
    row=save_provider(client)
    other=save_provider(client,name="OpenAI",
        protocol="openai_chat",preset="openai",
        base_url="https://api.openai.com/v1",api_key="different-key")
    model_name="claude-precise-2026-11"
    selected=client.put("/api/v1/ai/selections",json={"bindings":[
        {"task":task,"provider_id":row["id"],"model_id":model_name}
        for task in ("teacher","curriculum","edit")
    ]})
    assert selected.status_code==200,selected.text
    assert all(x["model_id"]==model_name for x in selected.json().values())
    changed=client.put("/api/v1/ai/selections",json={"bindings":[{
        "task":"edit","provider_id":other["id"],"model_id":"gpt-new-version"
    }]})
    assert changed.status_code==200
    assert changed.json()["teacher"]["model_id"]==model_name
    assert changed.json()["edit"]["model_id"]=="gpt-new-version"
    bad=client.put("/api/v1/ai/selections",json={"bindings":[
        {"task":"teacher","provider_id":row["id"],"model_id":"test"},
        {"task":"edit","provider_id":"0"*32,"model_id":"test"},
    ]})
    assert bad.status_code==404
    assert client.get("/api/v1/ai/selections").json()["teacher"]["model_id"]==model_name

    lesson=client.post("/api/v1/lessons",json={
        "title":"固定模型版本的题","problem":"证明一个极限",
        "reference_solution":"给定可审核的参考证明",
    }).json()
    queued=client.post("/api/v1/lessons/"+lesson["id"]+"/prepare")
    assert queued.status_code==202,queued.text
    job_id=queued.json()["id"]
    assert dispatched and dispatched[-1][1]==[job_id]
    with client.app.state.SessionLocal() as db:
        pinned=db.get(AiJobSelection,job_id)
        assert pinned is not None
        assert pinned.provider_id==row["id"]
        assert pinned.model_id==model_name
        assert pinned.provider_revision==row["revision"]
    revision=client.patch("/api/v1/ai/providers/"+row["id"],json={
        "json_mode":True,
    })
    assert revision.status_code==200
    client.app.state.run_job(job_id)
    failed=client.get("/api/v1/jobs/"+job_id).json()
    assert failed["status"]=="failed"
    assert "MODEL_PROVIDER_CHANGED_AFTER_JOB_QUEUED" in failed["error"]


def test_provider_delete_unbind_and_protect_credentials(studio):
    client,_=studio
    row=save_provider(client)
    binding=client.put("/api/v1/ai/selections",json={"bindings":[{
        "task":"teacher","provider_id":row["id"],"model_id":"claude-v1",
    }]})
    assert binding.status_code==200
    assert client.delete("/api/v1/ai/providers/"+row["id"]).status_code==409
    assert client.delete("/api/v1/ai/selections/teacher").status_code==200
    deleted=client.delete("/api/v1/ai/providers/"+row["id"])
    assert deleted.status_code==200
    assert client.get("/api/v1/ai/providers").json()==[]
    assert client.get("/api/v1/ai/selections").json()["teacher"] is None


def test_keys_and_network_endpoint_security(studio,monkeypatch):
    client,_=studio
    for addr in (
        "http://127.0.0.1:11434/v1",
        "https://127.0.0.1/v1",
        "https://169.254.169.254/v1",
        "http://malicious.example/v1",
        "https://user:pass@host.example/v1",
    ):
        result=client.post("/api/v1/ai/providers",json={
            "name":"blocked","preset":"custom","protocol":"openai_chat",
            "base_url":addr,"api_key":"not-leaked",
        })
        assert result.status_code==422,(addr,result.text)
    assert "not-leaked" not in client.get("/api/v1/ai/providers").text
    monkeypatch.setenv("WEIGUANG_ALLOW_PRIVATE_MODEL_ENDPOINTS","1")
    local=client.post("/api/v1/ai/providers",json={
        "name":"Local Ollama","preset":"ollama","protocol":"openai_chat",
        "base_url":"http://localhost:11434/v1","api_key":"ollama",
    })
    assert local.status_code==201,local.text
    saved=save_provider(client)
    changed=client.patch("/api/v1/ai/providers/"+saved["id"],json={
        "base_url":"https://different.example/v1",
    })
    assert changed.status_code==422
    assert "KEY" in changed.text



def test_selected_version_is_used_by_both_teacher_and_curriculum(studio,monkeypatch,tmp_path):
    import importlib
    module=importlib.import_module("weiguang_backend.main")
    compiler=importlib.import_module("weiguang_backend.compiler")
    client,_=studio
    provider=save_provider(client,protocol="openai_chat",preset="openai",
        name="统一模型",base_url="https://api.openai.com/v1")
    version="my-mathematics-version-2026-11"
    assert client.put("/api/v1/ai/selections",json={"bindings":[
        {"task":task,"provider_id":provider["id"],"model_id":version}
        for task in ("teacher","curriculum")
    ]}).status_code==200
    calls=[]
    def teacher(*,problem,reference_solution,output,provider):
        calls.append(("teacher",provider.model_id))
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps({"source":{"problem":problem}}),encoding="utf-8")
        return {"status":"teacher_draft_needs_review"}
    def curriculum(problem,reference_solution,teacher_package,candidate_path,*,provider):
        calls.append(("curriculum",provider.model_id))
        candidate_path.write_text("{}",encoding="utf-8")
        return {"status":"curriculum_candidate_waiting_review"}
    monkeypatch.setattr(module,"prepare_teacher_draft",teacher)
    monkeypatch.setattr(compiler,"draft_curriculum",curriculum)
    lesson=client.post("/api/v1/lessons",json={
        "title":"统一 API 课","problem":"求导数",
        "reference_solution":"先求极限再求导",
    }).json()
    first=client.post(f"/api/v1/lessons/{lesson['id']}/prepare")
    assert first.status_code==202,first.text
    assert first.json()["status"]=="queued"
    client.app.state.run_job(first.json()["id"])
    assert client.get("/api/v1/jobs/"+first.json()["id"]).json()["status"]=="succeeded"
    assert client.post(
        f"/api/v1/lessons/{lesson['id']}/teaching/review",
        json={"reviewer":"课程审核老师","confirmed":True},
    ).status_code==200
    second=client.post(f"/api/v1/lessons/{lesson['id']}/curriculum/prepare")
    assert second.status_code==202,second.text
    client.app.state.run_job(second.json()["id"])
    assert client.get("/api/v1/jobs/"+second.json()["id"]).json()["status"]=="succeeded"
    assert calls==[("teacher",version),("curriculum",version)]


def test_selected_model_is_used_for_micro_edit_candidates(studio,monkeypatch,tmp_path):
    import importlib
    module=importlib.import_module("weiguang_backend.edit_review")
    client,_=studio
    provider=save_provider(client,protocol="openai_chat",preset="openai",
        name="微调模型",base_url="https://api.openai.com/v1")
    version="unit-edit-model-version-2"
    assert client.put("/api/v1/ai/selections",json={"bindings":[{
        "task":"edit","provider_id":provider["id"],"model_id":version,
    }]}).status_code==200
    lesson=client.post("/api/v1/lessons",json={
        "title":"待微调","problem":"1+1","reference_solution":"2",
    }).json()
    src=tmp_path/"package"
    src.mkdir()
    (src/"spoken_classroom.json").write_text('{"mode":"test"}',encoding="utf-8")
    with client.app.state.SessionLocal() as db:
        item=db.get(Lesson,lesson["id"])
        item.status="ready";item.session_path=str(tmp_path/"session")
        db.commit()
    captured=[]
    def fake_generation(self,*,system,user_json,timeout=150):
        captured.append((self.model_id,json.loads(user_json)["exact_user_instruction"]))
        return {"schema_version":"1.0","requirements":[],"operations":[]}
    def fake_prepare(session,instruction,*,agent):
        result=agent(instruction,src,[])
        assert result["model"]==version
        return {"review_path":str(tmp_path),"status":"review_pending"}
    monkeypatch.setattr(HubClient,"generate_json",fake_generation)
    monkeypatch.setattr(module,"prepare_edit_review",fake_prepare)
    accepted=client.post(f"/api/v1/videos/{lesson['id']}/edits",
        json={"instruction":"只修改语音衔接"})
    assert accepted.status_code==202,accepted.text
    client.app.state.run_job(accepted.json()["job"]["id"])
    status=client.get("/api/v1/jobs/"+accepted.json()["job"]["id"]).json()
    assert status["status"]=="succeeded",status
    assert captured==[(version,"只修改语音衔接")]
