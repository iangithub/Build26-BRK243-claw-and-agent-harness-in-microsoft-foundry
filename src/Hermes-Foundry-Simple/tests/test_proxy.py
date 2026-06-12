# ============================================================
# 【檔案說明】proxy.py 的單元測試
# 用假的 FoundryClient(依賴注入)+ io.StringIO 跑主迴圈:
# 1. 啟動時主動推 gateway.ready 事件(TUI 判定就緒的依據)
# 2. 本機 method 的回覆形狀
# 3. prompt.submit 的 async turn:ack + message.start/complete 事件、
#    text/input/message fallback、session busy(4009)
# 4. 各種錯誤情境:Foundry 錯誤以 error 事件收尾,迴圈不會 crash
# 5. stdout 只含 JSON(無 log 污染)、中文不被 escape
# ============================================================

import io
import json
import threading

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
from hermes_foundry_proxy.proxy import JsonRpcProxy, _LineWriter


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
    """把多行請求餵進主迴圈,回傳 (全部 frame, response 列表, 事件列表, 原始 stdout)。

    frame 分兩種:有 id 的是 RPC response;method="event" 的是事件通知。
    run() 在 EOF 後會 join worker thread,所以事件保證已寫出。
    """
    stdin = io.StringIO("".join(f"{line}\n" for line in lines))
    stdout = io.StringIO()
    proxy_module.run(stdin, stdout, client or FakeFoundryClient())
    raw = stdout.getvalue()
    frames = [json.loads(line) for line in raw.splitlines() if line]
    responses = [f for f in frames if "id" in f]
    events = [f["params"] for f in frames if f.get("method") == "event"]
    return frames, responses, events, raw


def rpc(method, request_id=1, params=None):
    message = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        message["params"] = params
    return json.dumps(message, ensure_ascii=False)


# --- 啟動握手 ---

def test_gateway_ready_event_is_pushed_at_startup():
    frames, _, events, _ = run_proxy([])
    assert frames[0] == {
        "jsonrpc": "2.0",
        "method": "event",
        "params": {"type": "gateway.ready"},
    }
    assert events[0]["type"] == "gateway.ready"


# --- 本機 method ---

def test_gateway_ready():
    _, responses, _, _ = run_proxy([rpc("gateway.ready")])
    assert responses == [
        {"jsonrpc": "2.0", "id": 1, "result": {"ready": True, "backend": "foundry"}}
    ]


def test_commands_catalog_shape_matches_tui():
    _, responses, _, _ = run_proxy([rpc("commands.catalog")])
    assert responses[0]["result"] == {
        "pairs": [],
        "canon": {},
        "categories": [],
        "sub": {},
        "skill_count": 0,
    }


def test_config_get():
    _, responses, _, _ = run_proxy([rpc("config.get")])
    assert responses[0]["result"] == {"backend": "foundry", "streaming": False}


def test_setup_status_reports_provider_configured():
    _, responses, _, _ = run_proxy([rpc("setup.status")])
    assert responses[0]["result"] == {"provider_configured": True}


def test_input_detect_drop_never_matches():
    _, responses, _, _ = run_proxy([rpc("input.detect_drop", params={"text": "/tmp/x.png"})])
    assert responses[0]["result"] == {"matched": False}


def test_session_create_returns_local_session_id_and_info_version():
    _, responses, _, _ = run_proxy([rpc("session.create", params={"cols": 120})])
    result = responses[0]["result"]
    session_id = result["session_id"]
    assert session_id.startswith("local-") and len(session_id) > len("local-")
    # info.version 有值,TUI 才會直接進 ready 而非卡在 starting agent…
    assert result["info"]["version"]
    assert result["info"]["model"]


def test_session_status():
    _, responses, _, _ = run_proxy([rpc("session.status")])
    assert responses[0]["result"] == {"status": "ready"}


def test_session_interrupt_acks():
    _, responses, _, _ = run_proxy([rpc("session.interrupt", params={"session_id": "s1"})])
    assert responses[0]["result"] == {"interrupted": False}


def test_session_close():
    _, responses, _, _ = run_proxy([rpc("session.close")])
    assert responses[0]["result"] == {"closed": True}


def test_string_request_id_is_preserved():
    _, responses, _, _ = run_proxy([rpc("gateway.ready", request_id="req-abc")])
    assert responses[0]["id"] == "req-abc"


# --- prompt.submit(async turn:ack + 事件)---

def test_prompt_submit_acks_then_emits_start_and_complete():
    client = FakeFoundryClient(reply_text="answer!")
    _, responses, events, _ = run_proxy(
        [rpc("prompt.submit", params={"session_id": "s1", "text": "你好"})], client
    )
    assert client.calls == ["你好"]
    assert responses == [
        {"jsonrpc": "2.0", "id": 1, "result": {"status": "streaming"}}
    ]
    turn_events = [e for e in events if e["type"] != "gateway.ready"]
    assert [e["type"] for e in turn_events] == ["message.start", "message.complete"]
    assert all(e["session_id"] == "s1" for e in turn_events)
    assert turn_events[1]["payload"] == {"text": "answer!", "status": "complete"}


