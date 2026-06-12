# ============================================================
# 【檔案說明】stdin/stdout JSON-RPC 主迴圈與 method dispatch
#
# Hermes ui-tui 的 gatewayClient 對後端的期待(對齊真正的
# tui_gateway/entry.py + server.py):
# 1. 啟動後「主動」推一個 gateway.ready 事件通知(method="event",
#    params={"type": "gateway.ready"}),TUI 收到才算 gateway 就緒;
#    只回應 RPC 是不夠的 —— 等不到這個事件就會 gateway startup timeout。
# 2. prompt.submit 帶 params={"session_id", "text"};response 只是 ack
#    ({"status": "streaming"}),真正的回覆要用事件推回:
#    message.start → message.complete({"text", "status"})。
#    錯誤用 error 事件({"message"})收尾,TUI 才會解除 busy。
# 3. session 忙碌時 prompt.submit 回 code 4009 / "session busy",
#    TUI 會把訊息排進 queue 等本輪結束。
#
# 結構:
# 1. JsonRpcProxy —— method 處理表;本機 method 直接回,
#    prompt.submit 以 worker thread 轉送 Foundry 並用事件推回結果
# 2. _LineWriter —— stdout 行寫入器(lock 保護),主迴圈的 response
#    與 worker thread 的事件共用,確保不會交錯出半行
# 3. run —— 先推 gateway.ready 事件,再逐行讀 stdin 處理;
#    EOF 後 join 未完成的 turn(短暫寬限)。log 一律走 stderr
# ============================================================

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from typing import Any, Callable, TextIO

from pydantic import ValidationError

from .foundry import (
    AuthError,
    ConfigError,
    FoundryClient,
    FoundryError,
    FoundryHttpError,
    FoundryInvalidJsonError,
    FoundryMissingTextError,
    FoundryRequestError,
)
from .models import (
    ERR_AUTH,
    ERR_FOUNDRY_HTTP,
    ERR_FOUNDRY_INVALID_JSON,
    ERR_FOUNDRY_MISSING_TEXT,
    ERR_MISSING_ENDPOINT,
    ERR_SESSION_BUSY,
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    JsonRpcRequest,
    make_error,
    make_result,
)

log = logging.getLogger(__name__)

# EOF 後等待 in-flight turn 收尾的寬限;TUI 關閉時本來就會 kill 子行程,
# 這裡只是讓測試與正常退出時最後的事件能寫完。
_EOF_JOIN_GRACE_S = 5.0


class InvalidParamsError(Exception):
    """params 內容不符 method 要求(對應 -32602)。"""


class _LineWriter:
    """一行一個 JSON frame 的 stdout 寫入器;lock 讓 response 與事件不交錯。"""

    def __init__(self, stream: TextIO):
        self._stream = stream
        self._lock = threading.Lock()

    def write(self, obj: dict[str, Any]) -> None:
        with self._lock:
            self._stream.write(json.dumps(obj, ensure_ascii=False) + "\n")
            self._stream.flush()


