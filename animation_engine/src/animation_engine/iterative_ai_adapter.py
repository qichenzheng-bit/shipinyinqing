"""V2.6.5 optional real-model adapter: unrestricted instructions -> edit plan.

No AI calls occur without an explicit model configuration and an invocation.
The selected provider sees the current source package and past user feedback.
It must return inspectable JSON; invalid or incomplete model output is rejected
by the independent editing and mathematical acceptance gates.

This adapter speaks the common OpenAI-compatible chat-completions protocol;
alternative local / future AI agents can implement the same callable contract.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .iterative_edit_ops import EditEngineError


_SYSTEM = """You are editing the SOURCE of a mathematical classroom video, not
writing an ordinary chat answer. The current fully-verified package is provided
as JSON files, and the user's EXACT request may contain ANY language and ANY
number of independent or dependent requirements. Never ignore a requirement.
Interpret context references such as "here", "this equation" and "now" using
the latest source and preceding edit history.

Return exactly one JSON object with:
- schema_version: "1.0"
- model: a nonempty model identifier
- requirements: list of objects {"id":"r1","instruction": "...",
  "target":"stage/event/object or semantic target",
  "operation_ids":["p1", ...]}; one per distinct user requirement.
- operations: list of objects {"id":"p1","file":"relative existing JSON",
  "pointer":"/RFC6901/JSON/path","action":"set|insert|remove","value":...}
  ("remove" has no value). Every operation must be linked to >=1 requirement.
Use all requested edits. Keep original mathematical LaTeX source, mathematical
truth, source provenance, coverage and event IDs unchanged unless the user
requires changing them, in which case coordinate all related verified source
files and do not fake verification. Source validation will reject broken math
or unspoken formula changes. Speech math part 'latex' MUST match its source;
pronunciation is separate and never displayed as a math expression.
Never refer to a reference answer in narration. Do not add mock audio or
pretend a renderer succeeded. Return only the JSON, no Markdown."""

def _validate_endpoint(url: str):
    p = urlparse(url)
    if (p.scheme != "https" and not (
            p.scheme == "http" and p.hostname in (
                "localhost", "127.0.0.1", "::1"
            ))) or not p.hostname or p.username or p.password or p.fragment:
        raise EditEngineError("EDIT_AI_ENDPOINT_MUST_BE_HTTPS_OR_LOCAL")
    if not p.path.endswith("/chat/completions"):
        raise EditEngineError("EDIT_AI_ENDPOINT_MUST_BE_CHAT_COMPLETIONS")


def make_openai_compatible_agent(config: Path):
    spec = json.loads(Path(config).read_text(encoding="utf-8"))
    if set(spec) != {"kind", "model", "endpoint", "key_environment"} or (
            spec["kind"] != "openai_compatible" or
            not isinstance(spec["model"], str) or not spec["model"].strip() or
            not isinstance(spec["key_environment"], str) or
            not spec["key_environment"].strip()):
        raise EditEngineError("EDIT_AI_CONFIGURATION_INVALID")
    endpoint = spec["endpoint"]
    _validate_endpoint(endpoint)
    key_env = spec["key_environment"]
    # API key is intentionally loaded only at invocation, never written into
    # the session JSON export, logs, source patches or GitHub artifacts.
    def agent(instruction: str, package: Path, history: list[dict]) -> dict:
        key = os.environ.get(key_env, "")
        if not key:
            raise EditEngineError("EDIT_AI_API_KEY_MISSING")
        context={}
        for file in sorted(Path(package).rglob("*.json")):
            if file.is_symlink():
                raise EditEngineError("EDIT_AI_CONTEXT_SYMLINK")
            context[file.relative_to(package).as_posix()] = json.loads(
                file.read_text(encoding="utf-8")
            )
        timing_file=Path(package).parent/"current_timeline.json"
        subtitle_file=Path(package).parent/"current_subtitles.srt"
        current_timeline=(
            json.loads(timing_file.read_text(encoding="utf-8"))
            if timing_file.is_file() else None
        )
        current_subtitles=(
            subtitle_file.read_text(encoding="utf-8")
            if subtitle_file.is_file() else None
        )
        payload={
            "model": spec["model"],
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": json.dumps({
                    "exact_user_instruction": instruction,
                    "prior_rounds": history,
                    "current_package_json_files": context,
                    "latest_video_event_and_caption_timeline": current_timeline,
                    "latest_audio_subtitles": current_subtitles,
                },ensure_ascii=False)},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }
        req = Request(
            endpoint,
            data=json.dumps(payload,ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={"Authorization": "Bearer " + key,
                     "Content-Type": "application/json"},
        )
        try:
            with urlopen(req,timeout=150) as res:
                if res.status != 200:
                    raise EditEngineError("EDIT_AI_PROVIDER_HTTP_ERROR")
                doc=json.load(res)
            message=doc["choices"][0]["message"]["content"]
            if not isinstance(message,str):
                raise EditEngineError("EDIT_AI_NON_TEXT_RESPONSE")
            result=json.loads(message)
            if not isinstance(result,dict):
                raise EditEngineError("EDIT_AI_PLAN_NOT_JSON_OBJECT")
            # Identity of model used must come from configuration, not the
            # model's self-asserted text.
            result["model"] = spec["model"]
            return result
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise EditEngineError("EDIT_AI_PROVIDER_RESPONSE_INVALID") from exc
    return agent
