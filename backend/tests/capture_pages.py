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
from cryptography.fernet import Fernet
from weiguang_backend.model_hub import HubClient

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/
    "animation_engine"/"tests"/"fixtures"))
from build_novel_substitution_integral import build
from test_compiler import curriculum_fixture

from weiguang_backend.main import create_app
from weiguang_backend.models import Lesson, EditRecord

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
        teaching=Lesson(title="数学教师教学草稿",
            problem=sample["problem"],reference_solution=sample["reference_solution"],
            status="teacher_review_pending")
        curriculum=Lesson(title="课堂板书与口播编排",
            problem=sample["problem"],reference_solution=sample["reference_solution"],
            status="curriculum_review_pending")
        db.add_all((ready,review,other,teaching,curriculum));db.commit()
        db.refresh(ready);db.refresh(review);db.refresh(other);db.refresh(teaching)
        db.refresh(curriculum)
        _,candidate=curriculum_fixture(base/"curriculum_fixture")
        candidate_file=base/"lessons"/curriculum.id/"curriculum_candidate.json"
        candidate_file.parent.mkdir(parents=True,exist_ok=True)
        candidate_file.write_text(json.dumps(candidate,ensure_ascii=False),encoding="utf-8")
        draft=base/"lessons"/teaching.id/"teacher_draft"/"teaching_package.json"
        draft.parent.mkdir(parents=True,exist_ok=True)
        draft.write_text(json.dumps(
            json.loads((fixture/"integration"/"teaching_package.json").read_text(encoding="utf-8")),
            ensure_ascii=False,
        ),encoding="utf-8")
        video=base/"lessons"/ready.id/"output"/"latest.mp4"
        video.parent.mkdir(parents=True,exist_ok=True)
        # The HTML video player uses a non-video placeholder during UI
        # screenshots; this byte sequence is not reported as a real MP4.
        video.write_bytes(b"UI_SCREENSHOT_FIXTURE_NOT_PLAYABLE")
        ready.latest_video=str(video)
        review_folder=base/"lessons"/ready.id/"edit_review_ui"
        (review_folder/"package").mkdir(parents=True,exist_ok=True)
        (review_folder/"review.json").write_text(
            json.dumps({
                "schema_version":"1.0","status":"pending",
                "instruction":"结尾总结再简洁一点",
                "source_revision":0,
                "changed":["spoken_classroom.json"],
                "candidate_digests":{},
                "script_sha256":None,
                "source_spoken_sha256":"fixture",
                "reviewer":None,
                "reviewer_required":True,
                "plan":{"requirements":[{
                    "id":"r1","instruction":"结尾总结再简洁一点",
                    "target":"归纳总结","operation_ids":["o1"],
                }]},
            },ensure_ascii=False),encoding="utf-8",
        )
        (review_folder/"package"/"lesson_script.md").write_text(
            "本轮口播先归纳核心公式，再提醒容易混淆的知识点。",
            encoding="utf-8",
        )
        db.add(EditRecord(
            lesson_id=ready.id,original_instruction="结尾总结再简洁一点",
            status="review_pending",source_revision=0,
            review_path=str(review_folder),
        ))
        output=base/"lessons"/review.id/"package"
        import shutil
        shutil.copytree(fixture,output)
        db.commit()
        return ready.id,review.id,other.id,teaching.id,curriculum.id


