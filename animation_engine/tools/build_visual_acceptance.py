"""Generate human-readable 2.3 visual acceptance, not just PASS counts.

All equation pixels in panels come from the production MathTex layout renderer.
Annotations and labels are added *outside* its rendered mathematical content.
The controlled movement case changes ONLY layout regions in a copied, fully
revalidated storyboard; it is not claimed to be teacher-produced output.
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from visual_director.director import build_storyboard
from visual_director.models import Rect
from animation_engine.planner import build_execution_plan
from animation_engine.adaptive_layout import layout_storyboard, render_layout_png
from animation_engine.layout_transition import render_layout_transition


SOURCE = Path("visual_director/examples/limit_teaching_package.json")
CASES = [
    ("e_common", "01  连续推导：已有两条公式", "正常板书 · 当前推导保留"),
    ("e_k_eqv", "02  知识区太窄 → 扩展到整板", "新增知识点，旧公式保持原位"),
    ("e_app_eqv", "03  继续计算：保留上方三条", "下方新增一条，本题应用可见"),
    ("e_k_sin", "04  长式超出可用空间", "不裁切、不偷缩小：明确要求切幕"),
]


def _font(size: int):
    candidates = (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    )
    return ImageFont.truetype(next(p for p in candidates if Path(p).exists()), size)


def _annotate_card(src: Image.Image | None, *, title: str, subtitle: str,
                   row: dict, width: int = 900, height: int = 620):
    card = Image.new("RGB", (width, height), "#FFFFFF")
    d = ImageDraw.Draw(card)
    d.rounded_rectangle((2, 2, width - 3, height - 3), radius=18,
                        outline="#CAD5E2", width=3)
    d.rectangle((18, 18, width - 18, 114), fill="#F1F5F9")
    d.text((40, 30), title, font=_font(31), fill="#1E293B")
    d.text((40, 73), subtitle, font=_font(21), fill="#475569")

    x0, y0, nw, nh = 24, 132, width - 48, 470
    d.rectangle((x0, y0, x0 + nw, y0 + nh), outline="#CBD5E1", width=2)
    if src is None:
        d.text((76, 248), "CUT_REQUIRED", font=_font(55), fill="#C2410C")
        d.text((76, 342), "The requested scene cannot fit safely.",
               font=_font(24), fill="#475569")
        d.text((76, 395), "Requires step 2.4: a real page change.",
               font=_font(24), fill="#475569")
    else:
        img = src.convert("RGB").resize((nw, nh), Image.Resampling.LANCZOS)
        card.paste(img, (x0, y0))
        # Acceptance-only marker: last *new* math object, never drawn in the
        # actual lesson video or confused with an answer frame.
        arrivals = {t["object_id"] for t in row["transitions"] if t["kind"] == "appear"}
        for p in row["placements"]:
            if p["object_id"] not in arrivals:
                continue
            xx, yy = nw / 1280, nh / 720
            a = (x0 + p["x"] * xx - 6, y0 + p["y"] * yy - 5,
                 x0 + (p["x"] + p["w"]) * xx + 6,
                 y0 + (p["y"] + p["h"]) * yy + 5)
            d.rounded_rectangle(a, radius=6, outline="#2563EB", width=3)
    return card


def main(output: Path):
    output.mkdir(parents=True, exist_ok=True)
    raw = json.loads(SOURCE.read_text(encoding="utf-8"))
    board = build_storyboard(raw)
    execution = build_execution_plan(board)
    layout = layout_storyboard(board, execution)
    scenes = {s["event_id"]: s for s in layout["scenes"]}

    # Fail the acceptance job if it cannot show the advertised real features.
    assert scenes["e_common"]["status"] == "ready"
    assert scenes["e_k_eqv"]["status"] == "ready"
    assert scenes["e_k_eqv"]["mode"] == "expanded_scratch"
    assert scenes["e_app_eqv"]["status"] == "ready"
    assert scenes["e_app_eqv"]["mode"] == "expanded_scratch"
    assert scenes["e_k_sin"]["status"] == "cut_required"

    cards = []
    for event_id, label, desc in CASES:
        item = scenes[event_id]
        screenshot = None
        if item["status"] == "ready":
            png = output / (event_id + ".png")
            render_layout_png(board, execution, event_id=event_id, output_png=png,
                              output_json=output / (event_id + ".json"))
            screenshot = Image.open(png)
        cards.append(_annotate_card(screenshot, title=label, subtitle=desc, row=item))

    combined = Image.new("RGB", (1860, 1420), "#F8FAFC")
    d = ImageDraw.Draw(combined)
    d.text((34, 23), "2.3 实际课堂板书布局验收 — 同一道极限题",
           font=_font(44), fill="#0F172A")
    d.text((35, 82),
           "蓝色轮廓仅用于标明新出现的公式；公式本身来自真实 MathTex 渲染。",
           font=_font(23), fill="#475569")
    for i, card in enumerate(cards):
        combined.paste(card, (18 + (i % 2) * 922, 139 + (i // 2) * 646))
    combined.save(output / "acceptance_gallery.png")

    # A meaningful REAL-LESSON scene transition: two existing equations stay
    # on screen while a third mathematical item is written.
    lesson = render_layout_transition(
        board, execution, from_event_id="e_common", to_event_id="e_k_eqv",
        output_mp4=output / "real_lesson_expansion.mp4",
        output_json=output / "real_lesson_expansion.json")
    assert len(lesson["held_ids"]) >= 2, lesson
    assert len(lesson["written_ids"]) >= 1, lesson

    # Controlled layout-pressure fixture: keep all original mathematics and
    # action provenance; shift ONLY one scene's permitted content rectangle.
    shifted = board.model_copy(deep=True)
    target = next(s for s in shifted.scenes if s.event_id == "e_k_eqv")
    original = target.regions
    assert "board" in original and "scratch" in original
    target.regions["board"] = Rect(x=original["board"].x, y=.245,
                                     w=original["board"].w, h=.59)
    target.regions["scratch"] = Rect(x=original["scratch"].x, y=.245,
                                       w=original["scratch"].w, h=.59)
    shifted_execution = build_execution_plan(shifted)
    shifted_layout = layout_storyboard(shifted, shifted_execution)
    shifted_scenes = {s["event_id"]: s for s in shifted_layout["scenes"]}
    assert shifted_scenes["e_k_eqv"]["status"] == "ready", (
        shifted_scenes["e_k_eqv"])
    previous = {p["object_id"]: p for p in shifted_scenes["e_common"]["placements"]}
    current = {p["object_id"]: p for p in shifted_scenes["e_k_eqv"]["placements"]}
    moved = [mid for mid in previous.keys() & current.keys()
             if abs(previous[mid]["y"] - current[mid]["y"]) > 12]
    assert len(moved) >= 2, moved
    stress = render_layout_transition(
        shifted, shifted_execution, from_event_id="e_common",
        to_event_id="e_k_eqv",
        output_mp4=output / "controlled_movement.mp4",
        output_json=output / "controlled_movement.json")
    assert len(stress["moved_ids"]) >= 2, stress
    assert stress["written_ids"], stress

    scene_rows = [{"event_id": x["event_id"], "status": x["status"],
                   "mode": x["mode"], "visible_count": len(x["placements"])}
                  for x in layout["scenes"]]
    report = {
        "source_type": "official_sample_teacher_package",
        "title": "2.3 visual acceptance, genuine lesson + controlled stress test",
        "source_storyboard_sha256": layout["source_storyboard_sha256"],
        "scene_count": len(scene_rows),
        "cut_required_count": sum(s["status"] == "cut_required" for s in scene_rows),
        "panels": [id for id, _, _ in CASES],
        "real_lesson": {"from": "e_common", "to": "e_k_eqv",
                        "held_ids": lesson["held_ids"],
                        "written_ids": lesson["written_ids"],
                        "moved_ids": lesson["moved_ids"]},
        "controlled_stress": {
            "not_production_teacher_storyboard": True,
            "only_change": "shift e_k_eqv board/scratch region top to y=.245",
            "moved_ids": stress["moved_ids"],
            "written_ids": stress["written_ids"],
        },
        "unimplemented": [
            "automatic legitimate LaTeX multiline breaking",
            "actual page cutting after CUT_REQUIRED",
            "complete classroom header and spoken-caption composition",
            "complete narrated multi-event lesson"
        ],
        "scenes": scene_rows,
    }
    (output / "acceptance_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "README.txt").write_text(
        "2.3 VISIBLE ACCEPTANCE\n"
        "1. acceptance_gallery.png: 4 labelled scenes; only mathematics rendered by Manim.\n"
        "2. real_lesson_expansion.mp4: genuine lesson e_common -> e_k_eqv; "
        "old equations retained, one new knowledge equation written. No movement claim.\n"
        "3. controlled_movement.mp4: explicit layout-pressure test (NOT teacher-produced); "
        "two existing equations visibly move down while a new item is written.\n"
        "4. acceptance_report.json: exact proof of claimed held/written/moved objects "
        "and honest list of CUT_REQUIRED scenes.\n"
        "Neither video has real narration or subtitles. Annotation outlines "
        "appear ONLY on acceptance_gallery.png, not in raw Manim lesson frames.\n",
        encoding="utf-8")
    print("VISIBLE_ACCEPTANCE_SUCCESS", report["cut_required_count"],
          lesson["held_ids"], stress["moved_ids"])


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    main(parser.parse_args().output)
