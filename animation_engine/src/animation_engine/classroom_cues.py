"""Reference-led classroom direction: explicitly authored pedagogical cues only.

Cues are on-board teaching annotations, NOT speech transcripts/subtitles.
Their wording and sequence require approval by the teacher/content author.
The renderer cannot derive a cue from LaTeX or fabricate explanations.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

from visual_director.models import StoryboardPlan
from .models import ExecutionPlan
from .longboard_plan import LongboardError
from .classroom_compositor import _font


PHASES = frozenset({"observe", "strategy", "knowledge", "application",
                    "calculate", "check", "summary"})
PHASE_NAMES = {
    "observe": "观察题目", "strategy": "思路引导",
    "knowledge": "知识回顾", "application": "本题应用",
    "calculate": "逐步计算", "check": "结果检查",
    "summary": "归纳总结",
}
# Formula characters belong in the mathematically exact MathTex board, not
# in the CJK teaching-note raster layer or the TTS pronunciation layer.
NOTE_CHARACTERS = re.compile(r"^[\u3400-\u9fff，。、；：？！—（）《》“”‘’·\s]+$")
FONT_COLORS = {"ink":"#1E293B","muted":"#64748B","blue":"#2563EB"}


def checked_cues(source: dict, storyboard, execution) -> list[dict]:
    board = StoryboardPlan.model_validate(storyboard)
    plan = ExecutionPlan.model_validate(execution)
    if not isinstance(source, dict) or set(source) != {
        "schema_version", "source_storyboard_sha256", "events"
    } or source["schema_version"] != "1.0":
        raise LongboardError("CLASSROOM_CUES_SCHEMA")
    if source["source_storyboard_sha256"] != plan.source_storyboard_sha256:
        raise LongboardError("CLASSROOM_CUES_SOURCE_HASH")
    given = source["events"]
    if not isinstance(given, list) or len(given) != len(board.scenes):
        raise LongboardError("CLASSROOM_CUES_COVERAGE")
    checked = []
    for i, (item, scene, state) in enumerate(zip(given,board.scenes,plan.scenes)):
        required = {"event_id","phase","heading","detail","source_step_ids",
                    "pause_seconds","write_seconds"}
        if not isinstance(item,dict) or set(item) != required:
            raise LongboardError(f"CLASSROOM_CUE_FIELDS: event index {i}")
        if item["event_id"] != scene.event_id or item["event_id"] != state.event_id:
            raise LongboardError(f"CLASSROOM_CUE_ORDER: event index {i}")
        if item["phase"] not in PHASES:
            raise LongboardError(f"CLASSROOM_CUE_PHASE: {scene.event_id}")
        for name, limit in (("heading",19),("detail",58)):
            text=item[name]
            if (not isinstance(text,str) or not text.strip() or len(text)>limit
                    or not NOTE_CHARACTERS.fullmatch(text)):
                raise LongboardError(
                    f"CLASSROOM_CUE_NOT_PURE_TEXT: {scene.event_id}/{name}"
                )
        references = item["source_step_ids"]
        known = {s for a in state.actions for s in a.source_step_ids}
        if (not isinstance(references,list) or not references
                or any(type(s) is not str or s not in known for s in references)
                or len(set(references))!=len(references)):
            raise LongboardError(f"CLASSROOM_CUE_PROVENANCE: {scene.event_id}")
        for name,lo,hi in (("pause_seconds",1.0,4.5),
                           ("write_seconds",.6,2.2)):
            number=item[name]
            if (type(number) not in (float,int) or not math.isfinite(number)
                    or not lo <= number <= hi):
                raise LongboardError(f"CLASSROOM_CUE_PACING: {scene.event_id}")
        checked.append(dict(item))
    return checked


def draw_cue_overlay(item: dict, dest: Path, *,
                     width: int = 1280, height: int = 720) -> dict:
    from PIL import Image, ImageDraw

    if width != 1280 or height != 720:
        raise LongboardError("CLASSROOM_CUE_FRAME: current design requires 1280x720")
    canvas=Image.new("RGBA",(width,height),(255,255,255,0))
    d=ImageDraw.Draw(canvas)
    x,y=66,129
    # One restrained, purposeful teaching panel. The board's formula origin
    # is always below y=242; the panel never obscures MathTex or subtitles.
    d.rounded_rectangle((x,y,1195,216),radius=8,fill=(245,248,252,255))
    d.rounded_rectangle((x,y,x+6,216),radius=3,fill=FONT_COLORS["blue"])
    phase=PHASE_NAMES[item["phase"]]
    d.text((x+24,y+10),phase,font=_font(17),fill=FONT_COLORS["blue"])
    d.text((x+143,y+7),item["heading"],font=_font(27),fill=FONT_COLORS["ink"])
    d.text((x+24,y+48),item["detail"],font=_font(19),fill=FONT_COLORS["muted"])
    # Strict pixel boundaries, no silent text clipping.
    for txt,font_size,tx,ty in ((phase,17,x+24,y+10),
                                 (item["heading"],27,x+143,y+7),
                                 (item["detail"],19,x+24,y+48)):
        bbox=d.textbbox((tx,ty),txt,font=_font(font_size))
        if bbox[2]>1178 or bbox[3]>214:
            raise LongboardError(f"CLASSROOM_CUE_OVERFLOW: {item['event_id']}")
    dest=Path(dest)
    dest.parent.mkdir(parents=True,exist_ok=True)
    canvas.save(dest)
    return {"event_id":item["event_id"],"phase":item["phase"],
            "heading":item["heading"],"detail":item["detail"],
            "source_step_ids":item["source_step_ids"],
            "bbox_px":[x,y,1195-x,216-y]}


def cue_hash(data: dict) -> str:
    return hashlib.sha256(json.dumps(
        data,ensure_ascii=False,sort_keys=True,separators=(",",":")
    ).encode("utf-8")).hexdigest()
