"""Browser-driven snapshots of the ACTUAL same-origin frontend and FastAPI.

Dedicated demo database and reviewed source fixture; no movie is presented as
a rendered mathematics lesson. Screenshots are UI acceptance evidence only.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib.request import urlopen

import uvicorn
from playwright.sync_api import sync_playwright

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/
    "animation_engine"/"tests"/"fixtures"))
from build_novel_substitution_integral import build

from weiguang_backend.main import create_app
from weiguang_backend.models import Lesson

PORT=8942
BASE=f"http://127.0.0.1:{PORT}"


def seed(app,base):
    fixture=base/"reviewed"
    build(fixture)
    sample=json.loads(
        (fixture/"integration"/"teaching_package.json").read_text(encoding="utf-8")
    )["source"]
    with app.state.SessionLocal() as db:
        ready=Lesson(title="定积分与换元法",problem=sample["problem"],
            reference_solution=sample["reference_solution"],status="ready",
            fps=60,voice="zh-CN-YunxiNeural")
        review=Lesson(title="极限与泰勒展开（审核演示）",
            problem=sample["problem"],
            reference_solution=sample["reference_solution"],
            status="script_pending")
        other=Lesson(title="矩阵初等变换",problem="求矩阵的秩",
            reference_solution="示例中只保存文字，不触发数学推理。",
            status="draft")
        db.add_all((ready,review,other));db.commit()
        db.refresh(ready);db.refresh(review);db.refresh(other)
        video=base/"lessons"/ready.id/"output"/"latest.mp4"
        video.parent.mkdir(parents=True,exist_ok=True)
        # The HTML video player uses a non-video placeholder during UI
        # screenshots; this byte sequence is not reported as a real MP4.
        video.write_bytes(b"UI_SCREENSHOT_FIXTURE_NOT_PLAYABLE")
        ready.latest_video=str(video)
        output=base/"lessons"/review.id/"package"
        import shutil
        shutil.copytree(fixture,output)
        db.commit()
        return ready.id,review.id,other.id


def main():
    shots=Path(__file__).resolve().parents[2]/"frontend"/"screenshots"
    shots.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="weiguang-browser-") as tmp:
        data=Path(tmp)
        app=create_app(data_dir=data,local_dev=True,eager=True)
        ready,review,other=seed(app,data)
        config=uvicorn.Config(app,host="127.0.0.1",port=PORT,
                              log_level="error",access_log=False)
        server=uvicorn.Server(config)
        thread=threading.Thread(target=server.run,daemon=True)
        thread.start()
        for _ in range(100):
            try:
                if urlopen(BASE+"/health",timeout=.5).status==200:break
            except Exception:
                time.sleep(.1)
        else:
            raise RuntimeError("UI_ACCEPTANCE_SERVER_NOT_READY")
        with sync_playwright() as p:
            browser=p.chromium.launch(
                headless=True,args=["--no-sandbox"],
            )
            page=browser.new_page(viewport={"width":1440,"height":900},
                                  device_scale_factor=1)
            errors=[]
            page.on("pageerror",lambda error: errors.append(str(error)))
            page.goto(BASE,wait_until="networkidle")
            page.get_by_role("heading",name="制作视频").wait_for()
            page.screenshot(path=str(shots/"01-workspace.png"),full_page=True)
            page.get_by_role("button",name="视频库").click()
            page.get_by_text("定积分与换元法",exact=True).wait_for()
            page.screenshot(path=str(shots/"02-library.png"),full_page=True)
            page.get_by_text("定积分与换元法",exact=True).click()
            page.get_by_role("heading",name="定积分与换元法").wait_for()
            page.screenshot(path=str(shots/"03-video-detail.png"),full_page=True)
            page.get_by_role("button",name="视频库").click()
            page.get_by_text("极限与泰勒展开（审核演示）",exact=True).click()
            page.get_by_role("button",name="查看完整讲稿").click()
            page.get_by_role("heading",name="讲稿审核").wait_for()
            page.screenshot(path=str(shots/"04-review.png"),full_page=True)
            page.get_by_role("button",name="设置").click()
            page.get_by_role("heading",name="设置").wait_for()
            page.screenshot(path=str(shots/"05-settings.png"),full_page=True)
            page.get_by_role("button",name="视频库").click()
            page.locator('input.select-item[value="'+other+'"]').check()
            page.get_by_role("button",name="删除所选").click()
            page.get_by_role("heading",name="批量删除").wait_for()
            page.screenshot(path=str(shots/"06-batch-delete.png"),full_page=True)
            page.get_by_role("button",name="确认删除").click()
            page.get_by_role("button",name="回收站").click()
            page.get_by_role("heading",name="回收站").wait_for()
            page.get_by_text("矩阵初等变换",exact=True).wait_for()
            page.screenshot(path=str(shots/"07-trash.png"),full_page=True)
            page.get_by_role("button",name="恢复").click()
            page.get_by_text("回收站为空",exact=True).wait_for()
            if errors:
                raise AssertionError("UI_PAGE_ERRORS: "+str(errors))
            browser.close()
        server.should_exit=True
        thread.join(timeout=5)
    print("BROWSER_ACCEPTANCE_OK",len(list(shots.glob("*.png"))),
          "actual frontend screens and CRUD/review navigation")


if __name__=="__main__":
    main()
