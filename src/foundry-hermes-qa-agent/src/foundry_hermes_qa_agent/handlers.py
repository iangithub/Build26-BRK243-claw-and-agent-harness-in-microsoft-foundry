# ============================================================
# 【檔案說明】Invocations Protocol 的 invoke handler
# 1. handle_invoke —— 讀 request.json(),解析 kind / method / input,
#    呼叫 ChatService 取得回答,回 Starlette JSONResponse:
#    成功 → 200 {"type": "message.complete", "text": "..."}
#    contract 不符 → 400 {"error": "invalid_request", ...}
#    設定缺少 / LLM 失敗 → 500 {"error": ..., ...}
# 2. ChatService.complete 是同步呼叫(官方 v1 範例用同步 OpenAI
#    client),以 asyncio.to_thread 包裝避免卡住 event loop
# 3. 任何未預期例外都轉成 500 JSON error,不讓例外漏出 handler
# ============================================================

from __future__ import annotations

import asyncio
import logging

from starlette.requests import Request
from starlette.responses import JSONResponse

from .chat_service import ChatService
from .errors import AgentError, InvalidRequestError, error_body
from .models import extract_question, message_complete

log = logging.getLogger(__name__)


async def respond(payload: object, chat_service: ChatService) -> JSONResponse:
    """純邏輯入口(方便測試):payload dict 進、JSONResponse 出。"""
    try:
        question = extract_question(payload)
        text = await asyncio.to_thread(chat_service.complete, question)
        return JSONResponse(message_complete(text))
    except AgentError as exc:
        log.warning("%s (%d): %s", exc.code, exc.status_code, exc)
        return JSONResponse(error_body(exc), status_code=exc.status_code)
    except Exception as exc:  # 最後防線:不讓例外漏出 handler
        log.exception("unexpected error while handling invocation")
        return JSONResponse(
            {"error": "internal_error", "message": str(exc)}, status_code=500
        )


async def handle_invoke(request: Request, chat_service: ChatService) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception:
        error = InvalidRequestError("Request body must be valid JSON.")
        return JSONResponse(error_body(error), status_code=error.status_code)
    return await respond(payload, chat_service)
