"""Real PNG preview tests, using actual pixel content and the real lesson."""
import json
from pathlib import Path

import pytest
manim = pytest.importorskip("manim")
from PIL import Image
from visual_director import build_storyboard
from animation_engine import build_execution_plan
from animation_engine.render_contract import select_math_render_request
from animation_engine.math_preview import MathPreviewError, render_math_preview

manim = pytest.importorskip("manim")
SAMPLE = Path(__file__).resolve().parents[2] / "visual_director" / "examples" / "limit_teaching_package.json"


@pytest.fixture
def objects():
    storyboard = build_storyboard(json.loads(SAMPLE.read_text(encoding="utf-8")))
    execution = build_execution_plan(storyboard)
    target = next(s for s in execution.scenes if "m_d_sin" in s.visible_ids)
    request = select_math_render_request(storyboard, execution, event_id=target.event_id, object_id="m_d_sin")
    return storyboard, execution, request


def test_real_png_with_bounds_and_metadata(objects, tmp_path):
    _, _, request = objects
    png, meta = tmp_path / "math.png", tmp_path / "math.json"
    result = render_math_preview(request, output_png=png, output_json=meta)
    assert result.png_path == png and result.metadata_path == meta
    with Image.open(png) as img:
        assert img.size == (1280, 720)
        rgb = img.convert("RGB")
        assert rgb.getpixel((0, 0)) == (255, 255, 255)
        assert any(sum(rgb.getpixel((x, y))) < 700 for x in range(100, 1150, 7) for y in range(80, 610, 7))
    data = json.loads(meta.read_text(encoding="utf-8"))
    assert data["event_id"] == request.event_id and data["object_id"] == "m_d_sin"
    assert data["latex"] == request.latex
    assert data["source_storyboard_sha256"] == request.source_storyboard_sha256
    assert data["source_step_ids"] == list(request.source_step_ids)
    assert "duration" not in data and "start_second" not in data
    l, t, r, b = result.formula_bounds_px
    rect = request.region
    assert 0 <= l < r <= 1280 and 0 <= t < b <= 720
    assert rect.x * 1280 < l < r < (rect.x + rect.w) * 1280
    assert rect.y * 720 < t < b < (rect.y + rect.h) * 720


def test_overlong_formula_errors_and_creates_no_false_png(objects, tmp_path):
    from dataclasses import replace
    _, _, request = objects
    huge = replace(request, latex=r"\frac{12345678901234567890123456789012345678901234567890}{12345678901234567890123456789012345678901234567890}")
    png, meta = tmp_path / "overflow.png", tmp_path / "overflow.json"
    with pytest.raises(MathPreviewError, match="FORMULA_OVERFLOW"):
        render_math_preview(huge, output_png=png, output_json=meta)
    assert not png.exists() and not meta.exists()


def test_bad_latex_creates_no_success_artifacts(objects, tmp_path):
    from dataclasses import replace
    _, _, request = objects
    bad = replace(request, latex=r"\input{/etc/passwd}")
    png, meta = tmp_path / "bad.png", tmp_path / "bad.json"
    with pytest.raises(MathPreviewError, match="UNSAFE_TEX"):
        render_math_preview(bad, output_png=png, output_json=meta)
    assert not png.exists() and not meta.exists()


def test_cli_preview_renders_real_png_and_plan_still_works(objects, tmp_path):
    from animation_engine.cli import main
    board, execution, request = objects
    storyboard_file, execution_file = tmp_path / "board.json", tmp_path / "execution.json"
    storyboard_file.write_text(board.model_dump_json(), encoding="utf-8")
    execution_file.write_text(execution.model_dump_json(), encoding="utf-8")
    png, meta = tmp_path / "cli.png", tmp_path / "cli.json"
    assert main(["preview-math", "--storyboard", str(storyboard_file),
        "--execution", str(execution_file), "--event-id", request.event_id,
        "--object-id", request.object_id, "--output", str(png),
        "--metrics", str(meta)]) == 0
    assert png.exists() and meta.exists()
    plan_result = tmp_path / "plan.json"
    assert main(["plan", str(storyboard_file), "--output", str(plan_result)]) == 0


def test_cli_rejects_unknown_object(objects, tmp_path):
    from animation_engine.cli import main
    board, execution, request = objects
    a, b = tmp_path / "board.json", tmp_path / "execution.json"
    a.write_text(board.model_dump_json(), encoding="utf-8")
    b.write_text(execution.model_dump_json(), encoding="utf-8")
    assert main(["preview-math", "--storyboard", str(a), "--execution", str(b),
        "--event-id", request.event_id, "--object-id", "missing", "--output",
        str(tmp_path / "bad.png"), "--metrics", str(tmp_path / "bad.json")]) != 0
    assert not (tmp_path / "bad.png").exists()
