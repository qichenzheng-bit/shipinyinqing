"""Real mobile viewport screenshots against the actual FastAPI and React-free SPA.

Browser media/database fixtures are labelled synthetic; this is layout and
interaction acceptance, not native APK or real mathematical video validation.
"""
from __future__ import annotations

import os
import tempfile
import threading
import time
from pathlib import Path
from urllib.request import urlopen

import uvicorn
from playwright.sync_api import sync_playwright
from cryptography.fernet import Fernet

from capture_pages import seed
from weiguang_backend.main import create_app
from weiguang_backend.model_hub import HubClient

ROOT=Path(__file__).resolve().parents[2]
OUTPUT=ROOT/"android_app"/"screenshots"
PORT=8943
BASE=f"http://127.0.0.1:{PORT}"


def no_horizontal_overflow(page):
    info=page.evaluate("""() => ({
      client: document.documentElement.clientWidth,
      scroll: document.documentElement.scrollWidth,
      viewport: window.innerWidth
    })""")
    assert info["scroll"]<=info["client"]+2,info


def main():
    OUTPUT.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="weiguang-android-mobile-") as temp:
        data=Path(temp)
        os.environ["WEIGUANG_MODEL_MASTER_KEY"]=Fernet.generate_key().decode()
        previous_request=HubClient._request

        def demonstration(self,suffix,body=None,timeout=90):
            if suffix=="/models":
                return {"data":[{"id":"sample-version-1"},{"id":"sample-version-2"}]}
            if suffix=="/chat/completions":
                return {"choices":[{"message":{"content":'{"ok":true}'}}]}
            raise AssertionError("Unexpected screenshot model endpoint")

        HubClient._request=demonstration
        try:
            app=create_app(data_dir=data,local_dev=True,eager=True)
            ready,review,other,teacher,curriculum=seed(app,data)
            config=uvicorn.Config(
                app,host="127.0.0.1",port=PORT,
                log_level="error",access_log=False,
            )
            server=uvicorn.Server(config)
            thread=threading.Thread(target=server.run,daemon=True)
            thread.start()
            try:
                for attempt in range(100):
                    try:
                        if urlopen(BASE+"/health",timeout=.5).status==200:
                            break
                    except Exception:
                        time.sleep(.1)
                else:
                    raise RuntimeError("ANDROID_BROWSER_FIXTURE_SERVER_NOT_READY")

                with sync_playwright() as playwright:
                    browser=playwright.chromium.launch(
                        headless=True,args=["--no-sandbox"])
                    context=browser.new_context(
                        viewport={"width":393,"height":852},
                        device_scale_factor=2,
                        is_mobile=True,has_touch=True,
                        accept_downloads=True,
                    )
                    page=context.new_page()
                    errors=[]
                    page.on("pageerror",lambda e:errors.append(str(e)))
                    page.goto(BASE,wait_until="networkidle")
                    page.get_by_role("heading",name="制作视频").wait_for()
                    no_horizontal_overflow(page)
                    page.screenshot(path=str(OUTPUT/"01-mobile-workspace.png"),full_page=True)

                    page.get_by_role("button",name="视频库").click()
                    page.get_by_text("定积分与换元法",exact=True).wait_for()
                    no_horizontal_overflow(page)
                    page.screenshot(path=str(OUTPUT/"02-mobile-library.png"),full_page=True)
                    with page.expect_download() as pending:
                        page.get_by_role("button",name="导出全部记录").click()
                    download=pending.value
                    assert download.suggested_filename.endswith(".json")
                    assert download.failure() is None

                    page.get_by_text("定积分与换元法",exact=True).click()
                    page.get_by_role("heading",name="定积分与换元法").wait_for()
                    assert page.locator("video").count()==1
                    no_horizontal_overflow(page)
                    page.screenshot(path=str(OUTPUT/"03-mobile-video.png"),full_page=True)
                    page.get_by_role("button",name="审核修改").click()
                    page.get_by_role("heading",name="微调审核").wait_for()
                    no_horizontal_overflow(page)
                    page.screenshot(path=str(OUTPUT/"04-mobile-edit-review.png"),full_page=True)

                    page.get_by_role("button",name="设置").click()
                    page.get_by_role("button",name="管理模型 API").click()
                    page.get_by_role("heading",name="模型 API").wait_for()
                    no_horizontal_overflow(page)
                    page.screenshot(path=str(OUTPUT/"05-mobile-model-api.png"),full_page=True)
                    if errors:raise AssertionError("MOBILE_BROWSER_ERRORS:"+repr(errors))
                    context.close()
                    browser.close()
            finally:
                server.should_exit=True
                thread.join(timeout=8)
        finally:
            HubClient._request=previous_request
            os.environ.pop("WEIGUANG_MODEL_MASTER_KEY",None)

    print("ANDROID_MOBILE_BROWSER_ACCEPTANCE_OK",len(list(OUTPUT.glob("*.png"))))


if __name__=="__main__":
    main()
