"""V2.6.6 stress coverage: real verified source packages of different math types.

These source/board-state tests do not generate fake voice or claim an AI proof.
Separate native-render CI renders actual LaTeX/Manim scenes and compares
event window boundaries against fully rendered source-authoritative scenes.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from build_multipart_integral_lesson import build_variant as integral
from build_matrix_classroom_lesson import build_variant as matrix
from build_proof_classroom_lesson import build_variant as proof
from animation_engine.adaptive_layout import GlyphSize
from animation_engine.persistent_chalkboard import (
    make_chalkboard_plan,_event_entry_contract,
)
from animation_engine.incremental_render import _event_key
from animation_engine.render_cache import ArtifactCache


@pytest.mark.parametrize("kind,variant",[
    ("integral","A"),("integral","B"),("integral","C"),
    ("matrix","A"),("matrix","B"),("matrix","C"),
    ("proof","A"),("proof","B"),("proof","C"),
])
def test_every_math_type_restores_original_mathtex_board_objects(
        kind,variant,tmp_path):
    if kind=="integral":
        package,board,execution,cues,policy,contract,units,_,_=integral(variant)
        kw={"computation_manifest":contract}
        measure=lambda tex,height:GlyphSize(240,42)
    elif kind=="matrix":
        package,board,execution,cues,policy,contract,units,_=matrix(variant)
        kw={"matrix_manifest":contract}
        measure=lambda tex,height:GlyphSize(210,55)
    else:
        package,board,execution,cues,policy,contract,units=proof(variant)
        kw={"proof_manifest":contract}
        measure=lambda tex,height:GlyphSize(210,47)
    layout=make_chalkboard_plan(
        board,execution,cues,policy,measure=measure,**kw
    )
    assert len(layout["events"])==len(units)
    all_written=set()
    for index,row in enumerate(layout["events"]):
        entry=_event_entry_contract(layout,index)
        prev=layout["events"][index-1] if index else None
        assert entry["visible_block_ids"]==(
            prev["visible_block_ids"] if prev else []
        )
        assert entry["visible_diagram_ids"]==(
            prev.get("visible_diagram_ids",[]) if prev else []
        )
        assert len(entry["visible_block_ids"])==len(set(
            entry["visible_block_ids"]
        ))
        assert set(entry["visible_block_ids"])<=set(entry["block_catalog"])
        all_written.update(
            b["block_id"] for b in row["added_blocks"]
            if not b.get("carry")
        )
    assert all_written
    assert layout["event_count"]==len(units)
    source={
        x["math_object_id"] for x in package["lesson"]["math_objects"]
    }
    assert set(layout["math_written_ids"])==source
    cache=ArtifactCache(tmp_path/"cache")
    stage=SimpleNamespace(
        stage_id=f"{kind}_{variant}",engine="standard",
        storyboard=board.model_dump(mode="json"),
        execution=execution.model_dump(mode="json"),
        cues=cues,policy=policy,special=contract,
        package=package,handoff=(),events=tuple(
            row["event_id"] for row in layout["events"]
        ),
    )
    # Changing speech of one event must not affect cached unrelated event
    # clips. Changing the mathematical source invalidates all related clips.
    schedules={
        row["event_id"]:[{"duration":1.0}]
        for row in layout["events"]
    }
    first=layout["events"][0]["event_id"]
    last=layout["events"][-1]["event_id"]
    baseline=_event_key(
        stage,len(layout["events"])-1,last,
        fps=30,layout_hint=None,
        narration_events=schedules,cache=cache
    )
    schedules[first]=[{"duration":5.0}]
    if first!=last:
        assert baseline==_event_key(
            stage,len(layout["events"])-1,last,
            fps=30,layout_hint=None,
            narration_events=schedules,cache=cache
        )
    stage.execution={**stage.execution,
                     "source_storyboard_sha256":"0"*64}
    assert baseline!=_event_key(
        stage,len(layout["events"])-1,last,
        fps=30,layout_hint=None,
        narration_events=schedules,cache=cache
    )


def test_invalid_board_boundary_never_silently_restored():
    from animation_engine.longboard_plan import LongboardError
    valid={
        "events":[
            {"added_blocks":[{"block_id":"math_a","kind":"math"}],
             "visible_block_ids":["math_a"]},
            {"added_blocks":[],"visible_block_ids":["math_a"]}
        ]
    }
    assert _event_entry_contract(valid,1)["visible_block_ids"]==["math_a"]
    invalid={
        "events":[
            {"added_blocks":[],
             "visible_block_ids":["nonexistent_math_object"]},
            {"added_blocks":[],"visible_block_ids":["nonexistent_math_object"]}
        ]
    }
    with pytest.raises(LongboardError,match="MISSING_ENTRY_BLOCK"):
        _event_entry_contract(invalid,1)
    with pytest.raises(LongboardError,match="EVENT_WINDOW_INVALID"):
        _event_entry_contract(valid,-1)


@pytest.mark.parametrize("kind,variant,minimum_events",[
    ("integral","C",10),
    ("proof","A",9),
    ("proof","C",9),
    ("matrix","A",8),
])
def test_long_multi_event_lessons_are_not_silently_shortened(
        kind,variant,minimum_events):
    if kind=="integral":
        package,board,execution,cues,policy,contract,units,_,_=integral(variant)
        kw={"computation_manifest":contract}
        measure=lambda tex,height:GlyphSize(240,42)
    elif kind=="proof":
        package,board,execution,cues,policy,contract,units=proof(variant)
        kw={"proof_manifest":contract}
        measure=lambda tex,height:GlyphSize(210,47)
    else:
        package,board,execution,cues,policy,contract,units,_=matrix(variant)
        kw={"matrix_manifest":contract}
        measure=lambda tex,height:GlyphSize(210,55)
    layout=make_chalkboard_plan(
        board,execution,cues,policy,measure=measure,**kw
    )
    assert len(layout["events"])>=minimum_events
    assert [x["event_id"] for x in layout["events"]]==[
        "e_"+u["id"] for u in units
    ]
    # Every visible result and carried precondition must remain recoverable
    # at the beginning of all later event clips, even after a page erase.
    for index,row in enumerate(layout["events"]):
        state=_event_entry_contract(layout,index)
        expected=[] if index==0 else layout["events"][index-1][
            "visible_block_ids"
        ]
        assert state["visible_block_ids"]==expected
        assert set(state["visible_block_ids"]) <= set(
            state["block_catalog"]
        )
