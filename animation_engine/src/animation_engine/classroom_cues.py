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


PHASES = frozenset({"observe", "strategy", "knowledge", "pitfall",
                    "application", "calculate", "check", "conclusion", "summary"})
PHASE_NAMES = {
    "observe": "观察题目", "strategy": "思路引导",
    "knowledge": "核心知识点", "pitfall": "易错点",
    "application": "本题应用",
    "calculate": "逐步计算", "check": "结果检查",
    "conclusion": "最终结论", "summary": "归纳总结",
}
# Formula characters belong in the mathematically exact MathTex board, not
# in the CJK teaching-note raster layer or the TTS pronunciation layer.
NOTE_CHARACTERS = re.compile(r"^[\u3400-\u9fff0-9，。、；：？！—（）《》“”‘’·\s]+$")
# Reference-classroom typography: fixed sizes, category-specific colors.
# Chinese labels are PIL CJK glyphs; maths remains source MathTex.
BOARD_TEXT_STYLE = {
    "observe": {"heading": "#475569", "font_px": 20},
    "strategy": {"heading": "#2563EB", "font_px": 20},
    "knowledge": {"heading": "#7C3AED", "font_px": 20},
    "pitfall": {"heading": "#DC2626", "font_px": 20},
    "check": {"heading": "#D97706", "font_px": 20},
    "summary": {"heading": "#0F766E", "font_px": 20},
    "conclusion": {"heading": "#111111", "font_px": 20},
    "application": {"heading": "#111111", "font_px": 20},
    "calculate": {"heading": "#111111", "font_px": 20},
}
BOARD_DETAIL_FONT_PX = 18
BOARD_DERIVATION_INK = "#111111"
FONT_COLORS = {"ink":BOARD_DERIVATION_INK,"muted":"#64748B","blue":"#2563EB"}

# Actual board-writing sections inspired by reference videos: appear inside
# the central classroom, not as a persistent line beneath the question.
# Application and calculation explanations belong to future voice content;
# they are NOT converted to fake subtitles or repetitive board titles.
BOARD_GUIDANCE_PHASES = frozenset({"observe","strategy","knowledge","pitfall","check","summary"})



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
        if (not isinstance(references,list)
                or (not references and (item["phase"]!="summary" or known))
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
                     width: int = 1280, height: int = 720,
                     style: str = "classic") -> dict:
    from PIL import Image, ImageDraw

    if width != 1280 or height != 720:
        raise LongboardError("CLASSROOM_CUE_FRAME: current design requires 1280x720")
    if style == "board_context":
        # A real classroom section, not a banner beneath the fixed question.
        # Keep its top near the question; the formula is laid out after the
        # measured bottom of this note, never at a hard-coded overlapping y.
        panel = Image.new("RGBA", (width,height), (255,255,255,0))
        ink = ImageDraw.Draw(panel)
        phase = item["phase"]
        heading = PHASE_NAMES[phase] + "：" + item["heading"]
        detail = item["detail"]
        left, top, right = 320, 150, 1010
        font_h = _font(BOARD_TEXT_STYLE[phase]["font_px"])
        font_d = _font(BOARD_DETAIL_FONT_PX)
        head_rect = ink.textbbox((left,top),heading,font=font_h)
        if head_rect[0]<left or head_rect[2]>right:
            raise LongboardError(
                f"CLASSROOM_BOARD_HEADING_OVERFLOW: {item['event_id']}"
            )
        ink.text((left,top),heading,font=font_h,
                 fill=BOARD_TEXT_STYLE[phase]["heading"])
        lines, current = [], ""
        for char in detail:
            candidate=current+char
            if current and ink.textbbox((0,0),candidate,font=font_d)[2]>right-left:
                lines.append(current)
                current=char
            else:
                current=candidate
        if current:
            lines.append(current)
        if not lines or len(lines)>3:
            raise LongboardError(
                f"CLASSROOM_BOARD_NOTE_OVERFLOW: {item['event_id']}"
            )
        bottom = head_rect[3]
        for i,line in enumerate(lines):
            y=top+33+i*25
            rect=ink.textbbox((left,y),line,font=font_d)
            if rect[0]<left or rect[2]>right:
                raise LongboardError(
                    f"CLASSROOM_BOARD_NOTE_OVERFLOW: {item['event_id']}"
                )
            ink.text((left,y),line,font=font_d,fill=BOARD_DERIVATION_INK)
            bottom=max(bottom,rect[3])
        if bottom>285:
            raise LongboardError(
                f"CLASSROOM_BOARD_NOTE_HEIGHT: {item['event_id']}"
            )
        dest=Path(dest)
        dest.parent.mkdir(parents=True,exist_ok=True)
        panel.save(dest)
        return {
            "event_id":item["event_id"],"phase":phase,
            "heading":item["heading"],"detail":detail,
            "source_step_ids":item["source_step_ids"],
            "style":"board_context",
            "title_color":BOARD_TEXT_STYLE[phase]["heading"],
            "title_font_px":BOARD_TEXT_STYLE[phase]["font_px"],
            "detail_color":BOARD_DERIVATION_INK,
            "detail_font_px":BOARD_DETAIL_FONT_PX,
            "bbox_px":[left,top,right-left,bottom-top],
            "text_bottom_px":bottom,
            "is_temporary_board_section":True,
        }
    if style not in ("classic","simple_full_board","board_context"):
        raise LongboardError("CLASSROOM_CUE_STYLE")
    if style == "simple_full_board":
        # Chinese 五号字体 = 10.5 pt ≈ 14px at 96dpi.
        # No giant card: put the authored explanation in the middle of the
        # board, directly above the mathematically exact MathTex working area.
        # The text is never a subtitle and contains no faux math glyphs.
        center_x = width // 2
        panel = Image.new("RGBA", (width,height), (255,255,255,0))
        ink = ImageDraw.Draw(panel)
        phase = PHASE_NAMES[item["phase"]]
        heading = item["heading"]
        detail = item["detail"]
        line1 = phase + "  ·  " + heading
        spec = ((line1,14,145,FONT_COLORS["ink"]),
                (detail,14,168,FONT_COLORS["muted"]))
        textboxes = []
        for txt,points,y,color in spec:
            font = _font(points)
            bb = ink.textbbox((0,0),txt,font=font)
            x = round(center_x - (bb[2]-bb[0])/2)
            target_y = y-bb[1]
            actual = ink.textbbox((x,target_y),txt,font=font)
            if actual[0] < 82 or actual[2] > width-82 or actual[3] > 187:
                raise LongboardError(
                    f"CLASSROOM_COMPACT_TEXT_OVERFLOW: {item['event_id']}"
                )
            ink.text((x,target_y),txt,font=font,fill=color)
            textboxes.append(list(actual))
        dest = Path(dest)
        dest.parent.mkdir(parents=True,exist_ok=True)
        panel.save(dest)
        return {
            "event_id":item["event_id"],"phase":item["phase"],
            "heading":heading,"detail":detail,
            "source_step_ids":item["source_step_ids"],
            "style":"simple_full_board","font_pt":10.5,
            "text_boxes_px":textboxes,"occupied_bottom_px":188,
        }
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
