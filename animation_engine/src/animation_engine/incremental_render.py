"""V2.6.6 stage-level incremental Manim rendering.

A stage is an existing independently validated unit with its own board/voice
timings. A cache hit must preserve the exact event/action timings and source
contract; cross-stage diagram overlays, erases and global clock are rebuilt
from those reports, so later scenes remain synchronized after local edits.
"""
from __future__ import annotations

import time
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .persistent_chalkboard import render_persistent_chalkboard
from .render_cache import ArtifactCache


def stage_key(stage: Any, *, fps: int, layout_hint: str | None,
              narration_events: dict | None, cache: ArtifactCache) -> str:
    return cache.key("raw_stage", {
        "stage_id": stage.stage_id,
        "engine": stage.engine,
        "package": stage.package,
        "storyboard": stage.storyboard,
        "execution": stage.execution,
        "cues": stage.cues,
        "policy": stage.policy,
        "special": stage.special,
        "handoff": stage.handoff,
        "events": stage.events,
        "fps": fps,
        "width": 1280, "height": 720,
        "layout_hint": layout_hint,
        "narration_events": narration_events,
    })



def _event_key(stage, index: int, event_id: str, *,
               fps: int, layout_hint: str | None,
               narration_events: dict, cache: ArtifactCache) -> str:
    """An unaffected event is reusable after a different spoken event changes.

    The entire *mathematical* stage source is intentionally included: edited
    equations, diagrams, labels or handoff invalidate ALL affected event
    clips, even where an AI guesses they are unrelated. Only the voice schedule
    of this particular event is included in the dynamic inputs.
    """
    return cache.key("event_clip", {
        "stage_id":stage.stage_id,"event_index":index,"event_id":event_id,
        "storyboard":stage.storyboard,"execution":stage.execution,
        "cues":stage.cues,"policy":stage.policy,"special":stage.special,
        "package":stage.package,"handoff":stage.handoff,"events":stage.events,
        "narration":narration_events[event_id],
        "layout_hint":layout_hint,"fps":fps,"resolution":(1280,720),
    })


def _event_frame_bounds(events: list[dict], total_frames: int,
                        fps: int) -> list[int]:
    if not events or total_frames <= 0:
        raise ValueError("CACHE_EVENT_EMPTY")
    positions=[0]
    for current in events[1:]:
        positions.append(round(current["start_preview_second"]*fps))
    positions.append(total_frames)
    if (any(a >= b for a,b in zip(positions,positions[1:]))
            or positions[0]!=0 or positions[-1]!=total_frames):
        raise ValueError("CACHE_EVENT_NONCONTIGUOUS")
    return positions


def _cache_full_stage_events(
        stage, report: dict, stage_movie: Path, *, fps: int,
        layout_hint: str | None, narration_events: dict,
        cache: ArtifactCache) -> None:
    """Split one full scene ONCE into accurate per-event videos.

    This is an optimization, not a source of truth: the original full video
    remains accepted when the optional extraction cannot be verified.
    """
    from .unified_classroom_flow import _video_frames
    source_sha=stage.execution["source_storyboard_sha256"]
    events=report["event_timing"]
    expected=list(narration_events)
    if [x["event_id"] for x in events]!=expected:
        raise ValueError("CACHE_EVENT_SOURCE_ORDER_MISMATCH")
    total_frames=_video_frames(stage_movie,fps)
    positions=_event_frame_bounds(events,total_frames,fps)
    with tempfile.TemporaryDirectory(prefix="chalk-event-extract-") as scratch:
        folder=Path(scratch)
        for i, event in enumerate(events):
            eid=event["event_id"]
            key=_event_key(stage,i,eid,fps=fps,layout_hint=layout_hint,
                           narration_events=narration_events,cache=cache)
            if cache.read("event_clip",key,
                          filenames=("video.mp4","manifest.json")) is not None:
                continue
            a,b=positions[i],positions[i+1]
            movie=folder/f"event_{i:02d}.mp4"
            cmd=[
                "ffmpeg","-hide_banner","-loglevel","error","-y",
                "-i",str(stage_movie),
                "-vf",f"trim=start_frame={a}:end_frame={b},setpts=PTS-STARTPTS",
                "-an","-c:v","libx264","-pix_fmt","yuv420p",
                "-r",str(fps),"-frames:v",str(b-a),
                str(movie),
            ]
            run=subprocess.run(cmd,capture_output=True,text=True)
            if run.returncode:
                raise ValueError("CACHE_EVENT_EXTRACT_FAILED:"+run.stderr[-300:])
            if _video_frames(movie,fps,min_frames=1)!=b-a:
                raise ValueError("CACHE_EVENT_EXTRACT_WRONG_FRAMES")
            offset=event["start_preview_second"]
            localized={
                **event,
                "start_preview_second":0.0,
                "end_preview_second":(b-a)/fps,
                "action_timing":[{
                    **a0,
                    "start_preview_second":a0["start_preview_second"]-offset,
                    "end_preview_second":a0["end_preview_second"]-offset,
                } for a0 in event["action_timing"]],
            }
            # Entry state comes from the source-checked full Manim render.
            item={
                **report,
                "event_timing":[localized],
                "actual_preview_duration":(b-a)/fps,
                "rendered_event_index":i,
                "event_window_entry_verified":True,
                "actual_video_frames":b-a,
                "event_clip_origin":"verified_full_stage_frame_extract",
            }
            record=folder/f"event_{i:02d}.json"
            record.write_text(json.dumps(item,ensure_ascii=False),
                              encoding="utf-8")
            if item["source_storyboard_sha256"]!=source_sha:
                raise ValueError("CACHE_EVENT_SOURCE_PROVENANCE_FAILED")
            cache.store_stage(key,movie,record,namespace="event_clip")


