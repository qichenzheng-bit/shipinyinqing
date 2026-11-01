"""Review-only end-to-end integration of a new course compiler with strict V2.7.

No AI requests, no speech or movie rendering; only real source and math gates.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/
    "animation_engine"/"tests"/"fixtures"))
from build_novel_substitution_integral import (
    build, UNITS, KNOWLEDGE_CATALOG, NARRATION, READINGS, AFTER_MATH,
)
from animation_engine.spoken_classroom import checked_spoken
from animation_engine.iterative_edit_ops import validate_teaching_package
from animation_engine.v27_teacher_contract import (
    approve_prerender_script, require_prerender_script,
)
from weiguang_backend.compiler import compile_reviewed_curriculum


def curriculum_fixture(root):
    source=root/"original"
    build(source)
    package=json.loads(
        (source/"main"/"teaching_package.json").read_text(encoding="utf-8")
    ) if (source/"main"/"teaching_package.json").exists() else json.loads(
        (source/"integration"/"teaching_package.json").read_text(encoding="utf-8")
    )
    contract=json.loads(
        (source/"spoken_classroom.json").read_text(encoding="utf-8")
    )["lesson_contract"]
    narration={}
    for unit in UNITS:
        eid="e_"+unit["id"]
        narration[eid]={
            "note":NARRATION.get((eid,"note"),""),
            "math_intro":NARRATION.get((eid,"math"),""),
            "math_readings":{
                "m_"+item["id"]:READINGS["m_"+item["id"]]
                for item in unit["math"]
            },
            "math_after":AFTER_MATH.get(eid,""),
        }
    candidate={
        "units":UNITS,
        "knowledge_catalog":KNOWLEDGE_CATALOG,
        "narration":narration,
        "lesson_contract":contract,
    }
    return package["source"],candidate


def test_reviewed_course_compiles_to_real_source_verified_v27(tmp_path):
    source,candidate=curriculum_fixture(tmp_path)
    output=tmp_path/"compiled"
    with pytest.raises(ValueError,match="COURSE_COMPILATION_REQUIRES"):
        compile_reviewed_curriculum(
            problem=source["problem"],
            reference_solution=source["reference_solution"],
            candidate=candidate,output=output,
            reviewer="math teacher",confirmed=False,
        )
    assert not output.exists()
    outcome=compile_reviewed_curriculum(
        problem=source["problem"],
        reference_solution=source["reference_solution"],
        candidate=candidate,output=output,
        reviewer="math teacher",confirmed=True,
    )
    assert outcome["events"]==10
    assert outcome["status"]=="script_pending"
    checked=validate_teaching_package(output,adaptive=False)
    assert checked["spoken_actions"]>10
    contract=checked_spoken(output/"spoken_classroom.json",adaptive=False)
    with pytest.raises(Exception,match="HUMAN_APPROVAL_REQUIRED"):
        require_prerender_script(contract,output/"spoken_classroom.json")
    approve_prerender_script(
        contract,output/"spoken_classroom.json",
        reviewer="math teacher",confirmed=True,
    )
    document=require_prerender_script(
        contract,output/"spoken_classroom.json",
    )
    assert document["acceptance"]["contract_version"]=="2.7"
    assert len(document["events"])==10


def test_reviewed_compiler_rejects_unvalidated_math_without_source(tmp_path):
    source,candidate=curriculum_fixture(tmp_path)
    candidate["units"][3]["math"][0]["latex"]="\\write18{malicious}"
    with pytest.raises(Exception,match="UNSAFE_TEX"):
        compile_reviewed_curriculum(
            problem=source["problem"],
            reference_solution=source["reference_solution"],
            candidate=candidate,output=tmp_path/"blocked",
            reviewer="math teacher",confirmed=True,
        )
    assert not (tmp_path/"blocked").exists()
