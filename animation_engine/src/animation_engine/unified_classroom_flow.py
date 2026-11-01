"""V2.6.1 deterministic multi-engine classroom flow.

A stage is one independently validated V2.5 classroom. Its engine remains
unchanged and its source teacher-reviewed. An explicit, math-exact handoff
allows the next stage to rewrite a fact the preceding stage actually wrote.
Switching from a diagram to full-width mathematics uses an honest full-board
eraser sweep, while the approved question header stays pinned.

This is orchestration, not autonomous teaching-method selection, 2.6.2 mixed
intra-page layout, 2.6.3 advanced memory, or fabricated voice/subtitles.
"""
from __future__ import annotations

from .video_settings import DEFAULT_VIDEO_FPS, transition_frame_count

import hashlib
import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from visual_director.models import StoryboardPlan
from .models import ExecutionPlan
from .longboard_plan import LongboardError, _sources
from .persistent_chalkboard import (
    BOARD_START_Y, BOARD_BOTTOM_Y, make_chalkboard_plan,
    render_persistent_chalkboard, _strict_sources,
)

ENGINE_MANIFEST = {
    "diagram": "diagram_classroom.json",
    "computation": "computation_groups.json",
    "matrix": "matrix_steps.json",
    "proof": "proof_chain.json",
    "standard": None,
}
ENGINE_KWARG = {
    "diagram": "diagram_manifest",
    "computation": "computation_manifest",
    "matrix": "matrix_manifest",
    "proof": "proof_manifest",
}
REQUIRED_FILES = (
    "teaching_package.json", "storyboard.json", "execution.json",
    "teacher_approved_cues.json", "page_policy.json",
)
FLOW_FIELDS = frozenset({
    "schema_version", "mode", "teacher_reviewed", "lesson_id",
    "problem", "reference_solution_sha256", "stages",
})
STAGE_FIELDS = frozenset({
    "stage_id", "engine", "directory", "package_sha256",
    "source_storyboard_sha256", "event_ids", "handoff",
})
HANDOFF_FIELDS = frozenset({
    "from_stage", "from_object_id", "to_object_id",
})
TRANSITION_FRAMES = transition_frame_count(DEFAULT_VIDEO_FPS)  # default 36 frames; runtime duration stays 0.6s


def canonical_sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def _load(path: Path) -> dict:
    if not path.is_file():
        raise LongboardError("FLOW_MISSING_FILE: " + str(path))
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise LongboardError("FLOW_INVALID_JSON: " + str(path)) from exc
    if not isinstance(value, dict):
        raise LongboardError("FLOW_JSON_NOT_OBJECT")
    return value


@dataclass(frozen=True)
class Stage:
    stage_id: str
    engine: str
    folder: Path
    package: dict
    storyboard: dict
    execution: dict
    cues: dict
    policy: dict
    special: dict | None
    handoff: tuple[dict, ...]
    events: tuple[str, ...]

    def kwargs(self) -> dict:
        arg = ENGINE_KWARG.get(self.engine)
        return {arg: self.special} if arg is not None else {}


@dataclass(frozen=True)
class Flow:
    lesson_id: str
    problem: str
    source_sha256: str
    stages: tuple[Stage, ...]


