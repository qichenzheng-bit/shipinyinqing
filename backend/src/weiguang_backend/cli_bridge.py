"""Authenticated Windows-local CLI task bridge.

Docker never runs host commands. Electron polls with a dedicated secret and
delivers bounded JSON results. CLI credentials remain on the Windows host.
"""
from __future__ import annotations
import hmac
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from typing import Any
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker
from .models import CliBridgeState, CliInferenceRequest

CLI_KINDS = ("codex_cli", "gemini_cli", "codebuddy_cli")
EFFORT = {
    "codex_cli": ("default", "low", "medium", "high", "xhigh", "max"),
    "gemini_cli": ("default", "low", "medium", "high"),
    "codebuddy_cli": ("default", "minimal", "low", "medium", "high", "xhigh", "max"),
}
MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+\-]{0,199}$")
MAX_PROMPT = 200_000
MAX_RESULT = 2_000_000

def validate_cli_selection(kind: str, model_id: str, effort: str) -> None:
    if kind not in CLI_KINDS:
        raise ValueError("CLI_PROVIDER_NOT_SUPPORTED")
    if not MODEL_ID.fullmatch(model_id or ""):
        raise ValueError("CLI_MODEL_ID_INVALID")
    if effort not in EFFORT[kind]:
        raise ValueError("CLI_REASONING_EFFORT_NOT_SUPPORTED")

def bridge_connected(db) -> bool:
    row = db.get(CliBridgeState, "windows")
    if row is None:
        return False
    last = row.last_seen
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)-last < timedelta(seconds=32)

class CliClient:
    """HubClient-compatible JSON + typed-schema inference."""
    def __init__(self, *, engine, kind: str, model_id: str,
                 reasoning_effort: str="default", timeout_seconds: int=150):
        validate_cli_selection(kind, model_id, reasoning_effort)
        self.protocol=kind
        self.model_id=model_id
        self.reasoning_effort=reasoning_effort
        self.timeout_seconds=min(max(int(timeout_seconds),30),210)
        self.SessionLocal=sessionmaker(engine,expire_on_commit=False)

    def models(self):
        return {"models":[],"source":"manual","manual_allowed":True,
                "notice":"输入当前 CLI 账号可用的精确模型 ID 并执行真实连接测试。"}

    def generate_json(self, *, system: str, user_json: str, timeout: int=150) -> dict:
        payload=json.dumps({"system":system+"\nOnly return a JSON object. Do not use tools or edit files.",
                            "user_json":user_json},ensure_ascii=False)
        if len(payload)>MAX_PROMPT:
            raise RuntimeError("CLI_INPUT_EXCEEDS_SAFE_LIMIT")
        timeout=min(max(int(timeout),5),self.timeout_seconds)
        with self.SessionLocal() as db:
            if not bridge_connected(db):
                raise RuntimeError("WINDOWS_CLI_BRIDGE_OFFLINE_OPEN_LOCAL_APP")
            req=CliInferenceRequest(provider=self.protocol,model_id=self.model_id,
                reasoning_effort=self.reasoning_effort,payload=payload,
                expires_at=datetime.now(timezone.utc)+timedelta(seconds=timeout))
            db.add(req);db.commit();rid=req.id
        deadline=time.monotonic()+timeout
        try:
            while time.monotonic()<deadline:
                with self.SessionLocal() as db:
                    row=db.get(CliInferenceRequest,rid)
                    if row is None:
                        raise RuntimeError("CLI_REQUEST_LOST")
                    if row.state=="error":
                        raise RuntimeError(row.error or "CLI_EXECUTION_FAILED")
                    if row.state=="done":
                        try: data=json.loads(row.output or "null")
                        except ValueError as exc:
                            raise RuntimeError("CLI_RESPONSE_NOT_JSON") from exc
                        if not isinstance(data,dict):
                            raise RuntimeError("CLI_RESPONSE_NOT_JSON_OBJECT")
                        return data
                time.sleep(.45)
            raise RuntimeError("CLI_GENERATION_TIMEOUT")
        finally:
            with self.SessionLocal.begin() as db:
                db.execute(delete(CliInferenceRequest).where(CliInferenceRequest.id==rid))

    def generate(self, *, stage: str, system: str, user_json: str, schema):
        from pydantic import ValidationError
        data=self.generate_json(system=system,user_json=user_json)
        try: return schema.model_validate(data)
        except ValidationError as exc:
            raise RuntimeError("CLI_RESPONSE_SCHEMA_MISMATCH") from exc

    def probe(self):
        data=self.generate_json(system='Return exactly JSON object {"ok":true}.',
                                user_json='Return {"ok":true}.',timeout=65)
        if data.get("ok") is not True:
            raise RuntimeError("CLI_TEST_DID_NOT_RETURN_EXPECTED_JSON")
        return {"status":"connected","model_id":self.model_id,
                "protocol":self.protocol,"json_output":True}

