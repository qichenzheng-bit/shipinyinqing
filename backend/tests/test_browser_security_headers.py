"""Security contract for the browser workbench and authenticated API."""
from fastapi.testclient import TestClient
from weiguang_backend.main import create_app


def test_browser_csp_frame_and_api_no_store(tmp_path,monkeypatch):
    monkeypatch.setenv("WEIGUANG_API_TOKEN","security-test-token-not-for-release")
    monkeypatch.setenv("WEIGUANG_SESSION_SECRET","security-test-session-secret")
    app=create_app(data_dir=tmp_path,local_dev=True,eager=True)
    try:
        client=TestClient(app)
        page=client.get("/")
        assert page.status_code==200
        headers=page.headers
        assert headers["x-content-type-options"]=="nosniff"
        assert headers["x-frame-options"]=="DENY"
        assert headers["referrer-policy"]=="no-referrer"
        assert headers["cross-origin-resource-policy"]=="same-origin"
        policy=headers["content-security-policy"]
        for directive in ("script-src 'self'","connect-src 'self'",
                          "object-src 'none'","frame-ancestors 'none'",
                          "base-uri 'none'"):
            assert directive in policy
        assert "unsafe-eval" not in policy
        assert "https://accounts.google.com" not in policy
        api=client.get("/api/v1/ai/status",headers={
            "X-API-Key":"security-test-token-not-for-release"})
        assert api.status_code==200
        assert api.headers["cache-control"]=="no-store"
    finally:
        app.state.db_engine.dispose()


def test_cookie_mutations_reject_cross_origin_requests(tmp_path,monkeypatch):
    monkeypatch.setenv("WEIGUANG_API_TOKEN","security-test-token-not-for-release")
    monkeypatch.setenv("WEIGUANG_SESSION_SECRET","security-test-session-secret")
    app=create_app(data_dir=tmp_path,local_dev=True,eager=True)
    try:
        client=TestClient(app)
        login=client.post("/api/v1/auth/login",json={
            "token":"security-test-token-not-for-release"})
        assert login.status_code==200
        assert "httponly" in login.headers["set-cookie"].lower()
        assert "samesite=strict" in login.headers["set-cookie"].lower()
        denied=client.post("/api/v1/projects",
                           headers={"Origin":"https://untrusted.invalid"},
                           json={"title":"must never be created"})
        assert denied.status_code==403
        accepted=client.post("/api/v1/projects",
                             headers={"Origin":"http://testserver"},
                             json={"title":"local trusted request"})
        assert accepted.status_code==201
    finally:
        app.state.db_engine.dispose()
