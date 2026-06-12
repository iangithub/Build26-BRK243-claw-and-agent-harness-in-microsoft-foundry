# ============================================================
# 【檔案說明】JSON-RPC 與 Foundry 回覆的資料模型
# 1. JsonRpcRequest —— 用 pydantic 驗證每行 stdin 進來的請求格式
# 2. FoundryReply —— Foundry Invocations 回覆解析後的結果
# 3. make_result / make_error —— 產生 JSON-RPC 2.0 response dict
# 4. JSON-RPC 錯誤碼常數:-32700 ~ -32603 是規範保留碼,
#    -32000 ~ -32004 是本 proxy 自訂的 Foundry 相關錯誤碼
# ============================================================

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# --- JSON-RPC 2.0 規範保留的錯誤碼 ---
PARSE_ERROR = -32700        # stdin 該行不是合法 JSON
INVALID_REQUEST = -32600    # 缺 jsonrpc / method 等必要欄位
METHOD_NOT_FOUND = -32601   # 未支援的 method
INVALID_PARAMS = -32602     # prompt.submit 缺 input 與 message
INTERNAL_ERROR = -32603     # 其他未預期例外

# --- Hermes gateway 相容錯誤碼 ---
ERR_SESSION_BUSY = 4009            # turn 進行中又收到 prompt.submit(同真 gateway)

# --- 本 proxy 自訂的 Foundry 相關錯誤碼(-32000 ~ -32099 為實作保留區段)---
ERR_MISSING_ENDPOINT = -32000      # 缺 HERMES_FOUNDRY_INVOCATIONS_ENDPOINT
ERR_AUTH = -32001                  # DefaultAzureCredential 取 token 失敗
ERR_FOUNDRY_HTTP = -32002          # Foundry 回非 2xx,或連線層失敗
ERR_FOUNDRY_INVALID_JSON = -32003  # Foundry 回應無法解析成 JSON
ERR_FOUNDRY_MISSING_TEXT = -32004  # Foundry 回應缺 text 欄位


class JsonRpcRequest(BaseModel):
    """每行 stdin 的 JSON-RPC 2.0 request。"""

    model_config = ConfigDict(extra="allow")

    jsonrpc: Literal["2.0"]
    id: int | str | None = None
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


class FoundryReply(BaseModel):
    """Foundry Invocations 回覆解析後的結果(text 一定存在)。"""

    type: str = "message.complete"
    text: str


def make_result(request_id: int | str | None, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def make_error(
    request_id: int | str | None,
    code: int,
    message: str,
    data: Any = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}
