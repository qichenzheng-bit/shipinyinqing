"""Append-only classroom chalkboard: write, preserve, clear only on full board.

The original approved mathematical source is immutable. Every event adds either
an approved CJK teaching note and/or exact MathTex. No previously written ink
moves, fades, scrolls or silently disappears between ordinary teacher events.
A full board is erased in one visible sweep at an event boundary. A completed
result may then be explicitly REWRITTEN from the verified original source.
"""
from __future__ import annotations

from .video_settings import DEFAULT_VIDEO_FPS

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
NOTE_HEIGHT = 32
NOTE_DETAIL_LINE_HEIGHT = 27
BOARD_CENTER_X = BOARD_X + BOARD_WIDTH / 2
BOARD_CENTER_Y = (BOARD_START_Y + BOARD_BOTTOM_Y) / 2
QUESTION_TO_BOARD_MIN_GAP_PX = 22
MAX_PAGE_TOP_OFFSET_PX = 20

# V2.5.3: actual MathTex glyph widths, not the source string length, decide
# if a formula can share a horizontal teaching row. The rules apply to proof
# mode only; approved integral and matrix arrangements are unchanged.
PROOF_ROW_GUTTER = 36
PROOF_INLINE_MAX_FORMULA_WIDTH = 440
PROOF_INLINE_ROW_WIDTH = 940
PROOF_INLINE_MAX_ITEMS = 3
PROOF_STAGE_GUTTER = 68
PROOF_STAGE_MAX_WIDTH = 500
PROOF_PAIRED_ROW_WIDTH = 950

# Proof-only page two/three recap. Group the short givens and goal into
# a single, centered first row and visibly separate previously established
# results from the newly written derivation.
PROOF_CARRY_PAIR_GUTTER = 42
PROOF_CARRY_ROW_GAP = 26
PROOF_CARRY_TO_DERIVATION_GAP = 32

# V2.5.4 diagram lessons intentionally use two distinct mathematical areas.
# MathTex sits in the LEFT teaching area, the verified Manim diagram on the
# RIGHT; never center formulas over the diagram's actual strokes or labels.
DIAGRAM_LEFT_X = 110
DIAGRAM_LEFT_WIDTH = 485
DIAGRAM_MATH_CENTER_X = DIAGRAM_LEFT_X + DIAGRAM_LEFT_WIDTH/2


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
                         header_bottom_y: int,
                         proof_math_only: bool = False) -> list[dict]:
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
        # Left-hand guidance is not mathematical ink: its left edge
        # must not distort the independent center of the formula rows.
        horizontal = ([b for b in blocks if b["kind"] == "math"]
                      if proof_math_only else blocks)
        if not horizontal:
            horizontal = blocks
        left = min(block["x"] for block in horizontal)
        right = max(block["x"] + _ink_width(block) for block in horizontal)
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


