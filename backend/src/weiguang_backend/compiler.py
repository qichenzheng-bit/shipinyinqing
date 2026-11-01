"""Reviewed candidate -> full V2.7 source-verified classroom package.

One candidate is authored by AI for review and NEVER automatically approved.
The compiler rechecks source coverage, mathematical provenance contracts,
exact board-action audio, V2.7 phase order, and source hashes.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict

from animation_engine.classroom_teaching_units import compile_teaching_units
from animation_engine.classroom_policy import simple_classroom_policy
from animation_engine.unified_classroom_flow import canonical_sha, checked_flow
from animation_engine.spoken_classroom import checked_spoken, _expected_actions


class CurriculumCandidate(BaseModel):
    model_config=ConfigDict(extra="forbid")
    units: list[dict]=Field(min_length=2,max_length=60)
    knowledge_catalog: dict | None=None
    narration: dict[str,dict]
    lesson_contract: dict


def write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(
        json.dumps(data,ensure_ascii=False,indent=2)+"\n",
        encoding="utf-8",
    )


def draft_curriculum(
    problem: str, reference_solution: str,
    teacher_package: dict, candidate_path: Path,
    *, provider=None,
) -> dict:
    """Use configured teacher LLM to suggest draft only (no review claim)."""
    from math_teacher.provider import OpenAICompatibleJsonModel
    provider=provider if provider is not None else OpenAICompatibleJsonModel()
    instructions = """你是考研数学真实课堂视频课程编排者。参考已核验数学教师 A/B/C 的
源结构，为同一道题生成完整 V2.7 课程候选数据，绝不能替换题目/解法或省略必要步骤。
返回匹配 CurriculumCandidate 的严格 JSON：
units: 2~60 个有序教学单元，每个字段必须严格是
{id,event_type,phase,heading,detail,goal,pause_seconds,write_seconds,math}，
math 是 [{id,latex,reason},...]，只使用可信的规范数学 LaTeX；
首单元 observe，之后 strategy、knowledge、calculate/application、
conclusion，最后 summary；knowledge 必须先讲再用，适当插入 pitfall。
knowledge_catalog: 源可证明的可迁移知识点目录，必须与 units 对应；
narration: key 为 e_<unit_id>，value 为
{note: 自然口播文本,math_intro: 公式写出前读的话,
 math_readings: {m_<math_id>: 完整规范中文数学读音},
 math_after: 公式显示后继续讲解的话}。
