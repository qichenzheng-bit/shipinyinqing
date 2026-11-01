"""Build a visible classroom sequence from consecutive *approved* lesson events.

This is intentionally not a lecture compositor: no speech, TTS, subtitle or
automatic cut decisions are fabricated. Every adjacent transition is an actual
Manim MathTex MP4 with the verified fixed original question composited on top.
"""
from __future__ import annotations

from .video_settings import DEFAULT_VIDEO_FPS

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from visual_director.models import StoryboardPlan
from .adaptive_layout import AdaptiveLayoutError
from .classroom_transition import render_classroom_transition


def render_classroom_sequence(
    storyboard, execution, *, event_ids: list[str],
    output_mp4: Path, output_json: Path, fps: int = DEFAULT_VIDEO_FPS,
) -> dict:
    board = StoryboardPlan.model_validate(storyboard)
    names = [s.event_id for s in board.scenes]
    if (not isinstance(event_ids, list) or len(event_ids) < 3
            or len(set(event_ids)) != len(event_ids)
            or any(type(i) is not str for i in event_ids)):
        raise AdaptiveLayoutError("SEQUENCE_EVENTS: three or more distinct events required")
    indices = [names.index(i) if i in names else -1 for i in event_ids]
    if any(j != i + 1 for i, j in zip(indices, indices[1:])):
        raise AdaptiveLayoutError("NONCONSECUTIVE_EVENTS")
    output_mp4, output_json = Path(output_mp4), Path(output_json)
    if (output_mp4.resolve() == output_json.resolve()
            or output_mp4.suffix.lower() != ".mp4"
            or output_json.suffix.lower() != ".json"):
        raise AdaptiveLayoutError("INVALID_OUTPUT")
    if not shutil.which("ffmpeg"):
        raise AdaptiveLayoutError("FFMPEG_UNAVAILABLE")

    with tempfile.TemporaryDirectory(prefix="classroom-sequence-") as temp:
        temp = Path(temp)
        parts = []
        manifest_rows = []
        for n, (start, end) in enumerate(zip(event_ids, event_ids[1:])):
            movie = temp / f"scene_{n:02d}.mp4"
            manifest = temp / f"scene_{n:02d}.json"
            produced = render_classroom_transition(
                board, execution, from_event_id=start, to_event_id=end,
                output_mp4=movie, output_json=manifest, fps=fps)
            assert movie.exists()
            parts.append(movie)
            manifest_rows.append({
                "from_event_id": start, "to_event_id": end,
                "held_ids": produced["held_ids"],
                "moved_ids": produced["moved_ids"],
                "written_ids": produced["written_ids"],
                "removed_ids": produced["removed_ids"],
                "actual_preview_seconds": produced["actual_preview_seconds"],
            })
        names_file = temp / "parts.txt"
        names_file.write_text(
            "".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
        assembled = temp / "classroom_full.mp4"
        proc = subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "concat", "-safe", "0", "-i", str(names_file),
            "-c", "copy", str(assembled),
        ], capture_output=True, text=True, cwd=str(temp))
        if proc.returncode or not assembled.exists() or assembled.stat().st_size < 1000:
            raise AdaptiveLayoutError(
                "SEQUENCE_CONCAT_FAILED: " + proc.stderr[-280:])
        result = {
            "render_kind": "manim_mathtex_multiscene_classroom_sequence_mp4",
            "event_ids": event_ids,
            "segment_count": len(parts),
            "segments": manifest_rows,
            "fps": fps,
            "source_storyboard_sha256": produced["source_storyboard_sha256"],
            "question_source_sha256": produced["question_source_sha256"],
            "timing_source": "preview_only_not_audio_aligned",
            "subtitle_status": "not_rendered_no_audio",
            "next_stage": "2.4 owns actual cutting, page persistence, and scroll",
        }
        data = temp / "sequence.json"
        data.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        try:
            output_mp4.parent.mkdir(parents=True, exist_ok=True)
            output_json.parent.mkdir(parents=True, exist_ok=True)
            os.replace(assembled, output_mp4)
            os.replace(data, output_json)
        except Exception:
            output_mp4.unlink(missing_ok=True)
            output_json.unlink(missing_ok=True)
            raise
        return result
