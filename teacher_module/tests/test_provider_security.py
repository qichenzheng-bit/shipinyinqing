"""Security regressions for the configured AI transport boundary.

Both tests use only local loopback sockets and an intentionally fake token.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from math_teacher.models import Understanding
from math_teacher.provider import OpenAICompatibleJsonModel, ProviderError


def _provider(url: str) -> OpenAICompatibleJsonModel:
    return OpenAICompatibleJsonModel(model="test-model", api_key="FAKE_TEST_KEY", base_url=url, timeout=3)


@pytest.mark.parametrize("malicious_url", [
    "http://localhost.evil.example/v1",
    "http://127.0.0.1.evil.example/v1",
    "http://localhost@evil.example/v1",
    "http://127.0.0.1:999@evil.example/v1",
])
def test_http_only_allows_exact_loopback_hosts(malicious_url):
    with pytest.raises(ProviderError, match="HTTPS|loopback"):
        _provider(malicious_url)


@pytest.mark.parametrize("allowed_url", [
    "http://localhost:8765/v1",
    "http://127.0.0.1:8765/v1",
    "https://api.example.com/v1",
])
def test_https_or_exact_loopback_hosts_remain_allowed(allowed_url):
    assert _provider(allowed_url).base_url == allowed_url


def test_provider_does_not_follow_redirect_or_send_bearer_key_to_another_server():
    observed_headers: list[str | None] = []

    class Receiver(BaseHTTPRequestHandler):
        def do_GET(self):
            observed_headers.append(self.headers.get("Authorization"))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"choices":[{"message":{"content":"{}"}}]}')

        do_POST = do_GET

        def log_message(self, fmt, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Receiver) as receiver:
        receiver_thread = Thread(target=receiver.serve_forever, daemon=True)
        receiver_thread.start()
        try:
            class Redirector(BaseHTTPRequestHandler):
                def do_POST(self):
                    self.send_response(302)
                    self.send_header("Location", f"http://127.0.0.1:{receiver.server_port}/capture")
                    self.end_headers()

                def log_message(self, fmt, *args):
                    pass

            with ThreadingHTTPServer(("127.0.0.1", 0), Redirector) as redirector:
                redirector_thread = Thread(target=redirector.serve_forever, daemon=True)
                redirector_thread.start()
                try:
                    provider = _provider(f"http://127.0.0.1:{redirector.server_port}/v1")
                    with pytest.raises(ProviderError, match="HTTP 302"):
                        provider.generate(stage="A", system="test", user_json="{}", schema=Understanding)
                    assert observed_headers == [], "Bearer key must never reach the redirect target"
                finally:
                    redirector.shutdown()
                    redirector_thread.join(timeout=3)
        finally:
            receiver.shutdown()
            receiver_thread.join(timeout=3)
