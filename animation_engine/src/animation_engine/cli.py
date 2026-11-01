"""CLI: deterministic plan output and optional actual MathTex PNG preview."""
from __future__ import annotations

from .video_settings import DEFAULT_VIDEO_FPS

import argparse
import json
import sys
from pathlib import Path

from .planner import ExecutionError, build_execution_plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="shipinyinqing animation engine")
    subparsers = parser.add_subparsers(dest="command", required=True)

    command = subparsers.add_parser("plan", help="Compile StoryboardPlan to an offline execution plan")
    command.add_argument("input", type=Path, help="StoryboardPlan v1.0 JSON")
    command.add_argument("--output", type=Path, required=True, help="ExecutionPlan v1.0 JSON")

    preview = subparsers.add_parser("preview-math", help="Render one verified visible formula to real MathTex PNG")
    preview.add_argument("--storyboard", type=Path, required=True)
    preview.add_argument("--execution", type=Path, required=True)
    preview.add_argument("--event-id", required=True)
    preview.add_argument("--object-id", required=True)
    preview.add_argument("--output", type=Path, required=True)
    preview.add_argument("--metrics", type=Path, required=True)

    writing = subparsers.add_parser("render-writing",
        help="Render one provenance-verified formula's authentic progressive Write MP4")
    writing.add_argument("--storyboard", type=Path, required=True)
    writing.add_argument("--execution", type=Path, required=True)
    writing.add_argument("--event-id", required=True)
    writing.add_argument("--object-id", required=True)
    writing.add_argument("--hint", type=Path, help="Explicit approved structural parts JSON (optional)")
    writing.add_argument("--output", type=Path, required=True)
    writing.add_argument("--manifest", type=Path, required=True)
    writing.add_argument("--pixel-width", type=int, default=1280)
    writing.add_argument("--pixel-height", type=int, default=720)
    writing.add_argument("--fps", type=int, default=DEFAULT_VIDEO_FPS)

    layout = subparsers.add_parser("layout-board",
        help="2.3 measured adaptive layout: JSON plan or real MathTex board PNG")
    layout.add_argument("--storyboard", type=Path, required=True)
    layout.add_argument("--execution", type=Path, required=True)
    layout.add_argument("--output", type=Path, required=True)
    layout.add_argument("--event-id", help="Render selected event as PNG; omit for JSON plan")
    layout.add_argument("--manifest", type=Path, help="Required with --event-id")

    transition = subparsers.add_parser("render-layout-transition",
        help="2.3 genuine MathTex MP4 between two consecutive approved scenes")
    transition.add_argument("--storyboard", type=Path, required=True)
    transition.add_argument("--execution", type=Path, required=True)
    transition.add_argument("--from-event-id", required=True)
    transition.add_argument("--to-event-id", required=True)
    transition.add_argument("--output", type=Path, required=True)
    transition.add_argument("--manifest", type=Path, required=True)
    transition.add_argument("--fps", type=int, default=DEFAULT_VIDEO_FPS)

    classroom = subparsers.add_parser("preview-classroom",
        help="2.3 authentic mathematical question and board PNG")
    classroom.add_argument("--storyboard", type=Path, required=True)
    classroom.add_argument("--execution", type=Path, required=True)
    classroom.add_argument("--event-id", required=True)
    classroom.add_argument("--output", type=Path, required=True)
    classroom.add_argument("--manifest", type=Path, required=True)

    classroom_movie = subparsers.add_parser("render-classroom-transition",
        help="2.3 real MathTex transition MP4 with original question always visible")
    classroom_movie.add_argument("--storyboard", type=Path, required=True)
    classroom_movie.add_argument("--execution", type=Path, required=True)
    classroom_movie.add_argument("--from-event-id", required=True)
    classroom_movie.add_argument("--to-event-id", required=True)
    classroom_movie.add_argument("--output", type=Path, required=True)
    classroom_movie.add_argument("--manifest", type=Path, required=True)
    classroom_movie.add_argument("--fps", type=int, default=DEFAULT_VIDEO_FPS)

    sequence = subparsers.add_parser("render-classroom-sequence",
        help="Real MathTex multi-scene classroom preview, no inferred speech timing")
    sequence.add_argument("--storyboard", type=Path, required=True)
    sequence.add_argument("--execution", type=Path, required=True)
    sequence.add_argument("--event-ids", nargs="+", required=True)
    sequence.add_argument("--output", type=Path, required=True)
    sequence.add_argument("--manifest", type=Path, required=True)
    sequence.add_argument("--fps", type=int, default=DEFAULT_VIDEO_FPS)

    longboard_plan = subparsers.add_parser(
        "plan-longboard", help="2.4 true-size long lesson: plan scroll/cut/retained context")
    longboard_plan.add_argument("--storyboard", type=Path, required=True)
    longboard_plan.add_argument("--execution", type=Path, required=True)
    longboard_plan.add_argument("--policy", type=Path,
        help="Optional approved object IDs and exact LaTeX wrap hints JSON")
    longboard_plan.add_argument("--classroom-cues",type=Path,
        help="Mandatory for persistent classroom blackboard")
    longboard_plan.add_argument("--computation-groups",type=Path,
        help="V2.5.1 reviewed multi-part computation and carry ledger")
    longboard_plan.add_argument("--matrix-steps",type=Path,
        help="V2.5.2 algebra-verified before/operation/after matrix contract")
    longboard_plan.add_argument("--proof-chain",type=Path,
        help="V2.5.3 reviewed proof stages, dependencies, cases and carry context")
    longboard_plan.add_argument("--diagram-classroom",type=Path,
        help="V2.5.4 reviewed source-bound geometry, curves and shaded regions")
    longboard_plan.add_argument("--output", type=Path, required=True)
    longboard_plan.add_argument("--pixel-width", type=int, default=1280)
    longboard_plan.add_argument("--pixel-height", type=int, default=720)

    longboard_render = subparsers.add_parser(
        "render-longboard", help="2.4 full source-verified Manim teaching-board MP4")
    longboard_render.add_argument("--storyboard", type=Path, required=True)
    longboard_render.add_argument("--execution", type=Path, required=True)
    longboard_render.add_argument("--policy", type=Path)
    longboard_render.add_argument("--classroom-cues", type=Path,
        help="Teacher-approved event-by-event reasoning prompts, not voice subtitles")
    longboard_render.add_argument("--computation-groups",type=Path,
        help="V2.5.1 source-verified subproblem decomposition and safe breaks")
    longboard_render.add_argument("--matrix-steps",type=Path,
        help="V2.5.2 teacher-reviewed exact matrix operations")
    longboard_render.add_argument("--proof-chain",type=Path,
        help="V2.5.3 source-verified proof structure and safe page breaks")
    longboard_render.add_argument("--diagram-classroom",type=Path,
        help="V2.5.4 genuine geometric MathTex teaching and source-revealed diagram")
    longboard_render.add_argument("--output", type=Path, required=True)
    longboard_render.add_argument("--manifest", type=Path, required=True)
    longboard_render.add_argument("--pixel-width", type=int, default=1280)
    longboard_render.add_argument("--pixel-height", type=int, default=720)
    longboard_render.add_argument("--fps", type=int, default=DEFAULT_VIDEO_FPS)

    flow_plan = subparsers.add_parser(
        "plan-flow", help="V2.6.1 source-verified mixed classroom stages")
    flow_plan.add_argument("--flow",type=Path,required=True,
        help="Reviewed unified_flow.json with relative stage directories")
    flow_plan.add_argument("--output",type=Path,required=True)

    flow_render = subparsers.add_parser(
        "render-flow", help="V2.6.1 real multi-engine Manim MP4 with math-exact handoffs")
    flow_render.add_argument("--flow",type=Path,required=True)
    flow_render.add_argument("--output",type=Path,required=True)
    flow_render.add_argument("--manifest",type=Path,required=True)
    flow_render.add_argument("--fps",type=int,default=DEFAULT_VIDEO_FPS)

    adaptive_plan = subparsers.add_parser(
        "plan-adaptive-flow", help="V2.6.2 teacher-reviewed diagram lifecycle and native board layout")
    adaptive_plan.add_argument("--layout", type=Path, required=True)
    adaptive_plan.add_argument("--output", type=Path, required=True)
    adaptive_render = subparsers.add_parser(
        "render-adaptive-flow", help="V2.6.2 authentic MathTex plus persistent source diagram MP4")
    adaptive_render.add_argument("--layout", type=Path, required=True)
    adaptive_render.add_argument("--output", type=Path, required=True)
    adaptive_render.add_argument("--manifest", type=Path, required=True)
    adaptive_render.add_argument("--fps", type=int, default=DEFAULT_VIDEO_FPS)

    memory_plan = subparsers.add_parser(
        "plan-memory", help="V2.6.3 reviewed mathematical facts and scoped non-adjacent recalls")
    memory_plan.add_argument("--memory", type=Path, required=True)
    memory_plan.add_argument("--output", type=Path, required=True)
    memory_plan.add_argument("--adaptive", action="store_true")
    memory_render = subparsers.add_parser(
        "render-memory", help="V2.6.3 real verified memory-aware Manim classroom movie")
    memory_render.add_argument("--memory", type=Path, required=True)
    memory_render.add_argument("--output", type=Path, required=True)
    memory_render.add_argument("--manifest", type=Path, required=True)
    memory_render.add_argument("--fps", type=int, default=DEFAULT_VIDEO_FPS)
    memory_render.add_argument("--adaptive", action="store_true")

    spoken_plan = subparsers.add_parser(
        "plan-spoken", help="V2.6.4 complete approved spoken teaching coverage")
    spoken_plan.add_argument("--spoken", type=Path, required=True)
    spoken_plan.add_argument("--output", type=Path, required=True)
    spoken_plan.add_argument("--adaptive", action="store_true")
    script_export = subparsers.add_parser(
        "export-spoken-script",
        help="V2.7 mandatory pre-render complete narration and board writing script")
    script_export.add_argument("--spoken", type=Path, required=True)
    script_export.add_argument("--output", type=Path, required=True,
        help="Human-readable Markdown script; JSON is written beside spoken_classroom.json")
    script_export.add_argument("--adaptive", action="store_true")

    script_approval = subparsers.add_parser(
        "approve-spoken-script",
        help="Explicitly attest review of source-exact V2.7 script before rendering",
    )
    script_approval.add_argument("--spoken", type=Path, required=True)
    script_approval.add_argument("--reviewer", type=str, required=True)
    script_approval.add_argument("--confirm-reviewed", action="store_true", required=True)
    script_approval.add_argument("--adaptive", action="store_true")

    spoken_render = subparsers.add_parser(
        "render-spoken", help="V2.6.4 actual neural narration, MathTex and phrase captions")
    spoken_render.add_argument("--spoken", type=Path, required=True)
    spoken_render.add_argument("--output", type=Path, required=True)
    spoken_render.add_argument("--manifest", type=Path, required=True)
    spoken_render.add_argument("--srt", type=Path)
    spoken_render.add_argument("--fps", type=int, default=DEFAULT_VIDEO_FPS)
    spoken_render.add_argument("--adaptive", action="store_true")
    spoken_render.add_argument("--cache-dir", type=Path,
        help="Persistent content-addressed TTS, MathTex and stage cache")

    # V2.6.5 is a headless engine: no GUI or side-by-side comparison.
    editing_start = subparsers.add_parser(
        "edit-start", help="Initialize iterative editing on a verified spoken video")
    editing_start.add_argument("--package", type=Path, required=True)
    editing_start.add_argument("--movie", type=Path, required=True)
    editing_start.add_argument("--manifest", type=Path, required=True)
    editing_start.add_argument("--session", type=Path, required=True)
    editing_start.add_argument("--fps", type=int, default=DEFAULT_VIDEO_FPS)
    editing_start.add_argument("--nonadaptive", action="store_true")

    editing_apply = subparsers.add_parser(
        "edit-apply", help="Apply any number of natural-language changes to latest movie")
    editing_apply.add_argument("--session", type=Path, required=True)
    instructions=editing_apply.add_mutually_exclusive_group(required=True)
    instructions.add_argument("--instruction", type=str)
    instructions.add_argument("--instruction-file", type=Path)
    providers=editing_apply.add_mutually_exclusive_group(required=True)
    providers.add_argument("--plan", type=Path,
        help="Structured multi-request edit plan from an external AI model")
    providers.add_argument("--ai-config", type=Path,
        help="Opt-in OpenAI-compatible AI provider JSON configuration")
    editing_apply.add_argument("--math-reviewer", type=str,
        help="Explicit trusted Python module:function for mathematical content review")
    editing_apply.add_argument("--script-reviewer", type=str,
        help="Explicit trusted Python module:function for V2.7 candidate script approval")

    editing_feedback = subparsers.add_parser(
        "edit-feedback", help="Keep editing the latest movie until the user is satisfied")
    editing_feedback.add_argument("--session", type=Path, required=True)
    editing_feedback.add_argument("--text", type=str, required=True)
    editing_feedback.add_argument("--satisfied", action="store_true")

    editing_export = subparsers.add_parser(
        "edit-export", help="Export all original instructions and outcomes as ONE JSON")
    editing_export.add_argument("--session", type=Path, required=True)
    editing_export.add_argument("--output", type=Path, required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "edit-start":
            from .iterative_edit_engine import create_session
            result = create_session(
                args.package, args.movie, args.manifest, args.session,
                adaptive=not args.nonadaptive, fps=args.fps,
            )
            print(json.dumps({
                "revision": result["revision"],
                "latest_movie": str(args.session / "latest.mp4"),
            }, ensure_ascii=False))
            return 0
        if args.command == "edit-apply":
            from .iterative_edit_engine import run_edit, plan_from_file
            if args.plan is not None:
                agent=plan_from_file(args.plan)
            else:
                from .iterative_ai_adapter import make_openai_compatible_agent
                agent=make_openai_compatible_agent(args.ai_config)
            raw=(args.instruction if args.instruction is not None else
                 args.instruction_file.read_text(encoding="utf-8"))
            reviewers = {}
            for kind, specification in (
                ("math", args.math_reviewer),
                ("script", args.script_reviewer),
            ):
                if specification is None:
                    reviewers[kind] = None
                    continue
                import importlib
                module, sep, member = specification.partition(":")
                if not sep or not module or not member:
                    raise ValueError(f"EDIT_{kind.upper()}_REVIEWER_MODULE_FUNCTION")
                reviewer = getattr(importlib.import_module(module), member)
                if not callable(reviewer):
                    raise ValueError(f"EDIT_{kind.upper()}_REVIEWER_NOT_CALLABLE")
                reviewers[kind] = reviewer
            result=run_edit(
                args.session, raw, agent,
                math_reviewer=reviewers["math"],
                script_reviewer=reviewers["script"],
            )
            print(json.dumps(result, ensure_ascii=False))
            return 0 if result["status"]=="preview_ready" else 2
        if args.command == "edit-feedback":
            from .iterative_edit_engine import record_feedback
            result=record_feedback(args.session, args.text,
                                   satisfied=args.satisfied)
            print(json.dumps(result, ensure_ascii=False))
            return 0
        if args.command == "edit-export":
            from .iterative_edit_engine import export_history
            result=export_history(args.session, args.output)
            print(json.dumps({
                "output": str(args.output),
                "rounds": len(result["rounds"]),
                "revision": result["current_revision"],
            }, ensure_ascii=False))
            return 0
        if args.command == "plan-spoken":
            if args.output.suffix.lower() != ".json":
                raise ValueError("SPOKEN_PLAN_REQUIRES_JSON_OUTPUT")
            from .spoken_classroom import plan_spoken
            result = plan_spoken(args.spoken,adaptive=args.adaptive)
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(
                json.dumps(result,ensure_ascii=False,indent=2)+"\n",
                encoding="utf-8",
            )
            return 0
        if args.command == "export-spoken-script":
            from .spoken_classroom import checked_spoken
            from .v27_teacher_contract import export_spoken_script
            from .unified_classroom_flow import _load
            approved = checked_spoken(args.spoken, adaptive=args.adaptive)
            source_doc = _load(args.spoken)
            result = export_spoken_script(
                approved, output_json=args.spoken.parent / "lesson_script.json",
                output_md=args.output, source_document=source_doc,
                source_path=args.spoken,
            )
            print(json.dumps({
                "script": str(args.output),
                "machine_readable": str(args.spoken.parent / "lesson_script.json"),
                "events": len(result["events"]), "acceptance": result["acceptance"],
            }, ensure_ascii=False))
            return 0
        if args.command == "approve-spoken-script":
            from .spoken_classroom import checked_spoken
            from .v27_teacher_contract import approve_prerender_script
            source = args.spoken.resolve()
            reviewed = checked_spoken(source, adaptive=args.adaptive)
            approval = approve_prerender_script(
                reviewed, source, reviewer=args.reviewer,
                confirmed=args.confirm_reviewed,
            )
            print(json.dumps({
                "approval": str(source.parent / "lesson_script_approval.json"),
                "source_sha256": approval["source_spoken_sha256"],
                "script_sha256": approval["script_sha256"],
                "reviewer": approval["reviewer"],
            }, ensure_ascii=False))
            return 0
        if args.command == "render-spoken":
            from .spoken_movie import render_spoken_classroom
            render_spoken_classroom(
                args.spoken,output_mp4=args.output,
                output_json=args.manifest,output_srt=args.srt,
                fps=args.fps,adaptive=args.adaptive,
                cache_dir=args.cache_dir,
            )
            return 0
        if args.command == "plan-memory":
            if args.output.suffix.lower() != ".json":
                raise ValueError("MEMORY_PLAN_REQUIRES_JSON_OUTPUT")
            from .classroom_math_memory import plan_memory
            result = plan_memory(args.memory, adaptive=args.adaptive)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(result, ensure_ascii=False, indent=2)+"\n",
                encoding="utf-8",
            )
            return 0
        if args.command == "render-memory":
            from .classroom_math_memory import render_memory
            render_memory(args.memory, output_mp4=args.output,
                          output_json=args.manifest, fps=args.fps,
                          adaptive=args.adaptive)
            return 0
        if args.command == "plan-adaptive-flow":
            if args.output.suffix.lower() != ".json":
                raise ValueError("ADAPTIVE_PLAN_REQUIRES_JSON_OUTPUT")
            from .adaptive_classroom_flow import plan_adaptive_flow
            result = plan_adaptive_flow(args.layout)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            return 0
        if args.command == "render-adaptive-flow":
            from .adaptive_classroom_flow import render_adaptive_flow
            render_adaptive_flow(
                args.layout, output_mp4=args.output,
                output_json=args.manifest, fps=args.fps,
            )
            return 0
        if args.command == "plan-flow":
            if args.output.suffix.lower()!=".json":
                raise ValueError("FLOW_PLAN_REQUIRES_JSON_OUTPUT")
            from .unified_classroom_flow import plan_flow
            result=plan_flow(args.flow)
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(
                json.dumps(result,ensure_ascii=False,indent=2)+"\n",
                encoding="utf-8"
            )
            return 0
        if args.command == "render-flow":
            from .unified_classroom_flow import render_flow
            render_flow(
                args.flow,output_mp4=args.output,
                output_json=args.manifest,fps=args.fps
            )
            return 0
        if args.command in ("plan-longboard", "render-longboard"):
            raw_board = json.loads(args.storyboard.read_text(encoding="utf-8"))
            raw_execution = json.loads(args.execution.read_text(encoding="utf-8"))
            raw_policy = (
                json.loads(args.policy.read_text(encoding="utf-8"))
                if args.policy is not None else None
            )
            # User-approved classroom default for a simple lesson whose
            # reviewed pedagogical cue data is supplied. Specialized large
            # proof/diagram lessons can still pass an explicit layout policy.
            if args.classroom_cues is not None and raw_policy is None:
                # Special mathematical layouts require reviewed manifests.
                if (args.matrix_steps is not None or args.proof_chain is not None
                        or args.diagram_classroom is not None):
                    from .classroom_policy import simple_classroom_policy
                    raw_policy=simple_classroom_policy()
            if args.classroom_cues is not None and raw_policy is None:
                # The simple classroom cannot render explicit geometry,
                # matrix layouts or proof-scroll. Never silently drop them.
                scenes=raw_board.get("scenes",[])
                incompatible=[
                    s.get("event_id","?")
                    for s in scenes
                    if s.get("diagram") is not None
                    or s.get("layout") in (
                        "diagram_split","matrix_compare","proof_scroll"
                    )
                ]
                if incompatible:
                    raise ValueError(
                        "CLASSROOM_SPECIAL_LAYOUT_REQUIRES_EXPLICIT_POLICY: "+
                        ",".join(incompatible)
                    )
                from .classroom_policy import simple_classroom_policy
                raw_policy=simple_classroom_policy()
            chalkboard=(raw_policy is not None and
                raw_policy.get("guidance_style")=="persistent_chalkboard")
            computation_data=(
                json.loads(args.computation_groups.read_text(encoding="utf-8"))
                if args.computation_groups is not None else None
            )
            matrix_data=(
                json.loads(args.matrix_steps.read_text(encoding="utf-8"))
                if args.matrix_steps is not None else None
            )
            proof_data=(
                json.loads(args.proof_chain.read_text(encoding="utf-8"))
                if args.proof_chain is not None else None
            )
            diagram_data=(
                json.loads(args.diagram_classroom.read_text(encoding="utf-8"))
                if args.diagram_classroom is not None else None
            )
            if sum(value is not None for value in (
                    computation_data,matrix_data,proof_data,diagram_data))>1:
                raise ValueError("SPECIAL_CONTRACTS_MUTUALLY_EXCLUSIVE")
            if computation_data is not None and not chalkboard:
                raise ValueError("COMPUTATION_GROUPS_REQUIRES_PERSISTENT_CHALKBOARD")
            if matrix_data is not None and not chalkboard:
                raise ValueError("MATRIX_STEPS_REQUIRES_PERSISTENT_CHALKBOARD")
            if proof_data is not None and not chalkboard:
                raise ValueError("PROOF_CHAIN_REQUIRES_PERSISTENT_CHALKBOARD")
            if diagram_data is not None and not chalkboard:
                raise ValueError("DIAGRAM_REQUIRES_PERSISTENT_CHALKBOARD")
            if args.command == "plan-longboard":
                if chalkboard:
                    if args.classroom_cues is None:
                        raise ValueError("CHALKBOARD_NEEDS_APPROVED_CUES")
                    from .persistent_chalkboard import make_chalkboard_plan
                    result=make_chalkboard_plan(
                        raw_board,raw_execution,
                        json.loads(args.classroom_cues.read_text(encoding="utf-8")),
                        raw_policy,
                        **({"computation_manifest":computation_data}
                           if computation_data is not None else {}),
                        **({"matrix_manifest":matrix_data}
                           if matrix_data is not None else {}),
                        **({"proof_manifest":proof_data}
                           if proof_data is not None else {}),
                        **({"diagram_manifest":diagram_data}
                           if diagram_data is not None else {}),
                    )
                else:
                    from .longboard_plan import build_longboard_plan
                    result = build_longboard_plan(
                        raw_board, raw_execution, policy=raw_policy,
                        pixel_width=args.pixel_width, pixel_height=args.pixel_height,
                    )
                if args.output.suffix.lower() != ".json":
                    raise ValueError("LONGBOARD_OUTPUT: planning needs --output .json")
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(
                    json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            else:
                from .longboard_render import render_longboard_movie
                cue_data = (json.loads(args.classroom_cues.read_text(encoding="utf-8"))
                            if args.classroom_cues is not None else None)
                if chalkboard:
                    if cue_data is None:
                        raise ValueError("CHALKBOARD_NEEDS_APPROVED_CUES")
                    if (args.pixel_width,args.pixel_height)!=(1280,720):
                        raise ValueError("CHALKBOARD_FRAME_REQUIRES_1280x720")
                    from .persistent_chalkboard import render_persistent_chalkboard
                    render_persistent_chalkboard(
                        raw_board,raw_execution,cue_data,raw_policy,
                        output_mp4=args.output,output_json=args.manifest,fps=args.fps,
                        **({"computation_manifest":computation_data}
                           if computation_data is not None else {}),
                        **({"matrix_manifest":matrix_data}
                           if matrix_data is not None else {}),
                        **({"proof_manifest":proof_data}
                           if proof_data is not None else {}),
                        **({"diagram_manifest":diagram_data}
                           if diagram_data is not None else {}),
                    )
                else:
                    render_longboard_movie(
                        raw_board, raw_execution, policy=raw_policy,
                        classroom_cues=cue_data,
                        output_mp4=args.output, output_json=args.manifest,
                        pixel_width=args.pixel_width, pixel_height=args.pixel_height,
                        fps=args.fps,
                    )
            return 0

        if args.command == "plan":
            raw = json.loads(args.input.read_text(encoding="utf-8"))
            result = build_execution_plan(raw)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
            return 0

        if args.command == "render-classroom-sequence":
            from .classroom_sequence import render_classroom_sequence
            raw_board = json.loads(args.storyboard.read_text(encoding="utf-8"))
            raw_execution = json.loads(args.execution.read_text(encoding="utf-8"))
            render_classroom_sequence(raw_board, raw_execution,
                event_ids=args.event_ids, output_mp4=args.output,
                output_json=args.manifest, fps=args.fps)
            return 0

        if args.command == "render-classroom-transition":
            from .classroom_transition import render_classroom_transition
            raw_board = json.loads(args.storyboard.read_text(encoding="utf-8"))
            raw_execution = json.loads(args.execution.read_text(encoding="utf-8"))
            render_classroom_transition(raw_board, raw_execution,
                from_event_id=args.from_event_id, to_event_id=args.to_event_id,
                output_mp4=args.output, output_json=args.manifest, fps=args.fps)
            return 0

        if args.command == "preview-classroom":
            from .classroom_compositor import render_classroom_board_png
            raw_board = json.loads(args.storyboard.read_text(encoding="utf-8"))
            raw_execution = json.loads(args.execution.read_text(encoding="utf-8"))
            render_classroom_board_png(raw_board, raw_execution,
                event_id=args.event_id, output_png=args.output, output_json=args.manifest)
            return 0

        if args.command == "render-layout-transition":
            from .layout_transition import render_layout_transition
            raw_board = json.loads(args.storyboard.read_text(encoding="utf-8"))
            raw_execution = json.loads(args.execution.read_text(encoding="utf-8"))
            render_layout_transition(
                raw_board, raw_execution,
                from_event_id=args.from_event_id, to_event_id=args.to_event_id,
                output_mp4=args.output, output_json=args.manifest, fps=args.fps)
            return 0

        if args.command == "layout-board":
            from .adaptive_layout import layout_storyboard, render_layout_png
            raw_board = json.loads(args.storyboard.read_text(encoding="utf-8"))
            raw_execution = json.loads(args.execution.read_text(encoding="utf-8"))
            if args.event_id is not None:
                if args.manifest is None or args.output.suffix.lower() != ".png":
                    raise ValueError("LAYOUT_OUTPUT: --event-id needs --output .png and --manifest .json")
                render_layout_png(raw_board, raw_execution, event_id=args.event_id,
                                  output_png=args.output, output_json=args.manifest)
            else:
                if args.manifest is not None or args.output.suffix.lower() != ".json":
                    raise ValueError("LAYOUT_OUTPUT: planning needs --output .json only")
                result = layout_storyboard(raw_board, raw_execution)
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                                       encoding="utf-8")
            return 0

        if args.command == "render-writing":
            from .writing_cues import plan_math_writing
            from .writing_clip import render_math_writing_clip
            raw_board = json.loads(args.storyboard.read_text(encoding="utf-8"))
            raw_execution = json.loads(args.execution.read_text(encoding="utf-8"))
            hint = json.loads(args.hint.read_text(encoding="utf-8")) if args.hint is not None else None
            cue = plan_math_writing(raw_board, raw_execution,
                event_id=args.event_id, object_id=args.object_id, hint=hint)
            render_math_writing_clip(cue,
                output_mp4=args.output, output_json=args.manifest,
                pixel_width=args.pixel_width, pixel_height=args.pixel_height,
                fps=args.fps)
            return 0

        # Optional import only for the real-render command: old plan users
        # should never be forced to install Manim/LaTeX.
        from .render_contract import RenderContractError, select_math_render_request
        from .math_preview import MathPreviewError, render_math_preview

        raw_board = json.loads(args.storyboard.read_text(encoding="utf-8"))
        raw_execution = json.loads(args.execution.read_text(encoding="utf-8"))
        req = select_math_render_request(
            raw_board, raw_execution,
            event_id=args.event_id, object_id=args.object_id,
        )
        render_math_preview(req, output_png=args.output, output_json=args.metrics)
        return 0
    except (OSError, json.JSONDecodeError, ExecutionError, ValueError) as exc:
        print(f"Animation {args.command} failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