def _rebuild_stage_from_events(
        stage, *, output_mp4: Path, output_json: Path, fps: int,
        layout_hint: str | None, narration_events: dict,
        cache: ArtifactCache) -> dict | None:
    """Re-render only changed event(s), source-restore all others.

    Any ambiguity or loss of frame precision returns None, so the caller
    rebuilds the whole stage through the original trusted renderer.
    """
    from .unified_classroom_flow import _video_frames,_concat_verified_clips
    ids=list(narration_events)
    if len(ids)<2:
        return None
    # First render has no event clips: keep the efficient single-Manim-scene
    # path, then split its VERIFIED result once for future edit rounds.
    available=sum(
        cache.read(
            "event_clip",
            _event_key(stage,index,eid,fps=fps,layout_hint=layout_hint,
                       narration_events=narration_events,cache=cache),
            filenames=("video.mp4","manifest.json"),
        ) is not None
        for index,eid in enumerate(ids)
    )
    if available==0:
        return None
    with tempfile.TemporaryDirectory(prefix="chalk-event-merge-") as scratch:
        folder=Path(scratch)
        parts=[]
        manifests=[]
        expected_frames=0
        for index,eid in enumerate(ids):
            mp4=folder/f"event_{index:02d}.mp4"
            js=folder/f"event_{index:02d}.json"
            key=_event_key(stage,index,eid,fps=fps,layout_hint=layout_hint,
                           narration_events=narration_events,cache=cache)
            source_sha=stage.execution["source_storyboard_sha256"]
            previous=cache.restore_stage(
                key,mp4,js,fps=fps,source_storyboard_sha256=source_sha,
                namespace="event_clip",expected_event_id=eid,
                expected_event_index=index,
            )
            if previous is None:
                # A single MathTex/diagram event scene is independently
                # initialized using the live objects visible before it.
                # The source, geometry and audio ordering are revalidated.
                previous=render_persistent_chalkboard(
                    stage.storyboard,stage.execution,stage.cues,stage.policy,
                    output_mp4=mp4,output_json=js,
                    fps=fps,narration_events=narration_events,
                    layout_hint=layout_hint,event_index=index,
                    **stage.kwargs(),
                )
                if (previous["source_storyboard_sha256"]!=source_sha or
                        previous["voice_status"]!="not_recorded" or
                        previous.get("rendered_event_index")!=index):
                    raise ValueError("CACHE_EVENT_RENDER_SOURCE_MISMATCH")
                cache.store_stage(key,mp4,js,namespace="event_clip")
            if (len(previous["event_timing"])!=1 or
                    previous["event_timing"][0]["event_id"]!=eid):
                raise ValueError("CACHE_EVENT_ID_MISMATCH")
            frames=_video_frames(mp4,fps,min_frames=1)
            parts.append(mp4)
            manifests.append((previous,frames))
            expected_frames+=frames
        playlist=folder/"parts.txt"
        playlist.write_text(
            "".join(f"file '{p.as_posix()}'\n" for p in parts),
            encoding="utf-8",
        )
        frames,join_mode=_concat_verified_clips(
            playlist,output_mp4,fps=fps,expected_frames=expected_frames
        )
        if frames!=expected_frames:
            raise ValueError("CACHE_EVENT_ASSEMBLY_FRAME_COUNT")
        aggregate=[]
        cursor=0
        for previous,clip_frames in manifests:
            event=previous["event_timing"][0]
            start=cursor/fps
            action=[
                {**a0,
                 "start_preview_second":start+a0["start_preview_second"],
                 "end_preview_second":start+a0["end_preview_second"]}
                for a0 in event["action_timing"]
            ]
            aggregate.append({
                **event,
                "start_preview_second":start,
                "end_preview_second":start+clip_frames/fps,
                "action_timing":action,
            })
            cursor+=clip_frames
        # Every event must be present in stage order; no math or voice
        # action is invented, shifted out or accidentally duplicated.
        assert [x["event_id"] for x in aggregate]==ids
        report={
            **manifests[0][0],
            "event_timing":aggregate,
            "actual_preview_duration":frames/fps,
            "rendered_event_index":None,
            "event_window_entry_verified":False,
            "event_clip_count":len(parts),
            "event_join_mode":join_mode,
        }
        output_json.write_text(
            json.dumps(report,ensure_ascii=False,indent=2)+"\n",
            encoding="utf-8",
        )
        return report


