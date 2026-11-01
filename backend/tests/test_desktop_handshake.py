"""Desktop identity handshake binds a random nonce to the private API token."""
import hashlib
import hmac

from fastapi.testclient import TestClient

from weiguang_backend.main import create_app


def test_desktop_challenge_can_be_verified_without_sending_secret(tmp_path,monkeypatch):
    secret="desktop-private-auth-token-very-long-value"
    monkeypatch.setenv("WEIGUANG_API_TOKEN",secret)
    client=TestClient(create_app(
        data_dir=tmp_path/"app",local_dev=True,eager=True,
    ))
    nonce="7d"*32
    response=client.post(
        "/api/v1/desktop/handshake",json={"nonce":nonce},
    )
    assert response.status_code==200,response.text
    assert response.json()["schema_version"]=="1.0"
    expected=hmac.new(
        secret.encode(),("weiguang-desktop:"+nonce).encode(),
        hashlib.sha256,
    ).hexdigest()
    assert hmac.compare_digest(expected,response.json()["proof"])
    assert secret not in response.text
    assert client.get("/api/v1/lessons").status_code==401


def test_desktop_challenge_rejects_malformed_nonce_or_missing_key(tmp_path,monkeypatch):
    monkeypatch.setenv("WEIGUANG_API_TOKEN","a"*40)
    client=TestClient(create_app(
        data_dir=tmp_path/"source",local_dev=True,eager=True,
    ))
    for nonce in ["","123","g"*64,"7a"*31,"7d"*64,"../foo"]:
        response=client.post(
            "/api/v1/desktop/handshake",json={"nonce":nonce},
        )
        assert response.status_code==422,response.text
    monkeypatch.delenv("WEIGUANG_API_TOKEN",raising=False)
    unavailable=client.post(
        "/api/v1/desktop/handshake",json={"nonce":"7d"*32},
    )
    assert unavailable.status_code==503
