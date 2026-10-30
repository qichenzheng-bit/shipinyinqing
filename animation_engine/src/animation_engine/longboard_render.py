"""Render a genuine Manim 2.4 long-board MP4 from its verified page plan.

Event boundaries are the only legal points for scrolls/cuts. Every original
mathematical object is built from its exact source LaTeX, with optional checked
fragments. New objects Write, retained objects move without re-Writing, cuts
archive obsolete working content and preserve pinned results. Timing is ONLY
preview timing, never generated speech or a fake transcript.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .longboard_plan import LongboardError, build_longboard_plan
from .longboard_header import make_question_overlay
from .mathtex_renderer import validate_math_latex


def render_longboard_movie(
    storyboard: Any, execution: Any, *, output_mp4: Path,
    output_json: Path, policy: dict | None = None,
    pixel_width: int = 1280, pixel_height: int = 720,
    fps: int = 30,
) -> dict:
    if type(fps) is not int or not 8 <= fps <= 60:
        raise LongboardError("INVALID_FPS")
    output_mp4, output_json = Path(output_mp4), Path(output_json)
    if (output_mp4.resolve() == output_json.resolve()
            or output_mp4.suffix.lower() != ".mp4"
            or output_json.suffix.lower() != ".json"):
        raise LongboardError("INVALID_OUTPUT")
    if not shutil.which("ffmpeg"):
        raise LongboardError("FFMPEG_UNAVAILABLE")
    from visual_director.models import StoryboardPlan
    from .models import ExecutionPlan
    board = StoryboardPlan.model_validate(storyboard)
    source_plan = ExecutionPlan.model_validate(execution)
    layout = build_longboard_plan(
        board, source_plan, policy=policy,
        pixel_width=pixel_width, pixel_height=pixel_height,
    )
    try:
        from manim import (
            Scene, MathTex, VGroup, Write, FadeIn, FadeOut, tempconfig
        )
    except ImportError as exc:
        raise LongboardError("MANIM_UNAVAILABLE: install animation_engine[render]") from exc
    fw, fh = 8.0*pixel_width/pixel_height, 8.
    def center(p):
        return [((p["x"]+p["w"]/2)/pixel_width-.5)*fw,
                (.5-(p["y"]+p["h"]/2)/pixel_height)*fh,0]

    def make_object(p):
        pieces = []
        for frag in p["fragments"]:
            latex = frag["latex"]
            validate_math_latex(latex)
            obj = MathTex(latex, color=board.theme.ink)
            obj.scale(p["scale"])
            obj.move_to(center(frag))
            actual_w = obj.width / fw * pixel_width
            actual_h = obj.height / fh * pixel_height
            if (abs(actual_w-frag["w"]) > 2 or abs(actual_h-frag["h"]) > 2):
                raise LongboardError(
                    f"RENDER_BOUNDS_MISMATCH: {p['object_id']}/{frag['fragment_index']}"
                )
            pieces.append(obj)
        return VGroup(*pieces)

    if not layout["events"]:
        raise LongboardError("EMPTY_LESSON")
    try:
        with tempfile.TemporaryDirectory(prefix="longboard-2-4-") as tmp:
            temp = Path(tmp)
            with tempconfig({
                "pixel_width": pixel_width, "pixel_height": pixel_height,
                "frame_width": fw, "frame_height": fh, "frame_rate": fps,
                "background_color": board.theme.background,
                "format": "mp4", "renderer": "cairo", "media_dir": str(temp),
                "output_file": "math_longboard.mp4", "disable_caching": True,
                "preview": False,
            }):
                # An immutable math object remains alive in the scene as long as
                # it is visible. The renderer does not fake "transformation"
                # with a fresh Write of the same object.
                class LongboardScene(Scene):
                    def construct(self):
                        active = {}
                        previous = {}
                        self.actual_events = []
                        for scene_index, row in enumerate(layout["events"]):
                            target = {p["object_id"]:p for p in row["placements"]}
                            start = self.time
                            removing = [mid for mid in active if mid not in target]
                            if removing:
                                self.play(*[FadeOut(active[mid])
                                            for mid in removing],run_time=.24)
                                for mid in removing:
                                    active.pop(mid)
                            moving = []
                            for mid in list(active):
                                before = previous[mid]
                                dest = target[mid]
                                if (before["latex"] != dest["latex"]
                                        or before["source_step_ids"] != dest["source_step_ids"]
                                        or [q["latex"] for q in before["fragments"]] !=
                                           [q["latex"] for q in dest["fragments"]]):
                                    raise LongboardError(f"SOURCE_MUTATED_ON_SCREEN: {mid}")
                                if (abs(before["x"]-dest["x"]) >= .5
                                        or abs(before["y"]-dest["y"]) >= .5
                                        or abs(before["scale"]-dest["scale"]) >= .0001):
                                    # VGroup's center follows its real glyph
                                    # outline; target center is computed from
                                    # a freshly placed copy for exact placement.
                                    exemplar = make_object(dest)
                                    moving.append(active[mid].animate
                                                  .scale(dest["scale"]/before["scale"])
                                                  .move_to(exemplar.get_center()))
                            if moving:
                                self.play(*moving,run_time=.62
                                          if row["transition"] == "scroll" else .48)
                            added = []
                            for p in row["placements"]:
                                mid = p["object_id"]
                                if mid in active:
                                    continue
                                obj = make_object(p)
                                active[mid] = obj
                                if mid in row["new_ids"]:
                                    # Exactly one mathematical event, segmented
                                    # only when a validated break hint exists.
                                    for frag in obj:
                                        self.play(Write(frag),run_time=.55)
                                    added.append({"object_id":mid,"kind":"write"})
                                else:
                                    self.play(FadeIn(obj),run_time=.22)
                                    added.append({"object_id":mid,"kind":"carry"})
                            highlights = []
                            header_highlights_deferred = []
                            for action in source_plan.scenes[scene_index].actions:
                                if action.kind != "brief_highlight":
                                    continue
                                mid = action.object_id
                                if mid in active:
                                    self.play(
                                        active[mid].animate.set_color(board.theme.highlight),
                                        run_time=.20
                                    )
                                    self.wait(.14)
                                    self.play(
                                        active[mid].animate.set_color(board.theme.ink),
                                        run_time=.20
                                    )
                                    highlights.append(mid)
                                elif action.to_region == "question":
                                    # The fixed header is composed AFTER video
                                    # rendering. Do not pretend a static overlay
                                    # implements animated question highlighting.
                                    header_highlights_deferred.append(mid)
                                else:
                                    raise LongboardError(
                                        f"HIGHLIGHT_TARGET_NOT_VISIBLE: {row['event_id']}/{mid}"
                                    )
                            if row["transition"] == "cut":
                                # No black-screen transition: the fixed header
                                # is composed independently and stays visible.
                                self.wait(.25)
                            else:
                                self.wait(.12)
                            previous = target
                            self.actual_events.append({
                                "highlighted_ids": highlights,
                                "header_highlights_not_animated": header_highlights_deferred,
                                "event_id":row["event_id"],
                                "page_index":row["page_index"],
                                "transition":row["transition"],
                                "start_preview_second":start,
                                "end_preview_second":self.time,
                                "archived_from_view":removing,
                                "written_or_carried":added,
                            })
                        self.preview_duration = self.time
                scene = LongboardScene()
                scene.render()
                rendered = Path(scene.renderer.file_writer.movie_file_path)
                if not rendered.is_file() or rendered.stat().st_size < 1000:
                    raise LongboardError("VIDEO_RENDER_FAILED: no valid Manim video")
                generated = temp / "math_video.mp4"
                shutil.copyfile(rendered, generated)
                event_timing = list(scene.actual_events)
                duration = scene.preview_duration

            header = make_question_overlay(
                board, temp/"header.png", pixel_width=pixel_width,
                pixel_height=pixel_height)
            result = temp/"longboard.mp4"
            proc = subprocess.run([
                "ffmpeg","-hide_banner","-loglevel","error","-y",
                "-i",str(generated), "-loop","1","-i",str(temp/"header.png"),
                "-filter_complex",
                "[0:v][1:v]overlay=0:0:shortest=1:eof_action=repeat[v]",
                "-map","[v]", "-c:v","libx264","-pix_fmt","yuv420p",
                "-r",str(fps),"-an", "-movflags","+faststart",str(result),
            ], capture_output=True,text=True)
            if proc.returncode or not result.exists() or result.stat().st_size < 1000:
                raise LongboardError(
                    "VIDEO_COMPOSITION_FAILED: " + proc.stderr[-380:]
                )
            metadata = {
                **layout,
                "render_kind":"manim_mathtex_longboard_continuous_mp4",
                "actual_preview_duration":duration,
                "fps":fps,
                "header":header,
                "event_timing":event_timing,
                "subtitle_status":"not_rendered_no_audio",
                "audio_status":"no_audio",
                "cut_kind":"working_area_page_change_no_black_transition",
                "scroll_kind":"survivor_mathtex_move_at_complete_event_boundary",
            }
            manifest = temp/"manifest.json"
            manifest.write_text(
                json.dumps(metadata,ensure_ascii=False,indent=2)+"\n",
                encoding="utf-8"
            )
            try:
                output_mp4.parent.mkdir(parents=True,exist_ok=True)
                output_json.parent.mkdir(parents=True,exist_ok=True)
                os.replace(result,output_mp4)
                os.replace(manifest,output_json)
            except Exception:
                output_mp4.unlink(missing_ok=True)
                output_json.unlink(missing_ok=True)
                raise
            return metadata
    except Exception:
        # No misleading partial successful movie on failed TeX/ffmpeg.
        output_mp4.unlink(missing_ok=True)
        output_json.unlink(missing_ok=True)
        raise
