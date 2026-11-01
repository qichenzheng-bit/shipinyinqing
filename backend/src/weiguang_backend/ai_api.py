"""Authenticated, secret-safe API for a shared multi-provider model library."""
from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select

from .models import AiProvider, AiTaskSelection, now
from .model_hub import (
    CATALOG_MAP, PROTOCOLS, TASKS, HubClient, ModelHubError,
    encrypt_key, public_provider, public_selection, require_master_key,
    validate_base_url,
)


class ProviderCreate(BaseModel):
    model_config=ConfigDict(extra="forbid")
    name: str=Field(min_length=1,max_length=120)
    preset: str=Field(min_length=1,max_length=64)
    protocol: Literal["openai_chat","anthropic_messages","gemini_generate"]
    base_url: str=Field(min_length=8,max_length=600)
    api_key: str=Field(min_length=1,max_length=4096)
    json_mode: bool=False


class ProviderPatch(BaseModel):
    model_config=ConfigDict(extra="forbid")
    name: str | None=Field(default=None,min_length=1,max_length=120)
    protocol: Literal["openai_chat","anthropic_messages","gemini_generate"] | None=None
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


def _error(exc: ModelHubError, *, status=422):
    return HTTPException(status_code=status,detail=str(exc))


def build_ai_router(SessionLocal,auth):
    router=APIRouter(prefix="/api/v1/ai",dependencies=[Depends(auth)])

    def provider_get(db,identifier):
        provider=db.get(AiProvider,identifier)
        if provider is None or provider.deleted_at is not None:
            raise HTTPException(404,"MODEL_PROVIDER_NOT_FOUND")
        return provider

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
            row=db.get(AiTaskSelection,task)
            if row is not None:
                db.delete(row);db.commit()
            return {"cleared":task}

    return router
