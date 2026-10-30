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

    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            raw = json.loads(args.input.read_text(encoding="utf-8"))
            result = build_execution_plan(raw)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
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