def main():
    shots=Path(__file__).resolve().parents[2]/"frontend"/"screenshots"
    shots.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="weiguang-browser-") as tmp:
        data=Path(tmp)
        os.environ["WEIGUANG_MODEL_MASTER_KEY"]=Fernet.generate_key().decode()
        # Browser-only stub: exercises the real authenticated API and UI without
        # contacting a paid provider or pretending any model was actually called.
        old_hub_request=HubClient._request
        def screenshot_model_provider(self,suffix,body=None,timeout=90):
            if suffix=="/models":
                return {"data":[
                    {"id":"demo-math-model-2026-06"},
                    {"id":"demo-math-model-2026-11"},
                ]}
            if suffix=="/chat/completions":
                return {"choices":[{"message":{"content":'{"ok":true}'}}]}
            raise AssertionError("Unexpected screenshot provider endpoint")
        HubClient._request=screenshot_model_provider
        app=create_app(data_dir=data,local_dev=True,eager=True)
        ready,review,other,teaching,curriculum=seed(app,data)
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
            page.get_by_role("button",name="审核修改").click()
            page.get_by_role("heading",name="微调审核").wait_for()
            page.screenshot(path=str(shots/"12-edit-review.png"),full_page=True)
            page.get_by_role("button",name="退回修改").click()
            page.get_by_role("heading",name="定积分与换元法").wait_for()
            page.get_by_role("button",name="视频库").click()
            page.get_by_text("极限与泰勒展开（审核演示）",exact=True).click()
            page.get_by_role("button",name="查看完整讲稿").click()
            page.get_by_role("heading",name="讲稿审核").wait_for()
            page.screenshot(path=str(shots/"04-review.png"),full_page=True)
            page.get_by_role("button",name="设置").click()
            page.get_by_role("heading",name="设置").wait_for()
            page.screenshot(path=str(shots/"05-settings.png"),full_page=True)
            page.get_by_role("button",name="管理模型 API").click()
            page.get_by_role("heading",name="模型 API").wait_for()
            page.locator("#ai-name").fill("教学 API 验收连接")
            page.locator("#ai-key").fill("ONLY_BROWSER_FIXTURE_NOT_REAL_API_KEY")
            page.get_by_role("button",name="保存连接").click()
            page.get_by_role("button",name="读取模型列表").click()
            page.locator("#ai-versions").select_option("demo-math-model-2026-11")
            page.get_by_role("button",name="测试模型连接").click()
            page.locator(".api-layout .notice").filter(has_text="连接成功 · JSON 输出验证通过").wait_for()
            page.get_by_role("button",name="应用模型版本").click()
            page.locator("#ai-manual-model").wait_for()
            assert page.locator("#ai-key").input_value()==""
            page.screenshot(path=str(shots/"14-model-api-settings.png"),full_page=True)
            page.get_by_role("button",name="返回设置").click()
            page.once("dialog",lambda dialog: dialog.accept("视频项目管理测试"))
            page.get_by_role("button",name="新建",exact=True).click()
            page.get_by_text("视频项目管理测试",exact=True).wait_for()
            page.screenshot(path=str(shots/"11-project-management.png"),full_page=True)
            page.locator("input.project-item").check()
            page.get_by_role("button",name="批量删除",exact=True).click()
            page.get_by_role("heading",name="批量删除项目").wait_for()
            page.get_by_role("button",name="确认删除").click()
            page.once("dialog",lambda dialog: dialog.accept())
            page.get_by_role("button",name="回收站",exact=True).click()
            page.get_by_text("视频项目管理测试",exact=True).wait_for()
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
            os.environ["WEIGUANG_API_TOKEN"]="preview-browser-only-auth-secret"
            page.reload(wait_until="networkidle")
            page.get_by_role("heading",name="登录微光数学").wait_for()
            page.screenshot(path=str(shots/"08-login.png"),full_page=True)
            page.locator("#login-secret").fill("preview-browser-only-auth-secret")
            page.get_by_role("button",name="登录",exact=True).click()
            page.get_by_role("heading",name="制作视频").wait_for()
            page.get_by_role("button",name="视频库").click()
            page.get_by_text("数学教师教学草稿",exact=True).click()
            page.get_by_role("button",name="查看教学草稿").click()
            page.get_by_role("heading",name="教学草稿").wait_for()
            page.screenshot(path=str(shots/"09-teacher-draft.png"),full_page=True)
            page.locator("#teacher-reviewer").fill("数学审核教师")
            page.locator("#teacher-check").check()
            page.get_by_role("button",name="确认教学草稿").click()
            page.get_by_text("待准备",exact=True).wait_for()
            page.get_by_role("button",name="视频库").click()
            page.get_by_text("课堂板书与口播编排",exact=True).click()
            page.get_by_role("button",name="审核课堂编排").click()
            page.get_by_role("heading",name="课堂编排审核").wait_for()
            page.screenshot(path=str(shots/"10-curriculum.png"),full_page=True)
            page.locator("#curriculum-reviewer").fill("数学审核教师")
            page.locator("#curriculum-check").check()
            page.get_by_role("button",name="确认课堂编排").click()
            page.get_by_text("待审核",exact=True).wait_for()
            os.environ.pop("WEIGUANG_API_TOKEN",None)
            if errors:
                raise AssertionError("UI_PAGE_ERRORS: "+str(errors))
            browser.close()
        server.should_exit=True
        thread.join(timeout=12)
        if thread.is_alive():
            raise RuntimeError("WINDOWS_UI_TEST_SERVER_DID_NOT_STOP")
        # SQLite file handles persist across SQLAlchemy connection pools on
        # Windows. Dispose before TemporaryDirectory removes the test database.
        from sqlalchemy.orm import close_all_sessions
        close_all_sessions()
        app.state.SessionLocal.kw["bind"].dispose()
        HubClient._request=old_hub_request
        os.environ.pop("WEIGUANG_MODEL_MASTER_KEY",None)
    print("BROWSER_ACCEPTANCE_OK",len(list(shots.glob("*.png"))),
          "actual frontend screens and CRUD/review navigation")


if __name__=="__main__":
    main()
