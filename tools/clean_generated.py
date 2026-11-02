"""Safe cleanup: dry-run by default; ONLY preapproved generated locations.

Never removes the video library, database, micro-edit revisions, model secrets,
MathTeacher prompts, source files, true user video data or test fixtures.\nGenerated CI screenshots can be regenerated and are safe to clear.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
GENERATED=(
    "desktop/node_modules",
    "desktop/dist",
    "desktop/build",\n    "desktop/screenshots",\n    "frontend/screenshots",\n    "final-output",
    "v27-script",
    "animation_engine/.pytest_cache",
    "teacher_module/.pytest_cache",
    "visual_director/.pytest_cache",
    "backend/.pytest_cache",
    ".pytest_cache",
)


def clean(*, apply=False):
    for name in GENERATED:
        candidate=ROOT/name
        if not candidate.exists() and not candidate.is_symlink():
            continue
        if candidate.is_symlink() or not candidate.is_dir():
            raise RuntimeError("UNSAFE_GENERATED_PATH: "+name)
        # Never follow symbolic links outside the checked-out workspace.
        if not candidate.resolve().is_relative_to(ROOT.resolve()):
            raise RuntimeError("UNSAFE_PATH_OUTSIDE_REPO: "+name)
        print(("REMOVE" if apply else "WOULD_REMOVE"),name)
        if apply:shutil.rmtree(candidate)
    print("SAFE_CLEANUP_COMPLETE" if apply else "SAFE_CLEANUP_DRY_RUN")


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--apply",action="store_true",
                        help="Remove ONLY known generated build/caches")
    args=parser.parse_args()
    clean(apply=args.apply)
