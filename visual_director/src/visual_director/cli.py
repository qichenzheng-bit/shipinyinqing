"""Offline storyboard JSON export; does not render an animation or audio."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from pydantic import ValidationError
from .models import DirectorOptions, StoryboardPlan
from .director import build_storyboard, DirectorError


def main(argv=None):
    parser=argparse.ArgumentParser(description="Offline shipinyinqing visual director V1.0")
    sub=parser.add_subparsers(dest="command",required=True)
    run=sub.add_parser("plan",help="Generate JSON storyboard from TeachingPackage")
    run.add_argument("input",type=Path)
    run.add_argument("--output",type=Path,required=True)
    run.add_argument("--options",type=Path,default=None,help="Optional JSON with diagram hints/settings")
    run.add_argument("--allow-needs-review",action="store_true")
    schema=sub.add_parser("schema",help="Export StoryboardPlan JSON Schema")
    schema.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=="schema":
            payload=StoryboardPlan.model_json_schema()
        else:
            raw=json.loads(args.input.read_text(encoding="utf-8"))
            opts=json.loads(args.options.read_text(encoding="utf-8")) if args.options else {}
            if args.allow_needs_review: opts["allow_needs_review"]=True
            payload=build_storyboard(raw,DirectorOptions.model_validate(opts)).model_dump(mode="json")
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    except (OSError,ValueError,ValidationError,KeyError) as exc:
        print(f"Visual director failed: {exc}",file=sys.stderr)
        return 2
    return 0

if __name__=="__main__":
    raise SystemExit(main())