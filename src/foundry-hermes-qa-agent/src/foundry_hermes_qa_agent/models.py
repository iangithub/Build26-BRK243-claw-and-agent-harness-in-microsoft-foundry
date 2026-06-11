# ============================================================
# 【檔案說明】Invocations payload 的解析與回覆形狀
# 輸入 contract(foundry-tui-proxy 送來的最小格式):
#   {"kind": "hermes.rpc", "method": "prompt.submit", "input": "..."}
# 也相容:
#   {"kind": ..., "method": ..., "params": {"input": "..."}}
#   {"kind": ..., "method": ..., "params": {"message": "..."}}
# 處理規則:kind 必須是 hermes.rpc、method 必須是 prompt.submit、
# input 依序從 body.input → params.input → params.message 取得,
# 全部缺少或為空字串時拋 InvalidRequestError(HTTP 400)
# ============================================================

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .errors import InvalidRequestError

SUPPORTED_KIND = "hermes.rpc"
SUPPORTED_METHOD = "prompt.submit"


class HermesRpcPayload(BaseModel):
    """foundry-tui-proxy 送來的 Invocations request body。"""

    model_config = ConfigDict(extra="allow")

    kind: str
    method: str
    input: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


def extract_question(raw: Any) -> str:
    """驗證 payload 並取出使用者問題;不合 contract 即拋 InvalidRequestError。"""
    if not isinstance(raw, dict):
        raise InvalidRequestError("Request body must be a JSON object.")
    try:
        payload = HermesRpcPayload.model_validate(raw)
    except ValidationError as exc:
        summary = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()
        )
        raise InvalidRequestError(f"Invalid payload: {summary}") from exc
    if payload.kind != SUPPORTED_KIND:
        raise InvalidRequestError(
            f"Unsupported kind: {payload.kind!r}; this agent only accepts {SUPPORTED_KIND!r}."
        )
    if payload.method != SUPPORTED_METHOD:
        raise InvalidRequestError(
            f"Unsupported method: {payload.method!r}; this agent only accepts {SUPPORTED_METHOD!r}."
        )
    for candidate in (
        payload.input,
        payload.params.get("input"),
        payload.params.get("message"),
    ):
        if isinstance(candidate, str) and candidate.strip():
            return candidate
    raise InvalidRequestError(
        "Input is required; provide body.input, params.input, or params.message."
    )


def message_complete(text: str) -> dict[str, Any]:
    return {"type": "message.complete", "text": text}
