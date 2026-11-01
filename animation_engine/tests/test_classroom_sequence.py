"""Classroom sequence boundaries must be deterministic before rendering."""
import pytest
from visual_director.models import StoryboardPlan, HeaderPlan
from animation_engine.adaptive_layout import AdaptiveLayoutError
from animation_engine.classroom_sequence import render_classroom_sequence


def test_nonconsecutive_sequence_rejected_without_render(tmp_path):
    class SceneStub:
        def __init__(self, event_id): self.event_id=event_id
    # The function validates a real storyboard before any rendering.
    import json
    from pathlib import Path
    from visual_director.director import build_storyboard
    source=Path(__file__).resolve().parents[2] / "visual_director/examples/limit_teaching_package.json"
    board=build_storyboard(json.loads(source.read_text(encoding="utf-8")))
    path=tmp_path/"sequence.mp4"
    with pytest.raises(AdaptiveLayoutError,match="NONCONSECUTIVE_EVENTS"):
        render_classroom_sequence(board,{},event_ids=["e_read","e_common","e_k_eqv"],
            output_mp4=path,output_json=tmp_path/"sequence.json")
    assert not path.exists()


def test_repeated_ids_rejected_without_render(tmp_path):
    import json
    from pathlib import Path
    from visual_director.director import build_storyboard
    source=Path(__file__).resolve().parents[2] / "visual_director/examples/limit_teaching_package.json"
    board=build_storyboard(json.loads(source.read_text(encoding="utf-8")))
    with pytest.raises(AdaptiveLayoutError,match="SEQUENCE_EVENTS"):
        render_classroom_sequence(board,{},event_ids=["e_read","e_read","e_common"],
            output_mp4=tmp_path/"movie.mp4",output_json=tmp_path/"movie.json")