严格以动作对应的数学和实际口播为准，不能让教师读渲染器操作说明。
lesson_contract: V2.7 规定的完整开场、策略、知识点、易错点、结论、总结核验对象；
要与 narration 完全一致。开场必须完整读出原题，数学部分要有完整读音。
所有中文表达应自然，不要伪造结论或人工审核成功。输出仅 JSON。
"""
    input_data={
        "problem":problem,"reference_solution":reference_solution,
        "teacher_package":teacher_package,
    }
    candidate=provider.generate(
        stage="D",system=instructions,
        user_json=json.dumps(input_data,ensure_ascii=False),
        schema=CurriculumCandidate,
    )
    payload=candidate.model_dump(mode="json")
    from animation_engine.iterative_edit_ops import atomic_json
    atomic_json(Path(candidate_path),payload)
    return {
        "status":"curriculum_candidate_waiting_review",
        "units":len(payload["units"]),
    }


def compile_reviewed_curriculum(
    *, problem: str, reference_solution: str,
    candidate: CurriculumCandidate | dict, output: Path,
    reviewer: str, confirmed: bool,
) -> dict:
    """Emit usable unified-flow/spoken V2.7 package only after explicit review."""
    if confirmed is not True or not isinstance(reviewer,str) or not reviewer.strip():
        raise ValueError("COURSE_COMPILATION_REQUIRES_EXPLICIT_TEACHER_REVIEW")
    spec=CurriculumCandidate.model_validate(candidate)
    root=Path(output)
    if root.exists():
        raise ValueError("COURSE_SOURCE_ALREADY_PRESENT")
    # Validate in an isolated staging folder; don't publish partial math sources.
    import tempfile, shutil
    with tempfile.TemporaryDirectory(prefix="weiguang-course-") as tmp:
        staging=Path(tmp)/"package"
        staging.mkdir()
        package, board, execution, cues=compile_teaching_units(
            problem=problem,reference_solution=reference_solution,
            units=spec.units,teacher_reviewed=True,
            knowledge_catalog=spec.knowledge_catalog,
        )
        stage=staging/"main"
        files={
            "teaching_package.json":package,
            "storyboard.json":board.model_dump(mode="json"),
            "execution.json":execution.model_dump(mode="json"),
            "teacher_approved_cues.json":cues,
            "page_policy.json":simple_classroom_policy(),
            "teaching_units.json":{"schema_version":"1.0","units":spec.units},
        }
        if spec.knowledge_catalog is not None:
            files["core_knowledge.json"]=spec.knowledge_catalog
        for filename, content in files.items():
            write_json(stage/filename,content)
        lesson_slug="lesson_"+hashlib.sha256(problem.encode("utf-8")).hexdigest()[:12]
        write_json(staging/"unified_flow.json",{
            "schema_version":"1.0",
            "mode":"unified_classroom_flow",
            "teacher_reviewed":True,
            "lesson_id":lesson_slug,
            "problem":problem,
            "reference_solution_sha256":canonical_sha(reference_solution),
            "stages":[{
                "stage_id":"main","engine":"standard","directory":"main",
                "package_sha256":package["validated_content_sha256"],
                "source_storyboard_sha256":execution.source_storyboard_sha256,
                "event_ids":[e.event_id for e in board.scenes],
                "handoff":[],
            }],
        })
        flow=checked_flow(staging/"unified_flow.json")
        events=[]
        for event in _expected_actions(flow,adaptive=False):
            eid=event["event_id"]
            narration=spec.narration.get(eid)
            if not isinstance(narration,dict):
                raise ValueError(f"COURSE_NARRATION_MISSING: {eid}")
            if set(narration)!={"note","math_intro","math_readings","math_after"}:
                raise ValueError(f"COURSE_NARRATION_FIELDS: {eid}")
            readings=narration["math_readings"]
            if not isinstance(readings,dict):
                raise ValueError(f"COURSE_MATH_READINGS_MISSING: {eid}")
            spans=[]
            for kind,obj,tex in event["actions"]:
                if kind=="note":
                    text=narration["note"]
                    if not isinstance(text,str) or not text.strip():
                        raise ValueError(f"COURSE_NOTE_TEXT_MISSING: {eid}")
                    parts=[{"kind":"text","value":text}]
                elif kind=="math":
                    intro=narration["math_intro"]
                    reading=readings.get(obj)
                    after=narration["math_after"]
                    if (not isinstance(intro,str) or not intro.strip()
                            or not isinstance(reading,str) or not reading.strip()
                            or not isinstance(after,str)):
                        raise ValueError(f"COURSE_MATH_READING_MISSING: {eid}/{obj}")
                    parts=[
                        {"kind":"text","value":intro},
                        {"kind":"math","latex":tex,"reading":reading},
                    ]
                    if after.strip():
                        parts.append({"kind":"text","value":after})
                elif kind=="diagram":
                    raise ValueError("COURSE_DIAGRAM_REQUIRES_DEDICATED_APPROVED_DIAGRAM")
                else:
                    raise ValueError(f"COURSE_UNSUPPORTED_ACTION: {kind}")
                spans.append({"kind":kind,"object_id":obj,"parts":parts})
            events.append({
                "stage_id":"main","event_id":eid,
                "pedagogical_cue_covered":True,
                "spans":spans,
                "question_read_aloud":len(events)==0,
                "question_source_sha256":(
                    canonical_sha(problem) if not events else None
                ),
            })
        # Schema-and-semantic V2.7 source coverage checks happen here, not
        # after publication. Any AI inconsistency rejects compilation.
        source={
            "schema_version":"1.0",
            "mode":"verified_spoken_classroom",
            "teacher_reviewed":True,
            "source_flow_sha256":flow.source_sha256,
            "voice":"zh-CN-YunxiNeural",
            "speech_rate":"+1%",
            "lesson_contract":spec.lesson_contract,
            "events":events,
        }
        write_json(staging/"spoken_classroom.json",source)
        checked=checked_spoken(staging/"spoken_classroom.json",adaptive=False)
        from animation_engine.v27_teacher_contract import export_spoken_script
        export_spoken_script(
            checked,output_json=staging/"lesson_script.json",
            output_md=staging/"lesson_script.md",
            source_document=source,
            source_path=staging/"spoken_classroom.json",
        )
        # User explicitly approved the *candidate*, not yet the complete
        # exported script; a separate V2.7 script approval follows.
        root.parent.mkdir(parents=True,exist_ok=True)
        shutil.copytree(staging,root)
        return {
            "status":"script_pending",
            "events":len(events),
            "reviewer":reviewer,
            "source_spoken_sha256":checked.source_sha256,
        }
