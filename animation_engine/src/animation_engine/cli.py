"""Offline animation plan JSON exporter; does NOT render video or speech."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .planner import ExecutionError, build_execution_plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="shipinyinqing animation engine V1 step 1")
    subparsers = parser.add_subparsers(dest="command", required=True)
    command = subparsers.add_parser("plan", help="Compile StoryboardPlan to an offline execution plan")
    command.add_argument("input", type=Path, help="StoryboardPlan v1.0 JSON")
    command.add_argument("--output", type=Path, required=True, help="ExecutionPlan v1.0 JSON")
    args = parser.parse_args(argv)
    try:
        raw = json.loads(args.input.read_text(encoding="utf-8"))
        result = build_execution_plan(raw)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
        return 0
    except (OSError, json.JSONDecodeError, ExecutionError, ValueError) as exc:
        print(f"Animation execution plan failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
