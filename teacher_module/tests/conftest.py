import pytest
from math_teacher.models import TeacherInput, Understanding, TeachingPlan, LessonDraft

@pytest.fixture
def source():
    return TeacherInput(problem="求极限 lim_{x->0} (...)。", reference_solution="使用泰勒展开求得极限 1/2。")

@pytest.fixture
def understanding():
    return Understanding.model_validate({
        "problem_understanding": {"domain":"高等数学","problem_type":"极限","goal":"求极限","conditions":["x->0"],"math_objects":["x"],"subquestions":[]},
        "reference_method":"泰勒展开","solution_structure":"单链计算",
        "solution_steps":[{
            "step_id":"s1","origin":"source","source_refs":["solution:0"],"source_quotes":{"solution:0":"使用泰勒展开"},"step_role":"calculation",
            "input_expressions":["f(x)","x^2"],"output_expressions":["1/2"],"relation_type":"limit",
            "operation":"泰勒展开","depends_on":[],"assumptions":["x->0"],"justification":"参考解析中的展开","verification_status":"source_only"
        }],"check_requests":[],"issues":[],"review_status":"ready_candidate"
    })

@pytest.fixture
def plan():
    return TeachingPlan.model_validate({
        "teaching_strategy":"参考解析为主，知识点先讲再应用",
        "reference_step_coverage":{"s1":["e_read","e_k","e_apply","e_derive","e_end"]},
        "knowledge_bindings":[{
            "knowledge_id":"k1","source_step_ids":["s1"],"knowledge_type":"formula", "title":"泰勒展开",
            "formula_or_theorem":"\\ln(1+u)=u-u^2/2+o(u^2)","applicability_conditions":["u->0"],
            "application_mapping":{"u":"x^2"},"teaching_reason":"原解析使用该式","return_to_step_id":"s1"
        }],
        "teaching_events":[
            {"event_id":eid,"event_type":kind,"source_step_ids":["s1"],"knowledge_binding_ids":knowledge,
             "teaching_goal":eid,"intended_board_content":["当前相关数学表达式"],"mathematical_progression":"参考解法"}
            for eid,kind,knowledge in [("e_read","read_question",[]),("e_k","knowledge",["k1"]),
                                       ("e_apply","application",["k1"]),("e_derive","derivation",["k1"]),
                                       ("e_end","conclusion",[])]
        ],"supplement_requests":[],"planning_issues":[]
    })

@pytest.fixture
def draft():
    ids = ["e_read","e_k","e_apply","e_derive","e_end"]
    return LessonDraft.model_validate({
        "lesson_events":[{"event_id":eid,"source_step_ids":["s1"],"knowledge_binding_ids":(["k1"] if eid in ["e_k","e_apply","e_derive"] else []),
          "speech_unit_ids":["u_"+eid],"board_action_ids":["b_"+eid],"animation_intent_ids":["a_"+eid]} for eid in ids],
        "speech_units":[{"speech_unit_id":"u_"+eid,"event_id":eid,"parts":[{"kind":"text","value":"讲解当前数学步骤。","reading_intent":None},
                              {"kind":"math","value":"x^2","reading_intent":"x 平方"}]} for eid in ids],
        "math_objects":[{"math_object_id":"m_"+eid,"latex":"x^2","source_step_ids":["s1"]} for eid in ids],
        "board_actions":[{"board_action_id":"b_"+eid,"event_id":eid,"speech_unit_id":"u_"+eid,
                          "math_object_id":"m_"+eid,"action":"write","semantic_reason":"随口播书写当前数学公式"} for eid in ids],
        "animation_intents":[{"animation_id":"a_"+eid,"event_id":eid,"speech_unit_ids":["u_"+eid],
                              "board_action_ids":["b_"+eid],"mathematical_goal":"公式随讲解渐次出现"} for eid in ids],
        "consistency_issues":[]
    })

class FakeProvider:
    def __init__(self, understanding, plan, draft):
        self.outputs={"A":understanding,"B":plan,"C":draft}
        self.calls=[]
    def generate(self, *, stage, system, user_json, schema):
        self.calls.append((stage,system,user_json,schema))
        assert self.outputs[stage].__class__ == schema
        return self.outputs[stage]
