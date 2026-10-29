import json
import pytest
from math_teacher.pipeline import MathTeacherPipeline, PipelineValidationError
from math_teacher.models import Understanding, MathCheckRequest
from conftest import FakeProvider


def test_end_to_end_teacher_only(source, understanding, plan, draft):
    fake=FakeProvider(understanding,plan,draft)
    result=MathTeacherPipeline(fake).run(source)
    assert result.validation.status=="ready_with_limits"
    assert len(result.lesson.lesson_events)==5
    assert [s.speech_unit_id for s in result.subtitles] == ["u_"+e.event_id for e in result.lesson.lesson_events]
    assert result.subtitles[0].parts == result.lesson.speech_units[0].parts
    assert [c[0] for c in fake.calls]==["A","B","C"]
    assert result.input_sha256 and len(result.input_sha256)==64
    assert json.loads(fake.calls[0][2])["source"]["solution_segments"][0]["source_id"]=="solution:0"
    assert "参考解析" in fake.calls[0][1]


def test_reject_fabricated_source_before_planning(source, understanding, plan, draft):
    understanding.solution_steps[0].source_refs=["fake:42"]
    fake=FakeProvider(understanding,plan,draft)
    with pytest.raises(PipelineValidationError) as e:
        MathTeacherPipeline(fake).run(source)
    assert e.value.stage=="A"
    assert any(i.code=="UNKNOWN_SOURCE" for i in e.value.report.issues)
    assert len(fake.calls)==1


def test_reject_invalid_knowledge_order(source, understanding, plan, draft):
    plan.teaching_events[1],plan.teaching_events[2]=plan.teaching_events[2],plan.teaching_events[1]
    fake=FakeProvider(understanding,plan,draft)
    with pytest.raises(PipelineValidationError) as e:
        MathTeacherPipeline(fake).run(source)
    assert e.value.stage=="B"
    assert any(i.code=="INVALID_KNOWLEDGE_SEQUENCE" for i in e.value.report.issues)


def test_reject_unbound_board(source, understanding, plan, draft):
    draft.board_actions[0].speech_unit_id="missing"
    fake=FakeProvider(understanding,plan,draft)
    with pytest.raises(PipelineValidationError) as e:
        MathTeacherPipeline(fake).run(source)
    assert e.value.stage=="C"
    assert any(i.code=="UNSYNCED_BOARD" for i in e.value.report.issues)


def _add_derived_step(understanding, plan, draft):
    derived=understanding.solution_steps[0].model_copy(deep=True)
    derived.step_id="s2"
    derived.origin="derived"
    derived.depends_on=["s1"]
    derived.verification_status="pending_check"
    understanding.solution_steps.append(derived)
    plan.teaching_events[3].source_step_ids=["s1","s2"]
    plan.reference_step_coverage["s2"]=["e_derive"]
    draft.lesson_events[3].source_step_ids=["s1","s2"]
    return understanding, plan, draft


def test_derived_step_requires_review(source, understanding, plan, draft):
    understanding,plan,draft=_add_derived_step(understanding,plan,draft)
    fake=FakeProvider(understanding,plan,draft)
    with pytest.raises(PipelineValidationError) as e:
        MathTeacherPipeline(fake).run(source)
    assert e.value.stage=="A" and e.value.report.status=="needs_review"
    result=MathTeacherPipeline(FakeProvider(understanding,plan,draft)).run(source,allow_needs_review=True)
    assert result.validation.status=="needs_review"


def test_math_check_verified_polynomial_identity(source, understanding, plan, draft):
    understanding,plan,draft=_add_derived_step(understanding,plan,draft)
    understanding.solution_steps[-1].input_expressions = ["sin(x)**2-x**2"]
    understanding.solution_steps[-1].output_expressions = ["(sin(x)-x)*(sin(x)+x)"]
    understanding.check_requests=[MathCheckRequest(check_id="c1",step_id="s2",kind="algebraic_identity",
        lhs_expr="sin(x)**2-x**2", rhs_expr="(sin(x)-x)*(sin(x)+x)", conditions=[])]
    understanding=Understanding.model_validate(understanding.model_dump())
    result=MathTeacherPipeline(FakeProvider(understanding,plan,draft)).run(source)
    assert result.validation.math_checks[0].status=="verified"
    assert result.validation.status=="ready_with_limits"


def test_input_empty_blocked(source, understanding, plan, draft):
    source.problem=" "
    fake=FakeProvider(understanding,plan,draft)
    with pytest.raises(PipelineValidationError) as e:
        MathTeacherPipeline(fake).run(source)
    assert e.value.stage=="input"
    assert fake.calls==[]
