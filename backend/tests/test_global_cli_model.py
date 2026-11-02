"""Actual PostgreSQL global CLI selection and authenticated task round trip."""
import threading
import time
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select
from weiguang_backend.cli_bridge import CliClient
from weiguang_backend.main import create_app
from weiguang_backend.models import (
    AiJobRuntime,AiJobSelection,AiTaskSelection,CliInferenceRequest,Job,Lesson,
)

def studio(tmp_path,monkeypatch):
    monkeypatch.setenv("WEIGUANG_CLI_BRIDGE_TOKEN","ci-local-bridge-token")
    monkeypatch.setenv("WEIGUANG_MODEL_MASTER_KEY",Fernet.generate_key().decode())
    monkeypatch.setenv("WEIGUANG_API_TOKEN","")
    app=create_app(data_dir=tmp_path,local_dev=True,eager=False)
    return TestClient(app),app

def test_global_selection_applies_to_all_pipeline_tasks_and_pins_effort(tmp_path,monkeypatch):
    client,app=studio(tmp_path,monkeypatch)
    r=client.put("/api/v1/ai/global",json={
        "mode":"codex_cli","model_id":"gpt-6.1-sol",
        "reasoning_effort":"high","timeout_seconds":180})
    assert r.status_code==200,r.text
    assert r.json()["applies_to"]==["teacher","curriculum","edit"]
    with app.state.SessionLocal() as db:
        selected=[db.get(AiTaskSelection,t) for t in ("teacher","curriculum","edit")]
        assert len({x.provider_id for x in selected})==1
        assert len({x.model_id for x in selected})==1
        lesson=Lesson(title="测试题",problem="1+1",reference_solution="2")
        db.add(lesson);db.flush()
        from weiguang_backend.model_hub import pin_job_selection,pinned_client
        job=Job(lesson_id=lesson.id,kind="teacher")
        db.add(job);db.flush();pin_job_selection(db,job,"teacher");db.commit()
        assert db.get(AiJobSelection,job.id).model_id=="gpt-6.1-sol"
        assert db.get(AiJobRuntime,job.id).reasoning_effort=="high"
        assert pinned_client(db,job.id).reasoning_effort=="high"
    change=client.put("/api/v1/ai/global",json={
        "mode":"gemini_cli","model_id":"gemini-2.5-pro",
        "reasoning_effort":"medium"})
    assert change.status_code==200,change.text
    with app.state.SessionLocal() as db:
        assert db.get(AiJobSelection,job.id).model_id=="gpt-6.1-sol"
    legacy=client.put("/api/v1/ai/selections",json={"bindings":[{
        "task":"edit","provider_id":r.json()["provider_id"],"model_id":"different"}]})
    assert legacy.status_code==409
    app.state.db_engine.dispose()

def test_invalid_model_effort_and_workbuddy_limit(tmp_path,monkeypatch):
    client,app=studio(tmp_path,monkeypatch)
    status=client.get("/api/v1/ai/cli/status").json()
    assert status["bridge_connected"] is False
    assert status["workbuddy_desktop_external_model_override_verified"] is False
    for candidate in [
        {"mode":"codex_cli","model_id":"gpt-6.1-sol","reasoning_effort":"none"},
        {"mode":"gemini_cli","model_id":"bad && inject"},
        {"mode":"codebuddy_cli","model_id":"reasoning","reasoning_effort":"undefined"},
    ]:
        assert client.put("/api/v1/ai/global",json=candidate).status_code==422
    assert client.get("/api/v1/ai/global").json()["configured"] is False
    app.state.db_engine.dispose()

def test_authenticated_bridge_lease_and_one_shot_json_roundtrip(tmp_path,monkeypatch):
    client,app=studio(tmp_path,monkeypatch)
    url="/api/v1/ai/cli/"
    assert client.get(url+"next").status_code==403
    assert client.get(url+"next",headers={"X-CLI-Bridge-Token":"bad"}).status_code==403
    headers={"X-CLI-Bridge-Token":"ci-local-bridge-token"}
    assert client.post(url+"heartbeat",headers=headers,json={
        "versions":{"codex_cli":"installed","other":"blocked"}}).status_code==200
    done={}
    def generate():
        try:
            cli=CliClient(engine=app.state.db_engine,kind="codex_cli",model_id="gpt-6.1-sol")
            done["output"]=cli.generate_json(system="JSON",user_json='{"x":1}',timeout=20)
        except Exception as exc: done["error"]=str(exc)
    thread=threading.Thread(target=generate,daemon=True);thread.start()
    task=None
    for _ in range(60):
        response=client.get(url+"next",headers=headers)
        assert response.status_code==200
        task=response.json()["task"]
        if task:break
        time.sleep(.1)
    assert task is not None
    assert task["model_id"]=="gpt-6.1-sol"
    bad=client.post(url+"result",headers=headers,json={
        "id":task["id"],"lease_token":"f"*64,"output":{"ok":True}})
    assert bad.status_code==409
    success=client.post(url+"result",headers=headers,json={
        "id":task["id"],"lease_token":task["lease_token"],
        "output":{"lesson":"ready","ok":True}})
    assert success.status_code==200,success.text
    replay=client.post(url+"result",headers=headers,json={
        "id":task["id"],"lease_token":task["lease_token"],"output":{"ok":False}})
    assert replay.status_code==409
    thread.join(8)
    assert not thread.is_alive()
    assert done=={"output":{"lesson":"ready","ok":True}}
    with app.state.SessionLocal() as db:
        assert db.scalars(select(CliInferenceRequest)).first() is None
    app.state.db_engine.dispose()
