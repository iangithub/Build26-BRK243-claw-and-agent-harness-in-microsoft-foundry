# ============================================================
# 【檔案說明】Foundry Hosted Agent Invocations 的 HTTP client
# 1. 認證 —— 延遲建立 DefaultAzureCredential(首次 prompt.submit
#    才初始化,避免啟動就失敗),token scope 為
#    https://ai.azure.com/.default,並快取 AccessToken,
#    距到期不足 5 分鐘才重新取得
# 2. submit_prompt —— POST 到組好的 invocation URL,headers 帶
#    Authorization / Content-Type / Foundry-Features,body 為
#    {"kind": "hermes.rpc", "method": "prompt.submit", "input": ...}
# 3. 錯誤階層 —— 每種失敗情境各有對應例外,由 proxy.py 對應到
#    JSON-RPC 錯誤碼(見 models.py 的 ERR_* 常數)
# ============================================================

from __future__ import annotations

import logging
import time

import httpx

from .config import Settings, build_invocation_url
from .models import FoundryReply

log = logging.getLogger(__name__)

TOKEN_SCOPE = "https://ai.azure.com/.default"
FOUNDRY_FEATURES = "HostedAgents=V1Preview"
_TOKEN_REFRESH_MARGIN_S = 300
_REQUEST_TIMEOUT_S = 120.0
_BODY_SNIPPET_MAX_CHARS = 500


class FoundryError(Exception):
    """所有 Foundry 相關錯誤的基底。"""


class ConfigError(FoundryError):
    """缺少 HERMES_FOUNDRY_INVOCATIONS_ENDPOINT。"""


class AuthError(FoundryError):
    """DefaultAzureCredential 取得 token 失敗。"""


class FoundryRequestError(FoundryError):
    """連線層失敗(連不上、逾時等),還沒拿到 HTTP 回應。"""


class FoundryHttpError(FoundryError):
    """Foundry 回非 2xx。"""

    def __init__(self, status_code: int, body_snippet: str):
        super().__init__(f"Foundry returned HTTP {status_code}: {body_snippet}")
        self.status_code = status_code
        self.body_snippet = body_snippet


class FoundryInvalidJsonError(FoundryError):
    """Foundry 回應無法解析成 JSON。"""


class FoundryMissingTextError(FoundryError):
    """Foundry 回應缺少可用的 text 欄位。"""


class FoundryClient:
    def __init__(
        self,
        settings: Settings,
        http_client: httpx.Client | None = None,
        credential: object | None = None,
    ):
        self._settings = settings
        self._http = http_client or httpx.Client(timeout=_REQUEST_TIMEOUT_S)
        self._credential = credential
        self._cached_token = None

    def close(self) -> None:
        self._http.close()

    def _bearer_token(self) -> str:
        now = time.time()
        cached = self._cached_token
        if cached is not None and cached.expires_on - now > _TOKEN_REFRESH_MARGIN_S:
            return cached.token
        try:
            if self._credential is None:
                from azure.identity import DefaultAzureCredential

                self._credential = DefaultAzureCredential()
            # Foundry 資源的 tenant 可能不是 az CLI 預設訂閱的 tenant;
            # 不指定時 AzureCliCredential 會拿 home/預設 tenant 的 token,
            # Foundry 端會以「不存在的 principal」403 拒絕。
            token_kwargs = {}
            if self._settings.tenant_id:
                token_kwargs["tenant_id"] = self._settings.tenant_id
            self._cached_token = self._credential.get_token(
                TOKEN_SCOPE, **token_kwargs
            )
        except Exception as exc:
            raise AuthError(
                "Failed to acquire an Azure access token via DefaultAzureCredential. "
                "Run `az login` (or configure another supported credential) and retry. "
                f"Underlying error: {exc}"
            ) from exc
        return self._cached_token.token

    def submit_prompt(self, input_text: str) -> FoundryReply:
        endpoint = self._settings.invocations_endpoint
        if not endpoint:
            raise ConfigError(
                "HERMES_FOUNDRY_INVOCATIONS_ENDPOINT is not set. "
                "Point it at the Foundry Hosted Agent invocations endpoint."
            )
        url = build_invocation_url(endpoint, self._settings.agent_session_id)
        headers = {
            "Authorization": f"Bearer {self._bearer_token()}",
            "Content-Type": "application/json",
            "Foundry-Features": FOUNDRY_FEATURES,
        }
        body = {"kind": "hermes.rpc", "method": "prompt.submit", "input": input_text}
        log.info("prompt.submit -> Foundry (%d chars)", len(input_text))
        try:
            response = self._http.post(url, headers=headers, json=body)
        except httpx.HTTPError as exc:
            raise FoundryRequestError(
                f"Failed to reach the Foundry invocations endpoint: {exc}"
            ) from exc
        if not (200 <= response.status_code < 300):
            raise FoundryHttpError(
                response.status_code, response.text[:_BODY_SNIPPET_MAX_CHARS]
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise FoundryInvalidJsonError(
                "Foundry response is not valid JSON: "
                f"{response.text[:_BODY_SNIPPET_MAX_CHARS]!r}"
            ) from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
            raise FoundryMissingTextError(
                "Foundry response has no usable `text` field: "
                f"{str(payload)[:_BODY_SNIPPET_MAX_CHARS]}"
            )
        reply_type = payload.get("type")
        return FoundryReply(
            type=reply_type if isinstance(reply_type, str) and reply_type else "message.complete",
            text=payload["text"],
        )
