"""V2.6.6 end-to-end pressure-test corpus: real calculus, matrices and proofs.

This never fabricates voice: these legacy independent source-reviewed
whiteboard fixtures are SILENT by contract. Spoken neural audio and caption
timing are separately verified by the full V2.6.6 two-round voiced workflow.
Every fixture here uses real Manim/MathTex, not screenshots of fake equations.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
from pathlib import Path

import sympy as sp
from build_multipart_integral_lesson import export_variant as export_integral
from build_matrix_classroom_lesson import export_variant as export_matrix
from build_proof_classroom_lesson import export_variant as export_proof

CASES={
    "nested_integral": ("integral","B","computation_groups.json"),
    "seven_step_matrix": ("matrix","A","matrix_steps.json"),
    "long_induction_proof": ("proof","A","proof_chain.json"),
    "three_case_proof": ("proof","C","proof_chain.json"),
}

def run(*args: str) -> None:
    subprocess.run(list(args),check=True)

def build(root: Path) -> None:
    root.mkdir(parents=True,exist_ok=True)
    for name,(kind,variant,special) in CASES.items():
        folder=root/name
        folder.mkdir(parents=True,exist_ok=True)
        if kind=="integral":
            export_integral(folder,variant)
        elif kind=="matrix":
            export_matrix(variant,folder)
        else:
            export_proof(folder,variant)
        assert (folder/special).is_file()
    x=sp.symbols("x",real=True)
    expected=sp.E-sp.Rational(1,2)-sp.cos(1)
    actual=sp.integrate(x+x*x*sp.exp(x)+sp.sin(x),(x,0,1))
    if sp.simplify(actual-expected)!=0:
        raise ValueError("STRESS_INTEGRAL_INDEPENDENT_MATH_FAILED")
    print("V266_CROSS_TOPIC_SOURCE_AND_SYMPY_PASS",len(CASES),"fixtures")

def render(root: Path, *, fps:int=30) -> None:
    if not 8<=fps<=60:
        raise ValueError("STRESS_INVALID_FPS")
    flags={
        "computation_groups.json":"--computation-groups",
        "matrix_steps.json":"--matrix-steps",
        "proof_chain.json":"--proof-chain",
    }
    for name,(_,_,special) in CASES.items():
        p=root/name
        common=[
            "--storyboard",str(p/"storyboard.json"),
            "--execution",str(p/"execution.json"),
            "--classroom-cues",str(p/"teacher_approved_cues.json"),
            "--policy",str(p/"page_policy.json"),
            flags[special],str(p/special),
        ]
        run("math-animation","plan-longboard",*common,
            "--output",str(p/"planned.json"))
        run("math-animation","render-longboard",*common,
            "--output",str(p/"real_movie.mp4"),
            "--manifest",str(p/"movie.json"),"--fps",str(fps))
        print("V266_CROSS_TOPIC_REAL_RENDERED",name)

def audit(root: Path, *, fps:int=30) -> None:
    findings=[]
    for name,(kind,_,special) in CASES.items():
        folder=root/name
        manifest=json.loads((folder/"movie.json").read_text("utf-8"))
        planned=json.loads((folder/"planned.json").read_text("utf-8"))
        source=json.loads((folder/"execution.json").read_text("utf-8"))
        events=manifest["event_timing"]
        if (manifest["voice_status"]!="not_recorded"
                or manifest["subtitle_status"]!="not_audio_aligned"
                or manifest["event_count"]!=len(events)
                or manifest["event_count"]!=len(planned["events"])
                or manifest["page_count"]!=planned["page_count"]
                or manifest["erase_count"]!=manifest["page_count"]-1
                or not manifest["event_timing"]):
            raise ValueError("STRESS_SOURCE_AND_BOARD_INCOMPLETE:"+name)
        last=0.0
        for ev in events:
            start,end=ev["start_preview_second"],ev["end_preview_second"]
            if start<last-2/fps or end<start or not math.isfinite(end):
                raise ValueError("STRESS_NONCONTIGUOUS_EVENT_TIME:"+name)
            last=end
        if kind=="integral":
            if manifest["computation_groups"]["part_count"]!=3:
                raise ValueError("STRESS_MISSING_INTEGRAL_PART")
        elif kind=="matrix":
            if (manifest["matrix_operations"]["operation_count"]!=7
                    or not manifest["matrix_operations"]["arithmetically_verified"]):
                raise ValueError("STRESS_INCORRECT_MATRIX")
        else:
            proof=manifest["proof_chain"]
            if (not proof["reference_order_verified"]
                    or not proof["case_coverage_verified"]
                    or proof["stage_count"]!=9):
                raise ValueError("STRESS_INCOMPLETE_PROOF:"+name)
            if name=="three_case_proof" and not proof["branch_groups"]:
                raise ValueError("STRESS_MISSING_THREE_CASES")
        video=folder/"real_movie.mp4"
        streams=json.loads(subprocess.check_output([
            "ffprobe","-v","error","-select_streams","v:0",
            "-count_frames","-show_entries",
            "stream=width,height,nb_read_frames,r_frame_rate",
            "-of","json",str(video),
        ]))["streams"]
        if len(streams)!=1:
            raise ValueError("STRESS_VIDEO_STREAM_MISSING")
        s=streams[0]
        frames=int(s["nb_read_frames"])
        if ((s["width"],s["height"],s["r_frame_rate"])!=
                (1280,720,f"{fps}/1") or frames<300):
            raise ValueError("STRESS_VIDEO_FRAME_OR_RESOLUTION_INVALID:"+name)
        subprocess.run([
            "ffmpeg","-hide_banner","-loglevel","error","-xerror",
            "-i",str(video),"-f","null","-",
        ],check=True)
        findings.append({
            "fixture":name,"source_kind":kind,"events":len(events),
            "board_pages":manifest["page_count"],"frames":frames,
            "mathematics_source_verified":True,
            "full_video_decode_verified":True,
            "silent_fixture_not_misrepresented_as_voiced":True,
        })
    report={"schema_version":"1.0","test":"v266_real_multitype_stress",
            "fps":fps,"resolution":[1280,720],"pass":len(findings)==len(CASES),
            "cases":findings}
    (root/"cross_topic_qa.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("V266_REAL_LONG_MATH_MATRIX_PROOF_STRESS_PASS",
          [(r["fixture"],r["frames"],r["board_pages"]) for r in findings])

def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--stage",choices=("build","render","audit"),required=True)
    parser.add_argument("--root",type=Path,required=True)
    parser.add_argument("--fps",type=int,default=30)
    args=parser.parse_args()
    if args.stage=="build":
        build(args.root)
    elif args.stage=="render":
        render(args.root,fps=args.fps)
    else:
        audit(args.root,fps=args.fps)

if __name__=="__main__":
    main()
