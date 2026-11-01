"""CLI smoke tests using the real visual director contract, not fabricated video."""
import json
from pathlib import Path

from visual_director import build_storyboard

from animation_engine.cli import main


SAMPLE = Path(__file__).resolve().parents[2] / "visual_director" / "tests" / "fixtures" / "limit_teaching_package.json"


def test_plan_command_writes_execution_json(tmp_path):
    board = build_storyboard(json.loads(SAMPLE.read_text(encoding="utf-8")))
    source = tmp_path / "storyboard.json"
    target = tmp_path / "execution.json"
    source.write_text(board.model_dump_json(), encoding="utf-8")
    assert main(["plan", str(source), "--output", str(target)]) == 0
    result = json.loads(target.read_text(encoding="utf-8"))
    assert len(result["scenes"]) == 19
    assert result["sync_status"] == "semantic_anchors_only"
    assert "duration" not in target.read_text(encoding="utf-8")


def test_invalid_plan_is_not_written(tmp_path):
    source, target = tmp_path / "invalid.json", tmp_path / "execution.json"
    source.write_text('{"schema_version":"9.0"}', encoding="utf-8")
    assert main(["plan", str(source), "--output", str(target)]) != 0
    assert not target.exists()
