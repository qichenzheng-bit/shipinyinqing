"""Single source of truth for approved simple-problem real-classroom behavior.

Teacher content and math stay separately source-verified. These visual defaults
do not choose a solving method, generate teacher speech or modify a formula.
A complex/diagram problem must pass its explicit specialized layout policy.
"""
from __future__ import annotations


def simple_classroom_policy(*, result_ids: tuple[str,...]=()) -> dict:
    return {
        "guidance_style":"persistent_chalkboard",
        "board_mode":"simple_full_board",
        "pinned_ids":[],
        "result_ids":list(result_ids),
        "cut_before_events":[],
        "break_hints":{},
        "allow_scroll":False,
        "max_scrolls_per_page":0,
        "max_scroll_fraction":0.55,
        "carry_count":0,
        "full_width_without_diagram":True,
        "safe_auto_break":True,
        "content_top_offset_px":0,
        "board_column_width_px":1060,
        "math_base_scale":0.50,
        "math_min_scale":0.48,
        "row_gap_px":11,
    }


SIMPLE_CLASSROOM_RULES = {
    "writing":"append_only_until_board_full",
    "erasure":"only_at_whole_event_boundary_when_next_event_cannot_fit",
    "question":"fixed_visible_not_erased",
    "math_color":"#111111",
    "math_renderer":"MathTex",
    "speech_caption_policy":"do_not_fabricate_audio_or_subtitle_alignment",
    "knowledge_behavior":"appear_with_needed_math_and_remain_until_board_erase",
    "animation":"write_only_except_whole_board_wipe",
}