def _strict_sources(storyboard, execution, cues, policy, matrix_manifest=None,
                    proof_manifest=None, diagram_manifest=None):
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
    proof=None
    diagram=None
    if matrix_manifest is not None:
        from .matrix_steps import checked_matrix_steps
        matrix=checked_matrix_steps(matrix_manifest, board, plan)
    if proof_manifest is not None:
        from .proof_chain import checked_proof_chain
        proof=checked_proof_chain(proof_manifest, board, plan)
    if diagram_manifest is not None:
        from .diagram_classroom import checked_diagram_classroom
        diagram=checked_diagram_classroom(diagram_manifest, board, plan)
    unsupported=[
        scene.event_id for scene in board.scenes
        if (scene.diagram is not None and diagram is None)
        or (scene.layout=="diagram_split" and diagram is None)
        or (scene.layout=="proof_scroll" and proof is None)
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
    return board,plan,teaching,selected,matrix,proof,diagram


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


def _proof_math_rows(ids, sources, selected, measure, size_cache, y):
    """Pack genuinely short consecutive formulae; preserve source read order.

    Short mathematics reads left-to-right, then top-to-bottom. A long formula
    starts its own row; a too-wide expression is never shrunk to force a row.
    Every placement still uses the real MathTex sizing contract.
    """
    items=[
        _math_placement(mid,sources,selected,measure,size_cache,0)
        for mid in ids
    ]
    rows=[]
    current=[]
    for mid,item in zip(ids,items):
        width=sum(b["w"] for _,b in current)
        gap=PROOF_ROW_GUTTER*len(current)
        fits=(item["w"]<=PROOF_INLINE_MAX_FORMULA_WIDTH
              and all(b["w"]<=PROOF_INLINE_MAX_FORMULA_WIDTH
                      for _,b in current)
              and len(current)<PROOF_INLINE_MAX_ITEMS
              and width+gap+item["w"]<=PROOF_INLINE_ROW_WIDTH)
        if current and not fits:
            rows.append(current)
            current=[]
        current.append((mid,item))
    if current:
        rows.append(current)
    placed=[]
    positions=[]
    for row in rows:
        total=sum(item["w"] for _,item in row)+PROOF_ROW_GUTTER*(len(row)-1)
        x=BOARD_CENTER_X-total/2
        h=max(item["h"] for _,item in row)
        row_ids=[]
        for mid,item in row:
            _translate_block(item,dx=x-BOARD_X,dy=y+(h-item["h"])/2)
            placed.append({"kind":"math","block_id":mid,**item})
            row_ids.append(mid)
            x+=item["w"]+PROOF_ROW_GUTTER
        positions.append(row_ids)
        y+=h+BOARD_ROW_GAP
    return placed,y,positions


def _proof_stage_pair(first,second,sources,selected,measure,size_cache,y):
    """Two short chronological proof stages in stable left and right columns.

    Treat each stage as one semantic tile (up to two source formulae).
    Its own formulas stay vertical if necessary. The next event writes into
    its RESERVED right-hand tile; nothing already shown is repositioned.
    """
    first_ids,second_ids=first,second
    if not (1<=len(first_ids)<=2 and 1<=len(second_ids)<=2):
        return None
    placements=[]
    for ids in (first_ids,second_ids):
        items=[_math_placement(mid,sources,selected,measure,size_cache,0)
               for mid in ids]
        if any(item["w"]>PROOF_STAGE_MAX_WIDTH for item in items):
            return None
        placements.append(items)
    widths=[max(item["w"] for item in tile) for tile in placements]
    heights=[sum(item["h"] for item in tile)
             +BOARD_ROW_GAP*(len(tile)-1) for tile in placements]
    total=sum(widths)+PROOF_STAGE_GUTTER
    if total>PROOF_PAIRED_ROW_WIDTH:
        return None
    if y+max(heights)+BOARD_ROW_GAP>BOARD_BOTTOM_Y:
        return None
    x=BOARD_CENTER_X-total/2
    two=[]
    for ids,items,tile_width in zip(
            (first_ids,second_ids),placements,widths):
        col=[]
        line_y=y
        for mid,item in zip(ids,items):
            _translate_block(item,dx=x+(tile_width-item["w"])/2-BOARD_X,
                             dy=line_y)
            col.append({"kind":"math","block_id":mid,**item})
            line_y+=item["h"]+BOARD_ROW_GAP
        two.append(col)
        x+=tile_width+PROOF_STAGE_GUTTER
    return two,y+max(heights)+BOARD_ROW_GAP


def _proof_carry_layout(carryids, proof, sources, selected, measure,
                        size_cache, start_y):
    """Carry exact reviewed facts into a new page with readable breathing room.

    Conditions and the proof goal are a single 'context' row when their REAL
    glyph widths fit. Prior proved lemmas/results appear below it, each
    centered on its own row. The next active derivation starts after a
    deliberate larger gap. No source content is omitted or moved after Write.
    """
    pairs=[
        (mid,_math_placement(mid,sources,selected,measure,size_cache,0))
        for mid in carryids
    ]
    rows=[]
    if (len(pairs)>=2 and pairs[0][0]==proof.condition_id
            and pairs[1][0]==proof.goal_id
            and pairs[0][1]["w"]+pairs[1][1]["w"]
                +PROOF_CARRY_PAIR_GUTTER<=PROOF_INLINE_ROW_WIDTH):
        rows.append(pairs[:2])
        pairs=pairs[2:]
    rows.extend([item] for item in pairs)
    carried=[]
    row_ids=[]
    y=start_y
    for row_index,row in enumerate(rows):
        if row_index:
            y+=PROOF_CARRY_ROW_GAP
        height=max(item["h"] for _,item in row)
        width=sum(item["w"] for _,item in row)
        width+=PROOF_CARRY_PAIR_GUTTER*(len(row)-1)
        x=BOARD_CENTER_X-width/2
        this_ids=[]
        for mid,item in row:
            _translate_block(item,dx=x-BOARD_X,dy=y+(height-item["h"])/2)
            carried.append({
                "kind":"math","block_id":mid,"carry":True,**item,
            })
            this_ids.append(mid)
            x+=item["w"]+PROOF_CARRY_PAIR_GUTTER
        row_ids.append(this_ids)
        y+=height
    return carried,y+PROOF_CARRY_TO_DERIVATION_GAP,row_ids


def make_chalkboard_plan(storyboard,execution,cues,policy, *,
                         measure=None, computation_manifest=None,
                         matrix_manifest=None, proof_manifest=None,
                         diagram_manifest=None, layout_hint=None) -> dict:
    if layout_hint not in (None, "diagram_left", "preserve_diagram") or (
            layout_hint == "diagram_left" and any(x is not None for x in (
                computation_manifest, matrix_manifest, proof_manifest, diagram_manifest))) or (
            layout_hint == "preserve_diagram" and diagram_manifest is None):
        raise LongboardError("CHALKBOARD_UNSUPPORTED_ADAPTIVE_COLUMN")
    if sum(x is not None for x in (
            computation_manifest,matrix_manifest,proof_manifest,
            diagram_manifest))>1:
        raise LongboardError("CHALKBOARD_MULTIPLE_SPECIAL_CONTRACTS")
    board,execution_plan,teaching,selected,matrix,proof,diagram=_strict_sources(
        storyboard,execution,cues,policy,matrix_manifest=matrix_manifest,
        proof_manifest=proof_manifest,diagram_manifest=diagram_manifest
    )
    diagram_column=(diagram is not None or layout_hint == "diagram_left")
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
    opening_readout_ids=set()
    pending_proof_row=None
    shown_diagram=[]
    sequence=list(zip(board.scenes,execution_plan.scenes,teaching))
    for index,(scene,action_scene,cue) in enumerate(sequence):
        newids=list(dict.fromkeys(
            a.object_id for a in action_scene.actions
            if a.kind in ("progressive_write","restore")
            and a.object_id in sources and a.to_region!="question"
        ))
        if any(mid in written for mid in newids):
            raise LongboardError(
                f"CHALKBOARD_DUPLICATE_MATH_WRITE: {scene.event_id}"
            )
        # Reading a question already visible in the fixed header is an
        # AUDIO action, not a second new MathTex write. The source object,
        # exact pronunciation and subtitle stay in the verified script.
        # Opt-in is based on the teacher-authored heading and exact source,
        # never on a guessed substring or arbitrary early equation.
        opening_readout = (
            index == 0 and cue["phase"] == "observe"
            and cue["heading"] in {"完整读题", "读题", "题目朗读"}
            and bool(newids) and all(
                sources[mid]["latex"] in board.header.text for mid in newids
            )
        )
        speech_only_actions = []
        if opening_readout:
            opening_readout_ids.update(newids)
            speech_only_actions = [
                {"kind": "note", "object_id": "note:"+scene.event_id},
            ] + [{"kind": "math", "object_id":mid} for mid in newids]
            newids = []
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
        # Summary is a compact visual review. Only refer to *already shown*
        # knowledge and risk notes, never fabricate a new result or reread
        # the full explanation. Keep the actual answer in the conclusion.
        recap_references=[]
        if cue["phase"] == "summary":
            prior_knowledge=[]
            prior_pitfalls=[]
            for earlier_index,earlier in enumerate(events):
                older_cue=sequence[earlier_index][2]
                if older_cue["phase"] not in ("knowledge","pitfall"):
                    continue
                older_note=next(
                    (b for b in earlier["added_blocks"]
                     if b["kind"]=="teacher_note" and not b.get("carry")),None
                )
                older_math=[
                    b["block_id"] for b in earlier["added_blocks"]
                    if b["kind"]=="math" and not b.get("carry")
                    and b["block_id"] in written
                ]
                if older_cue["phase"]=="knowledge" and older_math:
                    prior_knowledge.append((older_cue,older_note,older_math))
                elif older_cue["phase"]=="pitfall" and older_note:
                    prior_pitfalls.append((older_cue,older_note,[]))
            # At most the latest 2 core facts and 2 genuine pitfalls;
            # adapt if a lesson has no such events. No answer is carried.
            recap_references=(
                [("knowledge",*item) for item in prior_knowledge[-2:]]
                + [("pitfall",*item) for item in prior_pitfalls[-2:]]
            )
        note_needed=(cue["phase"] in BOARD_GUIDANCE_PHASES
                     and cue["phase"] != "conclusion"
                     and not opening_readout)
        note_width=(DIAGRAM_LEFT_WIDTH if diagram_column else
                    KNOWLEDGE_WIDTH if paired else BOARD_WIDTH)
        lines=_note_lines(cue["detail"],note_width) if note_needed else []
        if cue["phase"]=="summary" and recap_references:
            # The teacher comments briefly; the reviewed source objects
            # below carry the educational substance without long text.
            lines=[]
        noteheight=(NOTE_HEIGHT + len(lines)*NOTE_DETAIL_LINE_HEIGHT+5
                    if note_needed else 0)
        proof_formula_rows=[]
        def center_new_content(blocks):
            if diagram_column:
                # The left MathTex column was measured and centered
                # individually; never recenter notes and math together.
                return
            if proof is not None and note_needed:
                # MathTex rows are individually centered by _proof_math_rows.
                # Centering the note AND formulas together previously shifted
                # each mathematical formula to the right.
                return
            _center_new_group(blocks)
        def group_at(start_y):
            additions=[]
            y=start_y
            if note_needed:
                additions.append({
                    "kind":"teacher_note","block_id":"note:"+scene.event_id,
                    "event_id":scene.event_id,
                    "phase":cue["phase"],
                    "heading":(
                        PHASE_NAMES["summary"] if cue["phase"]=="summary"
                        else PHASE_NAMES[cue["phase"]]+"："+cue["heading"]
                    ),
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
            if proof is not None and newids:
                formulae,y,rows=_proof_math_rows(
                    newids,sources,selected,size_of,size_cache,y
                )
                proof_formula_rows[:]=rows
                additions.extend(formulae)
            else:
                for mid in newids:
                    if diagram_column:
                        item=_math_placement(
                            mid,sources,selected,size_of,size_cache,y,
                            x=DIAGRAM_LEFT_X,width=DIAGRAM_LEFT_WIDTH
                        )
                        # Explicit left math column; the source formula
                        # remains unmodified and retains its true glyph size.
                        _translate_block(
                            item,dx=(DIAGRAM_LEFT_WIDTH-item["w"])/2
                        )
                    else:
                        item=_math_placement(
                            mid,sources,selected,size_of,size_cache,y
                        )
                    additions.append({"kind":"math","block_id":mid,**item})
                    y+=item["h"]+BOARD_ROW_GAP
            if cue["phase"]=="summary" and recap_references:
                for phase,source_cue,source_note,source_math in recap_references:
                    caption=(
                        "核心知识："+source_cue["heading"]
                        if phase=="knowledge"
                        else "易错点："+source_cue["heading"]
                    )
                    detail=source_cue["detail"] if phase=="pitfall" else ""
                    recap_lines=_note_lines(detail) if detail else []
                    recap_h=NOTE_HEIGHT+len(recap_lines)*NOTE_DETAIL_LINE_HEIGHT+5
                    additions.append({
                        "kind":"teacher_note",
                        "block_id":"recap:note:"+source_cue["event_id"],
                        "event_id":scene.event_id,
                        "phase":phase,
                        "heading":caption,"detail":detail,"lines":recap_lines,
                        "source_step_ids":list(source_cue["source_step_ids"]),
                        "source_block_id":source_note["block_id"] if source_note else None,
                        "carry":True,"recap_review":True,
                        "x":BOARD_X,"y":y,"w":BOARD_WIDTH,"h":recap_h,
                    })
                    y+=recap_h+BOARD_ROW_GAP
                    for mid in source_math:
                        item=_math_placement(
                            mid,sources,selected,size_of,size_cache,y
                        )
                        additions.append({
                            "kind":"math","block_id":mid,"carry":True,
                            "recap_review":True,"source_object_id":mid,**item,
                        })
                        y+=item["h"]+BOARD_ROW_GAP
            if note_needed and not newids and not recap_references:
                y+=BOARD_ROW_GAP
            return additions,y
        proof_layout_mode="stacked"
        proof_row_group_id=None
        planned_pair=None
        if pending_proof_row is not None:
            if pending_proof_row["second_event"]!=scene.event_id:
                raise LongboardError("PROOF_PAIR_EVENT_ORDER")
            # The left tile is already on screen and must NEVER move.
            proposed=pending_proof_row["blocks"]
            next_y=pending_proof_row["next_y"]
            proof_layout_mode="paired_right"
            proof_row_group_id=pending_proof_row["group_id"]
            proof_formula_rows[:]=[[mid] for mid in newids]
            pending_proof_row=None
        else:
            proposed,next_y=group_at(cursor)
            center_new_content(proposed)
            if proof is not None:
                if any(len(row)>1 for row in proof_formula_rows):
                    proof_layout_mode="compact_within_stage"
                # Only consecutive plain derivations / small lemmas qualify
                # for cross-event pairing. Never combine case distinctions,
                # title/knowledge notes, the final answer, or geometry.
                if (not note_needed and index+1<len(sequence)
                        and proof.for_event(scene.event_id).role
                        in ("derivation","lemma")):
                    next_scene,next_actions,next_cue=sequence[index+1]
                    next_stage=proof.for_event(next_scene.event_id)
                    next_ids=list(dict.fromkeys(
                        a.object_id for a in next_actions.actions
                        if a.kind in ("progressive_write","restore")
                        and a.object_id in sources and a.to_region!="question"
                    ))
                    if (next_stage.role in ("derivation","lemma")
                            and next_cue["phase"] not in BOARD_GUIDANCE_PHASES):
                        pair=_proof_stage_pair(
                            newids,next_ids,sources,selected,size_of,
                            size_cache,cursor
                        )
                        if pair is not None:
                            tiles,finish_y=pair
                            proposed=tiles[0]
                            next_y=cursor  # reserve the same board row
                            proof_layout_mode="paired_left"
                            proof_row_group_id="proof-row:"+scene.event_id
                            proof_formula_rows[:]=[[mid] for mid in newids]
                            planned_pair={
                                "second_event":next_scene.event_id,
                                "blocks":tiles[1],"next_y":finish_y,
                                "group_id":proof_row_group_id,
                            }
        clear=False
        carry_rows=[]
        diagram_carry_ids=[]
        if next_y>BOARD_BOTTOM_Y or (
                cue["phase"]=="summary" and bool(active)
            ):
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
            if (proof is not None and last_event_id is not None
                    and not proof.is_safe_page_boundary(last_event_id)):
                raise LongboardError(
                    "PROOF_NO_SAFE_BREAK: "+last_event_id+" -> "+scene.event_id
                )
            clear=True
            page+=1
            cursor=page_start_y
            # Carry only explicit, already-computed mathematical results.
            # Copying results follows a real classroom's new page and never
            # implies calculating them before the original teacher event.
            carryids=(
                [] if cue["phase"]=="summary" else
                proof.carry_at(scene.event_id,written)
                if proof is not None
                else computation.carry_at(scene.event_id,written)
                if computation is not None
                else [mid for mid in selected.result_ids if mid in written]
            )
            carried=[]
            carry_rows=[]
            if proof is not None and carryids:
                carried,cursor,carry_rows=_proof_carry_layout(
                    carryids,proof,sources,selected,size_of,size_cache,cursor
                )
            else:
                for mid in carryids:
                    if diagram_column:
                        item=_math_placement(
                            mid,sources,selected,size_of,size_cache,cursor,
                            x=DIAGRAM_LEFT_X,width=DIAGRAM_LEFT_WIDTH
                        )
                        _translate_block(
                            item,dx=(DIAGRAM_LEFT_WIDTH-item["w"])/2
                        )
                    else:
                        item=_math_placement(
                            mid,sources,selected,size_of,size_cache,cursor
                        )
                    carried.append({
                        "kind":"math","block_id":mid,"carry":True,**item
                    })
                    cursor+=item["h"]+BOARD_ROW_GAP
                if not diagram_column:
                    _center_new_group(carried)
            proposed,next_y=group_at(cursor)
            center_new_content(proposed)
            if next_y>BOARD_BOTTOM_Y:
                if computation is not None or proof is not None:
                    raise LongboardError(
                        ("PROOF_MANDATORY_CONTEXT_OVERFLOW: " if proof is not None
                         else "COMPUTATION_MANDATORY_CARRY_OVERFLOW: ")+
                        scene.event_id
                    )
                # Optional historical result carry may be skipped.
                # Summary reviews are source-backed; never silently omit them.
                if cue["phase"]=="summary" and recap_references:
                    raise LongboardError("CHALKBOARD_RECAP_REVIEW_OVERFLOW")
                # Legacy classroom mode: optional carry may be skipped.
                carried=[]
                cursor=page_start_y
                proposed,next_y=group_at(cursor)
                center_new_content(proposed)
            if next_y>BOARD_BOTTOM_Y:
                raise LongboardError(
                    f"CHALKBOARD_EVENT_TOO_TALL: {scene.event_id}"
                )
            active=[]
            if diagram is not None:
                diagram_carry_ids=list(shown_diagram)
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
        if diagram is not None:
            for ident in diagram.for_event(scene.event_id)["reveal_ids"]:
                if ident in shown_diagram:
                    raise LongboardError("DIAGRAM_REVEAL_TWICE")
                shown_diagram.append(ident)
        if planned_pair is not None:
            if clear:
                raise LongboardError("PROOF_PAIR_MUST_NOT_CLEAR")
            pending_proof_row=planned_pair
        events.append({
            "event_id":scene.event_id,"page_index":page,
            **(computation.event_info(scene.event_id)
               if computation is not None else {}),
            **(matrix.info(scene.event_id)
               if matrix is not None else {}),
            **(proof.event_info(scene.event_id)
               if proof is not None else {}),
            "carry_object_ids":(
                [a["block_id"] for a in added if a.get("carry")]
                if (computation is not None or proof is not None
                    or diagram is not None or cue["phase"]=="summary") else []
            ),
            **({"proof_carry_rows":carry_rows} if proof is not None else {}),
            "erase_before":clear,
            **({"diagram_reveal_ids":list(diagram.for_event(
                scene.event_id)["reveal_ids"]),
                "diagram_carry_ids":diagram_carry_ids,
                "diagram_order":diagram.for_event(scene.event_id)["order"],
                "visible_diagram_ids":list(shown_diagram)}
               if diagram is not None else {}),
            # One event is a teacher's coherent mathematical reasoning unit;
            # it may contain several MathTex Write operations. Page erasure
            # can occur before the entire unit but NEVER between its steps.
            "math_write_count":len(newids),
            "unit_source_step_ids":list(cue["source_step_ids"]),
            "unit_heading":cue["heading"],
            **({"proof_layout":{
                "mode":proof_layout_mode,
                "row_group_id":proof_row_group_id,
                "formula_rows":proof_formula_rows,
                "source_order_preserved":True,
            }} if proof is not None else {}),
            "erase_reason":("whole_reasoning_unit_cannot_fit"
                            if clear else None),
            "added_blocks":added,
            "speech_only_actions":speech_only_actions,
            "visible_block_ids":[a["block_id"] for a in active],
            "pause_seconds":cue["pause_seconds"],
            "recap_review_source_ids":[
                b.get("source_object_id",b.get("source_block_id"))
                for b in added if b.get("recap_review")
            ],
            "write_seconds":cue["write_seconds"],
        })
        last_event_id=scene.event_id
    if pending_proof_row is not None:
        raise LongboardError("PROOF_UNFINISHED_HORIZONTAL_ROW")
    if diagram is not None and set(shown_diagram)!=set(diagram.objects):
        raise LongboardError("DIAGRAM_INCOMPLETE_DRAWING")
    # Every requested write event must have survived the planning pass.
    expected={a.object_id for sc in execution_plan.scenes for a in sc.actions
              if a.kind in ("progressive_write","restore")
              and a.object_id in sources and a.to_region!="question"}
    if all_math | opening_readout_ids != expected:
        raise LongboardError("CHALKBOARD_MATH_EVENT_LOST")
    centering=_center_page_heights(
        events, page_start_y=page_start_y, header_bottom_y=header_bottom_y,
        proof_math_only=proof is not None
    )
    return {
        "schema_version":"1.0","mode":"persistent_chalkboard",
        "source_storyboard_sha256":execution_plan.source_storyboard_sha256,
        "page_count":page,"event_count":len(events),
        "math_written_ids":sorted(all_math),
        "coordinates":{"start_y":page_start_y,"bottom_y":BOARD_BOTTOM_Y,
                       "board_left":BOARD_X,"board_width":BOARD_WIDTH},
        "alignment":{"mode":(
                         "diagram_left_math_right_geometry"
                         if diagram_column else
                         "each_unit_centered_with_header_near_top"),
                     "center_x":(
                         DIAGRAM_MATH_CENTER_X
                         if diagram_column else BOARD_CENTER_X),
                     "proof_math_independent_centered":proof is not None,
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
        **({"diagram_classroom":{
            **diagram.public_manifest(),
            "all_revealed":True,
            "source_objects":diagram.objects
        }} if diagram is not None else {}),
        **({"proof_chain":{
            **proof.as_manifest(),
            "layout_strategy":"adaptive_short_math_rows_and_paired_proof_stages",
            "paired_stage_groups":sum(
                e["proof_layout"]["mode"]=="paired_left" for e in events
            ),
            "compact_stage_count":sum(
                e["proof_layout"]["mode"]=="compact_within_stage"
                for e in events
            ),
        }} if proof is not None else {}),
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


def _event_entry_contract(layout: dict, index: int) -> dict:
    """Source-authoritative live board state before a teaching event.

    No video screenshot is used: every previous visible MathTex/teacher note
    is reconstructable from the immutable validated layout, while geometry
    retains the exact original object order and coordinate definitions.
    """
    events=layout["events"]
    if type(index) is not int or not 0<=index<len(events):
        raise LongboardError("CHALKBOARD_EVENT_WINDOW_INVALID")
    previous=events[index-1] if index else None
    blocks=list(previous["visible_block_ids"]) if previous else []
    diagrams=list(previous.get("visible_diagram_ids",[])) if previous else []
    catalog={
        block["block_id"]:block
        for row in events[:index] for block in row["added_blocks"]
    }
    if any(ident not in catalog for ident in blocks):
        raise LongboardError("CHALKBOARD_EVENT_MISSING_ENTRY_BLOCK")
    if len(blocks)!=len(set(blocks)) or len(diagrams)!=len(set(diagrams)):
        raise LongboardError("CHALKBOARD_EVENT_DUPLICATE_ENTRY_INK")
    return {
        "visible_block_ids":blocks,
        "visible_diagram_ids":diagrams,
        "block_catalog":catalog,
    }


def render_persistent_chalkboard(storyboard,execution,cues,policy, *,
                                 output_mp4:Path,output_json:Path,fps: int = DEFAULT_VIDEO_FPS,
                                 computation_manifest=None,matrix_manifest=None,
                                 proof_manifest=None,diagram_manifest=None,
                                 layout_hint=None,narration_events=None,
                                 event_index=None):
    """Real uninterrupted-ink Manim video; erase only on board-full cut."""
    if not isinstance(fps,int) or not 8<=fps<=60:
        raise LongboardError("CHALKBOARD_INVALID_FPS")
    output_mp4,output_json=Path(output_mp4),Path(output_json)
    if output_mp4.suffix!=".mp4" or output_json.suffix!=".json":
        raise LongboardError("CHALKBOARD_OUTPUT_EXTENSION")
    if not shutil.which("ffmpeg"):
        raise LongboardError("CHALKBOARD_FFMPEG_UNAVAILABLE")
    board,contract,teaching,selected,matrix,proof,diagram=_strict_sources(
        storyboard,execution,cues,policy,matrix_manifest=matrix_manifest,
        proof_manifest=proof_manifest,diagram_manifest=diagram_manifest
    )
    layout=make_chalkboard_plan(
        board,contract,cues,selected,
        computation_manifest=computation_manifest,
        matrix_manifest=matrix_manifest,proof_manifest=proof_manifest,
        diagram_manifest=diagram_manifest, layout_hint=layout_hint
    )
    # Event-level incremental rendering starts from the *real* source-verified
    # board state of the preceding event, not a screenshot. It is intentionally
    # opt-in; ordinary full-stage rendering keeps the accepted behavior.
    if event_index is not None:
        if (type(event_index) is not int or
                not 0 <= event_index < len(layout["events"])):
            raise LongboardError("CHALKBOARD_EVENT_WINDOW_INVALID")
        if narration_events is None:
            raise LongboardError("CHALKBOARD_EVENT_REQUIRES_REAL_VOICE")
        state=_event_entry_contract(layout,event_index)
        entering_blocks=state["visible_block_ids"]
        entering_diagrams=state["visible_diagram_ids"]
        block_catalog=state["block_catalog"]
        event_rows=layout["events"][event_index:event_index+1]
    else:
        entering_blocks=[]
        entering_diagrams=[]
        block_catalog={}
        event_rows=layout["events"]
    # Source-bound, opt-in real-audio timings. Default Manim behavior remains
    # exactly the previously accepted V2.5-V2.6.3 visual behavior.
    if narration_events is not None:
        if not isinstance(narration_events, dict) or set(narration_events) != {
                e["event_id"] for e in layout["events"]}:
            raise LongboardError("CHALKBOARD_NARRATION_COVERAGE")
        for event in layout["events"]:
            spans=narration_events[event["event_id"]]
            expected=[]
            diag=(
                ("diagram","diagram:"+event["event_id"])
                if event.get("diagram_reveal_ids") else None
            )
            if diag and event["diagram_order"]=="diagram_then_math":
                expected.append(diag)
            expected.extend(
                ("note" if x["kind"]=="teacher_note" else "math",x["block_id"])
                for x in event["added_blocks"] if not x.get("carry")
            )
            expected.extend(
                (a["kind"],a["object_id"])
                for a in event.get("speech_only_actions",[])
            )
            if diag and event["diagram_order"]=="math_then_diagram":
                expected.append(diag)
            if (not isinstance(spans,list) or
                    [(x.get("kind"),x.get("object_id")) for x in spans
                     if isinstance(x,dict)] != expected or
                    len(spans) != len(expected) or
                    any(type(x.get("duration")) not in (int,float)
                        or not math.isfinite(x["duration"])
                        or not .45 <= x["duration"] <= 60
                        or (x.get("kind")=="math" and (
                            type(x.get("math_start_delay")) not in (int,float)
                            or not math.isfinite(x["math_start_delay"])
                            or x["math_start_delay"] < 0
                            or x["math_start_delay"] >= x["duration"]
                            or type(x.get("math_end_delay")) not in (int,float)
                            or not math.isfinite(x["math_end_delay"])
                            or not x["math_start_delay"] < x["math_end_delay"] <= x["duration"]
                        )) for x in spans)):
                raise LongboardError("CHALKBOARD_NARRATION_ACTION_MISMATCH")
    emphasis_fragments={}
    if narration_events:
        for action_list in narration_events.values():
            for action in action_list:
                for beat in action.get("math_emphasis_beats", []):
                    emphasis_fragments.setdefault(beat["source_object_id"],set()).add(
                        beat["latex_fragment"]
                    )
    from .diagram_classroom import DIAGRAM_PANEL
    from manim import (Scene,MathTex,VGroup,Write,FadeIn,Rectangle,WHITE,
                       tempconfig,linear,Indicate,RED)
    fw=8*1280/720
    fh=8.
    def place(rect):
        return [((rect["x"]+rect["w"]/2)/1280-.5)*fw,
                (.5-(rect["y"]+rect["h"]/2)/720)*fh,0]
    def build_math(block):
        pieces=[]
        for f in block["fragments"]:
            isolates=sorted((
                token for token in emphasis_fragments.get(block["block_id"],())
                if token in f["latex"]
            ),key=lambda x:-len(x))
            glyph=MathTex(
                f["latex"],color=BOARD_DERIVATION_INK,
                **({"substrings_to_isolate":isolates} if isolates else {})
            )
            glyph.scale(block["scale"])
            glyph.move_to(place(f))
            if (abs(glyph.width*90-f["w"])>2 or
                    abs(glyph.height*90-f["h"])>2):
                raise LongboardError("CHALKBOARD_TRUE_SIZE_MISMATCH")
            pieces.append(glyph)
        return VGroup(*pieces)
    def diagram_point(u,v):
        panel=diagram.public_manifest()["panel"]
        x=panel["x"]+u*panel["w"]
        y=panel["y"]+v*panel["h"]
        return [((x/1280)-.5)*fw, (.5-y/720)*fh,0]

    def build_diagram(ident):
        """Only model-data objects from the verified immutable source."""
        from manim import (
            Line,DashedLine,Dot,VMobject,Polygon,MathTex,
            BLUE,BLACK
        )
        record=diagram.objects[ident]
        kind=record["kind"]
        if kind=="coordinate":
            # Source geometry can reference this point without showing an
            # irrelevant dot at each axis or right-angle-marker corner.
            return None
        if kind=="point":
            return Dot(diagram_point(record["x"],record["y"]),
                       radius=.043,color=BLACK)
        if kind=="line":
            start=diagram.objects[record["start"]]
            end=diagram.objects[record["end"]]
            cls=DashedLine if record["dashed"] else Line
            return cls(
                diagram_point(start["x"],start["y"]),
                diagram_point(end["x"],end["y"]),
                color=BLACK,stroke_width=2.2
            )
        if kind=="curve":
            obj=VMobject(color=BLUE,stroke_width=3)
            obj.set_points_smoothly(
                [diagram_point(x,y) for x,y in record["points"]]
            )
            return obj
        if kind=="region":
            obj=Polygon(
                *(diagram_point(x,y) for x,y in record["boundary"]),
                stroke_width=0,fill_color="#93C5FD",
                fill_opacity=.32
            )
            obj.set_z_index(-1)
            return obj
        if kind=="label":
            from manim import MathTex
            obj=MathTex(record["latex"],color=BLACK)
            # Labels are genuine MathTex and must fit their authored,
            # line-avoiding region at a readable fixed mathematical scale.
            obj.scale(.42)
            panel=diagram.public_manifest()["panel"]
            limit_w=record["w"]*panel["w"]*.94
            limit_h=record["h"]*panel["h"]*.94
            if obj.width*90>limit_w+.7 or obj.height*90>limit_h+.7:
                raise LongboardError(
                    "DIAGRAM_REAL_MATHTEX_LABEL_OVERFLOW: "+ident
                )
            obj.move_to(diagram_point(
                record["x"]+record["w"]/2,
                record["y"]+record["h"]/2
            ))
            return obj
        raise LongboardError("DIAGRAM_UNKNOWN_DRAW_KIND")

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
                    diagram_active={}
                    self.timing=[]
                    # Restore live MathTex, note and diagram objects in the
                    # same original order before animating the chosen event.
                    # An erase at the event boundary must still visibly erase
                    # these objects as a real classroom chalkboard would.
                    for ident in entering_blocks:
                        block=block_catalog[ident]
                        if block["kind"]=="teacher_note":
                            from manim import ImageMobject
                            obj=ImageMobject(str(
                                temp/(ident.replace(":","_")+".png")
                            ))
                            obj.scale_to_fit_width(fw).move_to([0,0,0])
                        else:
                            obj=build_math(block)
                        self.add(obj)
                        active[ident]=obj
                    for ident in entering_diagrams:
                        if diagram is None:
                            raise LongboardError("CHALKBOARD_EVENT_DIAGRAM_NO_SOURCE")
                        obj=build_diagram(ident)
                        if obj is not None:
                            self.add(obj)
                        diagram_active[ident]=obj
                    for row in event_rows:
                        start=self.time
                        action_timings=[]
                        diagram_reveal_timings=[]
                        emphasis_timings=[]
                        clips=(narration_events or {}).get(row["event_id"],[])
                        clip_cursor=[0]
                        def perform_sync(kind,ident,paint):
                            if narration_events is None:
                                return paint(None)
                            if clip_cursor[0] >= len(clips):
                                raise LongboardError("CHALKBOARD_SPEECH_ACTION_MISSING")
                            speech=clips[clip_cursor[0]]
                            clip_cursor[0]+=1
                            if (speech["kind"],speech["object_id"])!=(kind,ident):
                                raise LongboardError("CHALKBOARD_SPEECH_ACTION_ORDER")
                            before=self.time
                            paint(speech)
                            after=self.time
                            if abs(after-before-speech["duration"])>2/fps:
                                raise LongboardError("CHALKBOARD_ACTUAL_AUDIO_DURATION_DESYNC")
                            action_timings.append({
                                "kind":kind,"object_id":ident,
                                "start_preview_second":before,
                                "end_preview_second":after,
                            })
                        keep_graph = (
                            diagram is not None and layout_hint == "preserve_diagram"
                            and bool(diagram_active) and row["erase_before"]
                        )
                        if row["erase_before"]:
                            # Preserve already revealed diagram ink in V2.6.2.
                            # The existing V2.5 behavior is untouched without
                            # the explicit, source-checked adaptive hint.
                            erase_w = (
                                (DIAGRAM_PANEL["x"] - 20) / 90 if keep_graph else fw + .2
                            )
                            erase_target = (
                                -fw/2 + erase_w/2 if keep_graph else 0
                            )
                            eraser=Rectangle(
                                width=erase_w,height=fh*.81,
                                fill_color=WHITE,fill_opacity=1,
                                stroke_opacity=0
                            )
                            eraser.move_to([-fw, -.45, 0])
                            self.add(eraser)
                            self.play(
                                eraser.animate.move_to([erase_target,-.45,0]),
                                run_time=.75,rate_func=linear
                            )
                            removing=list(active.values())+(
                                [] if keep_graph else list(diagram_active.values())
                            )
                            for obj in removing:
                                if obj is not None:
                                    self.remove(obj)
                            active.clear()
                            if not keep_graph:
                                diagram_active.clear()
                            self.remove(eraser)
                        if diagram is not None:
                            if keep_graph and list(diagram_active) != row["diagram_carry_ids"]:
                                raise LongboardError("DIAGRAM_PERSISTENCE_STATE_MISMATCH")
                            for ident in row["diagram_carry_ids"]:
                                if keep_graph and ident in diagram_active:
                                    continue  # same live object, never redrawn
                                if ident in diagram_active:
                                    raise LongboardError("DIAGRAM_CARRY_DUPLICATE")
                                obj=build_diagram(ident)
                                if obj is not None:
                                    self.add(obj)
                                diagram_active[ident]=obj
                            def reveal_diagram(speech=None):
                                from manim import Create,FadeIn
                                duration=speech["duration"] if speech else None
                                before=self.time
                                ids=row["diagram_reveal_ids"]
                                visible=sum(
                                    diagram.objects[x]["kind"]!="coordinate"
                                    for x in ids
                                )
                                if duration is not None and visible:
                                    # Let the actual geometry develop through
                                    # the spoken drawing beat, rather than
                                    # finishing it in the first second and
                                    # holding an unchanged picture for the rest
                                    # of a long narrated action. Cap each
                                    # object to avoid unnaturally slow strokes.
                                    each=min(2.25,max(.12,duration*.70/visible))
                                else:
                                    each=None
                                beat_map = {
                                    beat["object_id"]: beat
                                    for beat in (speech or {}).get("diagram_beats", [])
                                }
                                for ident in ids:
                                    if ident in diagram_active:
                                        raise LongboardError("DIAGRAM_REVEAL_LIVE")
                                    obj=build_diagram(ident)
                                    mode=diagram.objects[ident]["kind"]
                                    if obj is not None and beat_map:
                                        if ident not in beat_map:
                                            raise LongboardError("CHALKBOARD_DIAGRAM_BEAT_MISSING")
                                        beat=beat_map[ident]
                                        target_start=before+beat["start_offset"]
                                        if self.time > target_start + 2/fps:
                                            raise LongboardError("CHALKBOARD_DIAGRAM_BEAT_ORDER")
                                        if target_start > self.time:
                                            self.wait(target_start-self.time)
                                        window=beat["end_offset"]-beat["start_offset"]
                                        if window <= 0:
                                            raise LongboardError("CHALKBOARD_DIAGRAM_BEAT_WINDOW")
                                        draw_time=min(2.25,max(.08,window*.82))
                                    else:
                                        draw_time=each
                                    reveal_start=self.time
                                    if mode in ("line","curve"):
                                        self.play(
                                            Create(obj),run_time=draw_time if draw_time
                                            is not None else .72
                                        )
                                    elif obj is not None:
                                        self.play(
                                            FadeIn(obj),run_time=draw_time if draw_time
                                            is not None else .36
                                        )
                                    diagram_active[ident]=obj
                                    if obj is not None:
                                        diagram_reveal_timings.append({
                                            "object_id":ident,
                                            "start_preview_second":reveal_start,
                                            "end_preview_second":self.time,
                                        })
                                if duration is not None:
                                    remaining=duration-(self.time-before)
                                    if remaining>1e-5:
                                        self.wait(remaining)
                            if (row["diagram_order"]=="diagram_then_math"
                                    and row["diagram_reveal_ids"]):
                                perform_sync(
                                    "diagram","diagram:"+row["event_id"],
                                    reveal_diagram
                                )
                        for block in row["added_blocks"]:
                            ident=block["block_id"]
                            if ident in active:
                                raise LongboardError("CHALKBOARD_DUPLICATE_LIVE_OBJECT")
                            if block.get("carry"):
                                if block["kind"]=="teacher_note":
                                    from manim import ImageMobject
                                    obj=ImageMobject(str(
                                        temp/(ident.replace(":","_")+".png")
                                    ))
                                    obj.scale_to_fit_width(fw).move_to([0,0,0])
                                else:
                                    obj=build_math(block)
                                self.add(obj)
                                active[ident]=obj
                                continue
                            if block["kind"]=="teacher_note":
                                from manim import ImageMobject
                                obj=ImageMobject(str(temp/(ident.replace(":","_")+".png")))
                                obj.scale_to_fit_width(fw).move_to([0,0,0])
                                def write_note(speech):
                                    duration=speech["duration"] if speech else None
                                    before=self.time
                                    self.play(FadeIn(obj),run_time=.32 if duration is
                                              None else min(.32,duration*.5))
                                    if duration is not None:
                                        remaining=duration-(self.time-before)
                                        if remaining>1e-5:
                                            self.wait(remaining)
                                perform_sync("note",ident,write_note)
                            else:
                                obj=build_math(block)
                                def write_math(speech):
                                    duration=speech["duration"] if speech else None
                                    before=self.time
                                    if duration is None:
                                        for frag in obj:
                                            self.play(Write(frag),
                                                      run_time=row["write_seconds"])
                                    else:
                                        # Write while it is spoken, then keep
                                        # the finished expression visible for
                                        # the remainder of the explanation.
                                        # A teacher may explain the reason
                                        # before reading the displayed formula.
                                        # Begin the MathTex Write at the
                                        # actual *math* audio chunk, not at
                                        # the start of the spoken preamble.
                                        intro=speech["math_start_delay"]
                                        # Visual cancellation/highlights are
                                        # source-authorized and triggered by the
                                        # exact spoken phrase, BEFORE the new
                                        # simplified formula begins to write.
                                        marks=speech.get("math_emphasis_beats",[])
                                        if marks:
                                            groups={}
                                            for mark in marks:
                                                if mark["end_offset"]>intro+1/fps:
                                                    raise LongboardError("CHALKBOARD_MARK_AFTER_NEW_MATH")
                                                groups.setdefault(mark["start_offset"],[]).append(mark)
                                            for mark_start, group in sorted(groups.items()):
                                                if self.time > before+mark_start+2/fps:
                                                    raise LongboardError("CHALKBOARD_MARK_BEAT_ORDER")
                                                if self.time < before+mark_start:
                                                    self.wait(before+mark_start-self.time)
                                                targets=[]
                                                for mark in group:
                                                    source=active.get(mark["source_object_id"])
                                                    if source is None:
                                                        raise LongboardError("CHALKBOARD_MARK_SOURCE_NOT_VISIBLE")
                                                    # Manim Community 0.22 exposes
                                                    # get_part_by_tex, but *not*
                                                    # the legacy get_parts_by_tex.
                                                    # Use the exact source-identified
                                                    # substring-to-SVG map; no
                                                    # freehand or guessed bbox.
                                                    matches=[]
                                                    for glyph in source:
                                                        for tex_value,match_id in getattr(
                                                            glyph,"matched_strings_and_ids",()
                                                        ):
                                                            if tex_value == mark["latex_fragment"]:
                                                                match=getattr(glyph,"id_to_vgroup_dict",{}).get(match_id)
                                                                if match is not None:
                                                                    matches.append(match)
                                                    if mark["occurrence"] >= len(matches):
                                                        raise LongboardError("CHALKBOARD_MARK_GLYPH_NOT_FOUND")
                                                    targets.append(matches[mark["occurrence"]])
                                                window=min(m["end_offset"] for m in group)-mark_start
                                                remaining_intro=before+intro-self.time
                                                duration=min(.7,max(.15,window*.55),remaining_intro)
                                                if duration<.08:
                                                    raise LongboardError("CHALKBOARD_MARK_TOO_LATE")
                                                highlighted_at=self.time
                                                self.play(
                                                    *[Indicate(t,color=RED,scale_factor=1.06)
                                                      for t in targets],
                                                    run_time=duration,rate_func=linear
                                                )
                                                for mark in group:
                                                    emphasis_timings.append({
                                                        "source_object_id":mark["source_object_id"],
                                                        "latex_fragment":mark["latex_fragment"],
                                                        "spoken_phrase":mark["spoken_phrase"],
                                                        "start_preview_second":highlighted_at,
                                                        "end_preview_second":self.time,
                                                    })
                                        if before+intro>self.time+1e-5:
                                            self.wait(before+intro-self.time)
                                        # Math ink progresses throughout the
                                        # *measured math-reading audio*, and
                                        # finishes at that audio boundary.
                                        # Earlier versions capped each line at
                                        # 2.4s, displaying long equations
                                        # before the teacher had read them.
                                        math_window=speech["math_end_delay"]-intro
                                        each=math_window/len(obj)
                                        for frag in obj:
                                            self.play(
                                                Write(frag),run_time=each,
                                                rate_func=linear
                                            )
                                        remaining=duration-(self.time-before)
                                        if remaining>1e-5:
                                            self.wait(remaining)
                                    self.remove(*obj.submobjects)
                                    self.add(obj)
                                perform_sync("math",ident,write_math)
                            active[ident]=obj
                        if (diagram is not None and
                                row["diagram_order"]=="math_then_diagram"):
                            if row["diagram_reveal_ids"]:
                                perform_sync(
                                    "diagram","diagram:"+row["event_id"],
                                    reveal_diagram
                                )
                        for virtual in row.get("speech_only_actions", []):
                            # Question text/formula are already in the fixed
                            # header. Sound and source-bound MathTex subtitles
                            # remain; no duplicate drawing or invisible ink
                            # consumes the working board.
                            def read_existing_header(speech):
                                if speech is not None:
                                    self.wait(speech["duration"])
                            perform_sync(
                                virtual["kind"],virtual["object_id"],
                                read_existing_header,
                            )
                        if narration_events is not None and clip_cursor[0]!=len(clips):
                            raise LongboardError("CHALKBOARD_SPEECH_ACTION_UNUSED")
                        if (diagram is not None and
                                row["visible_diagram_ids"]!=list(diagram_active)):
                            raise LongboardError(
                                "DIAGRAM_VISIBLE_LIFECYCLE_MISMATCH"
                            )
                        # Printed ink is persistent until a real page erase.
                        if row["visible_block_ids"] != list(active.keys()):
                            raise LongboardError(
                                f"CHALKBOARD_VISIBLE_SET_MISMATCH: {row['event_id']}"
                            )
                        if narration_events is None:
                            self.wait(row["pause_seconds"])
                        self.timing.append({
                            "action_timing":action_timings,
                            "diagram_reveal_timing":diagram_reveal_timings,
                            "math_emphasis_timing":emphasis_timings,
                            "carry_object_ids":list(row.get("carry_object_ids",[])),
                            "event_id":row["event_id"],"page_index":row["page_index"],
                            "erase_before":row["erase_before"],
                            "math_write_count":row["math_write_count"],
                            "unit_heading":row["unit_heading"],
                            "erase_reason":row["erase_reason"],
                            "start_preview_second":start,
                            "end_preview_second":self.time,
                            "visible_block_ids":list(active),
                            **({"visible_diagram_ids":list(diagram_active)}
                               if diagram is not None else {}),
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
            "rendered_event_index":event_index,
            "event_window_entry_verified":event_index is not None,
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
