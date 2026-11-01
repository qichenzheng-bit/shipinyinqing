"""V2.6.6 exact-frame sparse MathTex overlay tests.

PNG test images are deterministic synthetic *compositor fixtures*; the real
voice and actual MathTex glyph integration test runs in V2.6.6 CI.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

PIL=pytest.importorskip("PIL")
from PIL import Image, ImageDraw
from animation_engine.longboard_plan import LongboardError
from animation_engine.sparse_caption_mux import (
    make_sparse_caption_playlist, mux_sparse_mathtex,
)

def _source_images(root: Path):
    out={}
    for name,rgba in (("blue",(0,100,255,255)),("red",(235,10,5,255))):
        image=Image.new("RGBA",(1280,88),(0,0,0,0))
        ImageDraw.Draw(image).rectangle((300,15,900,65),fill=rgba)
        p=root/(name+".png")
        image.save(p)
        out[("text",name)]=p
    return out

def _cues():
    return [
        {"kind":"text","display":"blue","start_frame":30,"end_frame":45},
        {"kind":"text","display":"red","start_frame":58,"end_frame":76},
    ]

def _run(args):
    return subprocess.run(args,capture_output=True,text=True,check=True)

@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="real FFmpeg/ffprobe required",
)
def test_direct_png_mux_has_exact_caption_on_and_off_frames(tmp_path):
    sources=_source_images(tmp_path)
    silent=tmp_path/"source.mp4"
    wav=tmp_path/"speech.wav"
    _run([
        "ffmpeg","-v","error","-y","-f","lavfi",
        "-i","color=c=white:s=1280x720:r=30:d=4",
        "-c:v","libx264","-pix_fmt","yuv420p",
        "-r","30",str(silent)
    ])
    _run([
        "ffmpeg","-v","error","-y","-f","lavfi",
        "-i","sine=frequency=440:duration=4:sample_rate=24000",
        "-ar","24000","-ac","1",str(wav),
    ])
    dest=tmp_path/"real_overlay.mp4"
    result=mux_sparse_mathtex(
        silent,wav,_cues(),sources,dest,
        workdir=tmp_path,fps=30,frames=120,
    )
    assert result["pipeline"]=="frame_exact_sparse_png_final_overlay"
    assert result["intermediate_ffv1_band_required"] is False
    probe=json.loads(subprocess.check_output([
        "ffprobe","-v","error","-show_streams","-of","json",str(dest)
    ]))["streams"]
    assert set(x["codec_type"] for x in probe)=={"video","audio"}
    assert next(x for x in probe if x["codec_type"]=="video")["width"]==1280
    assert result["output_frames"]==120

    # Read selected video frames in one decoded stream, avoiding screenshot
    # interpolation. RGB pixel is intentionally 500,660 in the caption band.
    selected=[0,29,30,44,45,57,58,75,76,119]
    select="+".join(f"eq(n\\,{k})" for k in selected)
    frames=subprocess.check_output([
        "ffmpeg","-v","error","-i",str(dest),
        "-vf","select="+select,
        "-fps_mode","passthrough","-pix_fmt","rgb24",
        "-f","rawvideo","-",
    ])
    size=1280*720*3
    assert len(frames)==size*len(selected)
    for i,number in enumerate(selected):
        pixel=frames[i*size+(660*1280+500)*3:
                     i*size+(660*1280+500)*3+3]
        rgb=list(pixel)
        if number in (30,44):
            assert rgb[2]>220 and rgb[0]<30, (number,rgb)
        elif number in (58,75):
            assert rgb[0]>185 and rgb[2]<40, (number,rgb)
        else:
            assert min(rgb)>225, (number,rgb)

def test_sparse_playlist_rejects_missing_overlapping_or_unsafe_pictures(tmp_path):
    pictures=_source_images(tmp_path)
    for cues,code in [
        ([{"kind":"text","display":"blue","start_frame":30,"end_frame":45},
          {"kind":"text","display":"red","start_frame":44,"end_frame":76}],
          "SPARSE_CAPTION_FRAME_OVERLAP"),
        ([{"kind":"text","display":"blue","start_frame":30,"end_frame":121}],
          "SPARSE_CAPTION_FRAME_OVERLAP"),
        ([{"kind":"text","display":"unknown","start_frame":20,"end_frame":40}],
          "SPARSE_CAPTION_UNRENDERED_MATHTEX"),
    ]:
        with pytest.raises(LongboardError,match=code):
            make_sparse_caption_playlist(
                cues,pictures,tmp_path/"bad",fps=30,frames=120
            )
    source=tmp_path/"opaque.png"
    Image.new("RGBA",(1280,88),(255,255,255,255)).save(source)
    with pytest.raises(LongboardError,match="SPARSE_CAPTION_INVALID_SAFE_BAND"):
        make_sparse_caption_playlist(
            [{"kind":"text","display":"opaque",
              "start_frame":10,"end_frame":45}],
            {("text","opaque"):source},
            tmp_path/"opaque",fps=30,frames=120,
        )

def test_sparse_playlist_has_complete_integer_frame_coverage(tmp_path):
    pictures=_source_images(tmp_path)
    path=make_sparse_caption_playlist(
        _cues(),pictures,tmp_path/"source",fps=30,frames=120
    )
    audit=json.loads(
        (path.parent/"source_caption_audit.json").read_text("utf-8")
    )
    assert audit["frame_coverage"]==120
    assert audit["unique_glyphs"]==2
    assert audit["segments"]==5
    lines=path.read_text("utf-8")
    assert lines.count("option framerate 30")==6
