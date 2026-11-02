"""Reusable V2.7 end-of-lesson recap: only already-reviewed source ink.

This is a presentation module, NOT a lesson author, a TTS script writer,
or a subtitle generator. It replays existing MathTex and approved error
notes during the unchanged summary voice action. It never creates new math,
a new speech event, or a new caption.
"""
from __future__ import annotations

from .longboard_plan import LongboardError

RECAP_BOARD_MODULE = "source_verified_knowledge_pitfall_reboard_v1"
# One readable page: latest relevant core formulae and actual pitfall(s).
MAX_KNOWLEDGE_ITEMS = 2
MAX_PITFALL_ITEMS = 2


def select_recap_sources(prior_events: list[dict], prior_cues: list[dict],
                         written: set[str]) -> list[tuple]:
    """Select source objects in teacher order; never synthesize a formula.

    Knowledge uses the first independently authored formula in each knowledge
    unit. Concrete error corrections may also replay their original MathTex.
    Previously rendered, source-bound note text is reused verbatim.
    """
    if len(prior_events) != len(prior_cues):
        raise LongboardError("RECAP_SOURCE_CUE_COUNT_MISMATCH")
    knowledge = []
    pitfalls = []
    for event, cue in zip(prior_events, prior_cues):
        phase = cue["phase"]
        if phase not in ("knowledge", "pitfall"):
            continue
        note = next((
            b for b in event["added_blocks"]
            if b["kind"] == "teacher_note" and not b.get("carry")
        ), None)
        maths = [
            b["block_id"] for b in event["added_blocks"]
            if b["kind"] == "math" and not b.get("carry")
            and b["block_id"] in written
        ]
        if phase == "knowledge" and maths:
            knowledge.append((phase, cue, note, maths[:1]))
        elif phase == "pitfall" and note is not None:
            pitfalls.append((phase, cue, note, maths[:1]))
    return knowledge[-MAX_KNOWLEDGE_ITEMS:] + pitfalls[-MAX_PITFALL_ITEMS:]


def recap_animation_budget(duration: float | None, count: int,
                           *, title_seconds: float = 0.32,
                           fps: int = 60) -> tuple[float, ...]:
    """Schedule visual re-boarding INSIDE existing summary narration time.

    Leaves a guard for frame rounding and voice finish. Nothing here changes
    source audio, captions, phrase order or total event duration.
    """
    if type(count) is not int or count < 0 or fps < 8 or fps > 60:
        raise ValueError("RECAP_ANIMATION_ARGUMENTS")
    if count == 0:
        return ()
    if duration is None:
        return (0.56,) * count
    if not isinstance(duration, (float, int)) or duration < 0:
        raise ValueError("RECAP_ANIMATION_DURATION")
    available = max(0.0, duration - title_seconds - 4 / fps)
    total = min(available, duration * 0.70, count * 1.35)
    return (total / count,) * count


def reveal_recap_during_summary(scene, objects: list[tuple[str, object]], *,
                                duration: float | None, fps: int) -> None:
    """Write real source MathTex and fade source notes while recap is spoken.

    Caller first fades in the summary title. This function must be invoked
    BEFORE the wait for the remaining summary speech, not after that wait.
    """
    from manim import FadeIn, Write, linear
    ticks = recap_animation_budget(duration, len(objects),
                                   title_seconds=0, fps=fps)
    for (kind, obj), seconds in zip(objects, ticks):
        if seconds < .13:
            # The source note or math remains visible; a very short voice
            # window cannot safely support a new prolonged animation.
            scene.add(obj)
        else:
            animation = Write(obj) if kind == "math" else FadeIn(obj)
            scene.play(animation, run_time=seconds, rate_func=linear)
