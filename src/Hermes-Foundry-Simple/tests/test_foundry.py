# ============================================================
# 【檔案說明】foundry.py 的單元測試
# 用 httpx.MockTransport(不發真實網路請求)+ 假 credential
# (stub get_token,不碰真實 Azure)驗證:
# 1. request 的 headers / body / URL(含 agent_session_id 附加)
# 2. 各種失敗情境拋出正確的例外
# 3. token 快取:未到期不重取,接近到期才重取
# ============================================================

import time

import httpx
import pytest
from azure.core.credentials import AccessToken

from hermes_foundry_proxy.config import Settings
from hermes_foundry_proxy.foundry import (
    FOUNDRY_FEATURES,
    TOKEN_SCOPE,
    AuthError,
    ConfigError,
    FoundryClient,
    FoundryHttpError,
    FoundryInvalidJsonError,
    FoundryMissingTextError,
    FoundryRequestError,
)

ENDPOINT = "https://unit.test/agents/demo/invocations?api-version=2025-05-15-preview"


class StubCredential:
    def __init__(self, expires_in=3600):
        self.expires_in = expires_in
        self.calls = 0
        self.scopes = None

    def get_token(self, *scopes, **kwargs):
        self.calls += 1
        self.scopes = scopes
        return AccessToken("stub-token", int(time.time()) + self.expires_in)


class FailingCredential:
    def get_token(self, *scopes, **kwargs):
        raise RuntimeError("no credential available")


def make_client(handler, endpoint=ENDPOINT, session_id=None, credential=None):
    settings = Settings(invocations_endpoint=endpoint, agent_session_id=session_id)
    return FoundryClient(
        settings,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        credential=credential if credential is not None else StubCredential(),
    )


def ok_handler(captured):
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"type": "message.complete", "text": "answer"})

    return handler


def test_submit_prompt_sends_expected_request():
    captured = []
    credential = StubCredential()
    client = make_client(ok_handler(captured), session_id="sess-1", credential=credential)

    reply = client.submit_prompt("你好")

    assert reply.type == "message.complete"
    assert reply.text == "answer"
    request = captured[0]
    assert request.method == "POST"
    assert request.url.params["api-version"] == "2025-05-15-preview"
    assert request.url.params["agent_session_id"] == "sess-1"
    assert request.headers["Authorization"] == "Bearer stub-token"
    assert request.headers["Content-Type"] == "application/json"
    assert request.headers["Foundry-Features"] == FOUNDRY_FEATURES
    import json

    assert json.loads(request.content) == {
        "kind": "hermes.rpc",
        "method": "prompt.submit",
        "input": "你好",
    }
    assert credential.scopes == (TOKEN_SCOPE,)


def test_missing_endpoint_raises_config_error():
    client = make_client(ok_handler([]), endpoint=None)
    with pytest.raises(ConfigError, match="HERMES_FOUNDRY_INVOCATIONS_ENDPOINT"):
        client.submit_prompt("hi")


def test_credential_failure_raises_auth_error_with_az_login_hint():
    client = make_client(ok_handler([]), credential=FailingCredential())
    with pytest.raises(AuthError, match="az login"):
        client.submit_prompt("hi")


def test_non_2xx_raises_http_error_with_status_and_snippet():
    def handler(request):
        return httpx.Response(500, text="x" * 1000)

    client = make_client(handler)
    with pytest.raises(FoundryHttpError) as excinfo:
        client.submit_prompt("hi")
    assert excinfo.value.status_code == 500
    assert excinfo.value.body_snippet == "x" * 500  # 摘要截斷在 500 字


def test_invalid_json_response_raises_protocol_error():
    def handler(request):
        return httpx.Response(200, text="<html>not json</html>")

    client = make_client(handler)
    with pytest.raises(FoundryInvalidJsonError):
        client.submit_prompt("hi")


@pytest.mark.parametrize(
    "payload",
    [{"type": "message.complete"}, {"text": 123}, {"text": None}, ["a", "b"]],
)
def test_response_without_usable_text_raises_missing_text_error(payload):
    def handler(request):
        return httpx.Response(200, json=payload)

    client = make_client(handler)
    with pytest.raises(FoundryMissingTextError):
        client.submit_prompt("hi")


def test_missing_type_defaults_to_message_complete():
    def handler(request):
        return httpx.Response(200, json={"text": "only text"})

    client = make_client(handler)
    reply = client.submit_prompt("hi")
    assert reply.type == "message.complete"
    assert reply.text == "only text"


def test_network_failure_raises_request_error():
    def handler(request):
        raise httpx.ConnectError("connection refused")

    client = make_client(handler)
    with pytest.raises(FoundryRequestError):
        client.submit_prompt("hi")


def test_token_is_cached_while_valid():
    credential = StubCredential(expires_in=3600)
    client = make_client(ok_handler([]), credential=credential)
    client.submit_prompt("a")
    client.submit_prompt("b")
    assert credential.calls == 1


def test_token_is_refreshed_near_expiry():
    credential = StubCredential(expires_in=60)  # 距到期 < 5 分鐘的快取邊界
    client = make_client(ok_handler([]), credential=credential)
    client.submit_prompt("a")
    client.submit_prompt("b")
    assert credential.calls == 2
