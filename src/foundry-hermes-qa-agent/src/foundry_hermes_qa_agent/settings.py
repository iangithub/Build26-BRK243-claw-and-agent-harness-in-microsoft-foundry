# ============================================================
# 【檔案說明】設定來源:AZURE_OPENAI_* 環境變數
# 1. AZURE_OPENAI_ENDPOINT(必填)—— 例如
#    https://<resource>.openai.azure.com 或已含 /openai/v1 的形式;
#    v1_base_url 會正規化成 v1 API 要求的 .../openai/v1/ 結尾
# 2. AZURE_OPENAI_DEPLOYMENT_NAME(必填)—— 模型部署名稱
# 3. AZURE_OPENAI_API_VERSION(選填)—— v1 GA API 已不需要
#    api-version;若有設定才會以 query string 傳給服務
# 4. AZURE_OPENAI_API_KEY(選填)—— 沒設定時走 Entra ID
#    (DefaultAzureCredential),這是建議做法;key 僅供本機測試
# 缺少必填變數時拋 MissingConfigError,由 handler 回清楚錯誤
# ============================================================

from __future__ import annotations

import os
from collections.abc import Mapping

from pydantic import BaseModel

from .errors import MissingConfigError

ENDPOINT_ENV = "AZURE_OPENAI_ENDPOINT"
DEPLOYMENT_ENV = "AZURE_OPENAI_DEPLOYMENT_NAME"
API_VERSION_ENV = "AZURE_OPENAI_API_VERSION"
API_KEY_ENV = "AZURE_OPENAI_API_KEY"


class Settings(BaseModel):
    endpoint: str
    deployment_name: str
    api_version: str | None = None
    api_key: str | None = None

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if environ is None else environ
        endpoint = (env.get(ENDPOINT_ENV) or "").strip()
        deployment = (env.get(DEPLOYMENT_ENV) or "").strip()
        missing = [
            name
            for name, value in ((ENDPOINT_ENV, endpoint), (DEPLOYMENT_ENV, deployment))
            if not value
        ]
        if missing:
            raise MissingConfigError(
                "Missing required environment variables: " + ", ".join(missing)
            )
        return cls(
            endpoint=endpoint,
            deployment_name=deployment,
            api_version=(env.get(API_VERSION_ENV) or "").strip() or None,
            api_key=(env.get(API_KEY_ENV) or "").strip() or None,
        )

    @property
    def v1_base_url(self) -> str:
        """正規化成 Azure OpenAI v1 API 的 base_url(.../openai/v1/)。"""
        base = self.endpoint.rstrip("/")
        if not base.endswith("/openai/v1"):
            base = f"{base}/openai/v1"
        return f"{base}/"
