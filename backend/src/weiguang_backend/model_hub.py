"""One provider/model registry for mathematics A/B/C, curriculum and edits.

Live model discovery is authoritative when offered; user-entered exact model
IDs remain available for providers without GET /models or with scoped access.
Only typed JSON responses are accepted by teaching and edit workflows.
"""
from __future__ import annotations

import base64
import ipaddress
import json
import os
import socket
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener

from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel, ValidationError

from .models import AiJobSelection, AiProvider, AiTaskSelection

TASKS = ("teacher", "curriculum", "edit")
PROTOCOLS = ("openai_chat", "anthropic_messages", "gemini_generate")
# Service URLs are *templates*, never an exhaustive or frozen model list.
# Regional accounts, gateways and new families use the same custom endpoint.
CATALOG = (
    ("openai", "OpenAI", "openai_chat", "https://api.openai.com/v1"),
    ("anthropic", "Anthropic / Claude", "anthropic_messages", "https://api.anthropic.com/v1"),
    ("gemini", "Google / Gemini", "gemini_generate", "https://generativelanguage.googleapis.com/v1beta"),
    ("deepseek", "DeepSeek", "openai_chat", "https://api.deepseek.com"),
    ("qwen", "阿里百炼 / Qwen", "openai_chat", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    ("zhipu", "智谱 / GLM", "openai_chat", "https://open.bigmodel.cn/api/paas/v4"),
    ("moonshot", "月之暗面 / Kimi", "openai_chat", "https://api.moonshot.cn/v1"),
    ("doubao", "火山引擎 / 豆包", "openai_chat", "https://ark.cn-beijing.volces.com/api/v3"),
    ("minimax", "MiniMax", "openai_chat", "https://api.minimax.io/v1"),
    ("xai", "xAI / Grok", "openai_chat", "https://api.x.ai/v1"),
    ("mistral", "Mistral", "openai_chat", "https://api.mistral.ai/v1"),
    ("groq", "Groq", "openai_chat", "https://api.groq.com/openai/v1"),
    ("together", "Together AI", "openai_chat", "https://api.together.xyz/v1"),
    ("fireworks", "Fireworks AI", "openai_chat", "https://api.fireworks.ai/inference/v1"),
    ("openrouter", "OpenRouter / 聚合模型", "openai_chat", "https://openrouter.ai/api/v1"),
    ("siliconflow", "硅基流动", "openai_chat", "https://api.siliconflow.cn/v1"),
    ("perplexity", "Perplexity", "openai_chat", "https://api.perplexity.ai"),
    ("ollama", "Ollama 本地模型", "openai_chat", "http://localhost:11434/v1"),
    ("lmstudio", "LM Studio 本地模型", "openai_chat", "http://localhost:1234/v1"),
    ("custom", "自定义兼容接口", "openai_chat", ""),
)
CATALOG_MAP = {key: {"id":key, "label":label, "protocol":protocol, "base_url":url}
               for key,label,protocol,url in CATALOG}


class ModelHubError(RuntimeError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def require_master_key() -> Fernet:
    raw = os.environ.get("WEIGUANG_MODEL_MASTER_KEY","")
    if not raw:
        raise ModelHubError("MODEL_MASTER_KEY_NOT_CONFIGURED")
    try:
        return Fernet(raw.encode("ascii"))
    except (ValueError, TypeError) as exc:
        raise ModelHubError("MODEL_MASTER_KEY_INVALID") from exc


def encrypt_key(secret: str) -> str:
    if not isinstance(secret,str) or not secret.strip() or len(secret)>4096:
        raise ModelHubError("MODEL_API_KEY_INVALID")
    return require_master_key().encrypt(secret.strip().encode("utf-8")).decode("ascii")


def decrypt_key(ciphertext: str) -> str:
    try:
        return require_master_key().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeDecodeError) as exc:
        raise ModelHubError("MODEL_MASTER_KEY_MISMATCH") from exc


def allow_private_network() -> bool:
    # Explicit opt-in for personal Ollama / LM Studio. Never enable on a public
    # deployment without understanding that the server can reach private URLs.
    return os.environ.get("WEIGUANG_ALLOW_PRIVATE_MODEL_ENDPOINTS")=="1"


def validate_base_url(value: str) -> str:
    if not isinstance(value,str) or len(value)>600:
        raise ModelHubError("MODEL_ENDPOINT_INVALID")
    value=value.strip().rstrip("/")
    try:
        parsed=urlsplit(value)
        hostname=parsed.hostname
        port=parsed.port
    except ValueError as exc:
        raise ModelHubError("MODEL_ENDPOINT_INVALID") from exc
    if (not hostname or parsed.scheme not in ("https","http")
            or parsed.username or parsed.password or parsed.query
            or parsed.fragment or not isinstance(port,(type(None),int))):
        raise ModelHubError("MODEL_ENDPOINT_INVALID")
    if any(s in parsed.path for s in ("..","\\","//")):
        raise ModelHubError("MODEL_ENDPOINT_PATH_INVALID")
    if parsed.scheme=="http" and not allow_private_network():
        raise ModelHubError("MODEL_HTTP_ENDPOINT_REQUIRES_PRIVATE_OPT_IN")
    if hostname in ("localhost","host.docker.internal") or hostname.endswith((".local",".internal",".localhost")):
        if not allow_private_network():
            raise ModelHubError("MODEL_PRIVATE_ENDPOINT_DISABLED")
    try:
        address=ipaddress.ip_address(hostname)
    except ValueError:
        address=None
    if address is not None and not address.is_global and not allow_private_network():
        raise ModelHubError("MODEL_PRIVATE_ENDPOINT_DISABLED")
    if parsed.scheme=="http" and address is None and hostname not in (
            "localhost","host.docker.internal") and not hostname.endswith((".local",".internal")):
        raise ModelHubError("MODEL_REMOTE_HTTP_FORBIDDEN")
    return value


def _guard_dns(url: str):
    hostname=urlsplit(url).hostname
    if not hostname:
        raise ModelHubError("MODEL_ENDPOINT_INVALID")
    if allow_private_network():
        return
    try:
        addresses=socket.getaddrinfo(hostname,None,type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ModelHubError("MODEL_ENDPOINT_DNS_UNAVAILABLE") from exc
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global
                            for row in addresses):
        raise ModelHubError("MODEL_ENDPOINT_PRIVATE_IP_REJECTED")


def request_json(url: str, *, method="GET", headers=None, body=None,
                 timeout=25) -> dict:
    """No redirects, bounded JSON, no raw body/secret in errors or logs."""
    _guard_dns(url)
    payload=(json.dumps(body,ensure_ascii=False).encode("utf-8")
             if body is not None else None)
    req=Request(url,data=payload,method=method,headers={
        "Accept":"application/json",
        **({"Content-Type":"application/json"} if payload is not None else {}),
        **(headers or {}),
    })
    try:
        with build_opener(_NoRedirect()).open(req,timeout=timeout) as response:
            if not 200<=response.status<300:
                raise ModelHubError("MODEL_UPSTREAM_HTTP_ERROR")
            raw=response.read(4_000_001)
        if len(raw)>4_000_000:
            raise ModelHubError("MODEL_RESPONSE_TOO_LARGE")
        document=json.loads(raw)
        if not isinstance(document,dict):
            raise ValueError("not an object")
        return document
    except HTTPError as exc:
        raise ModelHubError(f"MODEL_UPSTREAM_HTTP_{exc.code}") from exc
    except (URLError,TimeoutError,OSError) as exc:
        raise ModelHubError("MODEL_UPSTREAM_CONNECTION_FAILED") from exc
    except (UnicodeDecodeError,json.JSONDecodeError,ValueError) as exc:
        raise ModelHubError("MODEL_UPSTREAM_JSON_INVALID") from exc


def public_provider(row: AiProvider) -> dict:
    return {
        "id":row.id,"name":row.name,"preset":row.preset,
        "protocol":row.protocol,"base_url":row.base_url,
        "has_key":bool(row.encrypted_key),
        "revision":row.revision,"json_mode":row.json_mode,
    }


def public_selection(db, task: str) -> dict | None:
    selected=db.get(AiTaskSelection,task)
    if selected is None:
        return None
    provider=db.get(AiProvider,selected.provider_id)
    if provider is None:
        return None
    return {
        "task":task,"provider_id":provider.id,
        "provider_name":provider.name,"model_id":selected.model_id,
    }


def pin_job_selection(db, job, kind: str):
    task={"teacher":"teacher","curriculum":"curriculum",
          "edit":"edit","edit_prepare":"edit"}.get(kind)
    if task is None:
        return
    selected=db.get(AiTaskSelection,task)
    if selected is None:
        return  # Backward-compatible env-based configuration.
    provider=db.get(AiProvider,selected.provider_id)
    if provider is None:
        raise ModelHubError("MODEL_PROVIDER_REMOVED")
    db.flush()
    db.add(AiJobSelection(
        job_id=job.id,provider_id=provider.id,model_id=selected.model_id,
        provider_revision=provider.revision,
    ))


class HubClient:
    """Common JSON-producing interface for model families and versions."""
    def __init__(self, *, protocol: str, base_url: str, api_key: str,
                 model_id: str, json_mode: bool=False):
        if protocol not in PROTOCOLS:
            raise ModelHubError("MODEL_PROTOCOL_NOT_SUPPORTED")
        self.protocol=protocol
        self.base_url=validate_base_url(base_url)
        self.api_key=api_key
        if not isinstance(model_id,str) or not model_id.strip() or len(model_id)>200:
            raise ModelHubError("MODEL_ID_REQUIRED")
        self.model_id=model_id.strip()
        self.json_mode=json_mode

    @classmethod
    def from_provider(cls, provider: AiProvider, model_id: str):
        return cls(
            protocol=provider.protocol,base_url=provider.base_url,
            api_key=decrypt_key(provider.encrypted_key),
            model_id=model_id,json_mode=provider.json_mode,
        )

    def _headers(self) -> dict:
        if self.protocol=="anthropic_messages":
            return {
                "x-api-key":self.api_key,
                "anthropic-version":"2023-06-01",
            }
        if self.protocol=="gemini_generate":
            return {"x-goog-api-key":self.api_key}
        return {"Authorization":"Bearer "+self.api_key}

    def _request(self, suffix: str, *, body=None, timeout=90) -> dict:
        return request_json(
            self.base_url+suffix,
            method="POST" if body is not None else "GET",
            headers=self._headers(),body=body,timeout=timeout,
        )

    def models(self) -> dict:
        """Best-effort live catalog. A 404/401 is not a false empty model list."""
        try:
            entries=[]
            if self.protocol=="gemini_generate":
                page=None
                for _ in range(5):
                    suffix="/models?pageSize=1000"+(
                        "&pageToken="+quote(page,safe="") if page else ""
                    )
                    result=self._request(suffix)
                    for item in result.get("models",[]):
                        if not isinstance(item,dict):
                            continue
                        capabilities=item.get("supportedGenerationMethods",
                                              item.get("supportedActions",[]))
                        if capabilities and "generateContent" not in capabilities:
                            continue
                        raw=item.get("name","")
                        identifier=raw.removeprefix("models/")
                        if identifier:
                            entries.append({"id":identifier,
                                            "label":item.get("displayName") or identifier})
                    page=result.get("nextPageToken")
                    if not page:break
            else:
                suffix="/models"
                for _ in range(5):
                    result=self._request(suffix)
                    data=result.get("data",[])
                    if not isinstance(data,list):
                        raise ModelHubError("MODEL_CATALOG_SCHEMA_INVALID")
                    for item in data:
                        if isinstance(item,dict) and isinstance(item.get("id"),str):
                            identifier=item["id"]
                            entries.append({"id":identifier,
                                            "label":item.get("display_name") or
                                                    item.get("displayName") or identifier})
                    if self.protocol!="anthropic_messages" or not result.get("has_more") or not data:
                        break
                    suffix="/models?after_id="+quote(str(data[-1]["id"]),safe="")
            unique={m["id"]:m for m in entries if m["id"] and len(m["id"])<=200}
            return {
                "models":sorted(unique.values(),key=lambda m:m["id"].lower()),
                "source":"live","manual_allowed":True,
                "notice":"" if unique else "服务商没有返回可用的文本模型；可填写模型 ID 并测试。",
            }
        except ModelHubError as exc:
            # Some OpenAI-compatible services explicitly do not implement
            # GET /models. The UI must not invent versions from stale lists.
            return {
                "models":[],"source":"manual",
                "manual_allowed":True,"notice":f"模型列表不可用（{exc}），可手动输入精确模型 ID。",
            }

    def generate_json(self, *, system: str, user_json: str,
                      timeout: int=150) -> dict:
        system=system+"\nReturn ONLY a syntactically valid JSON object. No Markdown."
        if self.protocol=="anthropic_messages":
            result=self._request("/messages",timeout=timeout,body={
                "model":self.model_id,"max_tokens":16384,
                "system":system,
                "messages":[{"role":"user","content":user_json}],
            })
            raw="".join(part.get("text","") for part in result.get("content",[])
                        if isinstance(part,dict) and part.get("type")=="text")
        elif self.protocol=="gemini_generate":
            name=self.model_id.removeprefix("models/")
            safe=quote(name,safe="-_.")
            generation={"maxOutputTokens":16384}
            if self.json_mode:
                generation["responseMimeType"]="application/json"
            result=self._request(
                "/models/"+safe+":generateContent",
                timeout=timeout,body={
                    "systemInstruction":{"parts":[{"text":system}]},
                    "contents":[{"role":"user","parts":[{"text":user_json}]}],
                    "generationConfig":generation,
                },
            )
            try:
                raw="".join(p.get("text","") for p in
                    result["candidates"][0]["content"]["parts"] if "text" in p)
            except (KeyError,IndexError,TypeError) as exc:
                raise ModelHubError("MODEL_RESPONSE_TEXT_MISSING") from exc
        else:
            request={
                "model":self.model_id,
                "messages":[
                    {"role":"system","content":system},
                    {"role":"user","content":user_json},
                ],
            }
            if self.json_mode:
                request["response_format"]={"type":"json_object"}
            result=self._request("/chat/completions",body=request,timeout=timeout)
            try:
                raw=result["choices"][0]["message"]["content"]
                if isinstance(raw,list):
                    raw="".join(p.get("text","") for p in raw if isinstance(p,dict))
            except (KeyError,IndexError,TypeError) as exc:
                raise ModelHubError("MODEL_RESPONSE_TEXT_MISSING") from exc
        if not isinstance(raw,str) or not raw.strip():
            raise ModelHubError("MODEL_RESPONSE_TEXT_MISSING")
        trimmed=raw.strip()
        if trimmed.startswith("```"):
            trimmed=trimmed.split("\n",1)[-1].rsplit("```",1)[0].strip()
        try:
            document=json.loads(trimmed)
        except json.JSONDecodeError as exc:
            raise ModelHubError("MODEL_RESPONSE_NOT_JSON") from exc
        if not isinstance(document,dict):
            raise ModelHubError("MODEL_RESPONSE_NOT_JSON_OBJECT")
        return document

    def generate(self, *, stage: str, system: str, user_json: str,
                 schema: type[BaseModel]):
        result=self.generate_json(system=system,user_json=user_json)
        try:
            return schema.model_validate(result)
        except ValidationError as exc:
            raise ModelHubError("MODEL_RESPONSE_SCHEMA_MISMATCH") from exc

    def probe(self) -> dict:
        result=self.generate_json(
            system="Return valid JSON exactly as requested for API connectivity.",
            user_json='Return {"ok":true}.',
            timeout=35,
        )
        if result.get("ok") is not True:
            raise ModelHubError("MODEL_TEST_DID_NOT_RETURN_EXPECTED_JSON")
        return {"status":"connected","model_id":self.model_id,
                "protocol":self.protocol,"json_output":True}


def pinned_client(db, job_id: str) -> HubClient | None:
    selected=db.get(AiJobSelection,job_id)
    if selected is None:
        return None
    provider=db.get(AiProvider,selected.provider_id)
    if provider is None:
        raise ModelHubError("MODEL_PROVIDER_REMOVED")
    if selected.provider_revision!=provider.revision:
        raise ModelHubError("MODEL_PROVIDER_CHANGED_AFTER_JOB_QUEUED")
    return HubClient.from_provider(provider,selected.model_id)


def task_client(db, task: str) -> HubClient | None:
    selected=db.get(AiTaskSelection,task)
    if selected is None:
        return None
    provider=db.get(AiProvider,selected.provider_id)
    if provider is None:
        raise ModelHubError("MODEL_PROVIDER_REMOVED")
    return HubClient.from_provider(provider,selected.model_id)


def plan_agent(client: HubClient):
    """Use the original unlimited-language micro-edit contract, not keywords."""
    from animation_engine.iterative_ai_adapter import _SYSTEM
    def agent(instruction: str, package: Path, history: list[dict]) -> dict:
        context={}
        for file in sorted(Path(package).rglob("*.json")):
            if file.is_symlink():
                raise ModelHubError("MODEL_CONTEXT_SYMLINK_NOT_ALLOWED")
            context[file.relative_to(package).as_posix()]=json.loads(
                file.read_text(encoding="utf-8"),
            )
        timeline=package.parent/"current_timeline.json"
        subtitles=package.parent/"current_subtitles.srt"
        payload={
            "exact_user_instruction":instruction,
            "prior_rounds":history,
            "current_package_json_files":context,
            "latest_video_event_and_caption_timeline":(
                json.loads(timeline.read_text(encoding="utf-8"))
                if timeline.is_file() else None
            ),
            "latest_audio_subtitles":(
                subtitles.read_text(encoding="utf-8")
                if subtitles.is_file() else None
            ),
        }
        plan=client.generate_json(
            system=_SYSTEM,
            user_json=json.dumps(payload,ensure_ascii=False),
        )
        plan["model"]=client.model_id
        return plan
    return agent
