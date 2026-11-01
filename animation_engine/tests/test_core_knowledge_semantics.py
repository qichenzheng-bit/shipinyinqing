"""Cross-stage regression: knowledge = reusable, sourced mathematical fact.

No '核心知识点' may be just an instruction to simplify, expand or substitute.
This is provenance/type checking, not a claim of formal mathematical proof.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"fixtures"))

from animation_engine.classroom_teaching_units import compile_teaching_units
from animation_engine.core_knowledge import checked_core_knowledge
from animation_engine.longboard_plan import LongboardError
from animation_engine.mathtex_renderer import validate_math_latex
from build_proof_classroom_lesson import build_variant as proof
from build_proof_classroom_lesson import export_variant as export_proof
from build_proof_classroom_lesson import _knowledge_catalog as proof_catalog
from animation_engine.proof_chain import checked_proof_chain
from build_fresh_taylor_classroom import (
    build_new as build_taylor,
    UNITS as TAYLOR_UNITS,
    _knowledge_catalog as taylor_catalog,
)
from build_multipart_integral_lesson import build_variant as integrals
from build_multipart_integral_lesson import export_variant as export_integrals
from build_matrix_classroom_lesson import build_variant as matrix
from build_matrix_classroom_lesson import export_variant as export_matrix
from build_complete_ode_lesson import UNITS as ODE_UNITS


@pytest.mark.parametrize("variant,rule,event",[
    ("A",r"P(k)\Longrightarrow P(k+1)","e_knowledge_induction"),
    ("B",r"u^2+v^2+w^2\geq0","e_knowledge_square"),
    ("C",r"f(x)=A(x-h)^2+k","e_knowledge_quadratic"),
])
def test_real_proof_knowledge_not_local_arithmetic(variant,rule,event):
    pkg,board,execution,cues,policy,manifest,units=proof(variant)
    audited=proof_catalog(variant,units)
    proof_contract=checked_proof_chain(manifest,board,execution)
    for point in audited["points"]:
        mathids={f["object_id"] for f in point["formulae"]}
        for event_id in point["used_in"]:
            assert mathids.intersection(
                proof_contract.for_event(event_id).cites
            ), (variant,event_id)
    catalog=[u for u in units if u["phase"]=="knowledge"]
    assert len(catalog)==1, "No procedural proof stage should be colored knowledge"
    knowledge=catalog[0]
    assert event=="e_"+knowledge["id"]
    assert rule in knowledge["math"][0]["latex"]
    assert len(knowledge["math"])>=1
    for obj in knowledge["math"]:
        validate_math_latex(obj["latex"])
    by_id={c["event_id"]:c for c in cues["events"]}
    assert by_id[event]["phase"]=="knowledge"
    sources={m["math_object_id"]:m["latex"] for m in pkg["lesson"]["math_objects"]}
    assert [sources["m_"+item["id"]] for item in knowledge["math"]]==[
        item["latex"] for item in knowledge["math"]
    ]
    # Merely 'write the hypothesis', 'simplify brackets', 'make a difference'
    # or 'complete the square in this problem' belongs to calculations.
    for u in units:
        if u["id"] in (
            "hypothesis","lemma","difference","squares","square"
        ):
            assert u["phase"]!="knowledge"


@pytest.mark.parametrize("variant",["A","B","C"])
def test_exported_proof_knowledge_is_auditable_and_used(tmp_path,variant):
    folder=tmp_path/variant
    export_proof(folder,variant)
    catalog=json.loads((folder/"core_knowledge.json").read_text(encoding="utf-8"))
    units=json.loads((folder/"teaching_units.json").read_text(encoding="utf-8"))["units"]
    checked_core_knowledge(units,catalog)
    assert len(catalog["points"])==1
    point=catalog["points"][0]
    assert point["kind"] in ("principle","property","theorem","definition","formula")
    assert point["used_in"]
    assert all(f["latex"] for f in point["formulae"])
    assert len(point["formulae"])==2


@pytest.mark.parametrize("variant,expected",[("A",3),("B",4),("C",5)])
def test_integral_knowledge_is_real_integration_formula_and_used(tmp_path,variant,expected):
    folder=tmp_path/variant
    export_integrals(folder,variant)
    catalog=json.loads((folder/"core_knowledge.json").read_text(encoding="utf-8"))
    units=json.loads((folder/"teaching_units.json").read_text(encoding="utf-8"))["units"]
    assert len(catalog["points"])==expected
    checked_core_knowledge(units,catalog)
    for point in catalog["points"]:
        assert point["kind"]=="formula"
        assert point["formulae"][0]["latex"].startswith(r"\int")
        assert point["used_in"]==[point["event_id"]]
        assert not any(term in point["title"] for term in ("通分","化简","代入","提取"))


@pytest.mark.parametrize("variant",["A","B","C"])
def test_matrix_knowledge_is_a_principle_not_one_row_operation(tmp_path,variant):
    folder=tmp_path/variant
    export_matrix(variant,folder)
    catalog=json.loads((folder/"core_knowledge.json").read_text(encoding="utf-8"))
    units=json.loads((folder/"teaching_units.json").read_text(encoding="utf-8"))["units"]
    checked_core_knowledge(units,catalog)
    point=catalog["points"][0]
    assert point["event_id"]=="e_intro"
    assert point["used_in"]==["e_intro","e_step1"]
    assert point["formulae"][0]["object_id"]=="m_intro_rule"
    assert point["kind"]=="property"


def test_taylor_knowledge_is_genuine_maclaurin_formulas_not_truncation_instruction():
    pkg,board,execution,cues,policy=build_taylor()
    catalog=taylor_catalog()
    checked_core_knowledge(TAYLOR_UNITS,catalog)
    point=catalog["points"][0]
    assert point["title"]=="常用麦克劳林展开公式"
    assert {f["object_id"] for f in point["formulae"]}=={
        "m_sin","m_cosdiff","m_invcos"
    }
    assert point["used_in"]==["e_product","e_quotient"]


def test_old_ode_derivation_no_longer_mislabeled_core_knowledge():
    derive=next(u for u in ODE_UNITS if u["id"]=="derive")
    assert derive["phase"]=="calculate"
    assert not any(u["phase"]=="knowledge" for u in ODE_UNITS)


def test_global_teacher_compiler_rejects_knowledge_without_formula_catalog():
    pkg,board,execution,cues,policy,manifest,units=proof("A")
    with pytest.raises(LongboardError,match="CORE_KNOWLEDGE_CATALOG_REQUIRED"):
        compile_teaching_units(
            problem=pkg["source"]["problem"],
            reference_solution=pkg["source"]["reference_solution"],
            units=units,teacher_reviewed=True
        )


@pytest.mark.parametrize("damage,expected",[
    ("formula","CORE_KNOWLEDGE_FORMULA_SOURCE_MISMATCH"),
    ("not_reusable","CORE_KNOWLEDGE_NOT_TRANSFERABLE"),
    ("future","CORE_KNOWLEDGE_APPLICATION_REQUIRED"),
    ("premature","CORE_KNOWLEDGE_PREMATURE_APPLICATION"),
    ("missing","CORE_KNOWLEDGE_COVERAGE"),
    ("not_applied","CORE_KNOWLEDGE_NOT_APPLIED"),
])
def test_knowledge_misuse_fails_closed(tmp_path,damage,expected):
    dest=tmp_path/"A"
    export_proof(dest,"A")
    units=json.loads((dest/"teaching_units.json").read_text())["units"]
    base=json.loads((dest/"core_knowledge.json").read_text())
    bad=copy.deepcopy(base)
    point=bad["points"][0]
    if damage=="formula":
        point["formulae"][0]["latex"]="1=2"
    elif damage=="not_reusable":
        u=next(u for u in units if "e_"+u["id"]==point["event_id"])
        point["title"]=u["heading"]="把括号通分再化简"
    elif damage=="future":
        point["used_in"]=[]
    elif damage=="premature":
        point["used_in"]=["e_setup"]
    elif damage=="missing":
        bad["points"]=[]
    elif damage=="not_applied":
        point["used_in"]=["e_knowledge_induction"]
    with pytest.raises(LongboardError,match=expected):
        checked_core_knowledge(units,bad)
