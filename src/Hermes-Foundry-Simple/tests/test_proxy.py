# ============================================================
# 【檔案說明】proxy.py 的單元測試
# 用假的 FoundryClient(依賴注入)+ io.StringIO 跑主迴圈:
# 1. 六個本機 method 的回覆形狀
# 2. prompt.submit 的轉送與 input/message fallback
# 3. 各種錯誤情境對應正確的 JSON-RPC 錯誤碼,且迴圈不會 crash
# 4. stdout 只含 JSON(無 log 污染)、中文不被 escape
# ============================================================

import io
import json

from hermes_foundry_proxy import proxy as proxy_module
from hermes_foundry_proxy.foundry import (
    AuthError,
    ConfigError,
    FoundryHttpError,
    FoundryInvalidJsonError,
    FoundryMissingTextError,
    FoundryRequestError,
)
from hermes_foundry_proxy.models import FoundryReply


class FakeFoundryClient:
    def __init__(self, reply_text="hi from foundry", error=None):
        self.reply_text = reply_text
        self.error = error
        self.calls = []

    def submit_prompt(self, input_text):
        self.calls.append(input_text)
        if self.error is not None:
            raise self.error
        return FoundryReply(type="message.complete", text=self.reply_text)


def run_proxy(lines, client=None):
    """把多行請求餵進主迴圈,回傳 (解析後的 response 列表, 原始 stdout)。"""
    stdin = io.StringIO("".join(f"{line}\n" for line in lines))
    stdout = io.StringIO()
    proxy_module.run(stdin, stdout, client or FakeFoundryClient())
    raw = stdout.getvalue()
    return [json.loads(line) for line in raw.splitlines() if line], raw


def rpc(method, request_id=1, params=None):
    message = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        message["params"] = params
    return json.dumps(message, ensure_ascii=False)


# --- 本機 method ---

def test_gateway_ready():
    responses, _ = run_proxy([rpc("gateway.ready")])
    assert responses == [
        {"jsonrpc": "2.0", "id": 1, "result": {"ready": True, "backend": "foundry"}}
    ]


def test_commands_catalog():
    responses, _ = run_proxy([rpc("commands.catalog")])
    assert responses[0]["result"] == {"commands": []}


def test_config_get():
    responses, _ = run_proxy([rpc("config.get")])
    assert responses[0]["result"] == {"backend": "foundry", "streaming": False}


def test_session_create_returns_local_session_id():
    responses, _ = run_proxy([rpc("session.create")])
    session_id = responses[0]["result"]["session_id"]
    assert session_id.startswith("local-") and len(session_id) > len("local-")


def test_session_status():
    responses, _ = run_proxy([rpc("session.status")])
    assert responses[0]["result"] == {"status": "ready"}


def test_session_close():
    responses, _ = run_proxy([rpc("session.close")])
    assert responses[0]["result"] == {"closed": True}


def test_string_request_id_is_preserved():
    responses, _ = run_proxy([rpc("gateway.ready", request_id="req-abc")])
    assert responses[0]["id"] == "req-abc"


# --- prompt.submit ---

def test_prompt_submit_forwards_input():
    client = FakeFoundryClient(reply_text="answer!")
    responses, _ = run_proxy([rpc("prompt.submit", params={"input": "你好"})], client)
    assert client.calls == ["你好"]
    assert responses == [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"type": "message.complete", "text": "answer!"},
        }
    ]


def test_prompt_submit_falls_back_to_message_param():
    client = FakeFoundryClient()
    run_proxy([rpc("prompt.submit", params={"message": "from message"})], client)
    assert client.calls == ["from message"]


def test_prompt_submit_prefers_input_over_message():
    client = FakeFoundryClient()
    run_proxy([rpc("prompt.submit", params={"input": "a", "message": "b"})], client)
    assert client.calls == ["a"]


def test_prompt_submit_without_input_or_message_is_invalid_params():
    client = FakeFoundryClient()
    responses, _ = run_proxy([rpc("prompt.submit", params={})], client)
    assert responses[0]["error"]["code"] == -32602
    assert client.calls == []


def test_chinese_text_is_not_escaped_in_stdout():
    client = FakeFoundryClient(reply_text="繁體中文回覆")
    _, raw = run_proxy([rpc("prompt.submit", params={"input": "嗨"})], client)
    assert "繁體中文回覆" in raw


# --- 錯誤處理 ---

def test_invalid_json_line_returns_parse_error_and_loop_survives():
    responses, _ = run_proxy(["{not json", rpc("gateway.ready", request_id=2)])
    assert responses[0]["error"]["code"] == -32700
    assert responses[0]["id"] is None
    assert responses[1]["result"]["ready"] is True


def test_missing_method_field_is_invalid_request():
    responses, _ = run_proxy(['{"jsonrpc": "2.0", "id": 7}'])
    assert responses[0]["error"]["code"] == -32600
    assert responses[0]["id"] == 7


def test_non_object_json_is_invalid_request():
    responses, _ = run_proxy(["[1, 2, 3]"])
    assert responses[0]["error"]["code"] == -32600


def test_unknown_method_is_method_not_found():
    responses, _ = run_proxy([rpc("session.events")])
    assert responses[0]["error"]["code"] == -32601
    assert "session.events" in responses[0]["error"]["message"]


def test_blank_lines_are_ignored():
    responses, raw = run_proxy(["", "   ", rpc("gateway.ready")])
    assert len(responses) == 1
    assert len([line for line in raw.splitlines() if line]) == 1


def test_foundry_error_mapping():
    cases = [
        (ConfigError("endpoint missing"), -32000),
        (AuthError("run az login"), -32001),
        (FoundryHttpError(503, "upstream busy"), -32002),
        (FoundryRequestError("connect timeout"), -32002),
        (FoundryInvalidJsonError("not json"), -32003),
        (FoundryMissingTextError("no text"), -32004),
        (RuntimeError("boom"), -32603),
    ]
    for error, expected_code in cases:
        client = FakeFoundryClient(error=error)
        responses, _ = run_proxy([rpc("prompt.submit", params={"input": "x"})], client)
        assert responses[0]["error"]["code"] == expected_code, error


def test_foundry_http_error_includes_status_and_body():
    client = FakeFoundryClient(error=FoundryHttpError(404, "agent not found"))
    responses, _ = run_proxy([rpc("prompt.submit", params={"input": "x"})], client)
    error = responses[0]["error"]
    assert error["data"] == {"status_code": 404, "body": "agent not found"}


def test_loop_continues_after_foundry_error():
    client = FakeFoundryClient(error=RuntimeError("boom"))
    responses, _ = run_proxy(
        [rpc("prompt.submit", params={"input": "x"}), rpc("session.status", request_id=2)],
        client,
    )
    assert responses[0]["error"]["code"] == -32603
    assert responses[1]["result"] == {"status": "ready"}
