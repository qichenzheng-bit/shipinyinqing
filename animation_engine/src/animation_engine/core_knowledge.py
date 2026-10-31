"""Source-bound, reusable mathematical knowledge, not calculation narration.

A 'knowledge' cue is a teacher-verified transferable principle, property,
definition, theorem or formula, with genuine MathTex source and explicit use
in this lesson. It must never be used just to narrate a local simplification.
This checks provenance and category; it does NOT formally prove math truth.
"""
from __future__ import annotations

from .longboard_plan import LongboardError
from .mathtex_renderer import validate_math_latex


_KINDS=frozenset({"principle","theorem","definition","formula","property"})
_OPERATION_ONLY=("本题","先把","把括号","通分","代入","合并","计算括号","提取公因式",
                 "展开平方","整理同类项","下一步","再算")


def checked_core_knowledge(units: list[dict], catalog: dict) -> dict:
    """Validate exactly every authored knowledge cue and its sourced formulae."""
    if (not isinstance(catalog,dict) or set(catalog)!={
            "schema_version","teacher_reviewed","points"}
            or catalog["schema_version"]!="1.0"
            or catalog["teacher_reviewed"] is not True
            or not isinstance(catalog["points"],list)):
        raise LongboardError("CORE_KNOWLEDGE_CATALOG_REQUIRED")
    if not isinstance(units,list):
        raise LongboardError("CORE_KNOWLEDGE_UNITS_INVALID")
    by_event={"e_"+u["id"]:u for u in units
              if isinstance(u,dict) and isinstance(u.get("id"),str)}
    if len(by_event)!=len(units):
        raise LongboardError("CORE_KNOWLEDGE_UNIT_IDS")
    order={key:i for i,key in enumerate(by_event)}
    targets={eid for eid,u in by_event.items() if u.get("phase")=="knowledge"}
    points=catalog["points"]
    if len(points)!=len(targets):
        raise LongboardError("CORE_KNOWLEDGE_COVERAGE")
    seen=set()
    for item in points:
        if (not isinstance(item,dict) or set(item)!={
                "event_id","topic_id","title","kind","formulae","used_in"}):
            raise LongboardError("CORE_KNOWLEDGE_FIELDS")
        eid=item["event_id"]
        if type(eid) is not str or eid not in targets or eid in seen:
            raise LongboardError("CORE_KNOWLEDGE_EVENT_NOT_DECLARED")
        seen.add(eid)
        if (type(item["topic_id"]) is not str or not item["topic_id"].isidentifier()
                or item["kind"] not in _KINDS):
            raise LongboardError("CORE_KNOWLEDGE_KIND")
        title=item["title"]
        if (type(title) is not str or not 2<=len(title)<=19
                or title!=by_event[eid]["heading"]
                or any(term in title for term in _OPERATION_ONLY)):
            raise LongboardError("CORE_KNOWLEDGE_NOT_TRANSFERABLE: "+eid)
        listed=item["formulae"]
        if (not isinstance(listed,list) or not listed
                or any(not isinstance(f,dict) or set(f)!={"object_id","latex"}
                       for f in listed)):
            raise LongboardError("CORE_KNOWLEDGE_FORMULA_REQUIRED")
        source=by_event[eid]["math"]
        expected=["m_"+obj["id"] for obj in source]
        if len({f["object_id"] for f in listed})!=len(listed):
            raise LongboardError("CORE_KNOWLEDGE_DUPLICATE_FORMULA")
        formula_ids=[f["object_id"] for f in listed]
        if formula_ids!=expected[:len(formula_ids)]:
            raise LongboardError("CORE_KNOWLEDGE_FORMULA_MUST_BE_FIRST")
        for f,s in zip(listed,source):
            if f["latex"]!=s["latex"]:
                raise LongboardError("CORE_KNOWLEDGE_FORMULA_SOURCE_MISMATCH")
            validate_math_latex(f["latex"])
        uses=item["used_in"]
        if (not isinstance(uses,list) or not uses
                or any(type(x) is not str or x not in by_event for x in uses)
                or len(set(uses))!=len(uses)):
            raise LongboardError("CORE_KNOWLEDGE_APPLICATION_REQUIRED")
        # Same-event application is allowed for multipart integrals and
        # matrices, but only when other mathematical writes really apply it.
        for target in uses:
            if order[target]<order[eid]:
                raise LongboardError("CORE_KNOWLEDGE_PREMATURE_APPLICATION")
            if order[target]==order[eid] and len(source)==len(listed):
                raise LongboardError("CORE_KNOWLEDGE_NOT_APPLIED")
        # Knowledge is a formula, not merely text attached to a derivation.
        if by_event[eid]["phase"]!="knowledge":
            raise LongboardError("CORE_KNOWLEDGE_NOT_IN_KNOWLEDGE_PHASE")
    if seen!=targets:
        raise LongboardError("CORE_KNOWLEDGE_COVERAGE")
    return catalog
