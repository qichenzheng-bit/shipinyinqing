"""V2.6.6 content-addressed, persistent rendering resources.

No cached artifact is trusted by file name. Every hit checks provenance,
content digest, byte count and engine/runtime signature. Missing/corrupted
entries become misses and are regenerated from verified sources. Entries are
never edited in-place; failed writers cannot poison a published cache record.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import tempfile
import time
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any

CACHE_SCHEMA = "v2.6.6.1"
NAMESPACES = frozenset({"speech_pcm", "subtitle_png", "raw_stage", "composed_stage", "transition", "event_clip"})


def digest(data: Any) -> str:
    return hashlib.sha256(json.dumps(
        data, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), default=str,
    ).encode("utf-8")).hexdigest()


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@lru_cache(maxsize=1)
def engine_signature() -> str:
    """Invalidate after source/runtime changes, including fonts/TeX version
    changes that are relevant to MathTex. A full source hash is conservative.
    """
    src = Path(__file__).resolve().parent
    codes = [(x.relative_to(src).as_posix(), file_sha(x))
             for x in sorted(src.rglob("*.py"))]
    packages = {}
    for pkg in ("manim", "edge-tts", "Pillow", "av", "numpy"):
        try:
            packages[pkg] = importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            packages[pkg] = "not-installed"
    return digest({
        "schema": CACHE_SCHEMA, "source": codes,
        "packages": packages, "python": platform.python_version(),
        "platform": platform.platform(),
    })


class ArtifactCache:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.counts = Counter()
        self.seconds = Counter()

    def key(self, namespace: str, inputs: Any) -> str:
        if namespace not in NAMESPACES:
            raise ValueError("CACHE_UNKNOWN_NAMESPACE")
        return digest({
            "namespace": namespace,
            "inputs": inputs,
            "engine_signature": engine_signature(),
            "schema": CACHE_SCHEMA,
        })

    def _entry(self, namespace: str, key: str) -> Path:
        if namespace not in NAMESPACES or len(key) != 64 or any(
                c not in "0123456789abcdef" for c in key):
            raise ValueError("CACHE_INVALID_KEY")
        return self.root / namespace / key[:2] / key

    def read(self, namespace: str, key: str, *, filenames=("payload.bin",)):
        """Return verified bytes, or None; malformed cache always misses."""
        entry = self._entry(namespace, key)
        try:
            record = json.loads((entry / "record.json").read_text("utf-8"))
            if (record.get("schema") != CACHE_SCHEMA or
                    record.get("key") != key or
                    record.get("namespace") != namespace or
                    set(record["files"]) != set(filenames)):
                raise ValueError("CACHE_RECORD_MISMATCH")
            files = {}
            for filename in filenames:
                if filename not in ("payload.bin", "video.mp4", "manifest.json"):
                    raise ValueError("CACHE_FILENAME")
                p = entry / filename
                if p.is_symlink() or entry.is_symlink():
                    raise ValueError("CACHE_SYMLINK")
                data = p.read_bytes()
                info = record["files"][filename]
                if (len(data) != info["bytes"] or not data or
                        hashlib.sha256(data).hexdigest() != info["sha256"]):
                    raise ValueError("CACHE_CORRUPTED_FILE")
                files[filename] = data
            self.counts[namespace + "_hit"] += 1
            return files
        except (OSError, UnicodeError, ValueError, TypeError, KeyError,
                json.JSONDecodeError):
            self.counts[namespace + "_miss"] += 1
            return None

    def write(self, namespace: str, key: str, files: dict[str, bytes]):
        entry = self._entry(namespace, key)
        if not files or set(files) - {
                "payload.bin", "video.mp4", "manifest.json"}:
            raise ValueError("CACHE_BAD_PAYLOAD")
        if not all(isinstance(data, bytes) and data for data in files.values()):
            raise ValueError("CACHE_EMPTY_PAYLOAD")
        entry.parent.mkdir(parents=True, exist_ok=True)
        scratch = Path(tempfile.mkdtemp(
            prefix=".pending-", dir=entry.parent,
        ))
        try:
            details = {}
            for filename, data in files.items():
                (scratch / filename).write_bytes(data)
                details[filename] = {
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "bytes": len(data),
                }
            (scratch / "record.json").write_text(json.dumps({
                "schema": CACHE_SCHEMA,
                "key": key, "namespace": namespace,
                "files": details,
            }, sort_keys=True), encoding="utf-8")
            # Atomic directory rename. For a corrupted prior entry, replace
            # it under the session's render lock, never return it as valid.
            if entry.exists():
                shutil.rmtree(entry)
            os.replace(scratch, entry)
        finally:
            if scratch.exists():
                shutil.rmtree(scratch)

    def get_pcm(self, key: str) -> bytes | None:
        found = self.read("speech_pcm", key)
        if not found:
            return None
        pcm = found["payload.bin"]
        if len(pcm) < 24000 or len(pcm) % 2:
            self.counts["speech_pcm_invalid"] += 1
            return None
        # Recheck a non-silent waveform in addition to its provenance.
        from array import array
        decoded = array("h")
        decoded.frombytes(pcm)
        if not any(abs(decoded[i]) > 35 for i in range(0, len(decoded), 75)):
            self.counts["speech_pcm_invalid"] += 1
            return None
        return pcm

    def get_png(self, key: str, output: Path) -> bool:
        found = self.read("subtitle_png", key)
        if not found:
            return False
        from io import BytesIO
        from PIL import Image
        try:
            with Image.open(BytesIO(found["payload.bin"])) as picture:
                # Pillow.verify() must run immediately after open; after
                # accessing pixels use load() for full decoding/validation.
                picture.load()
                if picture.size != (1280, 88) or picture.mode != "RGBA":
                    raise ValueError("CACHE_CAPTION_DIMENSIONS")
                if picture.getchannel("A").getextrema()[0] != 0:
                    raise ValueError("CACHE_CAPTION_ALPHA")
        except (OSError, ValueError, TypeError):
            self.counts["subtitle_png_invalid"] += 1
            return False
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_bytes(found["payload.bin"])
        return True

    def restore_stage(self, key: str, video: Path, manifest: Path, *, fps: int,
                      source_storyboard_sha256: str, namespace: str="raw_stage",
                      expected_event_id: str | None=None,
                      expected_event_index: int | None=None) -> dict | None:
        if namespace not in ("raw_stage","event_clip"):
            raise ValueError("CACHE_STAGE_NAMESPACE")
        found = self.read(namespace, key, filenames=("video.mp4","manifest.json"))
        if not found:
            return None
        try:
            report = json.loads(found["manifest.json"])
            if (report["source_storyboard_sha256"] !=
                    source_storyboard_sha256 or
                    report["voice_status"] != "not_recorded" or
                    not report["event_timing"]):
                raise ValueError("CACHE_STAGE_PROVENANCE")
            if namespace=="event_clip":
                if (len(report["event_timing"])!=1 or
                        report["event_timing"][0]["event_id"]!=expected_event_id
                        or report.get("rendered_event_index")!=expected_event_index
                        or not report.get("event_window_entry_verified")):
                    raise ValueError("CACHE_EVENT_ENTRY_PROVENANCE")
            video.parent.mkdir(parents=True, exist_ok=True)
            manifest.parent.mkdir(parents=True, exist_ok=True)
            video.write_bytes(found["video.mp4"])
            manifest.write_bytes(found["manifest.json"])
            # This verifies actual video frames/fps via ffprobe; a content
            # hash alone is not proof of a valid or compatible movie.
            from .unified_classroom_flow import _video_frames
            frames = (
                _video_frames(video,fps,min_frames=1)
                if namespace=="event_clip" else _video_frames(video,fps)
            )
            if frames <= 0:
                raise ValueError("CACHE_STAGE_VIDEO_EMPTY")
            return report
        except (OSError, ValueError, KeyError, TypeError):
            video.unlink(missing_ok=True)
            manifest.unlink(missing_ok=True)
            self.counts[namespace+"_invalid"] += 1
            return None

    def store_stage(self, key: str, video: Path, manifest: Path,
                    *, namespace: str="raw_stage"):
        if namespace not in ("raw_stage","event_clip"):
            raise ValueError("CACHE_STAGE_NAMESPACE")
        self.write(namespace, key, {
            "video.mp4": video.read_bytes(),
            "manifest.json": manifest.read_bytes(),
        })

    def restore_video(self, namespace: str, key: str,
                      destination: Path, *, fps: int,
                      expected_frames: int) -> bool:
        """Restore a composite or wipe clip only after real frame/fps checks."""
        if namespace not in ("composed_stage", "transition"):
            raise ValueError("CACHE_VIDEO_NAMESPACE")
        found=self.read(namespace,key,filenames=("video.mp4",))
        if not found:
            return False
        destination=Path(destination)
        destination.parent.mkdir(parents=True,exist_ok=True)
        try:
            destination.write_bytes(found["video.mp4"])
            from .unified_classroom_flow import _video_frames
            count=_video_frames(destination,fps,min_frames=1)
            if count!=expected_frames:
                raise ValueError("CACHE_VIDEO_FRAME_COUNT_MISMATCH")
            return True
        except (OSError,ValueError,KeyError,TypeError):
            destination.unlink(missing_ok=True)
            self.counts[namespace+"_invalid"]+=1
            return False

    def store_video(self, namespace: str, key: str, video: Path) -> None:
        if namespace not in ("composed_stage", "transition"):
            raise ValueError("CACHE_VIDEO_NAMESPACE")
        self.write(namespace,key,{"video.mp4":Path(video).read_bytes()})

    def stats(self) -> dict:
        return {k: int(v) for k,v in sorted(self.counts.items())}

    def timed(self, name: str, elapsed: float):
        self.seconds[name] += max(0.0, elapsed)

    def profile(self) -> dict:
        return {k: round(v, 4) for k,v in sorted(self.seconds.items())}
