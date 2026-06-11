# ============================================================
# 【檔案說明】錯誤階層:每種失敗情境對應 HTTP status 與 error code
# 1. InvalidRequestError(400)—— kind/method 不支援、input 為空、
#    body 非 JSON
# 2. MissingConfigError(500)—— AZURE_OPENAI_* 環境變數缺少
# 3. ChatServiceError(500)—— LLM 呼叫失敗
# handler 統一把 AgentError 轉成 {"error": code, "message": ...}
# 的 JSONResponse,不讓例外往外漏
# ============================================================

from __future__ import annotations

from typing import Any


class AgentError(Exception):
    """所有 agent 錯誤的基底;子類別決定 HTTP status 與 error code。"""

    status_code = 500
    code = "internal_error"


class InvalidRequestError(AgentError):
    """payload 不符合 hermes.rpc / prompt.submit contract。"""

    status_code = 400
    code = "invalid_request"


class MissingConfigError(AgentError):
    """必要的環境變數缺少。"""

    status_code = 500
    code = "missing_configuration"


class ChatServiceError(AgentError):
    """LLM 呼叫失敗或回傳不可用。"""

    status_code = 500
    code = "chat_service_error"


def error_body(error: AgentError) -> dict[str, Any]:
    return {"error": error.code, "message": str(error)}