def checked_flow(input_file: Path | str) -> Flow:
    path = Path(input_file).resolve()
    source = _load(path)
    if (set(source) != FLOW_FIELDS or source["schema_version"] != "1.0"
            or source["mode"] != "unified_classroom_flow"
            or source["teacher_reviewed"] is not True
            or type(source["lesson_id"]) is not str
            or not source["lesson_id"].isidentifier()
            or type(source["problem"]) is not str
            or not source["problem"].strip()
            or type(source["reference_solution_sha256"]) is not str
            or len(source["reference_solution_sha256"]) != 64):
        raise LongboardError("FLOW_INVALID_MANIFEST")
    rows = source["stages"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 64:
        raise LongboardError("FLOW_BAD_STAGE_COUNT")
    stages = []
    names = set()
    folders = set()
    previous_header = None
    previous_theme = None
    previous_math = None
    previous_written = None
    for i, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != STAGE_FIELDS:
            raise LongboardError("FLOW_STAGE_FIELDS")
        sid, engine, dirname = (row["stage_id"], row["engine"], row["directory"])
        if type(sid) is not str or not sid.isidentifier() or sid in names:
            raise LongboardError("FLOW_DUPLICATE_STAGE")
        if engine not in ENGINE_MANIFEST:
            raise LongboardError("FLOW_UNKNOWN_ENGINE")
        if (type(dirname) is not str or not dirname or dirname in (".", "..")
                or Path(dirname).is_absolute() or
                any(part in (".", "..") for part in Path(dirname).parts)):
            raise LongboardError("FLOW_UNSAFE_DIRECTORY")
        folder = (path.parent / dirname).resolve()
        if not folder.is_relative_to(path.parent):
            raise LongboardError("FLOW_DIRECTORY_ESCAPE")
        if folder in folders:
            raise LongboardError("FLOW_DUPLICATE_STAGE_DIRECTORY")
        names.add(sid)
        folders.add(folder)
        if (type(row["package_sha256"]) is not str
                or type(row["source_storyboard_sha256"]) is not str
                or not isinstance(row["event_ids"], list)
                or not row["event_ids"]
                or not isinstance(row["handoff"], list)):
            raise LongboardError("FLOW_STAGE_PROVENANCE")
        files = {filename: _load(folder / filename) for filename in REQUIRED_FILES}
        package = files["teaching_package.json"]
        storyboard = files["storyboard.json"]
        execution = files["execution.json"]
        cues = files["teacher_approved_cues.json"]
        policy = files["page_policy.json"]
        content_sha = canonical_sha({
            k: v for k, v in package.items() if k != "validated_content_sha256"
        })
        if (package.get("validated_content_sha256") != content_sha
                or content_sha != row["package_sha256"]):
            raise LongboardError("FLOW_PACKAGE_SOURCE_HASH")
        ref = package.get("source", {})
        if (ref.get("problem") != source["problem"]
                or canonical_sha(ref.get("reference_solution"))
                  != source["reference_solution_sha256"]):
            raise LongboardError("FLOW_NOT_SAME_APPROVED_QUESTION")
        board = StoryboardPlan.model_validate(storyboard)
        plan = ExecutionPlan.model_validate(execution)
        # Director hashes the COMPLETE sealed teacher package when
        # creating a storyboard, including its validated_content_sha256.
        # The flow stage's approval digest instead hashes its pre-seal
        # contents. They are different, both valid provenance layers.
        sealed_package_sha=canonical_sha(package)
        if (board.header.text != source["problem"]
                or board.source_package_sha256 != sealed_package_sha
                or plan.source_package_sha256 != sealed_package_sha):
            raise LongboardError("FLOW_QUESTION_OR_STORYBOARD_PACKAGE_MUTATION")
        if plan.source_storyboard_sha256 != row["source_storyboard_sha256"]:
            raise LongboardError("FLOW_STORYBOARD_HASH")
        event_ids = [e.event_id for e in board.scenes]
        if (row["event_ids"] != event_ids or
                [e.event_id for e in plan.scenes] != event_ids):
            raise LongboardError("FLOW_EVENT_COVERAGE_OR_ORDER")
        header_geometry = [
            e.regions["question"].model_dump(mode="json") for e in board.scenes
        ]
        if any(h != header_geometry[0] for h in header_geometry):
            raise LongboardError("FLOW_HEADER_MOVES_IN_STAGE")
        if previous_header is not None and header_geometry[0] != previous_header:
            raise LongboardError("FLOW_FIXED_HEADER_MOVED")
        theme = board.theme.model_dump(mode="json")
        if previous_theme is not None and theme != previous_theme:
            raise LongboardError("FLOW_CLASSROOM_THEME_MISMATCH")
        previous_header = header_geometry[0]
        previous_theme = theme
        filename = ENGINE_MANIFEST[engine]
        special = _load(folder / filename) if filename is not None else None
        for other in ENGINE_MANIFEST.values():
            if other is not None and other != filename and (folder / other).exists():
                raise LongboardError("FLOW_ENGINE_MANIFEST_CONFLICT")
        options = {ENGINE_KWARG[engine]: special} if filename else {}
        _strict_sources(storyboard, execution, cues, policy, **options)
        if engine == "computation":
            from .computation_groups import checked_computation_groups
            checked_computation_groups(special, storyboard, execution)
        maths = _sources(plan)
        written = {
            action.object_id
            for scene in plan.scenes for action in scene.actions
            if action.kind in ("progressive_write", "restore")
        }
        bridges = row["handoff"]
        if i == 0:
            if bridges:
                raise LongboardError("FLOW_FIRST_STAGE_CANNOT_HANDOFF")
        else:
            if not bridges:
                raise LongboardError("FLOW_MISSING_EXPLICIT_HANDOFF")
            first_writes = [
                a.object_id for a in plan.scenes[0].actions
                if a.kind in ("progressive_write", "restore")
                and a.to_region != "question"
            ]
            if not first_writes:
                raise LongboardError("FLOW_HANDOFF_WITHOUT_FIRST_WRITE")
            used = set()
            for bridge in bridges:
                if not isinstance(bridge, dict) or set(bridge) != HANDOFF_FIELDS:
                    raise LongboardError("FLOW_HANDOFF_FIELDS")
                if bridge["from_stage"] != stages[-1].stage_id:
                    raise LongboardError("FLOW_HANDOFF_NONADJACENT")
                from_id = bridge["from_object_id"]
                to_id = bridge["to_object_id"]
                if (type(from_id) is not str or type(to_id) is not str
                        or from_id not in previous_written
                        or from_id not in previous_math
                        or to_id not in first_writes
                        or to_id not in maths):
                    raise LongboardError("FLOW_HANDOFF_NOT_WRITTEN")
                if to_id in used:
                    raise LongboardError("FLOW_DUPLICATE_HANDOFF")
                used.add(to_id)
                if previous_math[from_id]["latex"] != maths[to_id]["latex"]:
                    raise LongboardError("FLOW_HANDOFF_MATH_MUTATION")
            if first_writes[0] != bridges[0]["to_object_id"]:
                raise LongboardError("FLOW_HANDOFF_NOT_FIRST_BOARD_WRITE")
        stages.append(Stage(
            sid, engine, folder, package, storyboard, execution, cues, policy,
            special, tuple(dict(b) for b in bridges), tuple(event_ids)
        ))
        previous_math = maths
        previous_written = written
    return Flow(source["lesson_id"], source["problem"], canonical_sha(source),
                tuple(stages))


def plan_flow(input_file: Path | str, *, measure=None) -> dict:
    flow = checked_flow(input_file)
    result_stages = []
    result_events = []
    page_offset = 0
    for index, stage in enumerate(flow.stages):
        plan = make_chalkboard_plan(
            stage.storyboard, stage.execution, stage.cues, stage.policy,
            measure=measure, **stage.kwargs()
        )
        if plan["source_storyboard_sha256"] != stage.execution["source_storyboard_sha256"]:
            raise LongboardError("FLOW_STAGE_LAYOUT_SOURCE_MISMATCH")
        result_stages.append({
            "stage_id": stage.stage_id,
            "engine": stage.engine,
            "stage_index": index,
            "page_count": plan["page_count"],
            "event_count": plan["event_count"],
            "global_first_page": page_offset + 1,
            "transition": (
                "initial_board" if index == 0 else "full_board_erase_with_fixed_header"
            ),
            "handoff": list(stage.handoff),
            "layout_mode": plan["alignment"]["mode"],
            "source_storyboard_sha256": stage.execution["source_storyboard_sha256"],
        })
        for event in plan["events"]:
            result_events.append({
                "global_event_id": stage.stage_id + ":" + event["event_id"],
                "event_id": event["event_id"],
                "stage_id": stage.stage_id,
                "engine": stage.engine,
                "global_page_index": page_offset + event["page_index"],
                "math_write_count": event["math_write_count"],
            })
        page_offset += plan["page_count"]
    return {
        "schema_version": "1.0", "mode": "unified_classroom_flow",
        "source_verified": True, "mathematical_truth_status": "teacher_reviewed",
        "source_flow_sha256": flow.source_sha256,
        "lesson_id": flow.lesson_id, "problem": flow.problem,
        "stage_count": len(flow.stages), "page_count": page_offset,
        "event_count": len(result_events),
        "stages": result_stages, "events": result_events,
        "fixed_header": True, "mode_change_policy": "explicit_full_board_wipe",
        "voice_status": "not_recorded",
        "subtitle_status": "not_audio_aligned",
    }


def _command(args: list[str], name: str):
    p = subprocess.run(args, capture_output=True, text=True)
    if p.returncode:
        raise LongboardError(name + ": " + (p.stderr or p.stdout)[-700:])


def _concat_verified_clips(
    playlist: Path, output: Path, *, fps: int, expected_frames: int,
) -> tuple[int, str]:
    """Bitstream-copy compatible H.264 clips, else use verified re-encoding.

    No video pixels are changed in the copy path. If clips differ in codec,
    geometry, chroma format, profile timing, or fail validation, fallback to
    the previous fully encoded renderer. Always check the decoded frame count.
    """
    # Probe all clips listed by this trusted internal playlist. The playlist
    # is generated by the renderer, never directly from an AI edit plan.
    files=[]
    for line in playlist.read_text(encoding="utf-8").splitlines():
        if not line.startswith("file '") or not line.endswith("'"):
            raise LongboardError("FLOW_UNTRUSTED_CONCAT_PLAYLIST")
        files.append(Path(line[6:-1]))
    if not files:
        raise LongboardError("FLOW_EMPTY_CONCAT")
    compatible=True
    signature=None
    for video in files:
        p=subprocess.run([
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=codec_name,width,height,pix_fmt,profile,"
            "level,r_frame_rate,time_base,sample_aspect_ratio",
            "-of", "json", str(video),
        ],capture_output=True,text=True)
        if p.returncode:
            compatible=False
            break
        try:
            row=json.loads(p.stdout)["streams"][0]
            entry=tuple(str(row.get(k,"")) for k in (
                "codec_name","width","height","pix_fmt","profile",
                "level","r_frame_rate","time_base","sample_aspect_ratio"
            ))
            if (row["codec_name"]!="h264" or
                (int(row["width"]),int(row["height"]))!=(1280,720) or
                row["pix_fmt"]!="yuv420p" or
                row["r_frame_rate"] != f"{fps}/1"):
                compatible=False
            if signature is not None and entry != signature:
                compatible=False
            signature=entry
        except (KeyError,IndexError,TypeError,ValueError):
            compatible=False
            break
    if compatible:
        proc=subprocess.run([
            "ffmpeg","-hide_banner","-loglevel","error","-y",
            "-f","concat","-safe","0","-i",str(playlist),
            "-map","0:v:0","-c:v","copy","-an",
            "-movflags","+faststart",str(output)
        ],capture_output=True,text=True)
        if proc.returncode==0 and output.exists():
            try:
                frames=_video_frames(output,fps,min_frames=1)
                # A valid bitstream may still fail actual H264 decode. Do
                # not publish a copied movie if errors were suppressed.
                decoded=subprocess.run([
                    "ffmpeg","-hide_banner","-v","error","-xerror",
                    "-i",str(output),"-f","null","-",
                ],capture_output=True,text=True)
                if (abs(frames-expected_frames)<=2 and
                        decoded.returncode==0):
                    return frames,"codec_copy_verified"
            except (LongboardError,ValueError,KeyError):
                pass
        output.unlink(missing_ok=True)
    _command([
        "ffmpeg","-hide_banner","-loglevel","error","-y",
        "-f","concat","-safe","0","-i",str(playlist),
        "-c:v","libx264","-pix_fmt","yuv420p",
        "-r",str(fps),"-an","-movflags","+faststart",str(output),
    ],"FLOW_JOIN_FAILED")
    frames=_video_frames(output,fps,min_frames=1)
    if abs(frames-expected_frames)>2:
        raise LongboardError("FLOW_JOIN_FRAME_COUNT_MISMATCH")
    return frames,"reencode_verified_fallback"


def _video_frames(path: Path, fps: int, *, min_frames: int = 20) -> int:
    p = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-count_frames", "-show_entries",
        "stream=width,height,r_frame_rate,nb_read_frames",
        "-of", "json", str(path)
    ], capture_output=True, text=True)
    if p.returncode:
        raise LongboardError("FLOW_FFPROBE_FAILED: " + p.stderr[-300:])
    stream = json.loads(p.stdout)["streams"][0]
    if (stream["width"], stream["height"]) != (1280, 720):
        raise LongboardError("FLOW_VIDEO_SIZE")
    rate = stream["r_frame_rate"].split("/")
    if int(rate[0]) / int(rate[1]) != fps:
        raise LongboardError("FLOW_VIDEO_FPS")
    frames = int(stream["nb_read_frames"])
    if frames < min_frames:
        raise LongboardError("FLOW_VIDEO_TOO_SHORT")
    return frames


