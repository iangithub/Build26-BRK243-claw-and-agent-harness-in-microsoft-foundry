# ============================================================
# 【檔案說明】handlers.py 的單元測試
# 用假的 ChatService + 手工組裝的 Starlette Request 驗證:
# 1. 成功 → 200 {"type": "message.complete", "text": ...}
# 2. contract 不符(kind/method/空 input)→ 400 JSON error
# 3. 設定缺少 / LLM 失敗 → 500 JSON error
# 4. body 非 JSON → 400;未預期例外 → 500(不漏例外)
# ============================================================

import json

from starlette.requests import Request

from foundry_hermes_qa_agent.chat_service import ChatService
from foundry_hermes_qa_agent.errors import ChatServiceError, MissingConfigError
from foundry_hermes_qa_agent.handlers import handle_invoke, respond


class FakeChatService(ChatService):
    def __init__(self, answer="這是回答", error=None):
        self.answer = answer
        self.error = error
        self.questions = []

    def complete(self, question: str) -> str:
        self.questions.append(question)
        if self.error is not None:
            raise self.error
        return self.answer


def make_request(body: bytes) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": [(b"content-type", b"application/json")],
    }

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


def body_of(response) -> dict:
    return json.loads(response.body)


VALID = {"kind": "hermes.rpc", "method": "prompt.submit", "input": "你好"}


async def test_success_returns_message_complete():
    service = FakeChatService(answer="答案!")
    response = await respond(VALID, service)
    assert response.status_code == 200
    assert body_of(response) == {"type": "message.complete", "text": "答案!"}
    assert service.questions == ["你好"]


async def test_unsupported_kind_returns_400():
    service = FakeChatService()
    response = await respond({"kind": "x", "method": "prompt.submit", "input": "q"}, service)
    assert response.status_code == 400
    assert body_of(response)["error"] == "invalid_request"
    assert service.questions == []


async def test_unsupported_method_returns_400():
    response = await respond(
        {"kind": "hermes.rpc", "method": "other", "input": "q"}, FakeChatService()
    )
    assert response.status_code == 400


async def test_empty_input_returns_400():
    response = await respond(
        {"kind": "hermes.rpc", "method": "prompt.submit", "params": {}}, FakeChatService()
    )
    assert response.status_code == 400
    assert "nput" in body_of(response)["message"]


async def test_chat_failure_returns_500():
    service = FakeChatService(error=ChatServiceError("LLM call failed: boom"))
    response = await respond(VALID, service)
    assert response.status_code == 500
    assert body_of(response)["error"] == "chat_service_error"


async def test_missing_config_returns_500_with_clear_message():
    service = FakeChatService(
        error=MissingConfigError("Missing required environment variables: AZURE_OPENAI_ENDPOINT")
    )
    response = await respond(VALID, service)
    assert response.status_code == 500
    assert "AZURE_OPENAI_ENDPOINT" in body_of(response)["message"]


async def test_unexpected_exception_returns_500():
    service = FakeChatService(error=RuntimeError("boom"))
    response = await respond(VALID, service)
    assert response.status_code == 500
    assert body_of(response)["error"] == "internal_error"


async def test_handle_invoke_parses_request_json():
    service = FakeChatService(answer="ok")
    request = make_request(json.dumps(VALID).encode("utf-8"))
    response = await handle_invoke(request, service)
    assert response.status_code == 200
    assert body_of(response)["text"] == "ok"


async def test_handle_invoke_rejects_invalid_json():
    request = make_request(b"{not json")
    response = await handle_invoke(request, FakeChatService())
    assert response.status_code == 400
    assert body_of(response)["error"] == "invalid_request"
