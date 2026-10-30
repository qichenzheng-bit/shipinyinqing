"""Actual Manim MP4 showing an approved two-scene adaptive-layout transition.

No invented narration or mathematical transformations. Existing object IDs stay
the same; only pixel positions may move, then new objects are written.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .adaptive_layout import AdaptiveLayoutError, _overlap, layout_storyboard


def _at(p: dict, w: int, h: int):
    fw, fh = 8 * w / h, 8.0
    return [((p["x"] + p["w"] / 2) / w - 0.5) * fw,
            (0.5 - (p["y"] + p["h"] / 2) / h) * fh, 0]


def _verify_moving_bounds(before: dict[str, dict], after: dict[str, dict]) -> None:
    """Only simultaneous survivor moves matter; remove old objects first,
    write new objects after the move. Avoid tween collisions with survivors.
    """
    keys = list(after.keys() & before.keys())
    for step in range(13):
        t = step / 12
        interim = []
        for key in keys:
            a, b = before[key], after[key]
            interim.append({
                k: a[k] + (b[k] - a[k]) * t for k in ("x", "y", "w", "h")
            })
        if any(_overlap(interim[i], interim[j]) for i in range(len(interim))
               for j in range(i + 1, len(interim))):
            raise AdaptiveLayoutError(
                "TRANSITION_COLLISION: surviving formulas overlap during proposed motion"
            )


def render_layout_transition(
    storyboard: Any, execution: Any, *,
    from_event_id: str, to_event_id: str,
    output_mp4: Path, output_json: Path,
    pixel_width: int = 1280, pixel_height: int = 720, fps: int = 15,
) -> dict:
    if (pixel_width < 320 or pixel_height < 180
            or not 8 <= fps <= 60):
        raise AdaptiveLayoutError("INVALID_FRAME_SIZE")
    output_mp4, output_json = Path(output_mp4), Path(output_json)
    if (output_mp4.resolve() == output_json.resolve()
            or output_mp4.suffix.lower() != ".mp4"
            or output_json.suffix.lower() != ".json"):
        raise AdaptiveLayoutError("INVALID_OUTPUT")
    # Reject impossible event requests before launching an optional TeX compiler.
    from visual_director.models import StoryboardPlan
    event_names = [scene.event_id for scene in StoryboardPlan.model_validate(storyboard).scenes]
    if (from_event_id not in event_names or to_event_id not in event_names
            or event_names.index(to_event_id) != event_names.index(from_event_id) + 1):
        raise AdaptiveLayoutError("NONCONSECUTIVE_EVENTS")
    layout = layout_storyboard(storyboard, execution,
                               pixel_width=pixel_width, pixel_height=pixel_height)
    positions = {s["event_id"]: i for i, s in enumerate(layout["scenes"])}
    if (from_event_id not in positions or to_event_id not in positions
            or positions[to_event_id] != positions[from_event_id] + 1):
        raise AdaptiveLayoutError("NONCONSECUTIVE_EVENTS")
    before_scene = layout["scenes"][positions[from_event_id]]
    after_scene = layout["scenes"][positions[to_event_id]]
    if before_scene["status"] != "ready" or after_scene["status"] != "ready":
        raise AdaptiveLayoutError("CUT_REQUIRED: stage 2.4 must decide the new scene")
    before = {p["object_id"]: p for p in before_scene["placements"]}
    after = {p["object_id"]: p for p in after_scene["placements"]}
    for object_id in before.keys() & after.keys():
        if (before[object_id]["latex"] != after[object_id]["latex"]
                or before[object_id]["source_step_ids"] != after[object_id]["source_step_ids"]):
            raise AdaptiveLayoutError("MUTATED_MATH_OBJECT")
    _verify_moving_bounds(before, after)

    try:
        from manim import Scene, MathTex, FadeOut, Write, tempconfig
    except ImportError as exc:
        raise AdaptiveLayoutError("LATEX_ENV_UNAVAILABLE: install animation_engine[render]") from exc
    if not all(shutil.which(name) for name in ("latex", "dvisvgm", "ffmpeg")):
        raise AdaptiveLayoutError("LATEX_ENV_UNAVAILABLE: latex/dvisvgm/ffmpeg needed")
    from visual_director.models import StoryboardPlan
    board = StoryboardPlan.model_validate(storyboard)
    fw, fh = 8 * pixel_width / pixel_height, 8
    old_ids = set(before)
    new_ids = set(after)
    removed = [i for i in before if i not in new_ids]
    introduced = [i for i in after if i not in old_ids]
    moving = [i for i in after if i in old_ids and
              any(abs(before[i][k] - after[i][k]) >= .5 for k in ("x", "y", "w", "h"))]
    held = [i for i in after if i in old_ids and i not in moving]

    try:
        with tempfile.TemporaryDirectory(prefix="layout-transition-") as temp:
            with tempconfig({
                "pixel_width": pixel_width, "pixel_height": pixel_height,
                "frame_width": fw, "frame_height": fh, "frame_rate": fps,
                "background_color": board.theme.background,
                "format": "mp4", "renderer": "cairo", "media_dir": temp,
                "output_file": "transition.mp4", "disable_caching": True,
                "preview": False,
            }):
                existing = {}
                for key, item in before.items():
                    obj = MathTex(item["latex"],
                                  color=board.theme.ink)
                    obj.scale(item["scale"]).move_to(_at(item, pixel_width, pixel_height))
                    existing[key] = obj

                arriving = {}
                for key in introduced:
                    item = after[key]
                    obj = MathTex(item["latex"],
                                  color=board.theme.ink)
                    obj.scale(item["scale"]).move_to(_at(item, pixel_width, pixel_height))
                    arriving[key] = obj

                class TransitionScene(Scene):
                    def construct(self):
                        self.add(*existing.values())
                        self.wait(0.20)
                        if removed:
                            self.play(*(FadeOut(existing[key]) for key in removed),
                                      run_time=0.25)
                        if moving:
                            self.play(*(
                                existing[key].animate
                                .scale(after[key]["scale"] / before[key]["scale"])
                                .move_to(_at(after[key], pixel_width, pixel_height))
                                for key in moving
                            ), run_time=0.65)
                        for key in introduced:
                            self.play(Write(arriving[key]), run_time=0.55)
                        self.wait(0.30)
                        self.preview_end_seconds = self.time

                scene = TransitionScene()
                scene.render()
                film = Path(scene.renderer.file_writer.movie_file_path)
                if not film.is_file() or film.stat().st_size < 1000:
                    raise AdaptiveLayoutError("VIDEO_RENDER_FAILED: no valid MP4")
                duration = scene.preview_end_seconds
            manifest = {
                "render_kind": "manim_mathtex_two_scene_layout_transition_mp4",
                "source_storyboard_sha256": layout["source_storyboard_sha256"],
                "source_layout_sha256": layout["layout_sha256"],
                "from_event_id": from_event_id, "to_event_id": to_event_id,
                "from_placements": before_scene["placements"],
                "to_placements": after_scene["placements"],
                "removed_ids": removed, "moved_ids": moving,
                "held_ids": held, "written_ids": introduced,
                "timing_source": "preview_only_not_audio_aligned",
                "actual_preview_seconds": duration,
                "pixel_width": pixel_width, "pixel_height": pixel_height, "fps": fps,
            }
            tmp_json = Path(temp) / "transition.json"
            tmp_mp4 = Path(temp) / "approved.mp4"
            tmp_json.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8")
            shutil.copyfile(film, tmp_mp4)
            output_mp4.parent.mkdir(parents=True, exist_ok=True)
            output_json.parent.mkdir(parents=True, exist_ok=True)
            os.replace(tmp_mp4, output_mp4)
            os.replace(tmp_json, output_json)
            return manifest
    except Exception as exc:
        output_mp4.unlink(missing_ok=True)
        output_json.unlink(missing_ok=True)
        if isinstance(exc, AdaptiveLayoutError):
            raise
        raise AdaptiveLayoutError(
            f"VIDEO_RENDER_FAILED: {type(exc).__name__}: {str(exc)[:230]}"
        ) from exc
