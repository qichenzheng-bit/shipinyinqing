"""CLI: deterministic plan output and optional actual MathTex PNG preview."""
from __future__ import annotations

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
    writing.add_argument("--fps", type=int, default=15)

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
    transition.add_argument("--fps", type=int, default=15)

    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            raw = json.loads(args.input.read_text(encoding="utf-8"))
            result = build_execution_plan(raw)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
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