def test_prompt_submit_falls_back_to_input_then_message():
    client = FakeFoundryClient()
    run_proxy([rpc("prompt.submit", params={"input": "from input"})], client)
    assert client.calls == ["from input"]

    client = FakeFoundryClient()
    run_proxy([rpc("prompt.submit", params={"message": "from message"})], client)
    assert client.calls == ["from message"]


def test_prompt_submit_prefers_text_over_input_and_message():
    client = FakeFoundryClient()
    run_proxy(
        [rpc("prompt.submit", params={"text": "a", "input": "b", "message": "c"})],
        client,
    )
    assert client.calls == ["a"]


def test_prompt_submit_without_text_is_invalid_params():
    client = FakeFoundryClient()
    _, responses, _, _ = run_proxy([rpc("prompt.submit", params={})], client)
    assert responses[0]["error"]["code"] == -32602
    assert client.calls == []


def test_prompt_submit_while_running_returns_session_busy():
    """同 session 的第二個 prompt.submit 要回 4009 "session busy"(TUI 靠它排隊)。"""

    class BlockingClient:
        def __init__(self):
            self.release = threading.Event()
            self.started = threading.Event()

        def submit_prompt(self, input_text):
            self.started.set()
            assert self.release.wait(timeout=5)
            return FoundryReply(text="done")

    client = BlockingClient()
    stdout = io.StringIO()
    proxy = JsonRpcProxy(client, _LineWriter(stdout))

    first = proxy.handle_line(rpc("prompt.submit", params={"session_id": "s1", "text": "one"}))
    assert first["result"] == {"status": "streaming"}
    assert client.started.wait(timeout=5)

    second = proxy.handle_line(
        rpc("prompt.submit", request_id=2, params={"session_id": "s1", "text": "two"})
    )
    assert second["error"]["code"] == 4009
    assert second["error"]["message"] == "session busy"

    client.release.set()
    proxy.join_turns()
    frames = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert [f["params"]["type"] for f in frames] == ["message.start", "message.complete"]


def test_chinese_text_is_not_escaped_in_stdout():
    client = FakeFoundryClient(reply_text="繁體中文回覆")
    _, _, _, raw = run_proxy(
        [rpc("prompt.submit", params={"session_id": "s1", "text": "嗨"})], client
    )
    assert "繁體中文回覆" in raw


# --- 錯誤處理 ---

def test_invalid_json_line_returns_parse_error_and_loop_survives():
    _, responses, _, _ = run_proxy(["{not json", rpc("gateway.ready", request_id=2)])
    assert responses[0]["error"]["code"] == -32700
    assert responses[0]["id"] is None
    assert responses[1]["result"]["ready"] is True


def test_missing_method_field_is_invalid_request():
    _, responses, _, _ = run_proxy(['{"jsonrpc": "2.0", "id": 7}'])
    assert responses[0]["error"]["code"] == -32600
    assert responses[0]["id"] == 7


def test_non_object_json_is_invalid_request():
    _, responses, _, _ = run_proxy(["[1, 2, 3]"])
    assert responses[0]["error"]["code"] == -32600


def test_unknown_method_is_method_not_found():
    _, responses, _, _ = run_proxy([rpc("session.events")])
    assert responses[0]["error"]["code"] == -32601
    assert "session.events" in responses[0]["error"]["message"]


def test_blank_lines_are_ignored():
    frames, responses, _, _ = run_proxy(["", "   ", rpc("gateway.ready")])
    # gateway.ready 啟動事件 + 一個 response,空行不產生任何 frame
    assert len(frames) == 2
    assert len(responses) == 1


def test_foundry_errors_surface_as_error_events():
    """Foundry 失敗發生在 worker thread,要以 error 事件收尾(TUI 才會解除 busy)。"""
    cases = [
        ConfigError("endpoint missing"),
        AuthError("run az login"),
        FoundryHttpError(503, "upstream busy"),
        FoundryRequestError("connect timeout"),
        FoundryInvalidJsonError("not json"),
        FoundryMissingTextError("no text"),
        RuntimeError("boom"),
    ]
    for error in cases:
        client = FakeFoundryClient(error=error)
        _, responses, events, _ = run_proxy(
            [rpc("prompt.submit", params={"session_id": "s1", "text": "x"})], client
        )
        assert responses[0]["result"] == {"status": "streaming"}, error
        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) == 1, error
        assert error_events[0]["payload"]["message"], error


def test_loop_continues_after_foundry_error():
    client = FakeFoundryClient(error=RuntimeError("boom"))
    _, responses, events, _ = run_proxy(
        [
            rpc("prompt.submit", params={"session_id": "s1", "text": "x"}),
            rpc("session.status", request_id=2),
        ],
        client,
    )
    assert responses[1]["result"] == {"status": "ready"}
    assert any(e["type"] == "error" for e in events)


def test_session_not_busy_after_turn_completes():
    client = FakeFoundryClient()
    _, responses, _, _ = run_proxy(
        [
            rpc("prompt.submit", params={"session_id": "s1", "text": "one"}),
            rpc("session.status", request_id=2),
        ],
        client,
    )
    # 第一輪結束後(EOF join 前)第二個請求照常處理
    assert responses[0]["result"] == {"status": "streaming"}
