"""Regression rules for the user-approved natural Chinese teacher style.

Pure source/script tests only: never invoke Edge TTS, Manim or video encoding.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from animation_engine.spoken_audio import split_natural_phrases
from build_novel_substitution_integral import UNITS, NARRATION, AFTER_MATH, READINGS


def test_opening_directly_reads_the_question_without_announcing_a_reading():
    intro = NARRATION["e_intro", "note"] + NARRATION["e_intro", "math"]
    assert intro.startswith("同学们大家好，我们先来看一下这道定积分题。")
    assert intro.endswith("题目要求计算：")
    assert "我们来读一下" not in intro
    assert "把题目读" not in intro
    assert "我们把题目中的积分" not in intro
    assert "从零到二" in READINGS["m_intro"]
    assert "x 平方次幂" in READINGS["m_intro"]


def test_derivative_observation_precedes_the_method_and_its_name():
    first = NARRATION["e_strategy", "note"]
    before_math = NARRATION["e_strategy", "math"]
    relation = READINGS["m_strategy"]
    after_math = AFTER_MATH["e_strategy"]
    assert "换元法" not in (first + before_math + relation)
    assert "x 平方" in first
    assert "二 x" in first
    assert "x 平方对 x 求导" in relation
    assert "换元法" in after_math
    assert "导数同时出现" in after_math
    assert "为什么考虑换元法呢" not in (first + before_math + after_math)


def test_full_necessary_calculation_remains_and_recap_writes_no_new_formula():
    by_id = {u["id"]: u for u in UNITS}
    assert by_id["primitive"]["math"][0]["latex"] == r"I=\left[e^u\right]_0^4"
    assert by_id["evaluate"]["math"][0]["latex"] == r"I=e^4-e^0"
    assert by_id["conclusion"]["math"][0]["latex"] == r"I=e^4-1"
    assert by_id["summary"]["math"] == []
    assert "e 的零次方等于一" in NARRATION["e_conclusion", "note"]
    assert "上限" in NARRATION["e_pitfall", "note"]
    assert "积分限" in NARRATION["e_summary", "note"] or "上下限" in NARRATION["e_summary", "note"]


def test_all_authored_teacher_clauses_are_safe_for_natural_phrase_projection():
    # Unlike real TTS, this does not synthesize sound or render media.
    # Fail now rather than letting a later real-voice job cut a Chinese word.
    for event, value in [*NARRATION.items(), *AFTER_MATH.items()]:
        assert len(value) <= 170, (event, len(value))
        clauses = split_natural_phrases(value)
        assert "".join(clauses) == value
        assert all(len(clause) <= 23 for clause in clauses), event
