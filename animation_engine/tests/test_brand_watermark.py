"""No-render acceptance: real PNG alpha, stable muted palette and top-right FFmpeg map."""
from pathlib import Path

import pytest

from animation_engine.brand_watermark import (
    BRAND_MARK_VERSION, make_brand_watermark,overlay_branding,
)
from animation_engine.classroom_compositor import _cjk_font_path


def test_transparent_source_preserves_brand_book_star(tmp_path):
    Image=pytest.importorskip("PIL.Image")
    if _cjk_font_path() is None:
        pytest.skip("CJK font unavailable on this runner")
    target=tmp_path/"brand.png"
    audit=make_brand_watermark(target)
    with Image.open(target) as p:
        assert p.size==(174,48)
        assert p.mode=="RGBA"
        alpha=p.getchannel("A")
        assert alpha.getextrema()[0]==0
        assert alpha.getextrema()[1]>=140
        assert alpha.getbbox() is not None
        assert p.getpixel((173,47))[3]==0
    assert audit["version"]==BRAND_MARK_VERSION
    assert audit["position"]=="top_right"


def test_overlay_is_top_right_preserves_original_audio_and_source(
        tmp_path,monkeypatch):
    pytest.importorskip("PIL.Image")
    if _cjk_font_path() is None:
        pytest.skip("CJK font unavailable on this runner")
    monkeypatch.setattr("shutil.which",lambda name: "/mock/ffmpeg")
    source=tmp_path/"original.mp4"
    source.write_bytes(b"ORIGINAL_VIDEO_UNCHANGED")
    target=tmp_path/"branded.mp4"
    calls=[]
    def runner(command,name):
        calls.append((command,name))
        target.write_bytes(b"B"*1200)
    outcome=overlay_branding(
        source,target,fps=60,frames=120,runner=runner,
    )
    assert outcome["position"]=="top_right"
    assert len(calls)==1
    command=calls[0][0]
    expr=command[command.index("-filter_complex")+1]
    assert "overlay=W-w-22:14" in expr
    # A still watermark is a looping video input. Without this, shortest=1
    # truncates an otherwise fully voiced movie to the PNG\'s single frame.
    assert command[command.index("-loop")+1]=="1"
    assert command[command.index("-framerate")+1]=="60"
    assert command[command.index("-map")+1]=="[v]"
    assert "0:a:0" in command
    assert command[command.index("-c:a")+1]=="copy"
    assert command[command.index("-frames:v")+1]=="120"
    assert source.read_bytes()==b"ORIGINAL_VIDEO_UNCHANGED"
    assert not list(tmp_path.glob("*.watermark.png"))