def render_or_reuse_stage(stage, *, output_mp4: Path, output_json: Path,
                          fps: int, narration_events: dict | None,
                          layout_hint: str | None = None,
                          cache: ArtifactCache | None = None) -> tuple[dict,bool]:
    kwargs=stage.kwargs()
    if cache is None:
        report=render_persistent_chalkboard(
            stage.storyboard, stage.execution, stage.cues, stage.policy,
            output_mp4=output_mp4,output_json=output_json,
            fps=fps,narration_events=narration_events,
            layout_hint=layout_hint,**kwargs
        )
        return report,False
    key=stage_key(
        stage,fps=fps,layout_hint=layout_hint,
        narration_events=narration_events,cache=cache
    )
    started=time.perf_counter()
    restored=cache.restore_stage(
        key,output_mp4,output_json,fps=fps,
        source_storyboard_sha256=stage.execution["source_storyboard_sha256"],
    )
    if restored is not None:
        cache.timed("stage_cache_restore_seconds",time.perf_counter()-started)
        return restored,True
    report=None
    if narration_events is not None and len(narration_events)>1:
        try:
            report=_rebuild_stage_from_events(
                stage,output_mp4=output_mp4,output_json=output_json,
                fps=fps,layout_hint=layout_hint,
                narration_events=narration_events,cache=cache,
            )
            if report is not None:
                cache.counts["event_stage_reassembled"]+=1
        except (OSError,ValueError,RuntimeError,KeyError,AssertionError) as exc:
            # On any source/codec/state/clock mismatch, fall back to the full
            # stage path, which is already independently accepted by V2.6.5.
            cache.counts["event_stage_safe_fallback"]+=1
            output_mp4.unlink(missing_ok=True)
            output_json.unlink(missing_ok=True)
            report=None
    if report is None:
        report=render_persistent_chalkboard(
            stage.storyboard,stage.execution,stage.cues,stage.policy,
            output_mp4=output_mp4,output_json=output_json,
            fps=fps,narration_events=narration_events,
            layout_hint=layout_hint,**kwargs
        )
        cache.timed("stage_manim_render_seconds",
                    time.perf_counter()-started)
        if narration_events is not None and len(narration_events)>1:
            try:
                _cache_full_stage_events(
                    stage,report,output_mp4,
                    fps=fps,layout_hint=layout_hint,
                    narration_events=narration_events,cache=cache,
                )
            except (OSError,ValueError,RuntimeError,KeyError):
                # Event extraction is optional; never invalidate a good
                # completed stage or replace source-proven math with guesses.
                cache.counts["event_extract_unavailable"]+=1
    else:
        cache.timed("event_level_reassembly_seconds",
                    time.perf_counter()-started)
    if (report["source_storyboard_sha256"] !=
            stage.execution["source_storyboard_sha256"] or
            report.get("voice_status") != "not_recorded"):
        raise ValueError("CACHE_STAGE_RENDER_SOURCE_FAILED")
    cache.store_stage(key,output_mp4,output_json)
    return report,False
