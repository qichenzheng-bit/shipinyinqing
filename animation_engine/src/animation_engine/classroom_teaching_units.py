"""Teacher-authored *pedagogical units* -> source-verified classroom package.

A unit is an entire reasoning goal, not a single LaTeX expression.
One lesson event may contain 2-6 ordered mathematical writes and only ONE
teaching cue. Critical derivations can therefore remain together on the
blackboard, and natural page erasure cannot separate their internal steps.
This compiler never generates mathematical reasoning or invents narration.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from visual_director.director import build_storyboard
from visual_director.models import DiagramSpec, DirectorOptions
from .planner import build_execution_plan
from .classroom_cues import PHASES
from .longboard_plan import LongboardError
from .mathtex_renderer import validate_math_latex


def _hash(value: dict) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def compile_teaching_units(*, problem: str, reference_solution: str,
                           units: list[dict[str,Any]],
                           teacher_reviewed: bool = False,
                           knowledge_catalog: dict | None = None,
                           diagram_specs: list[dict] | None = None) -> tuple:
    """Preserve authored math/wording and bind every source object to a unit.

    Units:
      {id, event_type, phase, heading, detail, goal,
       pause_seconds, write_seconds,
       math: [{id,latex,reason},...]}
    """
    # Integrity hashes do not prove mathematical truth. The manual fixture
    # compiler must not label arbitrary imported/AI-generated formulas ready.
    # This explicit approval is a trust-boundary assertion by the caller;
    # it is NOT an automated mathematical verification.
    if teacher_reviewed is not True:
        raise LongboardError("TEACHING_UNITS_REQUIRES_EXPLICIT_TEACHER_REVIEW")
    if (not isinstance(problem,str) or not problem.strip()
            or not isinstance(reference_solution,str) or not reference_solution.strip()
            or not isinstance(units,list) or not 2<=len(units)<=60):
        raise LongboardError("TEACHING_UNITS_SOURCE_INVALID")
    # Globally enforce semantic separation: a purple "核心知识点" must
    # name a transferable fact and actually write its reviewed MathTex,
    # never merely narrate this problem's simplification.
    if knowledge_catalog is not None or any(
            u.get("phase")=="knowledge" for u in units if isinstance(u,dict)):
        from .core_knowledge import checked_core_knowledge
        checked_core_knowledge(units,knowledge_catalog)
    required={"id","event_type","phase","heading","detail","goal",
              "pause_seconds","write_seconds","math"}
    step_keys={"id","latex","reason"}
    seen_units=set()
    seen_math=set()
    source={
        "problem":problem,"reference_solution":reference_solution,
        "problem_segments":[{"source_id":"problem:0","text":problem,"kind":"problem"}],
        "solution_segments":[{"source_id":"solution:0","text":reference_solution,
                              "kind":"solution"}],
    }
    teacher=[]
    lesson=[]
    objects=[]
    speech=[]
    board_actions=[]
    animations=[]
    captions=[]
    cues=[]
    for i,unit in enumerate(units,1):
        if not isinstance(unit,dict) or set(unit)!=required:
            raise LongboardError(f"TEACHING_UNIT_FIELDS: {i}")
        uid=unit["id"]
        if (not isinstance(uid,str) or not uid.isidentifier() or
                uid in seen_units):
            raise LongboardError(f"TEACHING_UNIT_ID: {uid}")
        seen_units.add(uid)
        event_id="e_"+uid
        if (unit["phase"] not in PHASES or
                not isinstance(unit["event_type"],str) or
                not unit["event_type"].isidentifier()):
            raise LongboardError(f"TEACHING_UNIT_ROLE: {uid}")
        for field,limit in (("heading",19),("detail",58),("goal",90)):
            value=unit[field]
            if (not isinstance(value,str) or not value.strip()
                    or len(value)>limit):
                raise LongboardError(f"TEACHING_UNIT_WORDING: {uid}/{field}")
        # These counts are not animation steps. One pedagogical unit includes
        # as many genuine computation steps as necessary, up to screen-fit.
        steps=unit["math"]
        if (not isinstance(steps,list) or len(steps)>6 or
                (not steps and unit["phase"]!="summary")):
            raise LongboardError(f"TEACHING_UNIT_MATH_COVERAGE: {uid}")
        # A pure spoken summary is a genuine event: it introduces no new maths.
        # Formula count is NOT a proxy for teaching quality: a meaningful
        # insight can be one line, while a difficult derivation needs many.
        # The authored goal + per-line reasoning remain mandatory. A separate
        # review checks whether unrelated standalone events can be merged.
        if not 1<=unit["pause_seconds"]<=4.5 or not .6<=unit["write_seconds"]<=2.2:
            raise LongboardError(f"TEACHING_UNIT_PACING: {uid}")
        math_ids=[]
        board_ids=[]
        all_steps=[]
        semantic_parts=[{"kind":"text",
                         "value":unit["heading"]+"。"+unit["detail"],
                         "reading_intent":None}]
        for j,item in enumerate(steps,1):
            if not isinstance(item,dict) or set(item)!=step_keys:
                raise LongboardError(f"TEACHING_MATH_FIELDS: {uid}/{j}")
            mid=item["id"]
            if (not isinstance(mid,str) or not mid.isidentifier()
                    or mid in seen_math):
                raise LongboardError(f"TEACHING_MATH_ID: {mid}")
            seen_math.add(mid)
            latex=item["latex"]
            validate_math_latex(latex)
            why=item["reason"]
            if not isinstance(why,str) or not why.strip():
                raise LongboardError(f"TEACHING_MATH_REASON_MISSING: {uid}/{mid}")
            math_id="m_"+mid
            step_id=f"s{i}_{j}"
            action_id="b_"+mid
            math_ids.append(math_id)
            all_steps.append(step_id)
            board_ids.append(action_id)
            objects.append({"math_object_id":math_id,"latex":latex,
                            "source_step_ids":[step_id]})
            board_actions.append({
                "board_action_id":action_id,"event_id":event_id,
                "speech_unit_id":"u_"+uid,
                "math_object_id":math_id,"action":"write",
                "semantic_reason":why,
            })
            semantic_parts.append({"kind":"math","value":latex,
                                   "reading_intent":"语音层按规范数学读音解释"})
        teacher.append({
            "event_id":event_id,"event_type":unit["event_type"],
            "source_step_ids":all_steps,"knowledge_binding_ids":[],
            "teaching_goal":unit["goal"],
            "intended_board_content":[x["latex"] for x in steps],
            "mathematical_progression":unit["detail"],
        })
        lesson.append({
            "event_id":event_id,"source_step_ids":all_steps,
            "knowledge_binding_ids":[],"speech_unit_ids":["u_"+uid],
            "board_action_ids":board_ids,"animation_intent_ids":["a_"+uid],
        })
        speech.append({"speech_unit_id":"u_"+uid,"event_id":event_id,
                       "parts":semantic_parts})
        animations.append({"animation_id":"a_"+uid,"event_id":event_id,
                           "speech_unit_ids":["u_"+uid],
                           "board_action_ids":board_ids,
                           "mathematical_goal":unit["goal"]})
        captions.append({"subtitle_id":"subtitle:u_"+uid,
                         "speech_unit_id":"u_"+uid,
                         "parts":semantic_parts})
        cues.append({
            "event_id":event_id,"phase":unit["phase"],
            "heading":unit["heading"],"detail":unit["detail"],
            "source_step_ids":all_steps,
            "pause_seconds":unit["pause_seconds"],
            "write_seconds":unit["write_seconds"],
        })
    package={
        "schema_version":"1.0","input_sha256":_hash(source),
        "prompt_versions":{
            "global":"human-asserted-reviewed-pedagogical-units",
            "A":"teacher-authored","B":"unit-grouped","C":"source-verified"},
        "source":source,
        "plan":{"teaching_events":teacher},
        "lesson":{"lesson_events":lesson,"math_objects":objects,
                  "speech_units":speech,"board_actions":board_actions,
                  "animation_intents":animations},
        "subtitles":captions,
        "validation":{"status":"ready_with_limits","issues":[],
                      "math_checks":[]}
    }
    package["validated_content_sha256"]=_hash(package)
    options=(DirectorOptions(
        diagrams=[DiagramSpec.model_validate(value) for value in diagram_specs],
        max_visible_formulas=100,
    ) if diagram_specs is not None else None)
    storyboard=build_storyboard(package, options=options)
    execution=build_execution_plan(storyboard)
    approved={
        "schema_version":"1.0",
        "source_storyboard_sha256":execution.source_storyboard_sha256,
        "events":cues,
    }
    return package,storyboard,execution,approved
