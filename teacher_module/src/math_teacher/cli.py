"""Local CLI. No web UI, video runtime or credentials in output files."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from pydantic import ValidationError
from .models import TeacherInput, TeachingPackage
from .pipeline import MathTeacherPipeline, PipelineValidationError
from .provider import OpenAICompatibleJsonModel, ProviderError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Standalone math teacher V1 module")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Generate structured teaching package via a configured LLM")
    run.add_argument("input", type=Path, help="JSON with problem and reference_solution")
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--model", default=None)
    run.add_argument("--base-url", default=None)
    run.add_argument("--schema-mode", action="store_true", help="Require JSON Schema response_format support from provider")
    run.add_argument("--allow-needs-review", action="store_true", help="Produce REVIEW-REQUIRED draft for human/math verification; never bypass hard errors")
    schema = sub.add_parser("schema", help="Write one Pydantic JSON Schema to file")
    schema.add_argument("contract", choices=["input", "package"])
    schema.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "schema":
            model = TeacherInput if args.contract == "input" else TeachingPackage
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Wrote {args.contract} schema: {args.output}")
            return 0
        obj = TeacherInput.model_validate_json(args.input.read_text(encoding="utf-8"))
        provider = OpenAICompatibleJsonModel(model=args.model, base_url=args.base_url, schema_mode=args.schema_mode)
        package = MathTeacherPipeline(provider).run(obj, allow_needs_review=args.allow_needs_review)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(package.model_dump_json(indent=2), encoding="utf-8")
        print(f"Teaching package generated: {args.output} (status={package.validation.status})")
        return 0
    except PipelineValidationError as exc:
        print(f"Stopped at {exc.stage}: {exc.report.model_dump_json(indent=2)}")
        return 2
    except (ProviderError, ValidationError, OSError, ValueError) as exc:
        print(f"Math teacher error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
