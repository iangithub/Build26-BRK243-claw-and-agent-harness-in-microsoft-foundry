# ============================================================
# 【檔案說明】chat_service.py 的單元測試
# 1. AzureOpenAIChatService —— 注入假的 OpenAI client(stub
#    responses.create),驗證:一般回答、web_search 工具迴圈
#    (function_call → 執行搜尋 → function_call_output 回灌)、
#    LLM 失敗包成 ChatServiceError、空回答視為錯誤、
#    工具迴圈有上限不會無窮迴圈
# 2. DuckDuckGoWebSearch —— 用 respx 攔截 httpx,驗證結果萃取
#    與失敗時回傳說明文字(不拋例外)
# 3. Settings —— 缺環境變數拋 MissingConfigError、v1 base_url 正規化
# ============================================================

import json
from types import SimpleNamespace

import httpx
import pytest
import respx

from foundry_hermes_qa_agent.chat_service import (
    SYSTEM_PROMPT,
    AzureOpenAIChatService,
    DuckDuckGoWebSearch,
)
from foundry_hermes_qa_agent.errors import ChatServiceError, MissingConfigError
from foundry_hermes_qa_agent.settings import Settings


def make_settings(**overrides):
    values = {
        "endpoint": "https://unit.openai.azure.com",
        "deployment_name": "gpt-test",
    }
    values.update(overrides)
    return Settings(**values)


class FakeResponses:
    """stub client.responses:依序回傳排好的 response,並記錄每次呼叫參數。"""

    def __init__(self, queue):
        self.queue = list(queue)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        result = self.queue.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def fake_client(*responses):
    return SimpleNamespace(responses=FakeResponses(responses))


def text_response(text):
    return SimpleNamespace(output=[], output_text=text)


def tool_call_response(query, call_id="call-1"):
    call = SimpleNamespace(
        type="function_call",
        name="web_search",
        arguments=json.dumps({"query": query}),
        call_id=call_id,
    )
    return SimpleNamespace(output=[call], output_text="")


class FakeSearch:
    def __init__(self, result="搜尋結果"):
        self.result = result
        self.queries = []

    def search(self, query, max_results=5):
        self.queries.append(query)
        return self.result


# --- AzureOpenAIChatService ---

def test_simple_answer_without_tool_call():
    client = fake_client(text_response("台北是台灣的首都。"))
    service = AzureOpenAIChatService(
        settings=make_settings(), client=client, search=FakeSearch()
    )
    assert service.complete("台灣的首都?") == "台北是台灣的首都。"
    call = client.responses.calls[0]
    assert call["model"] == "gpt-test"
    assert call["instructions"] == SYSTEM_PROMPT
    assert call["input"] == [{"role": "user", "content": "台灣的首都?"}]
    assert call["tools"][0]["name"] == "web_search"


def test_web_search_tool_loop():
    client = fake_client(
        tool_call_response("2026 年最新消息"),
        text_response("根據搜尋結果,..."),
    )
    search = FakeSearch(result="1. 新聞標題\n   https://example.test\n   摘要")
    service = AzureOpenAIChatService(
        settings=make_settings(), client=client, search=search
    )
    assert service.complete("最新消息?") == "根據搜尋結果,..."
    assert search.queries == ["2026 年最新消息"]
    # 第二輪呼叫要把 function_call 與 function_call_output 一起回灌
    second_input = client.responses.calls[1]["input"]
    assert second_input[0] == {"role": "user", "content": "最新消息?"}
    assert getattr(second_input[1], "type", None) == "function_call"
    assert second_input[2]["type"] == "function_call_output"
    assert second_input[2]["call_id"] == "call-1"
    assert "新聞標題" in second_input[2]["output"]


def test_tool_loop_last_round_forces_answer_without_tools():
    # 模型每輪都要求搜尋:最後一輪要以 tool_choice="none" 強制作答
    client = fake_client(
        tool_call_response("q0", call_id="c0"),
        tool_call_response("q1", call_id="c1"),
        text_response("final"),
    )
    service = AzureOpenAIChatService(
        settings=make_settings(), client=client, search=FakeSearch(), max_tool_rounds=2
    )
    assert service.complete("loop?") == "final"
    assert len(client.responses.calls) == 3  # 1 + max_tool_rounds
    assert "tool_choice" not in client.responses.calls[1]  # 非最後一輪維持預設
    assert client.responses.calls[2]["tool_choice"] == "none"


