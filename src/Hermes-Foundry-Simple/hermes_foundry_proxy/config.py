# ============================================================
# 【檔案說明】設定來源:環境變數讀取與 invocation URL 組裝
# 1. Settings.from_env —— 讀取三個環境變數:
#    HERMES_FOUNDRY_INVOCATIONS_ENDPOINT(必填,但缺少時不在
#    啟動階段 crash,而是在 prompt.submit 時回 JSON-RPC error)
#    HERMES_FOUNDRY_AGENT_SESSION_ID(選填)
#    HERMES_FOUNDRY_TENANT_ID(選填;Foundry 資源所在 tenant 與
#    az CLI 預設訂閱的 tenant 不同時必須指定,否則
#    DefaultAzureCredential 會拿到錯 tenant 的 token → Foundry 403)
# 2. build_invocation_url —— 若有設定 agent_session_id 且 endpoint
#    的 query string 尚未包含 agent_session_id,自動附加上去
# ============================================================

from __future__ import annotations

import os
from collections.abc import Mapping
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel

ENDPOINT_ENV = "HERMES_FOUNDRY_INVOCATIONS_ENDPOINT"
SESSION_ID_ENV = "HERMES_FOUNDRY_AGENT_SESSION_ID"
TENANT_ID_ENV = "HERMES_FOUNDRY_TENANT_ID"


class Settings(BaseModel):
    invocations_endpoint: str | None = None
    agent_session_id: str | None = None
    tenant_id: str | None = None

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if environ is None else environ
        endpoint = (env.get(ENDPOINT_ENV) or "").strip() or None
        session_id = (env.get(SESSION_ID_ENV) or "").strip() or None
        tenant_id = (env.get(TENANT_ID_ENV) or "").strip() or None
        return cls(
            invocations_endpoint=endpoint,
            agent_session_id=session_id,
            tenant_id=tenant_id,
        )


def build_invocation_url(endpoint: str, agent_session_id: str | None) -> str:
    """endpoint 尚未帶 agent_session_id 時自動附加,已包含則原樣回傳。"""
    if not agent_session_id:
        return endpoint
    parts = urlsplit(endpoint)
    existing = parse_qs(parts.query, keep_blank_values=True)
    if "agent_session_id" in existing:
        return endpoint
    appended = urlencode({"agent_session_id": agent_session_id})
    query = f"{parts.query}&{appended}" if parts.query else appended
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))
