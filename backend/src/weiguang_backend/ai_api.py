"""Authenticated, secret-safe API for a shared multi-provider model library."""
from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select

from .models import AiProvider, AiTaskSelection, GlobalAiSetting, CliBridgeState, now
from .model_hub import (
    CATALOG_MAP, PROTOCOLS, TASKS, HubClient, ModelHubError,
    encrypt_key, public_provider, public_selection, require_master_key,
    validate_base_url, CLI_PROTOCOLS,
)


class ProviderCreate(BaseModel):
    model_config=ConfigDict(extra="forbid")
    name: str=Field(min_length=1,max_length=120)
    preset: str=Field(min_length=1,max_length=64)
    protocol: Literal["openai_chat","openai_responses","anthropic_messages","gemini_generate"]
    base_url: str=Field(min_length=8,max_length=600)
    api_key: str=Field(min_length=1,max_length=4096)
    json_mode: bool=False


class ProviderPatch(BaseModel):
    model_config=ConfigDict(extra="forbid")
    name: str | None=Field(default=None,min_length=1,max_length=120)
    protocol: Literal["openai_chat","openai_responses","anthropic_messages","gemini_generate"] | None=None
    base_url: str | None=Field(default=None,min_length=8,max_length=600)
    api_key: str | None=Field(default=None,max_length=4096)
    json_mode: bool | None=None


class VersionTest(BaseModel):
    model_id: str=Field(min_length=1,max_length=200)


class ModelBinding(BaseModel):
    task: Literal["teacher","curriculum","edit"]
    provider_id: str=Field(min_length=32,max_length=32)
    model_id: str=Field(min_length=1,max_length=200)


class Assignments(BaseModel):
    model_config=ConfigDict(extra="forbid")
    bindings: list[ModelBinding]=Field(min_length=1,max_length=3)


class GlobalModelInput(BaseModel):
    model_config=ConfigDict(extra="forbid")
    mode: Literal["api","codex_cli","gemini_cli","codebuddy_cli"]
    provider_id: str | None=Field(default=None,min_length=32,max_length=32)
    model_id: str=Field(min_length=1,max_length=200)
    reasoning_effort: str=Field(default="default",max_length=20)
    timeout_seconds: int=Field(default=150,ge=30,le=210)


class GlobalModelTest(GlobalModelInput):
    pass


def _error(exc: ModelHubError, *, status=422):
    return HTTPException(status_code=status,detail=str(exc))