class Heartbeat(BaseModel):
    model_config=ConfigDict(extra="forbid")
    versions: dict[str,str]=Field(default_factory=dict)

class CliResult(BaseModel):
    model_config=ConfigDict(extra="forbid")
    id: str=Field(pattern=r"^[0-9a-f]{32}$")
    lease_token: str=Field(pattern=r"^[0-9a-f]{64}$")
    output: dict[str,Any] | None=None
    error: str | None=Field(default=None,max_length=120)

def build_bridge_router(SessionLocal):
    router=APIRouter(prefix="/api/v1/ai/cli")
    def require_bridge(token: str | None=Header(default=None,alias="X-CLI-Bridge-Token")):
        expected=os.environ.get("WEIGUANG_CLI_BRIDGE_TOKEN","")
        if not expected or not token or not hmac.compare_digest(expected,token):
            raise HTTPException(403,"CLI_BRIDGE_AUTH_REQUIRED")

    @router.post("/heartbeat")
    def heartbeat(payload:Heartbeat,_=Depends(require_bridge)):
        versions={k:str(v)[:100] for k,v in payload.versions.items() if k in CLI_KINDS}
        with SessionLocal.begin() as db:
            state=db.get(CliBridgeState,"windows")
            if state is None:
                state=CliBridgeState(id="windows");db.add(state)
            state.last_seen=datetime.now(timezone.utc)
            state.versions_json=json.dumps(versions)
        return {"ok":True}

    @router.get("/next")
    def next_request(_=Depends(require_bridge)):
        with SessionLocal.begin() as db:
            row=db.scalar(select(CliInferenceRequest).where(
                CliInferenceRequest.state=="queued",
                CliInferenceRequest.expires_at>datetime.now(timezone.utc),
            ).order_by(CliInferenceRequest.created_at)
                          .with_for_update(skip_locked=True).limit(1))
            if row is None:
                return {"task":None}
            row.state="leased";row.lease_token=uuid4().hex+uuid4().hex
            return {"task":{"id":row.id,"lease_token":row.lease_token,
                            "provider":row.provider,"model_id":row.model_id,
                            "reasoning_effort":row.reasoning_effort,
                            "payload":json.loads(row.payload)}}

    @router.post("/result")
    def result(payload:CliResult,_=Depends(require_bridge)):
        if payload.output is None and not payload.error:
            raise HTTPException(422,"CLI_RESULT_MISSING")
        if payload.output is not None and len(json.dumps(payload.output,ensure_ascii=False))>MAX_RESULT:
            raise HTTPException(413,"CLI_OUTPUT_TOO_LARGE")
        with SessionLocal.begin() as db:
            row=db.scalar(select(CliInferenceRequest).where(
                CliInferenceRequest.id==payload.id).with_for_update())
            if row is None or row.state!="leased" or not hmac.compare_digest(
                row.lease_token or "",payload.lease_token):
                raise HTTPException(409,"CLI_RESULT_NOT_MATCHING_REQUEST")
            row.state="error" if payload.error else "done"
            row.output=json.dumps(payload.output,ensure_ascii=False) if payload.output is not None else None
            row.error=payload.error
        return {"ok":True}
    return router
