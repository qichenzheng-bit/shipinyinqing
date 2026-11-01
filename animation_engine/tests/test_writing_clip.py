"""Real Manim MP4 acceptance: MathTex progressive writing and color restoration."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("manim")
from visual_director import build_storyboard
from animation_engine import build_execution_plan
from animation_engine.writing_cues import plan_math_writing
from animation_engine.writing_clip import MathWritingClipError, render_math_writing_clip

FIXTURE = Path(__file__).resolve().parents[2] / "visual_director" / "tests" / "fixtures" / "limit_teaching_package.json"


@pytest.fixture
def inputs():
    board = build_storyboard(json.loads(FIXTURE.read_text(encoding="utf-8")))
    execution = build_execution_plan(board)
    hint = dict(
        source_storyboard_sha256=execution.source_storyboard_sha256,
        event_id="e_end", object_id="m_end", action_id="b_end",
        speech_unit_id="u_end",
        parts=["L", "=", "I_1+I_2+I_3", "=", r"-\frac13", r"+\frac12", r"+\frac12", r"=\frac23"],
        highlight_index=4,
    )
    return board, execution, hint


def _ffprobe_frames(mp4):
    assert shutil.which("ffprobe")
    p = subprocess.run(["ffprobe","-v","error","-select_streams","v:0",
        "-count_frames","-show_entries","stream=width,height,nb_read_frames",
        "-of","json",str(mp4)],capture_output=True,text=True,check=True)
    return json.loads(p.stdout)["streams"][0]


def _count_blue_pixels(mp4, second):
    """Check actual decoded frame, not metadata assertions alone."""
    import io
    from PIL import Image
    p=subprocess.run(["ffmpeg","-v","error","-ss",str(second),"-i",str(mp4),
        "-frames:v","1","-f","image2pipe","-vcodec","png","-"],
        capture_output=True,check=True)
    im=Image.open(io.BytesIO(p.stdout)).convert("RGB")
    blues=0
    for y in range(0, im.height, 3):
        for x in range(0, im.width, 3):
            r,g,b=im.getpixel((x,y))
            if b>r*1.4 and b>g*1.12 and b>90:
                blues+=1
    return blues


def test_real_segmented_movie_exact_target_blue_and_restores(inputs,tmp_path):
    board,ex,hint=inputs
    plan=plan_math_writing(board,ex,event_id="e_end",object_id="m_end",hint=hint)
    mp4,meta=tmp_path/"segmented.mp4",tmp_path/"segmented.json"
    res=render_math_writing_clip(plan,output_mp4=mp4,output_json=meta,
                                  pixel_width=640,pixel_height=360,fps=12)
    assert res.mp4_path==mp4 and mp4.stat().st_size>3000
    v=_ffprobe_frames(mp4)
    assert (int(v["width"]),int(v["height"]))==(640,360)
    assert int(v["nb_read_frames"])>20
    data=json.loads(meta.read_text(encoding="utf-8"))
    assert data["render_kind"]=="manim_mathtex_progressive_mp4"
    assert data["mode"]=="segmented" and data["parts"]==hint["parts"]
    assert data["source_storyboard_sha256"]==ex.source_storyboard_sha256
    assert data["source_step_ids"]==["s8"]
    assert data["action_id"]=="b_end" and data["speech_unit_id"]=="u_end"
    assert data["highlight_index"]==4
    assert data["timing_source"]=="preview_only_not_audio_aligned"
    assert "speech_start_second" not in data and "speech_end_second" not in data
    assert data["write_part_indices"]==list(range(len(hint["parts"])))
    assert _count_blue_pixels(mp4, data["highlight_sample_second"])>5
    assert _count_blue_pixels(mp4, data["final_sample_second"])==0


def test_no_hint_real_movie_writes_entire_formula_once(inputs,tmp_path):
    board,ex,_=inputs
    plan=plan_math_writing(board,ex,event_id="e_end",object_id="m_end")
    mp4,meta=tmp_path/"whole.mp4",tmp_path/"whole.json"
    render_math_writing_clip(plan,output_mp4=mp4,output_json=meta,
                             pixel_width=640,pixel_height=360,fps=12)
    data=json.loads(meta.read_text())
    assert data["mode"]=="whole_formula"
    assert data["hint_source"]=="safe_fallback"
    assert data["write_part_indices"]==[0]
    assert data["parts"]==[plan.request.latex]
    assert _count_blue_pixels(mp4, data["highlight_sample_second"])>5
    assert _count_blue_pixels(mp4, data["final_sample_second"])==0


def test_reject_overflow_without_creating_success_artifacts(inputs,tmp_path):
    from dataclasses import replace
    board,ex,_=inputs
    plan=plan_math_writing(board,ex,event_id="e_end",object_id="m_end")
    from visual_director.models import Rect
    too_big=replace(plan,request=replace(plan.request,region=Rect(x=.05,y=.05,w=.06,h=.06)))
    mp4,meta=tmp_path/"bad.mp4",tmp_path/"bad.json"
    with pytest.raises(MathWritingClipError,match="FORMULA_OVERFLOW"):
        render_math_writing_clip(too_big,output_mp4=mp4,output_json=meta,
                                 pixel_width=640,pixel_height=360,fps=12)
    assert not mp4.exists() and not meta.exists()


def test_reject_duplicate_output_paths(inputs,tmp_path):
    board,ex,_=inputs
    plan=plan_math_writing(board,ex,event_id="e_end",object_id="m_end")
    same=tmp_path/"same.mp4"
    with pytest.raises(MathWritingClipError,match="INVALID_OUTPUT"):
        render_math_writing_clip(plan,output_mp4=same,output_json=same)

def test_render_writing_cli_preserves_legacy_and_rejects_invalid_hint(inputs,tmp_path):
    from animation_engine.cli import main
    board,ex,hint=inputs
    boardfile,exfile,hintfile=(tmp_path/"board.json",tmp_path/"execution.json",tmp_path/"hint.json")
    boardfile.write_text(board.model_dump_json(),encoding="utf-8")
    exfile.write_text(ex.model_dump_json(),encoding="utf-8")
    hintfile.write_text(json.dumps(hint),encoding="utf-8")
    mp4,meta=tmp_path/"cli.mp4",tmp_path/"cli.json"
    args=["render-writing","--storyboard",str(boardfile),"--execution",str(exfile),
        "--event-id","e_end","--object-id","m_end","--hint",str(hintfile),
        "--output",str(mp4),"--manifest",str(meta)]
    assert main(args)==0
    assert mp4.exists() and meta.exists()
    assert json.loads(meta.read_text())["hint_source"]=="approved_explicit"
    hint["parts"][-1]="+o(x^7)"
    hintfile.write_text(json.dumps(hint),encoding="utf-8")
    bad_mp4,bad_meta=tmp_path/"invalid.mp4",tmp_path/"invalid.json"
    bad_args=args[:-4]+["--output",str(bad_mp4),"--manifest",str(bad_meta)]
    assert main(bad_args)!=0
    assert not bad_mp4.exists() and not bad_meta.exists()
    # Step 2.1 and plan commands still parse unchanged.
    planfile=tmp_path/"plan.json"
    assert main(["plan",str(boardfile),"--output",str(planfile)])==0

def test_repeated_identical_math_parts_highlight_only_selected_occurrence(inputs,tmp_path):
    import io
    from PIL import Image
    board,ex,hint=inputs
    assert hint["parts"][5] == hint["parts"][6] == r"+\frac12"
    hint["highlight_index"]=6
    plan=plan_math_writing(board,ex,event_id="e_end",object_id="m_end",hint=hint)
    mp4,meta=tmp_path/"repeated.mp4",tmp_path/"repeated.json"
    render_math_writing_clip(plan,output_mp4=mp4,output_json=meta,
                             pixel_width=640,pixel_height=360,fps=12)
    data=json.loads(meta.read_text())
    bounds=data["part_bounds_px"]
    assert len(bounds)==len(hint["parts"])
    assert bounds[5]!=bounds[6]
    p=subprocess.run(["ffmpeg","-v","error","-ss",str(data["highlight_sample_second"]),
        "-i",str(mp4),"-frames:v","1","-f","image2pipe","-vcodec","png","-"],
        capture_output=True,check=True)
    im=Image.open(io.BytesIO(p.stdout)).convert("RGB")
    def blue_count(box):
        left,top,right,bottom=box
        n=0
        for yy in range(max(0,int(top)),min(im.height,int(bottom)+1)):
            for xx in range(max(0,int(left)),min(im.width,int(right)+1)):
                r,g,b=im.getpixel((xx,yy))
                if b>r*1.4 and b>g*1.12 and b>90:
                    n+=1
        return n
    assert blue_count(bounds[6])>5
    assert blue_count(bounds[5])==0
