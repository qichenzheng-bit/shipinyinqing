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
BOARD_X = 320
BOARD_WIDTH = 655
BOARD_ROW_GAP = 13
NOTE_MAX_CHARS_PER_LINE = 32
# A real 16px CJK glyph is narrower than 32*~20px, so these fit in 655px.
NOTE_HEIGHT = 29
NOTE_DETAIL_LINE_HEIGHT = 24


def _strict_sources(storyboard, execution, cues, policy):
    from visual_director.models import StoryboardPlan
    from .models import ExecutionPlan
    board=StoryboardPlan.model_validate(storyboard)
    plan=ExecutionPlan.model_validate(execution)
    if plan.model_dump(mode="json") != build_execution_plan(board).model_dump(mode="json"):
        raise LongboardError("CHALKBOARD_SOURCE_CONTRACT_MISMATCH")
    teaching=checked_cues(cues,board,plan)
    selected=LongboardPolicy.parse(policy)
    selected.validate(set(_sources(plan)),{s.event_id for s in board.scenes},_sources(plan))
    if selected.guidance_style != "persistent_chalkboard":
        raise LongboardError("CHALKBOARD_REQUIRES_PERSISTENT_GUIDANCE_STYLE")
    if selected.board_mode != "simple_full_board":
        raise LongboardError("CHALKBOARD_REQUIRES_SIMPLE_FULL_BOARD")
    if selected.cut_before_events or selected.pinned_ids:
        raise LongboardError("CHALKBOARD_DISALLOWS_FORCED_CUT_OR_PINNING")
    return board,plan,teaching,selected


def _note_lines(detail: str) -> list[str]:
    return [detail[i:i+NOTE_MAX_CHARS_PER_LINE]
            for i in range(0,len(detail),NOTE_MAX_CHARS_PER_LINE)]


def _math_placement(mid,sources,selected,measure,size_cache,y):
    source=sources[mid]
    parts=_size_parts(mid,source,selected,measure,720,size_cache,BOARD_WIDTH)
    return _make_placement(
        mid,source,parts,BOARD_X,y,BOARD_WIDTH,(1280,720),"working",
        selected.math_base_scale,selected.math_min_scale
    )