class JsonRpcProxy:
    def __init__(self, client: FoundryClient, writer: _LineWriter):
        self._client = client
        self._writer = writer
        self._running_sids: set[str] = set()
        self._running_lock = threading.Lock()
        self._turn_threads: list[threading.Thread] = []
        self._handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "gateway.ready": self._gateway_ready,
            "commands.catalog": self._commands_catalog,
            "config.get": self._config_get,
            "setup.status": self._setup_status,
            "input.detect_drop": self._input_detect_drop,
            "session.create": self._session_create,
            "session.status": self._session_status,
            "session.interrupt": self._session_interrupt,
            "session.close": self._session_close,
        }

    # --- 事件推送(對齊 tui_gateway/server.py 的 _emit)---

    def emit_event(self, event_type: str, sid: str = "", payload: dict[str, Any] | None = None) -> None:
        params: dict[str, Any] = {"type": event_type}
        if sid:
            params["session_id"] = sid
        if payload is not None:
            params["payload"] = payload
        self._writer.write({"jsonrpc": "2.0", "method": "event", "params": params})

    # --- 本機直接回覆的 method ---

    def _gateway_ready(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"ready": True, "backend": "foundry"}

    def _commands_catalog(self, params: dict[str, Any]) -> dict[str, Any]:
        # TUI 期待 pairs/canon/categories/sub/skill_count;全空 = 沒有 slash 指令。
        return {"pairs": [], "canon": {}, "categories": [], "sub": {}, "skill_count": 0}

    def _config_get(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"backend": "foundry", "streaming": False}

    def _setup_status(self, params: dict[str, Any]) -> dict[str, Any]:
        # 一定要回 provider_configured=True:TUI 在 session.create 前先問這個,
        # 拿不到(或 False)就不開 session,之後送訊息只會得到 session not ready。
        # 認證問題留給 prompt.submit 時的 AuthError 事件呈現。
        return {"provider_configured": True}

    def _input_detect_drop(self, params: dict[str, Any]) -> dict[str, Any]:
        # 不支援檔案拖放偵測;回 matched=False 讓 TUI 走一般送出路徑。
        return {"matched": False}

    def _session_create(self, params: dict[str, Any]) -> dict[str, Any]:
        # info.version 有值 TUI 才會直接進 ready(否則卡在 starting agent…
        # 直到第一個 message.complete)。
        return {
            "session_id": f"local-{uuid.uuid4().hex[:12]}",
            "info": {
                "model": "foundry-hermes-qa-agent",
                "version": "hermes-foundry-simple",
                "tools": {},
                "skills": {},
                "cwd": os.getcwd(),
            },
        }

    def _session_status(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"status": "ready"}

    def _session_interrupt(self, params: dict[str, Any]) -> dict[str, Any]:
        # 無法中斷已送出的 Foundry HTTP 呼叫;回 ack 即可,turn 仍會自然收尾。
        return {"interrupted": False}

    def _session_close(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"closed": True}

    # --- 轉送 Foundry 的 method(async turn:ack + 事件推回)---

    def _prompt_submit(self, request: JsonRpcRequest) -> dict[str, Any]:
        params = request.params
        text = params.get("text")
        if not isinstance(text, str):
            text = params.get("input")
        if not isinstance(text, str):
            text = params.get("message")
        if not isinstance(text, str):
            raise InvalidParamsError(
                "prompt.submit requires `params.text` (or `input` / `message`) as a string."
            )
        sid = str(params.get("session_id") or "")
        with self._running_lock:
            if sid in self._running_sids:
                # 與真 gateway 同碼同字串;TUI 靠 "session busy" 字樣排隊。
                return make_error(request.id, ERR_SESSION_BUSY, "session busy")
            self._running_sids.add(sid)

        worker = threading.Thread(
            target=self._run_turn, args=(sid, text), name="foundry-turn", daemon=True
        )
        self._turn_threads.append(worker)
        worker.start()
        return make_result(request.id, {"status": "streaming"})

    def _run_turn(self, sid: str, text: str) -> None:
        self.emit_event("message.start", sid)
        try:
            reply = self._client.submit_prompt(text)
            self.emit_event(
                "message.complete", sid, {"text": reply.text, "status": "complete"}
            )
        except FoundryError as exc:
            self.emit_event("error", sid, {"message": str(exc)})
        except Exception as exc:  # 任何錯誤都不讓 proxy crash,也不讓 TUI 卡 busy
            log.exception("unexpected error during foundry turn")
            self.emit_event("error", sid, {"message": f"Internal error: {exc}"})
        finally:
            # busy 旗標要等收尾事件送出後才釋放:TUI 的 queue 是在
            # message.complete 才 drain,先釋放會讓新 turn 搶在完成事件前開跑。
            with self._running_lock:
                self._running_sids.discard(sid)

    def join_turns(self, timeout: float = _EOF_JOIN_GRACE_S) -> None:
        for thread in self._turn_threads:
            thread.join(timeout=timeout)

    # --- 一行進、一個 response 出(prompt.submit 另以事件推回結果)---

    def handle_line(self, line: str) -> dict[str, Any] | None:
        line = line.strip()
        if not line:
            return None
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            return make_error(None, PARSE_ERROR, f"Parse error: invalid JSON ({exc})")
        request_id = raw.get("id") if isinstance(raw, dict) else None
        try:
            request = JsonRpcRequest.model_validate(raw)
        except ValidationError as exc:
            summary = "; ".join(
                f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}"
                for err in exc.errors()
            )
            return make_error(
                request_id, INVALID_REQUEST, f"Invalid JSON-RPC 2.0 request: {summary}"
            )
        if request.method == "prompt.submit":
            try:
                return self._prompt_submit(request)
            except InvalidParamsError as exc:
                return make_error(request.id, INVALID_PARAMS, str(exc))
        handler = self._handlers.get(request.method)
        if handler is None:
            return make_error(
                request.id, METHOD_NOT_FOUND, f"Method not found: {request.method}"
            )
        try:
            result = handler(request.params)
        except InvalidParamsError as exc:
            return make_error(request.id, INVALID_PARAMS, str(exc))
        except ConfigError as exc:
            return make_error(request.id, ERR_MISSING_ENDPOINT, str(exc))
        except AuthError as exc:
            return make_error(request.id, ERR_AUTH, str(exc))
        except FoundryHttpError as exc:
            return make_error(
                request.id,
                ERR_FOUNDRY_HTTP,
                str(exc),
                data={"status_code": exc.status_code, "body": exc.body_snippet},
            )
        except FoundryRequestError as exc:
            return make_error(request.id, ERR_FOUNDRY_HTTP, str(exc))
        except FoundryInvalidJsonError as exc:
            return make_error(request.id, ERR_FOUNDRY_INVALID_JSON, str(exc))
        except FoundryMissingTextError as exc:
            return make_error(request.id, ERR_FOUNDRY_MISSING_TEXT, str(exc))
        except Exception as exc:  # 規格第 9 點:任何錯誤不得讓 proxy crash
            log.exception("unexpected error while handling %s", request.method)
            return make_error(request.id, INTERNAL_ERROR, f"Internal error: {exc}")
        return make_result(request.id, result)


def run(stdin: TextIO, stdout: TextIO, client: FoundryClient) -> int:
    writer = _LineWriter(stdout)
    proxy = JsonRpcProxy(client, writer)
    # TUI 等的是這個事件,不是任何 RPC response —— 對齊真 gateway 的
    # entry.py:main() 開頭的 gateway.ready 通知。
    proxy.emit_event("gateway.ready")
    for line in stdin:
        try:
            response = proxy.handle_line(line)
        except Exception:  # handle_line 已各自攔截,這層是最後防線
            log.exception("unhandled error while processing a line")
            response = make_error(None, INTERNAL_ERROR, "Internal proxy error")
        if response is None:
            continue
        writer.write(response)
    proxy.join_turns()
    return 0
