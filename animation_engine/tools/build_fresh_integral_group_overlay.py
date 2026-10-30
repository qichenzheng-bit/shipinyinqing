"""Human-reviewed 2.5.1 overlay for the *existing* original 2.4 integral fixture.

This script does not infer independent parts from LaTeX. IDs below are audited
against build_fresh_integral_acceptance.STEPS. Generated hashes bind the
reviewed display instructions to a particular storyboard/execution snapshot.
"""
from __future__ import annotations

import json
from pathlib import Path

from animation_engine.calculation_group_models import validate_calculation_overlay
from animation_engine.longboard_plan import _sha
from animation_engine.models import ExecutionPlan


def create_overlay(execution: ExecutionPlan | dict) -> dict:
    source = ExecutionPlan.model_validate(execution)
    overlay = {
        "schema_version": "1.0",
        "source_storyboard_sha256": source.source_storyboard_sha256,
        "source_execution_sha256": _sha(source.model_dump(mode="json")),
        "source_package_sha256": source.source_package_sha256,
        "approval": "teacher_reviewed",
        "approval_reference": "manual-review:original-fresh-integral-2026-10-30",
        "group_id": "fresh_integral_three_parts",
        "group_kind": "independent_sum",
        "overview_object_ids": ["m_split"],
        "parts": [
            {
                "part_id": "integral_1", "intro_event_id": "e_a0",
                "event_ids": [
                    "e_a0", "e_a_sub", "e_a1", "e_a2", "e_a_done",
                ],
                "input_object_ids": ["m_a0"],
                "working_object_ids": ["m_a_sub", "m_a1", "m_a2"],
                "result_object_ids": ["m_a_done"],
                "dependency_part_ids": [],
            },
            {
                "part_id": "integral_2", "intro_event_id": "e_b0",
                "event_ids": [
                    "e_b0", "e_b_sub", "e_b1", "e_b_parts",
                    "e_b2", "e_b3", "e_b_done",
                ],
                "input_object_ids": ["m_b0"],
                "working_object_ids": [
                    "m_b_sub", "m_b1", "m_b_parts", "m_b2", "m_b3",
                ],
                "result_object_ids": ["m_b_done"],
                "dependency_part_ids": [],
            },
            {
                "part_id": "integral_3", "intro_event_id": "e_c0",
                "event_ids": ["e_c0", "e_c1", "e_c_done"],
                "input_object_ids": ["m_c0"],
                "working_object_ids": ["m_c1"],
                "result_object_ids": ["m_c_done"],
                "dependency_part_ids": [],
            },
        ],
        "combine_event_ids": ["e_summary", "e_substitution"],
        "final_object_ids": ["m_final"],
        "display_preferences": {
            "retain_overview": True,
            "max_overview_objects": 3,
            "max_retained_results": 3,
        },
    }
    validate_calculation_overlay(overlay, source)
    return overlay


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = json.loads(args.execution.read_text(encoding="utf-8"))
    overlay = create_overlay(source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(overlay, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )


if __name__ == "__main__":
    main()
