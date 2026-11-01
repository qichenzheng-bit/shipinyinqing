"""Overlay the exact source question on real two-scene Manim MathTex video.

No invented speech or subtitles; no board equation is modified or overlaid.
Video is a preview (not audio aligned), and the top question is compositor
generated with genuine MathTex and a separate CJK text font.
"""
from __future__ import annotations
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from visual_director.models import StoryboardPlan
from .adaptive_layout import AdaptiveLayoutError
from .classroom_compositor import render_classroom_board_png
from .layout_transition import render_layout_transition


def render_classroom_transition(
    storyboard, execution, *, from_event_id: str, to_event_id: str,
    output_mp4: Path, output_json: Path,
    pixel_width: int = 1280, pixel_height: int = 720, fps: int = 15,
) -> dict:
    output_mp4, output_json = Path(output_mp4), Path(output_json)
    if output_mp4.resolve() == output_json.resolve() or (
        output_mp4.suffix.lower() != ".mp4" or output_json.suffix.lower() != ".json"
    ):
        raise AdaptiveLayoutError("INVALID_OUTPUT")
    if not shutil.which("ffmpeg"):
        raise AdaptiveLayoutError("FFMPEG_UNAVAILABLE")
    board = StoryboardPlan.model_validate(storyboard)
    with tempfile.TemporaryDirectory(prefix="classroom-transition-") as temp:
        temp = Path(temp)
        transition = render_layout_transition(
            board, execution,
            from_event_id=from_event_id, to_event_id=to_event_id,
            output_mp4=temp / "math_only.mp4",
            output_json=temp / "math_only.json",
            pixel_width=pixel_width, pixel_height=pixel_height, fps=fps)
        composed = render_classroom_board_png(
            board, execution, event_id=to_event_id,
            output_png=temp / "classroom.png",
            output_json=temp / "classroom.json",
            pixel_width=pixel_width, pixel_height=pixel_height)
        from PIL import Image
        with Image.open(temp / "classroom.png") as full:
            overlay = Image.new("RGBA", (pixel_width, pixel_height),
                                (255,255,255,0))
            z = next(s for s in board.scenes if s.event_id == to_event_id).regions["question"]
            # Only question region. Keep every board/diagram/caption pixel
            # transparent, so no mathematical work can be hidden by the overlay.
            y0 = int(z.y * pixel_height)
            y1 = int((z.y + z.h) * pixel_height)
            x0 = int(z.x * pixel_width)
            x1 = int((z.x + z.w) * pixel_width)
            strip = full.convert("RGBA").crop((x0, y0, x1, y1))
            overlay.paste(strip, (x0,y0))
            overlay.save(temp / "header_overlay.png")
        movie = temp / "complete.mp4"
        task = subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(temp / "math_only.mp4"),
            "-i", str(temp / "header_overlay.png"),
            "-filter_complex", "[0:v][1:v]overlay=0:0:eof_action=repeat:shortest=0[v]",
            "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-an", str(movie)
        ], capture_output=True, text=True)
        if task.returncode != 0 or not movie.is_file() or movie.stat().st_size < 1000:
            raise AdaptiveLayoutError(
                "FFMPEG_CLASSROOM_OVERLAY_FAILED: " + task.stderr[-320:]
            )
        metadata = {
            **transition,
            "render_kind": "manim_mathtex_two_scene_classroom_question_mp4",
            "question_source_sha256": composed["question_source_sha256"],
            "question_parts": composed["question_parts"],
            "question_overlay_source": "classroom_compositor_verified_mathtex_cjk",
            "subtitle_status": "not_rendered_no_audio",
            "timing_source": "preview_only_not_audio_aligned",
        }
        (temp / "complete.json").write_text(json.dumps(
            metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        try:
            output_mp4.parent.mkdir(parents=True, exist_ok=True)
            output_json.parent.mkdir(parents=True, exist_ok=True)
            os.replace(movie, output_mp4)
            os.replace(temp / "complete.json", output_json)
        except Exception:
            output_mp4.unlink(missing_ok=True)
            output_json.unlink(missing_ok=True)
            raise
        return metadata
