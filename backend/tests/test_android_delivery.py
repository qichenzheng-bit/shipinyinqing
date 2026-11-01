"""Source gates for Android application / real backend and mobile Web UI."""
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
ANDROID=ROOT/"android_app"/"app"
A="{http://schemas.android.com/apk/res/android}"


def test_android_secure_manifest_and_existing_server_integration():
    manifest=ET.parse(ANDROID/"src/main/AndroidManifest.xml").getroot()
    permissions=[
        x.attrib.get(A+"name") for x in manifest.findall("uses-permission")
    ]
    assert permissions==["android.permission.INTERNET"]
    app=manifest.find("application")
    assert app is not None
    assert app.attrib[A+"usesCleartextTraffic"]=="false"
    assert app.attrib[A+"allowBackup"]=="false"
    assert app.attrib[A+"icon"]=="@mipmap/ic_launcher"
    activities=app.findall("activity")
    assert len(activities)==1
    assert activities[0].attrib[A+"exported"]=="true"


def test_android_server_origin_is_single_remote_https_source():
    source=(ANDROID/"src/main/java/cn/weiguang/math/MainActivity.java").read_text(
        encoding="utf-8")
    assert "UrlPolicy.normalizeServer" in source
    assert '"/health"' in source
    assert "HttpsURLConnection" in source
    assert "setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW)" in source
    assert "setAllowFileAccess(false)" in source
    assert "setAcceptThirdPartyCookies(view, false)" in source
    assert "handler.cancel()" in source
    assert "onShowFileChooser" in source
    assert "setDownloadListener" in source
    assert "addJavascriptInterface" not in source
    assert "setJavaScriptCanOpenWindowsAutomatically(true)" not in source


def test_android_downloads_use_mediastore_and_existing_cookie_without_redirect():
    source=(ANDROID/"src/main/java/cn/weiguang/math/FileSaver.java").read_text(
        encoding="utf-8")
    assert "setInstanceFollowRedirects(false)" in source
    assert "CookieManager.getInstance().getCookie" in source
    assert "MediaStore.Downloads" in source
    assert "UrlPolicy.approvedDownload(origin, url)" in source
    assert "openOutputStream(saved)" in source
    js=(ROOT/"frontend/app.js").read_text(encoding="utf-8")
    assert "a.href='/api/v1/system/edit-history/export'" in js
    assert "URL.createObjectURL(blob)" not in js


def test_mobile_responsive_layout_and_logo_retained():
    css=(ROOT/"frontend/styles.css").read_text(encoding="utf-8")
    assert "@media (max-width: 600px)" in css
    assert ".topnav{display:grid" in css
    assert ".table-wrap tbody tr{display:grid" in css
    assert ".api-layout{display:grid" in css
    assert (ROOT/"frontend/logo.svg").exists()
    assert (ANDROID/"src/main/res/drawable/ic_launcher_foreground.xml").is_file()
    assert "CEAB63" in (
        ANDROID/"src/main/res/drawable/ic_launcher_foreground.xml"
    ).read_text(encoding="utf-8")
