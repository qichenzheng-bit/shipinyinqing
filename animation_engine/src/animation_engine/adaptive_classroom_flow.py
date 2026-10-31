"""V2.6.2 source-bound classroom layout with retained diagram state.

A teacher-reviewed sidecar chooses when a verified diagram is visible. Genuine
Manim/MathTex stages are rendered in their native measured board columns;
FFmpeg composes a pixel-accurate memento of the finished diagram on later
frames. Math is NEVER shrunk by scaling a finished full-screen video.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .diagram_classroom import DIAGRAM_PANEL, checked_diagram_classroom
from .longboard_plan import LongboardError
from .persistent_chalkboard import (
    BOARD_BOTTOM_Y, BOARD_START_Y, DIAGRAM_LEFT_X, DIAGRAM_LEFT_WIDTH,
    make_chalkboard_plan, render_persistent_chalkboard,
)
from .unified_classroom_flow import (
    TRANSITION_FRAMES, Flow, _command, _load, _render_board_wipe,
    _video_frames, checked_flow, plan_flow,
)

LAYOUT_FIELDS = frozenset({
    "schema_version", "mode", "teacher_reviewed",
    "source_flow_sha256", "stages",
})
STAGE_FIELDS = frozenset({
    "stage_id", "layout", "diagram_action", "diagram_source_stage",
    "teaching_reason",
})
LAYOUTS = frozenset({"diagram_native", "math_left_diagram_right", "full_width"})
ACTIONS = frozenset({"create", "hold", "hide", "restore", "none"})
PANEL_MARGIN = 20


@dataclass(frozen=True)
class AdaptiveStage:
    stage_id: str
    layout: str
    action: str
    source_stage_id: str | None
    reason: str


@dataclass(frozen=True)
class AdaptiveFlow:
    flow: Flow
    flow_file: Path
    stages: tuple[AdaptiveStage, ...]
    manifest_sha256: str


def _sha(value) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def checked_adaptive_flow(input_file: Path | str) -> AdaptiveFlow:
    """Reject unsourced images, premature reveals, and incompatible regions."""
    input_path = Path(input_file).resolve()
    payload = _load(input_path)
    if (set(payload) != LAYOUT_FIELDS or payload["schema_version"] != "1.0"
            or payload["mode"] != "adaptive_classroom_layout"
            or payload["teacher_reviewed"] is not True):
        raise LongboardError("ADAPTIVE_INVALID_MANIFEST")
    flow_file = input_path.parent / "unified_flow.json"
    flow = checked_flow(flow_file)
    if payload["source_flow_sha256"] != flow.source_sha256:
        raise LongboardError("ADAPTIVE_FLOW_SOURCE_MUTATED")
    rows = payload["stages"]
    if not isinstance(rows, list) or len(rows) != len(flow.stages):
        raise LongboardError("ADAPTIVE_STAGE_COVERAGE")
    saved_diagrams = {}
    visible = None
    seen_hidden = set()
    out = []
    for i, (row, stage) in enumerate(zip(rows, flow.stages)):
        if not isinstance(row, dict) or set(row) != STAGE_FIELDS:
            raise LongboardError("ADAPTIVE_STAGE_FIELDS")
        ident = row["stage_id"]
        layout = row["layout"]
        action = row["diagram_action"]
        source = row["diagram_source_stage"]
        reason = row["teaching_reason"]
        if ident != stage.stage_id or layout not in LAYOUTS or action not in ACTIONS:
            raise LongboardError("ADAPTIVE_STAGE_ORDER_OR_MODE")
        if (type(reason) is not str or not reason.strip()
                or len(reason) > 180):
            raise LongboardError("ADAPTIVE_MISSING_TEACHING_REASON")
        if i == 0:
            if stage.engine == "diagram":
                if (layout, action, source) != (
                        "diagram_native", "create", ident):
                    raise LongboardError("ADAPTIVE_DIAGRAM_MUST_REVEAL_FROM_SOURCE")
            elif (layout, action, source) != ("full_width", "none", None):
                raise LongboardError("ADAPTIVE_UNVERIFIED_FIRST_DIAGRAM")
        if action == "create":
            if (stage.engine != "diagram" or
                    layout != "diagram_native" or source != ident or
                    visible is not None or source in saved_diagrams):
                raise LongboardError("ADAPTIVE_INVALID_DIAGRAM_CREATE")
            # Source geometry, labels, fill and reveal order are independently
            # checked by the existing V2.5.4 source contract.
            checked_diagram_classroom(stage.special, stage.storyboard, stage.execution)
            saved_diagrams[source] = stage.special["source_storyboard_sha256"]
            visible = source
        elif action == "hold":
            if (layout != "math_left_diagram_right" or
                    stage.engine != "standard" or source != visible or
                    source not in saved_diagrams):
                raise LongboardError("ADAPTIVE_HOLD_WITHOUT_VISIBLE_SOURCE")
        elif action == "restore":
            if (layout != "math_left_diagram_right" or
                    stage.engine != "standard" or visible is not None or
                    source not in saved_diagrams or source not in seen_hidden):
                raise LongboardError("ADAPTIVE_RESTORE_WITHOUT_SAVED_SOURCE")
            visible = source
        elif action == "hide":
            if (layout != "full_width" or source != visible or
                    source not in saved_diagrams or stage.engine == "diagram"):
                raise LongboardError("ADAPTIVE_HIDE_NOT_VISIBLE")
            seen_hidden.add(source)
            visible = None
        elif action == "none":
            if (layout != "full_width" or source is not None
                    or visible is not None or stage.engine == "diagram"):
                raise LongboardError("ADAPTIVE_NONE_WHILE_DIAGRAM_VISIBLE")
        if (action in ("hide", "none") and layout != "full_width") or (
                action in ("hold", "restore") and layout != "math_left_diagram_right"):
            raise LongboardError("ADAPTIVE_LAYOUT_ACTION_CONFLICT")
        out.append(AdaptiveStage(ident, layout, action, source, reason))
    return AdaptiveFlow(flow, flow_file, tuple(out), _sha(payload))


def _stage_plan(stage, adaptive, *, measure=None) -> dict:
    layout_hint = (
        "diagram_left"
        if adaptive.layout == "math_left_diagram_right"
        else None
    )
    board = make_chalkboard_plan(
        stage.storyboard, stage.execution, stage.cues, stage.policy,
        measure=measure, layout_hint=layout_hint, **stage.kwargs(),
    )
    if layout_hint:
        right = DIAGRAM_LEFT_X + DIAGRAM_LEFT_WIDTH
        for event in board["events"]:
            for block in event["added_blocks"]:
                if block["x"] < DIAGRAM_LEFT_X - .01 or (
                        block["x"] + block["w"] > right + .01):
                    raise LongboardError("ADAPTIVE_LEFT_COLUMN_OVERFLOW")
    return board


def plan_adaptive_flow(input_file: Path | str, *, measure=None) -> dict:
    checked = checked_adaptive_flow(input_file)
    old = plan_flow(checked.flow_file, measure=measure)
    for index, (stage, spec) in enumerate(zip(checked.flow.stages, checked.stages)):
        native = _stage_plan(stage, spec, measure=measure)
        old["stages"][index].update({
            "layout_mode": spec.layout,
            "diagram_action": spec.action,
            "diagram_source_stage": spec.source_stage_id,
            "teaching_reason": spec.reason,
            "native_math_size_preserved": True,
            "page_count": native["page_count"],
            "alignment": native["alignment"],
        })
    old.update({
        "mode": "adaptive_classroom_layout",
        "schema_version": "1.0",
        "source_adaptive_manifest_sha256": checked.manifest_sha256,
        "diagram_lifecycle_source_verified": True,
        "mode_change_policy": "selective_board_wipe_with_source_diagram_retention",
    })
    return old


def _extract_frame(video: Path, png: Path):
    _command([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-sseof", "-0.05", "-i", str(video), "-frames:v", "1", str(png),
    ], "ADAPTIVE_EXTRACT_SOURCE_FRAME")


def _extract_panel(video: Path, png: Path, root: Path):
    from PIL import Image
    full = root / ("source_frame_" + png.stem + ".png")
    _extract_frame(video, full)
    img = Image.open(full).convert("RGB")
    if img.size != (1280, 720):
        raise LongboardError("ADAPTIVE_SOURCE_FRAME_SIZE")
    p = DIAGRAM_PANEL
    img.crop((p["x"], p["y"], p["x"]+p["w"], p["y"]+p["h"])).save(png)
    # These are the original verified rendered pixels, not a recreated sketch.


def _with_diagram(stage_video: Path, panel: Path, dest: Path,
                  fps: int, frames: int) -> int:
    p = DIAGRAM_PANEL
    _command([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(stage_video), "-loop", "1", "-i", str(panel),
        "-filter_complex",
        f"[0:v][1:v]overlay={p['x']}:{p['y']}:shortest=1:eof_action=repeat[v]",
        "-map", "[v]", "-frames:v", str(frames),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps),
        "-an", str(dest),
    ], "ADAPTIVE_PANEL_COMPOSE")
    actual = _video_frames(dest, fps)
    if actual != frames:
        raise LongboardError("ADAPTIVE_PANEL_FRAME_COUNT_CHANGED")
    return actual


def _wipe_preserving_diagram(prior_mp4: Path, dest: Path,
                             scratch: Path, fps: int, index: int) -> int:
    """Erase mathematical work only; retain the *same* panel on every frame."""
    from PIL import Image, ImageDraw
    frame = scratch / f"adaptive_last_{index}.png"
    _extract_frame(prior_mp4, frame)
    img = Image.open(frame).convert("RGB")
    if img.size != (1280, 720):
        raise LongboardError("ADAPTIVE_WIPE_FRAME_SIZE")
    strip = scratch / f"adaptive_wipe_{index}"
    strip.mkdir()
    width = DIAGRAM_PANEL["x"] - PANEL_MARGIN
    for i in range(TRANSITION_FRAMES):
        out = img.copy()
        ImageDraw.Draw(out).rectangle(
            (0, BOARD_START_Y - 4,
             round(width*(i+1)/TRANSITION_FRAMES), BOARD_BOTTOM_Y+3),
            fill=(255,255,255),
        )
        out.save(strip / f"frame_{i:03d}.png")
    _command([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-framerate", str(fps), "-i", str(strip / "frame_%03d.png"),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps),
        str(dest),
    ], "ADAPTIVE_PRESERVING_WIPE")
    return _video_frames(dest, fps, min_frames=TRANSITION_FRAMES)


def render_adaptive_flow(input_file: Path | str, *,
                         output_mp4: Path, output_json: Path,
                         fps: int = 30) -> dict:
    if (type(fps) is not int or not 8 <= fps <= 60
            or Path(output_mp4).suffix.lower() != ".mp4"
            or Path(output_json).suffix.lower() != ".json"):
        raise LongboardError("ADAPTIVE_RENDER_ARGUMENTS")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise LongboardError("ADAPTIVE_FFMPEG_UNAVAILABLE")
    checked = checked_adaptive_flow(input_file)
    layout = plan_adaptive_flow(input_file)
    flow = checked.flow
    with tempfile.TemporaryDirectory(prefix="adaptive-classroom-") as tmp:
        root = Path(tmp)
        panels = {}
        parts = []
        reports = []
        timings = []
        frame_offset = 0
        for i, (stage, spec) in enumerate(zip(flow.stages, checked.stages)):
            raw = root / f"raw_stage_{i:02d}.mp4"
            raw_manifest = root / f"raw_stage_{i:02d}.json"
            rendered = render_persistent_chalkboard(
                stage.storyboard, stage.execution, stage.cues, stage.policy,
                output_mp4=raw, output_json=raw_manifest, fps=fps,
                layout_hint=("diagram_left" if spec.layout ==
                             "math_left_diagram_right" else None),
                **stage.kwargs(),
            )
            if (rendered["source_storyboard_sha256"] !=
                    stage.execution["source_storyboard_sha256"]
                    or rendered["voice_status"] != "not_recorded"):
                raise LongboardError("ADAPTIVE_UNVERIFIED_RENDERED_SOURCE")
            raw_frames = _video_frames(raw, fps)
            clip = raw
            if spec.action == "create":
                panel_path = root / f"diagram_{stage.stage_id}.png"
                _extract_panel(raw, panel_path, root)
                panels[stage.stage_id] = panel_path
            elif spec.action in ("hold", "restore"):
                clip = root / f"composed_stage_{i:02d}.mp4"
                _with_diagram(raw, panels[spec.source_stage_id],
                              clip, fps, raw_frames)
            start = frame_offset
            parts.append(clip)
            for event in rendered["event_timing"]:
                timings.append({
                    **event,
                    "stage_id": stage.stage_id,
                    "global_event_id": stage.stage_id + ":" + event["event_id"],
                    "global_start_second": start/fps + event["start_preview_second"],
                    "global_end_second": start/fps + event["end_preview_second"],
                })
            reports.append({
                "stage_id": stage.stage_id,
                "engine": stage.engine,
                "layout": spec.layout,
                "diagram_action": spec.action,
                "diagram_source_stage": spec.source_stage_id,
                "source_storyboard_sha256":
                    stage.execution["source_storyboard_sha256"],
                "start_frame": start,
                "video_frames": raw_frames,
                "page_count": rendered["page_count"],
                "event_count": rendered["event_count"],
                "native_math_size_preserved": True,
                "handoff": list(stage.handoff),
            })
            frame_offset += raw_frames
            if i < len(flow.stages) - 1:
                next_spec = checked.stages[i+1]
                wipe = root / f"transition_{i:02d}.mp4"
                keep = (
                    next_spec.action == "hold"
                    and next_spec.source_stage_id == spec.source_stage_id
                    and spec.action in ("create", "hold", "restore")
                )
                transition_frames = (
                    _wipe_preserving_diagram(clip, wipe, root, fps, i)
                    if keep else
                    _render_board_wipe(clip, wipe, root, fps, i)
                )
                parts.append(wipe)
                frame_offset += transition_frames
        playlist = root / "segments.txt"
        playlist.write_text(
            "".join(f"file '{v.as_posix()}'\n" for v in parts),
            encoding="utf-8",
        )
        movie = root / "adaptive_full.mp4"
        _command([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "concat", "-safe", "0", "-i", str(playlist),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-r", str(fps), "-an", "-movflags", "+faststart", str(movie),
        ], "ADAPTIVE_JOIN_FAILED")
        frames = _video_frames(movie, fps)
        if abs(frames-frame_offset) > 2:
            raise LongboardError("ADAPTIVE_JOIN_FRAME_MISMATCH")
        report = {
            **layout,
            "video": "true_manim_source_bound_adaptive_classroom",
            "fps": fps,
            "pixel_width": 1280,
            "pixel_height": 720,
            "actual_video_frames": frames,
            "erase_count_at_engine_changes": len(flow.stages)-1,
            "preserving_wipe_count": sum(
                a.action in ("create", "hold", "restore") and
                b.action == "hold" and
                a.source_stage_id == b.source_stage_id
                for a,b in zip(checked.stages, checked.stages[1:])),
            "fabricated_voice_or_subtitle_count": 0,
            "stage_render_reports": reports,
            "event_timing": timings,
            "diagram_panel_pixels": dict(DIAGRAM_PANEL),
        }
        target = Path(output_mp4)
        manifest = Path(output_json)
        target.parent.mkdir(parents=True, exist_ok=True)
        manifest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(movie, target)
        manifest.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return report
