"""Pure deterministic storyboard planning from a teacher TeachingPackage v1.0.

No AI, no math inference, no TTS, no timing guesses and no renderer.
"""
from __future__ import annotations
import hashlib
import json
import math
import re
from typing import Any
from .geometry import GeometryError, place_diagram
from .models import (
    Rect, Theme, HeaderPlan, DirectorOptions, CaptionPart, CaptionCue,
    BoardVisualAction, ScenePlan, StoryboardPlan,
)


class DirectorError(ValueError):
    pass


def _indexed(rows, field):
    ids = [r.get(field) for r in rows]
    if any(not isinstance(x,str) or not x.strip() for x in ids) or len(ids)!=len(set(ids)):
        raise DirectorError(f"DUPLICATE_OR_EMPTY_ID: {field}")
    return {r[field]:r for r in rows}


def _header(question: str) -> HeaderPlan:
    # Approximate visual occupancy; LaTeX syntax costs fewer glyphs than raw
    # characters, but detailed typography is delegated to a renderer.
    length = len(question)
    if length <= 110:
        lines = 1
        height = .165
        align = "center"
    else:
        lines = math.ceil(length / 92)
        height = min(.34,.115+.04*lines)
        align = "left"
    if lines > 6:
        raise DirectorError("HEADER_OVERFLOW: question requires dedicated multiline layout")
    return HeaderPlan(text=question,align=align,lines=lines,height=height,font_scale=1.0)


def _regions(header: HeaderPlan, layout: str):
    top = header.height + .022
    bottom = .848
    height = bottom-top
    if height < .38:
        raise DirectorError("LAYOUT_OVERFLOW: header leaves too little space")
    zones = {
        "question": Rect(x=.035,y=.01,w=.93,h=header.height-.01),
        "captions": Rect(x=.05,y=.875,w=.90,h=.102),
    }
    if layout in ("split_scratch", "diagram_split"):
        zones["board"]=Rect(x=.04,y=top,w=.575,h=height)
        zones["scratch" if layout=="split_scratch" else "diagram"]=Rect(x=.645,y=top,w=.315,h=height)
    else:
        zones["board"]=Rect(x=.04,y=top,w=.92,h=height)
    return zones


def _layout(event_type: str, obj_latex: list[str], diagram: bool) -> str:
    if diagram:
        return "diagram_split"
    if event_type == "proof":
        return "proof_scroll"
    if any(re.search(r"\\begin\{(?:[a-zA-Z]*matrix|array)\}", s) for s in obj_latex):
        return "matrix_compare"
    if event_type in ("knowledge", "application"):
        if any(len(s) > 105 for s in obj_latex):
            return "full_board"
        return "split_scratch"
    return "full_board"


