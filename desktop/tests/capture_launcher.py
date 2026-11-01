"""Capture actual desktop launcher HTML in Chromium (no fake Docker launch).

This is a layout/UI fixture, not proof the installed Electron .exe has run.
Native Windows installers are built and checked independently on windows-latest.
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]


def main():
    source=ROOT/"desktop"/"launcher.html"
    output=ROOT/"desktop"/"screenshots"
    output.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True,args=["--no-sandbox"])
        page=browser.new_page(viewport={"width":760,"height":590},device_scale_factor=1)
        problems=[]
        page.on("pageerror",lambda error:problems.append(str(error)))
        page.add_init_script("""window.weiGuangLauncher={
            status: async ()=>({ok:true,mode:'local',url:'http://127.0.0.1:8000'}),
            startLocal: async ()=>({ok:false,error:'仅截图，不启动 Docker'}),
            connectLocal: async ()=>({ok:false,error:'仅截图，不启动 Docker'}),
            connectRemote: async ()=>({ok:false,error:'仅截图，不连接服务器'}),
            onProgress: ()=>{}
        };""")
        page.goto(source.as_uri(),wait_until="networkidle")
        page.get_by_role("heading",name="微光数学").wait_for()
        page.get_by_role("button",name="启动并进入工作台").wait_for()
        page.screenshot(path=str(output/"01-windows-app-local-launcher.png"),full_page=True)
        page.get_by_role("tab",name="连接服务器").click()
        page.get_by_label("服务器 HTTPS 地址").fill("https://math.example.com")
        page.get_by_role("button",name="连接服务器",exact=True).wait_for()
        page.screenshot(path=str(output/"02-windows-app-server-launcher.png"),full_page=True)
        assert not problems,problems
        browser.close()
    print("DESKTOP_LAUNCHER_UI_ACCEPTED",len(list(output.glob("*.png"))))


if __name__=="__main__":
    main()
