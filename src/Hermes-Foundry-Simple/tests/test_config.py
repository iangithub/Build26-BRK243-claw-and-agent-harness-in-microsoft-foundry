# ============================================================
# 【檔案說明】config.py 的單元測試
# 重點:invocation URL 的 agent_session_id 附加規則,
# 以及 Settings.from_env 對空值/未設定的處理
# ============================================================

from hermes_foundry_proxy.config import (
    ENDPOINT_ENV,
    SESSION_ID_ENV,
    Settings,
    build_invocation_url,
)

ENDPOINT = "https://example.services.ai.azure.com/api/projects/p/agents/a/invocations"


def test_no_session_id_returns_endpoint_unchanged():
    assert build_invocation_url(ENDPOINT, None) == ENDPOINT


def test_appends_session_id_when_no_query_string():
    url = build_invocation_url(ENDPOINT, "sess-123")
    assert url == f"{ENDPOINT}?agent_session_id=sess-123"


def test_appends_session_id_preserving_existing_query():
    url = build_invocation_url(f"{ENDPOINT}?api-version=2025-05-15-preview", "sess-123")
    assert url == f"{ENDPOINT}?api-version=2025-05-15-preview&agent_session_id=sess-123"


def test_does_not_duplicate_existing_agent_session_id():
    endpoint = f"{ENDPOINT}?agent_session_id=already-there"
    assert build_invocation_url(endpoint, "sess-123") == endpoint


def test_session_id_is_url_encoded():
    url = build_invocation_url(ENDPOINT, "sess 123/x")
    assert url == f"{ENDPOINT}?agent_session_id=sess+123%2Fx"


def test_settings_from_env_reads_values():
    settings = Settings.from_env(
        {ENDPOINT_ENV: f" {ENDPOINT} ", SESSION_ID_ENV: "sess-9"}
    )
    assert settings.invocations_endpoint == ENDPOINT
    assert settings.agent_session_id == "sess-9"


def test_settings_from_env_treats_blank_as_missing():
    settings = Settings.from_env({ENDPOINT_ENV: "   ", SESSION_ID_ENV: ""})
    assert settings.invocations_endpoint is None
    assert settings.agent_session_id is None