def _validate(p: dict, opts: DirectorOptions):
    if not isinstance(p,dict) or p.get("schema_version")!="1.0":
        raise DirectorError("UNSUPPORTED_TEACHER_SCHEMA: expected TeachingPackage 1.0")
    validation=p.get("validation") or {}
    status=validation.get("status")
    if status=="blocked":
        raise DirectorError("BLOCKED_PACKAGE: teacher refused this content")
    if status=="needs_review" and not opts.allow_needs_review:
        raise DirectorError("NEEDS_REVIEW: explicitly allow review-only storyboard")
    if status not in ("ready_with_limits","needs_review"):
        raise DirectorError("UNKNOWN_VALIDATION_STATUS")
    try:
        source=p["source"]; lesson=p["lesson"]; plan=p["plan"]
        events=lesson["lesson_events"]
        event_map=_indexed(events,"event_id")
        teacher_events=_indexed(plan["teaching_events"],"event_id")
        actions=_indexed(lesson["board_actions"],"board_action_id")
        math_objects=_indexed(lesson["math_objects"],"math_object_id")
        speech_units=_indexed(lesson["speech_units"],"speech_unit_id")
        animations=_indexed(lesson["animation_intents"],"animation_id")
        _indexed(p["subtitles"],"subtitle_id")
    except (KeyError,TypeError,AttributeError) as exc:
        raise DirectorError(f"MALFORMED_TEACHER_PACKAGE: {exc}") from exc
    if not source.get("problem","").strip():
        raise DirectorError("EMPTY_QUESTION")
    if set(event_map) != set(teacher_events):
        raise DirectorError("EVENT_MISMATCH: planning and lesson events differ")
    if [e["event_id"] for e in events] != [e["event_id"] for e in plan["teaching_events"]]:
        raise DirectorError("EVENT_ORDER_MISMATCH")
    if len(opts.diagrams)!=len(set(x.event_id for x in opts.diagrams)):
        raise DirectorError("DIAGRAM_REFERENCE: duplicate event hints")
    if any(x.event_id not in event_map for x in opts.diagrams):
        raise DirectorError("DIAGRAM_REFERENCE: nonexistent event")
    for m in math_objects.values():
        if not m.get("latex","").strip():
            raise DirectorError("EMPTY_LATEX_OBJECT")
        if "\\boxed" in m["latex"] or "\\fbox" in m["latex"]:
            raise DirectorError("BOXED_ANSWER: decorative boxes prohibited")
    for e in events:
        event_id=e["event_id"]
        for uid in e["speech_unit_ids"]:
            if uid not in speech_units or speech_units[uid]["event_id"]!=event_id:
                raise DirectorError("SPEECH_REFERENCE: orphan or mismatched unit")
        for aid in e["board_action_ids"]:
            if aid not in actions or actions[aid]["event_id"] != event_id:
                raise DirectorError("BOARD_REFERENCE: orphan or mismatched action")
            a=actions[aid]
            if a["math_object_id"] not in math_objects:
                raise DirectorError("UNKNOWN_MATH_OBJECT: "+a["math_object_id"])
            if a["speech_unit_id"] not in e["speech_unit_ids"]:
                raise DirectorError("SPEECH_REFERENCE: board action has speech unit outside its event: " + aid)
        for anim_id in e["animation_intent_ids"]:
            if anim_id not in animations or animations[anim_id]["event_id"]!=event_id:
                raise DirectorError("ANIMATION_REFERENCE: missing or mismatched animation")
            anim=animations[anim_id]
            if any(aid not in e["board_action_ids"] for aid in anim["board_action_ids"]):
                raise DirectorError("ANIMATION_REFERENCE: unknown board action")
            if any(uid not in e["speech_unit_ids"] for uid in anim["speech_unit_ids"]):
                raise DirectorError("ANIMATION_REFERENCE: unknown speech unit")
        # A purely spoken transition may intentionally have no board action.
    for a in actions.values():
        if a["event_id"] not in event_map or a["board_action_id"] not in event_map[a["event_id"]]["board_action_ids"]:
            raise DirectorError("BOARD_REFERENCE: action omitted from parent event")
    for animation in animations.values():
        if animation["event_id"] not in event_map or animation["animation_id"] not in event_map[animation["event_id"]]["animation_intent_ids"]:
            raise DirectorError("ANIMATION_REFERENCE: omitted from parent event")
    for speech in speech_units.values():
        if speech["event_id"] not in event_map or speech["speech_unit_id"] not in event_map[speech["event_id"]]["speech_unit_ids"]:
            raise DirectorError("SPEECH_REFERENCE: orphaned speech unit")
    for cap in p["subtitles"]:
        uid=cap["speech_unit_id"]
        if uid not in speech_units:
            raise DirectorError("CAPTION_SPEECH_REFERENCE: unknown unit")
        spoken=[(x["kind"],x["value"]) for x in speech_units[uid]["parts"]]
        actual=[(x["kind"],x["value"]) for x in cap["parts"]]
        if spoken != actual:
            raise DirectorError("CAPTION_MISMATCH: caption text/math differs from speech semantic source")
        if any(kind not in ("text","math") or not isinstance(value,str) for kind,value in actual):
            raise DirectorError("INVALID_CAPTION_PART")
    if set(c["speech_unit_id"] for c in p["subtitles"])!=set(speech_units):
        raise DirectorError("CAPTION_COVERAGE: not all speech units are subtitled")
    return source,events,teacher_events,actions,math_objects,speech_units


def _validated_diagram(spec):
    try:
        return place_diagram(spec)
    except GeometryError as exc:
        raise DirectorError(str(exc)) from exc


