"""Regression checks for 2.3 adaptive layout: no visual guessing, no silent cropping."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from animation_engine.adaptive_layout import (
    AdaptiveLayoutError, GlyphSize, MIN_SCALE, _overlap,
    layout_storyboard, render_layout_png,
)
from animation_engine.planner import build_execution_plan
from visual_director.director import build_storyboard


@pytest.fixture(scope="module")
def approved():
    source = Path(__file__).resolve().parents[2] / (
        "visual_director/examples/limit_teaching_package.json"
    )
    board = build_storyboard(json.loads(source.read_text(encoding="utf-8")))
    execution = build_execution_plan(board)
    return board, execution


def measure(latex: str, _: int) -> GlyphSize:
    return GlyphSize(145, 36, 40 if "=" in latex else None)


def test_all_scenes_fit_safely_and_preserve_provenance(approved):
    board, execution = approved
    before = board.model_dump_json()
    result = layout_storyboard(board, execution, measure=measure)
    assert result["source_storyboard_sha256"] == execution.source_storyboard_sha256
    assert result["timing_source"] == "semantic_anchors_only_not_audio_aligned"
    assert len(result["scenes"]) == len(board.scenes) == 19
    assert any(s["status"] == "ready" and s["placements"] for s in result["scenes"])
    for original, scene in zip(board.scenes, result["scenes"]):
        if scene["status"] == "cut_required":
            assert scene["placements"] == [] and scene["transitions"] == []
            continue
        assert [p["object_id"] for p in scene["placements"]] == original.visible_ids
        assert all(p["scale"] >= MIN_SCALE for p in scene["placements"])
        for i, a in enumerate(scene["placements"]):
            assert a["source_step_ids"]
            for b in scene["placements"][i + 1:]:
                assert not _overlap(a, b)
    assert board.model_dump_json() == before


def test_stability_across_consecutive_events(approved):
    board, execution = approved
    result = layout_storyboard(board, execution, measure=measure)
    seen: dict[str, dict] = {}
    holds = 0
    for scene in result["scenes"]:
        for p in scene["placements"]:
            if p["object_id"] in seen:
                old = seen[p["object_id"]]
                if old["visual_region"] == p["visual_region"]:
                    assert p["x"] == old["x"] and p["y"] == old["y"]
                    holds += 1
            seen[p["object_id"]] = p
    assert holds > 0


def test_long_math_in_scratch_expands_only_when_safe(approved):
    board, execution = approved
    def wide(latex, h):
        return GlyphSize(440 if "sin" in latex else 120, 35, None)
    result = layout_storyboard(board, execution, measure=wide)
    expanded = [s for s in result["scenes"] if s["mode"] == "expanded_scratch"]
    assert expanded
    assert all(p["visual_region"] == "board" for s in expanded
               for p in s["placements"])
    assert all(s["status"] == "ready" for s in expanded)


def test_oversized_math_requests_cut_instead_of_clipping(approved):
    board, execution = approved
    result = layout_storyboard(
        board, execution, measure=lambda latex, h: GlyphSize(100000, 40)
    )
    cut = [s for s in result["scenes"] if s["status"] == "cut_required"]
    assert cut
    assert all(not s["placements"] and not s["transitions"] for s in cut)


def test_stale_contract_and_invalid_metrics_are_rejected(approved):
    board, execution = approved
    wrong = execution.model_copy(update={
        "source_storyboard_sha256": "0" * 64
    })
    with pytest.raises(AdaptiveLayoutError, match="MISMATCH_EXECUTION_PLAN"):
        layout_storyboard(board, wrong, measure=measure)
    with pytest.raises(AdaptiveLayoutError, match="INVALID_GLYPH_METRICS"):
        layout_storyboard(board, execution,
                          measure=lambda latex, h: GlyphSize(float("nan"), 25))


def test_no_preview_on_cut_and_no_partial_files(approved, tmp_path, monkeypatch):
    board, execution = approved
    # Existing real scene may or may not fit; force cut through measured size.
    import animation_engine.adaptive_layout as module
    original = module.layout_storyboard
    def cuts(*args, **kwargs):
        result = original(*args, **kwargs, measure=lambda latex, h: GlyphSize(10000, 35))
        return result
    monkeypatch.setattr(module, "layout_storyboard", cuts)
    with pytest.raises(AdaptiveLayoutError, match="CUT_REQUIRED"):
        render_layout_png(board, execution, event_id="e_end",
                          output_png=tmp_path / "preview.png",
                          output_json=tmp_path / "preview.json")
    assert not list(tmp_path.iterdir())


@pytest.mark.render
def test_real_measure_and_layout_png(approved, tmp_path):
    pytest.importorskip("manim")
    from animation_engine.adaptive_layout import _real_measure
    from animation_engine.mathtex_renderer import MathTexRenderError
    m = _real_measure(r"\frac{x}{2}=1", 720)
    assert m.width_px > 10 and m.height_px > 10
    assert m.equals_x_px is not None and m.equals_x_px > 0
    board, execution = approved
    # A genuine visible event: select one that the true measured layout can fit.
    result = layout_storyboard(board, execution)
    event = next(s["event_id"] for s in result["scenes"]
                 if s["status"] == "ready" and s["placements"])
    png = tmp_path / "layout.png"
    manifest = tmp_path / "layout.json"
    got = render_layout_png(board, execution, event_id=event,
                            output_png=png, output_json=manifest)
    assert png.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert json.loads(manifest.read_text(encoding="utf-8"))["preview_event_id"] == event
    assert got["timing_source"] != "audio_aligned"
