import httpx
import pytest
from mailbender.client.config import ClientConfig
from mailbender.client.api import ApiClient, ApiError, NotConfigured


def _client(handler):
    transport = httpx.MockTransport(handler)
    return ApiClient(ClientConfig(url="http://api", token="tok"), transport=transport)


def test_requires_url_and_token():
    with pytest.raises(NotConfigured):
        ApiClient(ClientConfig(url=None, token=None))


def test_chat_hits_post_with_question_and_bearer():
    seen = {}

    def handler(request):
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["auth"] = request.headers.get("authorization")
        import json
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"text": "A", "sources": []})

    with _client(handler) as c:
        out = c.chat("hi")
    assert out == {"text": "A", "sources": []}
    assert seen["method"] == "POST" and seen["path"] == "/chat"
    assert seen["auth"] == "Bearer tok"
    assert seen["body"] == {"question": "hi"}


def test_run_sends_run_type():
    seen = {}

    def handler(request):
        import json
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"status": "ok", "run_type": "style"})

    with _client(handler) as c:
        c.run("style")
    assert seen["body"] == {"run_type": "style"}


def test_401_translates_to_friendly_error():
    def handler(request):
        return httpx.Response(401, json={"detail": "Unauthorized"})

    with _client(handler) as c:
        with pytest.raises(ApiError) as exc:
            c.priorities()
    assert "login" in str(exc.value).lower()


def test_connect_error_translates():
    def handler(request):
        raise httpx.ConnectError("refused")

    with _client(handler) as c:
        with pytest.raises(ApiError) as exc:
            c.priorities()
    assert "unreachable" in str(exc.value).lower()