def _render_board_wipe(prior_mp4: Path, dest: Path, scratch: Path,
                       fps: int, index: int) -> int:
    """Visible white eraser wipe of the board ONLY; header is never erased."""
    from PIL import Image, ImageDraw
    frame = scratch / f"last_{index}.png"
    _command(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
              "-sseof", "-0.05", "-i", str(prior_mp4),
              "-frames:v", "1", str(frame)], "FLOW_EXTRACT_LAST_FRAME")
    img = Image.open(frame).convert("RGB")
    if img.size != (1280, 720):
        raise LongboardError("FLOW_WIPE_FRAME_SIZE")
    pattern = scratch / f"wipe_{index}"
    pattern.mkdir()
    wipe_frames = transition_frame_count(fps)
    for i in range(wipe_frames):
        out = img.copy()
        width = round(1280 * (i+1) / wipe_frames)
        draw = ImageDraw.Draw(out)
        draw.rectangle([0, BOARD_START_Y-4, width, BOARD_BOTTOM_Y+3],
                       fill=(255,255,255))
        out.save(pattern / f"frame_{i:03d}.png")
    _command(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
              "-framerate", str(fps), "-i", str(pattern / "frame_%03d.png"),
              "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps),
              str(dest)], "FLOW_WIPE_ENCODE")
    # Keep the real-time 0.6s wipe at both 30 and 60 FPS.
    return _video_frames(dest, fps, min_frames=wipe_frames)


