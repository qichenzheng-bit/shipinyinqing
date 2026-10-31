"""Append-only classroom chalkboard: write, preserve, clear only on full board.

The original approved mathematical source is immutable. Every event adds either
an approved CJK teaching note and/or exact MathTex. No previously written ink
moves, fades, scrolls or silently disappears between ordinary teacher events.
A full board is erased in one visible sweep at an event boundary. A completed
result may then be explicitly REWRITTEN from the verified original source.
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

from .longboard_plan import (
    LongboardError, LongboardPolicy, _sources, _size_parts, _make_placement
)
from .planner import build_execution_plan
from .adaptive_layout import _real_measure
from .classroom_cues import (
    checked_cues, BOARD_GUIDANCE_PHASES, BOARD_TEXT_STYLE,
    BOARD_DERIVATION_INK, BOARD_DETAIL_FONT_PX, PHASE_NAMES
)
from .longboard_header import make_question_overlay
from .board_motion import overlaps


BOARD_START_Y = 148
BOARD_BOTTOM_Y = 620
# Wide board: left margin and right side are both usable, without touching
# the fixed question or the separate lower subtitle safety area.
BOARD_X = 110
BOARD_WIDTH = 1060
BOARD_ROW_GAP = 11
KNOWLEDGE_WIDTH = 430
KNOWLEDGE_GUTTER = 24
NOTE_MAX_CHARS_PER_LINE = 48
NOTE_HEIGHT = 29
NOTE_DETAIL_LINE_HEIGHT = 23
BOARD_CENTER_X = BOARD_X + BOARD_WIDTH / 2
BOARD_CENTER_Y = (BOARD_START_Y + BOARD_BOTTOM_Y) / 2
QUESTION_TO_BOARD_MIN_GAP_PX = 22
MAX_PAGE_TOP_OFFSET_PX = 20


def _page_start_y(board) -> tuple[int, int]:
    """Keep the first board write below the APPROVED fixed-question region.

    Header geometry is the conservative source of truth. The generic
    148px baseline is retained for ordinary one-line exam questions.
    """
    zone = board.scenes[0].regions["question"]
    header_bottom = math.ceil((zone.y + zone.h) * 720)
    return max(BOARD_START_Y, header_bottom + QUESTION_TO_BOARD_MIN_GAP_PX), header_bottom



def _ink_width(block: dict) -> float:
    """Estimate the visible CJK glyph span, not the empty note reservation.

    Mathematical bounds are real MathTex measurements. For Chinese notes the
    deterministic estimate only selects horizontal placement; the renderer
    still verifies actual font glyph bounds before creating the video.
    """
    if block["kind"] == "math":
        return block["w"]
    from .classroom_cues import BOARD_TEXT_STYLE
    title_px = BOARD_TEXT_STYLE[block["phase"]]["font_px"]
    return min(block["w"], max(
        len(block["heading"]) * title_px,
        *(len(line) * BOARD_DETAIL_FONT_PX for line in block["lines"]),
        1,
    ) + 2)


def _translate_block(block: dict, *, dx: float = 0, dy: float = 0):
    """Move only an unrendered layout plan; never animate existing ink."""
    block["x"] = round(block["x"] + dx, 3)
    block["y"] = round(block["y"] + dy, 3)
    for fragment in block.get("fragments", []):
        fragment["x"] = round(fragment["x"] + dx, 3)
        fragment["y"] = round(fragment["y"] + dy, 3)


def _center_new_group(blocks: list[dict]) -> float:
    """Place each incoming teacher unit around the same board center line.

    A two-column knowledge/calculation unit is centered as ONE group,
    preserving its internal columns. Single-column calculation units, recap
    and summary are centered as well. Existing ink is never reflowed.
    """
    if not blocks:
        return 0.0
    left = min(block["x"] for block in blocks)
    right = max(block["x"] + _ink_width(block) for block in blocks)
    dx = round(BOARD_CENTER_X - (left + right) / 2, 3)
    for block in blocks:
        _translate_block(block, dx=dx)
    return dx


def _center_page_heights(events: list[dict], *, page_start_y: int,
                         header_bottom_y: int) -> list[dict]:
    """Keep every page close to the question, with modest vertical balancing.

    Formerly, short pages were unconditionally centered at y=384; their
    first formula could start far below the question. Cap the page's single
    pre-render translation so its first ink starts near the header instead.
    Horizontal centering and persistent ink remain unchanged.
    """
    pages: dict[int, list[dict]] = {}
    for event in events:
        pages.setdefault(event["page_index"], []).extend(event["added_blocks"])
    records = []
    for page_index, blocks in pages.items():
        if not blocks:
            continue
        top = min(block["y"] for block in blocks)
        bottom = max(block["y"] + block["h"] for block in blocks)
        ideal_shift = BOARD_CENTER_Y - (top + bottom) / 2
        max_down_shift = page_start_y + MAX_PAGE_TOP_OFFSET_PX - top
        dy = round(max(0.0, min(ideal_shift, max_down_shift)), 3)
        for block in blocks:
            _translate_block(block, dy=dy)
            if (block["y"] < page_start_y-0.01 or
                    block["y"] + block["h"] > BOARD_BOTTOM_Y+0.01 or
                    block["x"] < BOARD_X-0.01 or
                    block["x"] + _ink_width(block) > BOARD_X+BOARD_WIDTH+0.01):
                raise LongboardError("CHALKBOARD_CENTERING_OUT_OF_BOUNDS")
        left = min(block["x"] for block in blocks)
        right = max(block["x"] + _ink_width(block) for block in blocks)
        new_top = min(block["y"] for block in blocks)
        new_bottom = max(block["y"] + block["h"] for block in blocks)
        if new_top > page_start_y + MAX_PAGE_TOP_OFFSET_PX + 0.01:
            raise LongboardError("CHALKBOARD_HEADER_GAP_TOO_LARGE")
        if new_top < header_bottom_y + QUESTION_TO_BOARD_MIN_GAP_PX - 0.01:
            raise LongboardError("CHALKBOARD_HEADER_GAP_TOO_SMALL")
        records.append({
            "page_index": page_index,
            "ink_center_x": round((left+right)/2, 3),
            "ink_center_y": round((new_top+new_bottom)/2, 3),
            "first_ink_y": round(new_top, 3),
            "header_bottom_y": header_bottom_y,
            "header_to_ink_gap_px": round(new_top - header_bottom_y, 3),
            "vertical_offset_px": dy,
        })
    return records


def _strict_sources(storyboard, execution, cues, policy, matrix_manifest=None):
    from visual_director.models import StoryboardPlan
    from .models import ExecutionPlan
    board=StoryboardPlan.model_validate(storyboard)
    plan=ExecutionPlan.model_validate(execution)
    if plan.model_dump(mode="json") != build_execution_plan(board).model_dump(mode="json"):
        raise LongboardError("CHALKBOARD_SOURCE_CONTRACT_MISMATCH")
    teaching=checked_cues(cues,board,plan)
    selected=LongboardPolicy.parse(policy)
    selected.validate(set(_sources(plan)),{s.event_id for s in board.scenes},_sources(plan))
    # This specialized layout never renders diagram objects, matrix columns
    # or proof-scroll regions. Reject incompatible source rather than produce
    # a plausible-looking MP4 that silently omits essential content.
    matrix=None
    if matrix_manifest is not None:
        from .matrix_steps import checked_matrix_steps
        matrix=checked_matrix_steps(matrix_manifest, board, plan)
    unsupported=[
        scene.event_id for scene in board.scenes
        if scene.diagram is not None
        or scene.layout in ("diagram_split","proof_scroll")
        or (scene.layout=="matrix_compare" and matrix is None)
    ]
    if unsupported:
        raise LongboardError(
            "CHALKBOARD_UNSUPPORTED_SPECIAL_LAYOUT: "+
            ",".join(unsupported)
        )
    if selected.guidance_style != "persistent_chalkboard":
        raise LongboardError("CHALKBOARD_REQUIRES_PERSISTENT_GUIDANCE_STYLE")
    if selected.board_mode != "simple_full_board":
        raise LongboardError("CHALKBOARD_REQUIRES_SIMPLE_FULL_BOARD")
    if selected.cut_before_events or selected.pinned_ids:
        raise LongboardError("CHALKBOARD_DISALLOWS_FORCED_CUT_OR_PINNING")
    return board,plan,teaching,selected,matrix


def _note_lines(detail: str, width: int = BOARD_WIDTH) -> list[str]:
    # Conservative Chinese line length. The final PIL glyph bounds are
    # checked again before rendering; never let a note spill into math.
    chars=min(NOTE_MAX_CHARS_PER_LINE,max(10,int(width/18)))
    return [detail[i:i+chars] for i in range(0,len(detail),chars)]


def _math_placement(mid,sources,selected,measure,size_cache,y, *,
                    x=BOARD_X,width=BOARD_WIDTH):
    source=sources[mid]
    parts=_size_parts(mid,source,selected,measure,720,size_cache,width)
    return _make_placement(
        mid,source,parts,x,y,width,(1280,720),"working",
        selected.math_base_scale,selected.math_min_scale
    )


def make_chalkboard_plan(storyboard,execution,cues,policy, *,
                         measure=None, computation_manifest=None,
                         matrix_manifest=None) -> dict:
    if matrix_manifest is not None and computation_manifest is not None:
        raise LongboardError("CHALKBOARD_MULTIPLE_SPECIAL_CONTRACTS")
    board,execution_plan,teaching,selected,matrix=_strict_sources(
        storyboard,execution,cues,policy,matrix_manifest=matrix_manifest
    )
    sources=_sources(execution_plan)
    computation=None
    if computation_manifest is not None:
        from .computation_groups import checked_computation_groups
        computation=checked_computation_groups(
            computation_manifest,board,execution_plan
        )
    original_measure=measure or _real_measure
    measurements={}
    def size_of(latex,height):
        key=(latex,height)
        if key not in measurements:
            measurements[key]=original_measure(latex,height)
        return measurements[key]
    size_cache={}
    page_start_y, header_bottom_y = _page_start_y(board)
    cursor=page_start_y
    page=1
    active=[]
    written=set()
    events=[]
    all_math=set()
    last_event_id=None
    for scene,action_scene,cue in zip(board.scenes,execution_plan.scenes,teaching):
        newids=list(dict.fromkeys(
            a.object_id for a in action_scene.actions
            if a.kind in ("progressive_write","restore")
            and a.object_id in sources and a.to_region!="question"
        ))
        if any(mid in written for mid in newids):
            raise LongboardError(
                f"CHALKBOARD_DUPLICATE_MATH_WRITE: {scene.event_id}"
            )
        # For a reviewed integral, dedicate the left portion to the
        # knowledge description and its *real MathTex formula*. Put the
        # complete step-by-step computation on the right. The two sections
        # write in source order and remain visible until a whole-board wipe.
        matrix_step=(matrix.for_event(scene.event_id)
                     if matrix is not None else None)
        knowledge_id=(computation.knowledge_for_event(scene.event_id)
                      if computation is not None else None)
        paired=(knowledge_id is not None and cue["phase"]=="knowledge"
                and newids and newids[0]==knowledge_id)
        if knowledge_id is not None and not paired:
            raise LongboardError(
                "COMPUTATION_KNOWLEDGE_LAYOUT_MISMATCH: "+scene.event_id
            )
        note_needed=cue["phase"] in BOARD_GUIDANCE_PHASES
        note_width=KNOWLEDGE_WIDTH if paired else BOARD_WIDTH
        lines=_note_lines(cue["detail"],note_width) if note_needed else []
        noteheight=(NOTE_HEIGHT + len(lines)*NOTE_DETAIL_LINE_HEIGHT+5
                    if note_needed else 0)
        def group_at(start_y):
            additions=[]
            y=start_y
            if note_needed:
                additions.append({
                    "kind":"teacher_note","block_id":"note:"+scene.event_id,
                    "event_id":scene.event_id,
                    "phase":cue["phase"],
                    "heading":PHASE_NAMES[cue["phase"]]+"："+cue["heading"],
                    "detail":cue["detail"],"lines":lines,
                    "source_step_ids":list(cue["source_step_ids"]),
                    "x":BOARD_X,"y":y,"w":note_width,"h":noteheight,
                })
                y+=noteheight+5
            if matrix_step is not None:
                # Atomic classroom unit: source before -> named row operation
                # -> independently verified after state. Keep every old row.
                ids=[
                    matrix_step.before_id,matrix_step.operation_id,
                    matrix_step.after_id
                ]
                if newids!=ids:
                    raise LongboardError("MATRIX_SCENE_OBJECT_ORDER: "+scene.event_id)
                items=[
                    _math_placement(mid,sources,selected,size_of,size_cache,0)
                    for mid in ids
                ]
                spacing=24
                total=sum(item["w"] for item in items)+2*spacing
                if total<=BOARD_WIDTH:
                    x=BOARD_CENTER_X-total/2
                    tallest=max(item["h"] for item in items)
                    for mid,item in zip(ids,items):
                        dy=y+(tallest-item["h"])/2
                        _translate_block(item,dx=x-BOARD_X,dy=dy)
                        additions.append({"kind":"math","block_id":mid,**item})
                        x+=item["w"]+spacing
                    return additions,y+tallest+BOARD_ROW_GAP
                # Oversized matrices: before+op above, after below. Never
                # shrink indefinitely or erase a required intermediate state.
                top_width=items[0]["w"]+spacing+items[1]["w"]
                if max(top_width,items[2]["w"])>BOARD_WIDTH:
                    raise LongboardError("MATRIX_COMPARE_CANNOT_FIT")
                x=BOARD_CENTER_X-top_width/2
                h=max(items[0]["h"],items[1]["h"])
                for mid,item in zip(ids[:2],items[:2]):
                    _translate_block(item,dx=x-BOARD_X,
                                     dy=y+(h-item["h"])/2)
                    additions.append({"kind":"math","block_id":mid,**item})
                    x+=item["w"]+spacing
                after=items[2]
                _translate_block(after,dx=BOARD_CENTER_X-after["w"]/2-BOARD_X,
                                 dy=y+h+BOARD_ROW_GAP)
                additions.append({"kind":"math","block_id":ids[2],**after})
                return additions,y+h+BOARD_ROW_GAP+after["h"]+BOARD_ROW_GAP
            if paired:
                item=_math_placement(knowledge_id,sources,selected,
                                     size_of,size_cache,y,
                                     x=BOARD_X,width=KNOWLEDGE_WIDTH)
                additions.append({"kind":"math","block_id":knowledge_id,**item})
                left_bottom=y+item["h"]+BOARD_ROW_GAP
                work_x=BOARD_X+KNOWLEDGE_WIDTH+KNOWLEDGE_GUTTER
                work_width=BOARD_WIDTH-KNOWLEDGE_WIDTH-KNOWLEDGE_GUTTER
                work_y=start_y
                for mid in newids[1:]:
                    item=_math_placement(mid,sources,selected,
                                         size_of,size_cache,work_y,
                                         x=work_x,width=work_width)
                    additions.append({"kind":"math","block_id":mid,**item})
                    work_y+=item["h"]+BOARD_ROW_GAP
                return additions,max(left_bottom,work_y)
            for mid in newids:
                item=_math_placement(mid,sources,selected,size_of,size_cache,y)
                additions.append({"kind":"math","block_id":mid,**item})
                y+=item["h"]+BOARD_ROW_GAP
            if note_needed and not newids:
                y+=BOARD_ROW_GAP
            return additions,y
        proposed,next_y=group_at(cursor)
        _center_new_group(proposed)
        clear=False
        if next_y>BOARD_BOTTOM_Y:
            if not active:
                raise LongboardError(
                    f"CHALKBOARD_EVENT_TOO_TALL: {scene.event_id}"
                )
            if (computation is not None and last_event_id is not None
                    and not computation.is_safe_page_boundary(
                        last_event_id,scene.event_id)):
                raise LongboardError(
                    "COMPUTATION_NO_SAFE_BREAK: "+
                    last_event_id+" -> "+scene.event_id
                )
            clear=True
            page+=1
            cursor=page_start_y
            # Carry only explicit, already-computed mathematical results.
            # Copying results follows a real classroom's new page and never
            # implies calculating them before the original teacher event.
            carryids=(
                computation.carry_at(scene.event_id,written)
                if computation is not None
                else [mid for mid in selected.result_ids if mid in written]
            )
            carried=[]
            for mid in carryids:
                item=_math_placement(mid,sources,selected,size_of,size_cache,cursor)
                carried.append({"kind":"math","block_id":mid,"carry":True,**item})
                cursor+=item["h"]+BOARD_ROW_GAP
            _center_new_group(carried)
            proposed,next_y=group_at(cursor)
            _center_new_group(proposed)
            if next_y>BOARD_BOTTOM_Y:
                if computation is not None:
                    raise LongboardError(
                        "COMPUTATION_MANDATORY_CARRY_OVERFLOW: "+
                        scene.event_id
                    )
                # Legacy classroom mode: optional carry may be skipped.
                carried=[]
                cursor=page_start_y
                proposed,next_y=group_at(cursor)
                _center_new_group(proposed)
            if next_y>BOARD_BOTTOM_Y:
                raise LongboardError(
                    f"CHALKBOARD_EVENT_TOO_TALL: {scene.event_id}"
                )
            active=[]
            proposed=carried+proposed
        added=[]
        for item in proposed:
            # A carried result begins a fresh page, so no duplicate ID there.
            for old in active:
                if overlaps(item,old,margin=0):
                    raise LongboardError(
                        f"CHALKBOARD_INK_COLLISION: {scene.event_id}/"
                        f"{item['block_id']}/{old['block_id']}"
                    )
            if item["x"] < BOARD_X-0.01 or item["x"]+_ink_width(item)>BOARD_X+BOARD_WIDTH+1:
                raise LongboardError(
                    f"CHALKBOARD_HORIZONTAL_OVERFLOW: {scene.event_id}"
                )
            if item["y"]<page_start_y or item["y"]+item["h"]>BOARD_BOTTOM_Y:
                raise LongboardError(
                    f"CHALKBOARD_VERTICAL_OVERFLOW: {scene.event_id}"
                )
            if item["kind"]=="math" and not item.get("carry"):
                written.add(item["block_id"])
                all_math.add(item["block_id"])
            active.append(item)
            added.append(item)
        cursor=next_y
        events.append({
            "event_id":scene.event_id,"page_index":page,
            **(computation.event_info(scene.event_id)
               if computation is not None else {}),
            **(matrix.info(scene.event_id)
               if matrix is not None else {}),
            "carry_object_ids":(
                [a["block_id"] for a in added if a.get("carry")]
                if computation is not None else []
            ),
            "erase_before":clear,
            # One event is a teacher's coherent mathematical reasoning unit;
            # it may contain several MathTex Write operations. Page erasure
            # can occur before the entire unit but NEVER between its steps.
            "math_write_count":len(newids),
            "unit_source_step_ids":list(cue["source_step_ids"]),
            "unit_heading":cue["heading"],
            "erase_reason":("whole_reasoning_unit_cannot_fit"
                            if clear else None),
            "added_blocks":added,
            "visible_block_ids":[a["block_id"] for a in active],
            "pause_seconds":cue["pause_seconds"],
            "write_seconds":cue["write_seconds"],
        })
        last_event_id=scene.event_id
    # Every requested write event must have survived the planning pass.
    expected={a.object_id for sc in execution_plan.scenes for a in sc.actions
              if a.kind in ("progressive_write","restore")
              and a.object_id in sources and a.to_region!="question"}
    if all_math != expected:
        raise LongboardError("CHALKBOARD_MATH_EVENT_LOST")
    centering=_center_page_heights(
        events, page_start_y=page_start_y, header_bottom_y=header_bottom_y
    )
    return {
        "schema_version":"1.0","mode":"persistent_chalkboard",
        "source_storyboard_sha256":execution_plan.source_storyboard_sha256,
        "page_count":page,"event_count":len(events),
        "math_written_ids":sorted(all_math),
        "coordinates":{"start_y":page_start_y,"bottom_y":BOARD_BOTTOM_Y,
                       "board_left":BOARD_X,"board_width":BOARD_WIDTH},
        "alignment":{"mode":"each_unit_centered_with_header_near_top",
                     "center_x":BOARD_CENTER_X,
                     "preferred_vertical_center_y":BOARD_CENTER_Y,
                     "header_bottom_y":header_bottom_y,
                     "max_first_ink_y":page_start_y+MAX_PAGE_TOP_OFFSET_PX,
                     "pages":centering},
        "events":events,
        **({"computation_groups":computation.as_manifest()}
           if computation is not None else {}),
        **({"matrix_operations":{
            "kind":matrix.kind,
            "initial_event_id":matrix.initial_event_id,
            "operation_count":len(matrix.steps),
            "ordered_event_ids":[a.event_id for a in matrix.steps],
            "source_verified":True,
            "arithmetically_verified":True,
            "presentation":"before_operation_after_atomic"
        }} if matrix is not None else {}),
    }


def _note_png(block,output):
    from PIL import Image, ImageDraw
    from .classroom_compositor import _font
    canvas=Image.new("RGBA",(1280,720),(255,255,255,0))
    draw=ImageDraw.Draw(canvas)
    x,y=block["x"],block["y"]
    style=BOARD_TEXT_STYLE[block["phase"]]
    heading=block["heading"]
    header_font=_font(style["font_px"])
    detail_font=_font(BOARD_DETAIL_FONT_PX)
    hbox=draw.textbbox((x,y),heading,font=header_font)
    if hbox[2]>x+block["w"] or hbox[3]>y+NOTE_HEIGHT:
        raise LongboardError("CHALKBOARD_NOTE_HEADER_OVERFLOW")
    draw.text((x,y),heading,font=header_font,fill=style["heading"])
    for idx,line in enumerate(block["lines"]):
        line_y=y+NOTE_HEIGHT+idx*NOTE_DETAIL_LINE_HEIGHT
        box=draw.textbbox((x,line_y),line,font=detail_font)
        if box[2]>x+block["w"] or box[3]>y+block["h"]:
            raise LongboardError("CHALKBOARD_NOTE_BODY_OVERFLOW")
        draw.text((x,line_y),line,font=detail_font,fill=BOARD_DERIVATION_INK)
    canvas.save(output)


def render_persistent_chalkboard(storyboard,execution,cues,policy, *,
                                 output_mp4:Path,output_json:Path,fps:int=30,
                                 computation_manifest=None,matrix_manifest=None):
    """Real uninterrupted-ink Manim video; erase only on board-full cut."""
    if not isinstance(fps,int) or not 8<=fps<=60:
        raise LongboardError("CHALKBOARD_INVALID_FPS")
    output_mp4,output_json=Path(output_mp4),Path(output_json)
    if output_mp4.suffix!=".mp4" or output_json.suffix!=".json":
        raise LongboardError("CHALKBOARD_OUTPUT_EXTENSION")
    if not shutil.which("ffmpeg"):
        raise LongboardError("CHALKBOARD_FFMPEG_UNAVAILABLE")
    board,contract,teaching,selected,matrix=_strict_sources(
        storyboard,execution,cues,policy,matrix_manifest=matrix_manifest
    )
    layout=make_chalkboard_plan(
        board,contract,cues,selected,
        computation_manifest=computation_manifest,
        matrix_manifest=matrix_manifest
    )
    from manim import (Scene,MathTex,VGroup,Write,FadeIn,Rectangle,WHITE,
                       tempconfig,linear)
    fw=8*1280/720
    fh=8.
    def place(rect):
        return [((rect["x"]+rect["w"]/2)/1280-.5)*fw,
                (.5-(rect["y"]+rect["h"]/2)/720)*fh,0]
    def build_math(block):
        pieces=[]
        for f in block["fragments"]:
            glyph=MathTex(f["latex"],color=BOARD_DERIVATION_INK)
            glyph.scale(block["scale"])
            glyph.move_to(place(f))
            if (abs(glyph.width*90-f["w"])>2 or
                    abs(glyph.height*90-f["h"])>2):
                raise LongboardError("CHALKBOARD_TRUE_SIZE_MISMATCH")
            pieces.append(glyph)
        return VGroup(*pieces)
    with tempfile.TemporaryDirectory(prefix="classroom-chalkboard-") as directory:
        temp=Path(directory)
        header=make_question_overlay(board,temp/"header.png",
                    compact=True,ink_color=BOARD_DERIVATION_INK)
        for row in layout["events"]:
            for block in row["added_blocks"]:
                if block["kind"]=="teacher_note":
                    _note_png(block,temp/(block["block_id"].replace(":","_")+".png"))
        with tempconfig({
            "pixel_width":1280,"pixel_height":720,
            "frame_width":fw,"frame_height":fh,"frame_rate":fps,
            "background_color":board.theme.background,
            "renderer":"cairo","format":"mp4","media_dir":str(temp),
            "output_file":"chalkboard.mp4","disable_caching":True,
            "preview":False,
        }):
            class ChalkboardScene(Scene):
                def construct(self):
                    active={}
                    self.timing=[]
                    for row in layout["events"]:
                        start=self.time
                        if row["erase_before"]:
                            # A classroom-style horizontal eraser sweep.
                            # No partial-content fade/move during lecture.
                            eraser=Rectangle(
                                width=fw+.2,height=fh*.81,
                                fill_color=WHITE,fill_opacity=1,
                                stroke_opacity=0
                            )
                            eraser.move_to([-fw, -.45, 0])
                            self.add(eraser)
                            self.play(eraser.animate.move_to([0,-.45,0]),
                                      run_time=.75,rate_func=linear)
                            for obj in active.values():
                                self.remove(obj)
                            active.clear()
                            self.remove(eraser)
                        for block in row["added_blocks"]:
                            ident=block["block_id"]
                            if ident in active:
                                raise LongboardError("CHALKBOARD_DUPLICATE_LIVE_OBJECT")
                            if block["kind"]=="teacher_note":
                                from manim import ImageMobject
                                obj=ImageMobject(str(temp/(ident.replace(":","_")+".png")))
                                obj.scale_to_fit_width(fw).move_to([0,0,0])
                                self.play(FadeIn(obj),run_time=.32)
                            else:
                                obj=build_math(block)
                                for frag in obj:
                                    self.play(Write(frag),run_time=row["write_seconds"])
                                self.remove(*obj.submobjects)
                                self.add(obj)
                            active[ident]=obj
                        # Printed ink is persistent until a real page erase.
                        if row["visible_block_ids"] != list(active.keys()):
                            raise LongboardError(
                                f"CHALKBOARD_VISIBLE_SET_MISMATCH: {row['event_id']}"
                            )
                        self.wait(row["pause_seconds"])
                        self.timing.append({
                            "event_id":row["event_id"],"page_index":row["page_index"],
                            "erase_before":row["erase_before"],
                            "math_write_count":row["math_write_count"],
                            "unit_heading":row["unit_heading"],
                            "erase_reason":row["erase_reason"],
                            "start_preview_second":start,
                            "end_preview_second":self.time,
                            "visible_block_ids":list(active),
                        })
                    self.total=self.time
            scene=ChalkboardScene()
            scene.render()
            raw=Path(scene.renderer.file_writer.movie_file_path)
            if not raw.is_file() or raw.stat().st_size<1000:
                raise LongboardError("CHALKBOARD_RENDER_FAILURE")
            rendered=temp/"chalkboard_no_header.mp4"
            shutil.copyfile(raw,rendered)
        combined=temp/"result.mp4"
        proc=subprocess.run([
            "ffmpeg","-hide_banner","-loglevel","error","-y",
            "-i",str(rendered),"-loop","1","-i",str(temp/"header.png"),
            "-filter_complex","[0:v][1:v]overlay=0:0:shortest=1:eof_action=repeat[v]",
            "-map","[v]","-c:v","libx264","-pix_fmt","yuv420p",
            "-r",str(fps),"-an","-movflags","+faststart",str(combined)
        ],capture_output=True,text=True)
        if proc.returncode or not combined.is_file():
            raise LongboardError("CHALKBOARD_COMPOSE_FAILED: "+proc.stderr[-450:])
        manifest={
            **layout,"header":header,
            "fps":fps,"video":"true_manim_persistent_chalkboard",
            "actual_preview_duration":scene.total,
            "event_timing":scene.timing,
            "erase_count":sum(x["erase_before"] for x in layout["events"]),
            "in_page_reposition_count":0,
            "in_page_fadeout_count":0,
            "voice_status":"not_recorded","subtitle_status":"not_audio_aligned",
            "color_scheme":{"math":"#111111",
                            **{k:v["heading"] for k,v in BOARD_TEXT_STYLE.items()}},
        }
        output_mp4.parent.mkdir(parents=True,exist_ok=True)
        output_json.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(combined,output_mp4)
        output_json.write_text(
            json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",
            encoding="utf-8"
        )
        return manifest