def make_chalkboard_plan(storyboard,execution,cues,policy, *,
                         measure=None) -> dict:
    board,execution_plan,teaching,selected=_strict_sources(
        storyboard,execution,cues,policy
    )
    sources=_sources(execution_plan)
    original_measure=measure or _real_measure
    measurements={}
    def size_of(latex,height):
        key=(latex,height)
        if key not in measurements:
            measurements[key]=original_measure(latex,height)
        return measurements[key]
    size_cache={}
    cursor=BOARD_START_Y
    page=1
    active=[]
    written=set()
    events=[]
    all_math=set()
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
        note_needed=cue["phase"] in BOARD_GUIDANCE_PHASES
        lines=_note_lines(cue["detail"]) if note_needed else []
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
                    "x":BOARD_X,"y":y,"w":BOARD_WIDTH,"h":noteheight,
                })
                y+=noteheight+5
            for mid in newids:
                item=_math_placement(mid,sources,selected,size_of,size_cache,y)
                additions.append({"kind":"math","block_id":mid,**item})
                y+=item["h"]+BOARD_ROW_GAP
            if note_needed and not newids:
                y+=BOARD_ROW_GAP
            return additions,y
        proposed,next_y=group_at(cursor)
        clear=False
        if next_y>BOARD_BOTTOM_Y:
            if not active:
                raise LongboardError(
                    f"CHALKBOARD_EVENT_TOO_TALL: {scene.event_id}"
                )
            clear=True
            page+=1
            cursor=BOARD_START_Y
            # Carry only explicit, already-computed mathematical results.
            # Copying results follows a real classroom's new page and never
            # implies calculating them before the original teacher event.
            carryids=[mid for mid in selected.result_ids if mid in written]
            carried=[]
            for mid in carryids:
                item=_math_placement(mid,sources,selected,size_of,size_cache,cursor)
                carried.append({"kind":"math","block_id":mid,"carry":True,**item})
                cursor+=item["h"]+BOARD_ROW_GAP
            proposed,next_y=group_at(cursor)
            if next_y>BOARD_BOTTOM_Y:
                # Do not attempt to cram a formula into the footer. When this
                # event itself needs space, drop optional carried results.
                carried=[]
                cursor=BOARD_START_Y
                proposed,next_y=group_at(cursor)
            if next_y>BOARD_BOTTOM_Y:
                raise LongboardError(
                    f"CHALKBOARD_EVENT_TOO_TALL: {scene.event_id}"
                )
            active=carried[:]
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
            if item["x"]<BOARD_X or item["x"]+item["w"]>BOARD_X+BOARD_WIDTH+1:
                raise LongboardError(
                    f"CHALKBOARD_HORIZONTAL_OVERFLOW: {scene.event_id}"
                )
            if item["y"]<BOARD_START_Y or item["y"]+item["h"]>BOARD_BOTTOM_Y:
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
            "erase_before":clear,
            "added_blocks":added,
            "visible_block_ids":[a["block_id"] for a in active],
            "pause_seconds":cue["pause_seconds"],
            "write_seconds":cue["write_seconds"],
        })
    # Every requested write event must have survived the planning pass.
    expected={a.object_id for sc in execution_plan.scenes for a in sc.actions
              if a.kind in ("progressive_write","restore")
              and a.object_id in sources and a.to_region!="question"}
    if all_math != expected:
        raise LongboardError("CHALKBOARD_MATH_EVENT_LOST")
    return {
        "schema_version":"1.0","mode":"persistent_chalkboard",
        "source_storyboard_sha256":execution_plan.source_storyboard_sha256,
        "page_count":page,"event_count":len(events),
        "math_written_ids":sorted(all_math),
        "coordinates":{"start_y":BOARD_START_Y,"bottom_y":BOARD_BOTTOM_Y,
                       "board_left":BOARD_X,"board_width":BOARD_WIDTH},
        "events":events,
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
    if hbox[2]>x+BOARD_WIDTH or hbox[3]>y+NOTE_HEIGHT:
        raise LongboardError("CHALKBOARD_NOTE_HEADER_OVERFLOW")
    draw.text((x,y),heading,font=header_font,fill=style["heading"])
    for idx,line in enumerate(block["lines"]):
        line_y=y+NOTE_HEIGHT+idx*NOTE_DETAIL_LINE_HEIGHT
        box=draw.textbbox((x,line_y),line,font=detail_font)
        if box[2]>x+BOARD_WIDTH or box[3]>y+block["h"]:
            raise LongboardError("CHALKBOARD_NOTE_BODY_OVERFLOW")
        draw.text((x,line_y),line,font=detail_font,fill=BOARD_DERIVATION_INK)
    canvas.save(output)


def render_persistent_chalkboard(storyboard,execution,cues,policy, *,
                                 output_mp4:Path,output_json:Path,fps:int=30):
    """Real uninterrupted-ink Manim video; erase only on board-full cut."""
    if not isinstance(fps,int) or not 8<=fps<=60:
        raise LongboardError("CHALKBOARD_INVALID_FPS")
    output_mp4,output_json=Path(output_mp4),Path(output_json)
    if output_mp4.suffix!=".mp4" or output_json.suffix!=".json":
        raise LongboardError("CHALKBOARD_OUTPUT_EXTENSION")
    if not shutil.which("ffmpeg"):
        raise LongboardError("CHALKBOARD_FFMPEG_UNAVAILABLE")
    board,contract,teaching,selected=_strict_sources(storyboard,execution,cues,policy)
    layout=make_chalkboard_plan(board,contract,cues,selected)
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
