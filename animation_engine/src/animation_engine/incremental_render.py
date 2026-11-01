"""V2.6.6 stage-level incremental Manim rendering.

A stage is an existing independently validated unit with its own board/voice
timings. A cache hit must preserve the exact event/action timings and source
contract; cross-stage diagram overlays, erases and global clock are rebuilt
from those reports, so later scenes remain synchronized after local edits.
"""
from __future__ import annotations

import time
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
    report=render_persistent_chalkboard(
        stage.storyboard, stage.execution, stage.cues, stage.policy,
        output_mp4=output_mp4,output_json=output_json,
        fps=fps,narration_events=narration_events,
        layout_hint=layout_hint,**kwargs
    )
    cache.timed("stage_manim_render_seconds",time.perf_counter()-started)
    if (report["source_storyboard_sha256"] !=
            stage.execution["source_storyboard_sha256"] or
            report.get("voice_status") != "not_recorded"):
        raise ValueError("CACHE_STAGE_RENDER_SOURCE_FAILED")
    cache.store_stage(key,output_mp4,output_json)
    return report,False