def test_empty_answer_after_forced_round_is_error():
    client = fake_client(
        tool_call_response("q0", call_id="c0"),
        text_response(""),
    )
    service = AzureOpenAIChatService(
        settings=make_settings(), client=client, search=FakeSearch(), max_tool_rounds=1
    )
    with pytest.raises(ChatServiceError, match="empty"):
        service.complete("loop?")


def test_llm_failure_wrapped_as_chat_service_error():
    client = fake_client(RuntimeError("connection reset"))
    service = AzureOpenAIChatService(
        settings=make_settings(), client=client, search=FakeSearch()
    )
    with pytest.raises(ChatServiceError, match="LLM call failed"):
        service.complete("hi")


def test_empty_answer_is_an_error():
    client = fake_client(text_response("   "))
    service = AzureOpenAIChatService(
        settings=make_settings(), client=client, search=FakeSearch()
    )
    with pytest.raises(ChatServiceError, match="empty"):
        service.complete("hi")


# --- DuckDuckGoWebSearch ---

SEARCH_HTML = """
<div class="result">
  <a class="result__a" href="https://example.test/page">Example <b>Title</b></a>
  <a class="result__snippet" href="#">A short &amp; useful snippet</a>
</div>
"""


@respx.mock
def test_duckduckgo_search_extracts_results():
    respx.get(DuckDuckGoWebSearch.SEARCH_URL).mock(
        return_value=httpx.Response(200, text=SEARCH_HTML)
    )
    search = DuckDuckGoWebSearch(http_client=httpx.Client())
    result = search.search("example")
    assert "Example Title" in result
    assert "https://example.test/page" in result
    assert "A short & useful snippet" in result


@respx.mock
def test_duckduckgo_transport_failure_returns_text_not_exception():
    respx.get(DuckDuckGoWebSearch.SEARCH_URL).mock(
        side_effect=httpx.ConnectError("connection refused")
    )
    search = DuckDuckGoWebSearch(http_client=httpx.Client())
    assert "web search failed" in search.search("example")


@respx.mock
def test_duckduckgo_non_200_means_search_unavailable():
    # DuckDuckGo 反爬蟲時回 202:要回「搜尋不可用」說明,不當成空結果
    respx.get(DuckDuckGoWebSearch.SEARCH_URL).mock(
        return_value=httpx.Response(202, text="")
    )
    search = DuckDuckGoWebSearch(http_client=httpx.Client())
    result = search.search("example")
    assert "web search unavailable" in result
    assert "202" in result


@respx.mock
def test_duckduckgo_no_results():
    respx.get(DuckDuckGoWebSearch.SEARCH_URL).mock(
        return_value=httpx.Response(200, text="<html></html>")
    )
    search = DuckDuckGoWebSearch(http_client=httpx.Client())
    assert search.search("example") == "(no search results)"


# --- Settings ---

def test_settings_missing_env_raises_clear_error():
    with pytest.raises(MissingConfigError, match="AZURE_OPENAI_ENDPOINT"):
        Settings.from_env({})


def test_settings_missing_deployment_only():
    with pytest.raises(MissingConfigError, match="AZURE_OPENAI_DEPLOYMENT_NAME"):
        Settings.from_env({"AZURE_OPENAI_ENDPOINT": "https://x.openai.azure.com"})


def test_settings_from_env_reads_all_values():
    settings = Settings.from_env(
        {
            "AZURE_OPENAI_ENDPOINT": "https://x.openai.azure.com",
            "AZURE_OPENAI_DEPLOYMENT_NAME": "gpt-5.5",
            "AZURE_OPENAI_API_VERSION": "preview",
            "AZURE_OPENAI_API_KEY": "k",
        }
    )
    assert settings.deployment_name == "gpt-5.5"
    assert settings.api_version == "preview"
    assert settings.api_key == "k"


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://x.openai.azure.com",
        "https://x.openai.azure.com/",
        "https://x.openai.azure.com/openai/v1",
        "https://x.openai.azure.com/openai/v1/",
    ],
)
def test_v1_base_url_normalization(endpoint):
    settings = make_settings(endpoint=endpoint)
    assert settings.v1_base_url == "https://x.openai.azure.com/openai/v1/"