def build_storyboard(package: dict[str,Any], options: DirectorOptions | None=None) -> StoryboardPlan:
    opts=options or DirectorOptions()
    source,events,teacher_events,actions,objects,units=_validate(package,opts)
    header=_header(source["problem"])
    diagram_hints={hint.event_id:hint for hint in opts.diagrams}
    visible:list[str]=[]
    archived:list[str]=[]
    placement:dict[str,str]={}
    warnings:list[str]=[]
    scenes:list[ScenePlan]=[]
    for event in events:
        eid=event["event_id"]
        event_type=teacher_events[eid]["event_type"]
        board_actions=[actions[aid] for aid in event["board_action_ids"]]
        current_refs={action["math_object_id"] for action in board_actions}
        # Scratch formulas occupy the temporary right-hand area only while a
        # knowledge/application scene is active. At the next ordinary lesson
        # scene, they are archived without discarding mathematical provenance.
        math_text=[objects[a["math_object_id"]]["latex"] for a in board_actions]
        layout=_layout(event_type,math_text,eid in diagram_hints)
        if layout != "split_scratch":
            for mid in list(visible):
                if placement.get(mid)=="scratch" and mid not in current_refs:
                    visible.remove(mid)
                    if mid not in archived: archived.append(mid)
                    placement.pop(mid,None)
        regions=_regions(header,layout)
        planned_actions=[]
        for action in board_actions:
            obj=objects[action["math_object_id"]]
            mid=obj["math_object_id"]
            op=action["action"]
            if op in ("transform","substitute"):
                # Teacher v1 has no from/to math-subpart mapping. Never claim
                # mathematical transformation merely because the enum says so.
                visual_op="progressive_write"
                if "TRANSFORM_REQUIRES_MAPPING" not in warnings:
                    warnings.append("TRANSFORM_REQUIRES_MAPPING")
            elif op in ("write",):
                visual_op="progressive_write"
            elif op in ("highlight",):
                visual_op="brief_highlight"
            elif op in ("retain","group","remove"):
                visual_op=op
            else:
                raise DirectorError("UNSUPPORTED_BOARD_ACTION: "+op)
            # An object that only exists in a highlight instruction can be a
            # title/header object (e.g. question). Do not render it twice.
            if op=="highlight" and mid not in visible and mid not in archived:
                if event_type == "read_question" or obj["latex"].strip() in source["problem"]:
                    visual_op="brief_highlight"
                else:
                    visual_op="progressive_write"
                    warnings.append("HIGHLIGHT_UNSEEN_DOWNGRADED")
            if op=="remove":
                placement.pop(mid,None)
                if mid in visible: visible.remove(mid)
                if mid in archived: archived.remove(mid)
            elif op in ("retain","group"):
                if mid in archived: archived.remove(mid)
                if mid not in visible: visible.append(mid)
                placement[mid] = "scratch" if layout=="split_scratch" else "board"
            elif op=="highlight" and visual_op=="brief_highlight" and (event_type == "read_question" or obj["latex"].strip() in source["problem"]):
                # Header already pinned on screen.
                pass
            elif mid not in visible:
                if mid in archived: archived.remove(mid)
                visible.append(mid)
                placement[mid] = "scratch" if layout=="split_scratch" else "board"
            planned_actions.append(BoardVisualAction(
                action_id=action["board_action_id"],event_id=eid,object_id=mid,
                latex=obj["latex"],kind=visual_op,source_action=op,
                speech_unit_id=action["speech_unit_id"],reason=action["semantic_reason"],
                source_step_ids=obj["source_step_ids"]
            ))
        scroll=False
        # Hold the most recent active formulas. Older formulas are archived,
        # never deleted from the storyboard's provenance or previous scenes.
        while len(visible)>opts.max_visible_formulas:
            old=visible.pop(0)
            if old not in archived: archived.append(old)
            placement.pop(old,None)
            scroll=True
        scenes.append(ScenePlan(
            event_id=eid,event_type=event_type,layout=layout,regions=regions,
            actions=planned_actions,visible_ids=list(visible),archived_ids=list(archived),
            object_regions={mid:placement.get(mid,"board") for mid in visible},
            scroll_board=scroll or (layout=="proof_scroll" and len(archived)>0),
            diagram=_validated_diagram(diagram_hints[eid]) if eid in diagram_hints else None,
        ))
    captions=[CaptionCue(subtitle_id=c["subtitle_id"],speech_unit_id=c["speech_unit_id"],
                parts=[CaptionPart(kind=part["kind"],value=part["value"]) for part in c["parts"]]) for c in package["subtitles"]]
    if package["validation"]["status"]=="needs_review":
        warnings.append("NEEDS_REVIEW")
    digest=package.get("input_sha256") or hashlib.sha256(json.dumps(source,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    return StoryboardPlan(source_input_sha256=digest,source_schema_version=package["schema_version"],
        theme=Theme(),header=header,scenes=scenes,captions=captions,warnings=sorted(set(warnings)))