def render_flow(input_file: Path | str, *, output_mp4: Path,
                output_json: Path, fps: int = DEFAULT_VIDEO_FPS,
                narration_schedules=None, cache=None) -> dict:
    if (type(fps) is not int or not 8 <= fps <= 60
            or Path(output_mp4).suffix.lower() != ".mp4"
            or Path(output_json).suffix.lower() != ".json"):
        raise LongboardError("FLOW_RENDER_ARGUMENTS")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise LongboardError("FLOW_FFMPEG_UNAVAILABLE")
    flow = checked_flow(input_file)
    plan = plan_flow(input_file)
    with tempfile.TemporaryDirectory(prefix="unified-classroom-") as tmp:
        root = Path(tmp)
        parts = []
        timings = []
        stage_reports = []
        frame_offset = 0
        wipe_frames = transition_frame_count(fps)
        for i, stage in enumerate(flow.stages):
            part_video = root / f"stage_{i:02d}.mp4"
            part_json = root / f"stage_{i:02d}.json"
            from .incremental_render import render_or_reuse_stage
            manifest, cache_hit = render_or_reuse_stage(
                stage, output_mp4=part_video, output_json=part_json,
                fps=fps, narration_events=(
                    narration_schedules[stage.stage_id]
                    if narration_schedules is not None else None
                ), cache=cache,
            )
            if manifest["source_storyboard_sha256"] != stage.execution["source_storyboard_sha256"]:
                raise LongboardError("FLOW_RENDERED_STAGE_SOURCE_MISMATCH")
            if manifest["voice_status"] != "not_recorded":
                raise LongboardError("FLOW_UNVERIFIED_AUDIO")
            frames = _video_frames(part_video, fps)
            start_frames = frame_offset
            parts.append(part_video)
            for event in manifest["event_timing"]:
                timings.append({
                    **event, "stage_id": stage.stage_id,
                    "global_event_id": stage.stage_id + ":" + event["event_id"],
                    "global_start_second": start_frames/fps+event["start_preview_second"],
                    "global_end_second": start_frames/fps+event["end_preview_second"],
                })
            stage_reports.append({
                "stage_id": stage.stage_id,
                "engine": stage.engine,
                "source_storyboard_sha256": stage.execution["source_storyboard_sha256"],
                "start_frame": start_frames,
                "video_frames": frames,
                "page_count": manifest["page_count"],
                "event_count": manifest["event_count"],
                "handoff": list(stage.handoff),
                "stage_cache_hit": cache_hit,
            })
            frame_offset += frames
            if i != len(flow.stages)-1:
                wipe = root / f"wipe_{i:02d}.mp4"
                from .render_cache import file_sha
                transition_key=(
                    cache.key("transition",{
                        "source_clip":file_sha(part_video),
                        "action":"ordinary_chalkboard_wipe",
                        "next_stage":flow.stages[i+1].stage_id,
                        "fps":fps,"frames":wipe_frames,
                    }) if cache is not None else None
                )
                if cache is not None and cache.restore_video(
                        "transition",transition_key,wipe,
                        fps=fps,expected_frames=wipe_frames):
                    transition_frames=wipe_frames
                else:
                    transition_frames=_render_board_wipe(
                        part_video,wipe,root,fps,i
                    )
                    if cache is not None:
                        cache.store_video("transition",transition_key,wipe)
                frame_offset+=transition_frames
                parts.append(wipe)
        playlist = root / "segments.txt"
        playlist.write_text(
            "".join(f"file '{part.as_posix()}'\n" for part in parts),
            encoding="utf-8"
        )
        out = root / "full_classroom.mp4"
        total_frames, join_mode = _concat_verified_clips(
            playlist,out,fps=fps,expected_frames=frame_offset,
        )
        if abs(total_frames-frame_offset) > 2:
            raise LongboardError("FLOW_JOIN_FRAME_COUNT_MISMATCH")
        report = {
            **plan, "video": "authentic_manim_unified_classroom_flow",
            "fps": fps, "pixel_width": 1280, "pixel_height": 720,
            "actual_video_frames": total_frames,
            "erase_count_at_engine_changes": len(flow.stages)-1,
            "in_page_reposition_count": 0,
            "fabricated_voice_or_subtitle_count": 0,
            "stage_render_reports": stage_reports,
            "event_timing": timings,
            "incremental_stage_cache": (
                cache.stats() if cache is not None else None
            ),
            "join_mode": join_mode,
        }
        output_mp4 = Path(output_mp4)
        output_json = Path(output_json)
        output_mp4.parent.mkdir(parents=True, exist_ok=True)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(out, output_mp4)
        output_json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2)+"\n",
            encoding="utf-8"
        )
        return report