def build_ai_router(SessionLocal,auth):
    router=APIRouter(prefix="/api/v1/ai",dependencies=[Depends(auth)])

    def provider_get(db,identifier):
        provider=db.get(AiProvider,identifier)
        if provider is None or provider.deleted_at is not None:
            raise HTTPException(404,"MODEL_PROVIDER_NOT_FOUND")
        return provider

    def global_provider(db,payload):
        from .cli_bridge import validate_cli_selection
        if payload.mode=="api":
            if not payload.provider_id:
                raise HTTPException(422,"GLOBAL_API_PROVIDER_REQUIRED")
            provider=provider_get(db,payload.provider_id)
            if provider.protocol in CLI_PROTOCOLS:
                raise HTTPException(422,"GLOBAL_PROVIDER_MODE_MISMATCH")
            if payload.reasoning_effort!="default" and provider.protocol not in (
                    "openai_chat","openai_responses"):
                raise HTTPException(422,"MODEL_REASONING_UNAVAILABLE_FOR_PROTOCOL")
            if payload.reasoning_effort not in (
                    "default","none","minimal","low","medium","high","xhigh","max"):
                raise HTTPException(422,"MODEL_REASONING_UNRECOGNIZED")
        else:
            try: validate_cli_selection(payload.mode,payload.model_id,payload.reasoning_effort)
            except ValueError as exc:
                raise HTTPException(422,str(exc)) from exc
            provider=db.scalar(select(AiProvider).where(
                AiProvider.preset==payload.mode,
                AiProvider.protocol==payload.mode,
                AiProvider.deleted_at.is_(None),
            ).order_by(AiProvider.created_at))
            if provider is None:
                provider=AiProvider(
                    name={"codex_cli":"Codex CLI","gemini_cli":"Gemini CLI",
                          "codebuddy_cli":"CodeBuddy CLI"}[payload.mode],
                    preset=payload.mode,protocol=payload.mode,
                    base_url="local-cli://"+payload.mode,
                    encrypted_key="",json_mode=True,
                )
                db.add(provider);db.flush()
        return provider

    @router.get("/global")
    def global_model():
        with SessionLocal() as db:
            row=db.get(GlobalAiSetting,"global")
            if row is None:
                return {"configured":False,
                        "bindings":{task:public_selection(db,task) for task in TASKS}}
            provider=provider_get(db,row.provider_id)
            return {"configured":True,
                    "mode":provider.protocol if provider.protocol in CLI_PROTOCOLS else "api",
                    "provider_id":provider.id,"provider_name":provider.name,
                    "model_id":row.model_id,"reasoning_effort":row.reasoning_effort,
                    "timeout_seconds":row.timeout_seconds}

    @router.put("/global")
    def set_global(payload:GlobalModelInput):
        if not payload.model_id.strip():
            raise HTTPException(422,"MODEL_VERSION_REQUIRED")
        with SessionLocal() as db:
            provider=global_provider(db,payload)
            model_id=payload.model_id.strip()
            for task in TASKS:
                row=db.get(AiTaskSelection,task)
                if row is None:
                    row=AiTaskSelection(task=task);db.add(row)
                row.provider_id=provider.id
                row.model_id=model_id
            setting=db.get(GlobalAiSetting,"global")
            if setting is None:
                setting=GlobalAiSetting(id="global");db.add(setting)
            setting.provider_id=provider.id
            setting.model_id=model_id
            setting.reasoning_effort=payload.reasoning_effort
            setting.timeout_seconds=payload.timeout_seconds
            db.commit()
            return {"configured":True,"mode":payload.mode,"provider_id":provider.id,
                    "provider_name":provider.name,"model_id":model_id,
                    "reasoning_effort":payload.reasoning_effort,
                    "timeout_seconds":payload.timeout_seconds,"applies_to":list(TASKS)}

    @router.post("/global/test")
    def test_global(payload:GlobalModelTest):
        with SessionLocal() as db:
            if payload.mode=="api":
                provider=global_provider(db,payload)
                client=HubClient.from_provider(provider,payload.model_id)
                client.reasoning_effort=payload.reasoning_effort
            else:
                from .cli_bridge import CliClient
                try:
                    client=CliClient(engine=db.get_bind(),kind=payload.mode,
                        model_id=payload.model_id,
                        reasoning_effort=payload.reasoning_effort,
                        timeout_seconds=payload.timeout_seconds)
                except ValueError as exc:
                    raise HTTPException(422,str(exc)) from exc
            try: return client.probe()
            except (ModelHubError,RuntimeError) as exc:
                raise HTTPException(502,str(exc)) from exc

    @router.get("/cli/status")
    def cli_status():
        from .cli_bridge import CLI_KINDS,EFFORT,bridge_connected
        import json
        with SessionLocal() as db:
            row=db.get(CliBridgeState,"windows")
            ready=bridge_connected(db)
            versions=json.loads(row.versions_json) if row and ready else {}
            return {"bridge_connected":ready,
                    "cli":{kind:{"installed":bool(versions.get(kind)),
                                 "version":versions.get(kind,""),
                                 "reasoning_efforts":list(EFFORT[kind])}
                           for kind in CLI_KINDS},
                    "note":"仅支持 Codex、Gemini 与 CodeBuddy CLI，登录由各自官方程序完成。"}

    @router.get("/catalog")
    def catalog():
        return {
            "protocols":list(PROTOCOLS),
            "providers":list(CATALOG_MAP.values()),
            "note":"实时模型列表由服务商返回；不支持列表时可手动填写模型版本 ID。",
        }

    @router.get("/status")
    def status():
        try:
            require_master_key()
            ready=True
        except ModelHubError:
            ready=False
        return {"secret_store_ready":ready,
                "model_families_dynamic":True,
                "manual_model_id_supported":True}

    @router.get("/providers")
    def providers():
        with SessionLocal() as db:
            rows=db.scalars(
                select(AiProvider).where(
                    AiProvider.deleted_at.is_(None)
                ).order_by(AiProvider.created_at)
            )
            return [public_provider(x) for x in rows]

    @router.post("/providers",status_code=201)
    def provider_create(payload: ProviderCreate):
        if payload.preset not in CATALOG_MAP:
            raise HTTPException(422,"MODEL_PRESET_UNKNOWN")
        try:
            safe_url=validate_base_url(payload.base_url)
            secret=encrypt_key(payload.api_key)
        except ModelHubError as exc:
            raise _error(exc) from exc
        with SessionLocal() as db:
            row=AiProvider(
                name=payload.name.strip(),preset=payload.preset,
                protocol=payload.protocol,base_url=safe_url,
                encrypted_key=secret,json_mode=payload.json_mode,
            )
            db.add(row);db.commit();db.refresh(row)
            return public_provider(row)

    @router.patch("/providers/{id}")
    def provider_patch(id: str,payload: ProviderPatch):
        changes=payload.model_dump(exclude_unset=True)
        if not changes:
            raise HTTPException(422,"MODEL_PROVIDER_UPDATE_EMPTY")
        with SessionLocal() as db:
            row=provider_get(db,id)
            current_origin=urlsplit(row.base_url).netloc
            next_url=changes.get("base_url",row.base_url)
            try:
                next_url=validate_base_url(next_url)
                if urlsplit(next_url).netloc!=current_origin and not changes.get("api_key"):
                    raise ModelHubError("MODEL_ENDPOINT_CHANGE_REQUIRES_NEW_KEY")
                if changes.get("api_key"):
                    row.encrypted_key=encrypt_key(changes["api_key"])
            except ModelHubError as exc:
                raise _error(exc) from exc
            for field in ("name","protocol","json_mode"):
                if field in changes and changes[field] is not None:
                    setattr(row,field,changes[field])
            row.base_url=next_url
            row.revision+=1
            db.commit()
            return public_provider(row)

    @router.delete("/providers/{id}")
    def provider_delete(id: str):
        with SessionLocal() as db:
            provider_get(db,id)
            bound=db.scalars(select(AiTaskSelection).where(
                AiTaskSelection.provider_id==id,
            )).first()
            if bound:
                raise HTTPException(409,"MODEL_PROVIDER_IN_USE_CLEAR_SELECTION_FIRST")
            row=provider_get(db,id)
            row.deleted_at=now()
            row.encrypted_key=""  # Destroy saved credential, retain audit identity.
            row.revision+=1
            db.commit()
            return {"deleted":id}

    @router.post("/providers/{id}/models")
    def discover_models(id: str):
        with SessionLocal() as db:
            row=provider_get(db,id)
            try:
                client=HubClient.from_provider(row,"listing-only")
                return client.models()
            except ModelHubError as exc:
                raise _error(exc,status=503) from exc

    @router.post("/providers/{id}/test")
    def test_model(id: str,payload: VersionTest):
        with SessionLocal() as db:
            row=provider_get(db,id)
            try:
                client=HubClient.from_provider(row,payload.model_id)
                return client.probe()
            except ModelHubError as exc:
                raise _error(exc,status=502) from exc

    @router.get("/selections")
    def selections():
        with SessionLocal() as db:
            return {task:public_selection(db,task) for task in TASKS}

    @router.put("/selections")
    def assign_models(payload: Assignments):
        if len({b.task for b in payload.bindings})!=len(payload.bindings):
            raise HTTPException(422,"MODEL_SELECTION_TASK_DUPLICATE")
        with SessionLocal() as db:
            if db.get(GlobalAiSetting,"global") is not None:
                raise HTTPException(409,"USE_GLOBAL_MODEL_SELECTION")
            for binding in payload.bindings:
                if (db.get(AiProvider,binding.provider_id) is None
                        or db.get(AiProvider,binding.provider_id).deleted_at is not None):
                    raise HTTPException(404,"MODEL_PROVIDER_NOT_FOUND")
                if not binding.model_id.strip():
                    raise HTTPException(422,"MODEL_VERSION_REQUIRED")
                existing=db.get(AiTaskSelection,binding.task)
                if existing is None:
                    existing=AiTaskSelection(task=binding.task)
                    db.add(existing)
                existing.provider_id=binding.provider_id
                existing.model_id=binding.model_id.strip()
            db.commit()
            return {task:public_selection(db,task) for task in TASKS}

    @router.delete("/selections/{task}")
    def clear_selection(task: str):
        if task not in TASKS:
            raise HTTPException(404,"MODEL_TASK_UNKNOWN")
        with SessionLocal() as db:
            if db.get(GlobalAiSetting,"global") is not None:
                raise HTTPException(409,"USE_GLOBAL_MODEL_SELECTION")
            row=db.get(AiTaskSelection,task)
            if row is not None:
                db.delete(row);db.commit()
            return {"cleared":task}

    return router
