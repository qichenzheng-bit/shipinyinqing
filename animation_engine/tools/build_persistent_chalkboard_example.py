"""Exactly the previously verified teacher lesson, new append-only board policy."""
from __future__ import annotations
import json
from pathlib import Path
from build_classroom_rework_example import build
from animation_engine.classroom_policy import simple_classroom_policy

def main(root: Path):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    pkg,board,execution,cues,policy=build()
    policy=simple_classroom_policy(result_ids=("m_jresult",))
    values={
        "teaching_package.json":pkg,
        "storyboard.json":board.model_dump(mode="json"),
        "execution.json":execution.model_dump(mode="json"),
        "teacher_approved_cues.json":cues,
        "page_policy.json":policy
    }
    for key,value in values.items():
        (root/key).write_text(
            json.dumps(value,ensure_ascii=False,indent=2)+"\n",
            encoding="utf-8"
        )
    print("CHALKBOARD_REUSES_APPROVED_LESSON",len(cues["events"]),
          "same exact mathematics; only display style changed")

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path,required=True)
    main(p.parse_args().output)
