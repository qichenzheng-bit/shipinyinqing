"""Minimal LLM boundary; OpenAI-compatible JSON chat endpoint, no project coupling."""
from __future__ import annotations
import json
import os
from typing import Protocol, TypeVar
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class JsonModel(Protocol):
    def generate(self, *, stage: str, system: str, user_json: str, schema: type[T]) -> T: ...


class ProviderError(RuntimeError):
    pass


class OpenAICompatibleJsonModel:
    """Sends one JSON response request per stage; never logs credentials or inputs.

    The remote endpoint must accept /chat/completions. json_schema output is
    optional because not all OpenAI-compatible providers implement it.
    """
    def __init__(self, *, model: str | None = None, base_url: str | None = None,
                 api_key: str | None = None, schema_mode: bool = False,
                 timeout: int = 90):
        self.model = model or os.getenv("MATH_TEACHER_MODEL", "")
        self.base_url = (base_url or os.getenv("MATH_TEACHER_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.api_key = api_key or os.getenv("MATH_TEACHER_API_KEY", "")
        self.schema_mode = schema_mode
        self.timeout = timeout
        if not self.model or not self.api_key:
            raise ProviderError("Set MATH_TEACHER_MODEL and MATH_TEACHER_API_KEY (or pass model/key explicitly)")
        if not self.base_url.startswith(("https://", "http://localhost", "http://127.0.0.1")):
            raise ProviderError("Provider URL must use HTTPS, or local loopback HTTP")

    def generate(self, *, stage: str, system: str, user_json: str, schema: type[T]) -> T:
        response_format = {"type": "json_object"}
        if self.schema_mode:
            response_format = {"type": "json_schema", "json_schema": {
                "name": f"math_teacher_{stage}", "strict": True,
                "schema": schema.model_json_schema()
            }}
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_json},
            ],
            "response_format": response_format,
        }
        request = Request(
            self.base_url + "/chat/completions",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                result = json.load(response)
        except HTTPError as exc:
            # Avoid echoing private input/auth; response bodies may contain traces.
            raise ProviderError(f"Provider returned HTTP {exc.code} at stage {stage}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ProviderError(f"Provider request failed at stage {stage}: {type(exc).__name__}") from exc
        try:
            msg = result["choices"][0]["message"]
            if msg.get("refusal"):
                raise ProviderError(f"Provider refused stage {stage}")
            content = msg["content"]
            if not isinstance(content, str):
                raise ValueError("Expected JSON string content")
            return schema.model_validate_json(content)
        except (KeyError, IndexError, TypeError, ValueError, ValidationError) as exc:
            raise ProviderError(f"Invalid structured output at stage {stage}: {type(exc).__name__}: {str(exc)[:300]}") from exc
