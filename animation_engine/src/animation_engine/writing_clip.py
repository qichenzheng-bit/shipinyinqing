"""Real Manim MathTex writing clips, not inferred audio or mathematical steps.

Manim is imported only when the optional render operation is invoked.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .mathtex_renderer import MathTexRenderError, validate_math_latex
from .writing_cues import MathWritingPlan


class MathWritingClipError(ValueError):
    """The requested real MP4 could not be rendered truthfully."""


@dataclass(frozen=True)
class MathWritingClipResult:
    mp4_path: Path
    metadata_path: Path
    formula_bounds_px: tuple[float, float, float, float]


_WRITE_SECONDS = 0.6
_COLOR_SECONDS = 0.3
_HIGHLIGHT_HOLD_SECONDS = 0.36
_FINAL_HOLD_SECONDS = 0.25
_SAFETY_MARGIN = 0.13


def render_math_writing_clip(
    plan: MathWritingPlan,
    *,
    output_mp4: Path,
    output_json: Path,
    pixel_width: int = 1280,
    pixel_height: int = 720,
    fps: int = 15,
) -> MathWritingClipResult:
    output_mp4, output_json = Path(output_mp4), Path(output_json)
    if output_mp4.resolve() == output_json.resolve():
        raise MathWritingClipError("INVALID_OUTPUT: MP4 and manifest paths overlap")
    if output_mp4.suffix.lower() != ".mp4" or output_json.suffix.lower() != ".json":
        raise MathWritingClipError("INVALID_OUTPUT: expected .mp4 and .json")
    if pixel_width < 320 or pixel_height < 180 or fps < 8 or fps > 60:
        raise MathWritingClipError("INVALID_FRAME_SIZE: unreasonable preview resolution/fps")
    if not plan.parts or "".join(plan.parts) != plan.request.latex:
        raise MathWritingClipError("WRITING_LATEX_MISMATCH: segment plan differs from original formula")
    if (plan.highlight_index is not None and
        (type(plan.highlight_index) is not int or
         not (0 <= plan.highlight_index < len(plan.parts)))):
        raise MathWritingClipError("HINT_HIGHLIGHT_INDEX: out of range")
    if plan.mode == "whole_formula" and len(plan.parts) != 1:
        raise MathWritingClipError("WRITING_SCHEMA: fallback must be exactly one part")
    if plan.mode == "segmented" and len(plan.parts) < 2:
        raise MathWritingClipError("WRITING_SCHEMA: segmented plan needs multiple parts")

    try:
        validate_math_latex(plan.request.latex)
        for part in plan.parts:
            validate_math_latex(part)
    except MathTexRenderError as exc:
        raise MathWritingClipError(str(exc)) from exc
    try:
        from manim import MathTex, Scene, Write, tempconfig
    except ImportError as exc:
        raise MathWritingClipError("LATEX_ENV_UNAVAILABLE: Manim render extra missing") from exc
    if not shutil.which("latex") or not shutil.which("dvisvgm") or not shutil.which("ffmpeg"):
        raise MathWritingClipError("LATEX_ENV_UNAVAILABLE: latex, dvisvgm and ffmpeg required")

    fw = 8.0 * pixel_width / pixel_height
    fh = 8.0
    rect = plan.request.region
    bounds: tuple[float, float, float, float] | None = None

    with tempfile.TemporaryDirectory(prefix="manim-writing-") as work:
        config_settings = {
            "pixel_width": pixel_width,
            "pixel_height": pixel_height,
            "frame_width": fw,
            "frame_height": fh,
            "frame_rate": fps,
            "background_color": plan.request.theme.background,
            "renderer": "cairo",
            "format": "mp4",
            "media_dir": work,
            "output_file": "math_writing.mp4",
            "disable_caching": True,
            "preview": False,
        }
        try:
            with tempconfig(config_settings):
                # This one MathTex object owns every approved math subpart. It
                # keeps geometry fixed throughout the clip; Write is the only
                # entrance animation, and highlighting changes color only.
                full = MathTex(*plan.parts, arg_separator="",
                               color=plan.request.theme.ink)
                if len(full.submobjects) != len(plan.parts):
                    raise MathWritingClipError(
                        "PART_RENDER_MISMATCH: Manim could not map parts one-to-one"
                    )
                if (full.width + 2 * _SAFETY_MARGIN >= rect.w * fw
                        or full.height + 2 * _SAFETY_MARGIN >= rect.h * fh):
                    raise MathWritingClipError(
                        f"FORMULA_OVERFLOW: {plan.request.event_id}/{plan.request.object_id}"
                    )
                x = (rect.x + rect.w / 2 - .5) * fw
                y = (.5 - rect.y - rect.h / 2) * fh
                full.move_to([x, y, 0])
                bounds = (
                    float((full.get_left()[0] / fw + .5) * pixel_width),
                    float((.5 - full.get_top()[1] / fh) * pixel_height),
                    float((full.get_right()[0] / fw + .5) * pixel_width),
                    float((.5 - full.get_bottom()[1] / fh) * pixel_height),
                )
                target_index = plan.highlight_index
                target = full if target_index is None else full[target_index]

                class ApprovedWritingScene(Scene):
                    def construct(self):
                        for part in full.submobjects:
                            self.play(Write(part), run_time=_WRITE_SECONDS)
                        self.play(target.animate.set_color(plan.request.theme.highlight),
                                  run_time=_COLOR_SECONDS)
                        self.wait(_HIGHLIGHT_HOLD_SECONDS)
                        self.play(target.animate.set_color(plan.request.theme.ink),
                                  run_time=_COLOR_SECONDS)
                        self.wait(_FINAL_HOLD_SECONDS)

                scene = ApprovedWritingScene()
                scene.render()
                movie = Path(scene.renderer.file_writer.movie_file_path)
                if not movie.is_file() or movie.stat().st_size < 1000:
                    raise MathWritingClipError("VIDEO_RENDER_FAILED: genuine MP4 was not produced")

            metadata = {
                "render_kind": "manim_mathtex_progressive_mp4",
                "event_id": plan.request.event_id,
                "object_id": plan.request.object_id,
                "action_id": plan.action_id,
                "speech_unit_id": plan.speech_unit_id,
                "source_storyboard_sha256": plan.request.source_storyboard_sha256,
                "source_step_ids": list(plan.request.source_step_ids),
                "latex": plan.request.latex,
                "parts": list(plan.parts),
                "mode": plan.mode,
                "hint_source": plan.hint_source,
                "highlight_index": plan.highlight_index,
                "write_part_indices": list(range(len(plan.parts))),
                "formula_bounds_px": list(bounds),
                "frame_size_px": [pixel_width, pixel_height],
                "fps": fps,
                "timing_source": "preview_only_not_audio_aligned",
                "preview_highlight_seconds": _COLOR_SECONDS,
                "highlight_sample_second": (
                    len(plan.parts) * _WRITE_SECONDS +
                    _COLOR_SECONDS + _HIGHLIGHT_HOLD_SECONDS / 2
                ),
                "final_sample_second": (
                    len(plan.parts) * _WRITE_SECONDS +
                    2 * _COLOR_SECONDS + _HIGHLIGHT_HOLD_SECONDS +
                    _FINAL_HOLD_SECONDS / 2
                ),
            }
            tmp_json = Path(work) / "math_writing.json"
            tmp_json.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8")
            output_mp4.parent.mkdir(parents=True, exist_ok=True)
            output_json.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(movie, Path(work) / "ready.mp4")
            os.replace(Path(work) / "ready.mp4", output_mp4)
            os.replace(tmp_json, output_json)
        except Exception as exc:
            # A failed render is not a successful video. Don't preserve a
            # misleading partial artifact, including from a failing ffmpeg.
            output_mp4.unlink(missing_ok=True)
            output_json.unlink(missing_ok=True)
            if isinstance(exc, MathWritingClipError):
                raise
            raise MathWritingClipError(
                f"VIDEO_RENDER_FAILED: {plan.request.event_id}/{plan.request.object_id}: "
                f"{type(exc).__name__}: {str(exc)[:240]}"
            ) from exc

    assert bounds is not None
    return MathWritingClipResult(
        mp4_path=output_mp4, metadata_path=output_json, formula_bounds_px=bounds
    )
