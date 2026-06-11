# ============================================================
# 【檔案說明】stdin/stdout JSON-RPC 主迴圈與 method dispatch
# 1. JsonRpcProxy —— 七個 method 的處理表:
#    gateway.ready / commands.catalog / config.get /
#    session.create / session.status / session.close 在本機直接回,
#    prompt.submit 透過 FoundryClient 轉送到 Foundry
# 2. handle_line —— 一行進、一個 response dict 出(空行回 None);
#    所有失敗情境都轉成 JSON-RPC error,任何錯誤都不讓 process crash
# 3. run —— 逐行讀 stdin、逐行寫 stdout(立即 flush);
#    stdin/stdout 以參數注入,方便測試。log 一律走 stderr
# ============================================================

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Callable, TextIO

from pydantic import ValidationError

from .foundry import (
    AuthError,
    ConfigError,
    FoundryClient,
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


class InvalidParamsError(Exception):
    """params 內容不符 method 要求(對應 -32602)。"""


class JsonRpcProxy:
    def __init__(self, client: FoundryClient):
        self._client = client
        self._handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "gateway.ready": self._gateway_ready,
            "commands.catalog": self._commands_catalog,
            "config.get": self._config_get,
            "session.create": self._session_create,
            "session.status": self._session_status,
            "session.close": self._session_close,
            "prompt.submit": self._prompt_submit,
        }

    # --- 本機直接回覆的 method ---

    def _gateway_ready(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"ready": True, "backend": "foundry"}

    def _commands_catalog(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"commands": []}

    def _config_get(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"backend": "foundry", "streaming": False}

    def _session_create(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"session_id": f"local-{uuid.uuid4().hex[:12]}"}

    def _session_status(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"status": "ready"}

    def _session_close(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"closed": True}

    # --- 轉送 Foundry 的 method ---

    def _prompt_submit(self, params: dict[str, Any]) -> dict[str, Any]:
        text = params.get("input")
        if not isinstance(text, str):
            text = params.get("message")
        if not isinstance(text, str):
            raise InvalidParamsError(
                "prompt.submit requires `params.input` or `params.message` (string)."
            )
        reply = self._client.submit_prompt(text)
        return {"type": reply.type, "text": reply.text}

    # --- 一行進、一個 response 出 ---

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
    proxy = JsonRpcProxy(client)
    for line in stdin:
        try:
            response = proxy.handle_line(line)
        except Exception:  # handle_line 已各自攔截,這層是最後防線
            log.exception("unhandled error while processing a line")
            response = make_error(None, INTERNAL_ERROR, "Internal proxy error")
        if response is None:
            continue
        stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        stdout.flush()
    return 0
