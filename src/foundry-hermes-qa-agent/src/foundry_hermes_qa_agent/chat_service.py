# ============================================================
# 【檔案說明】LLM 呼叫:ChatService 抽象 + Azure OpenAI 實作
# 1. AzureOpenAIChatService —— 依官方 v1 API 建議
#    (learn.microsoft.com/azure/foundry/openai/api-version-lifecycle):
#    用 openai 套件的 OpenAI() client,base_url 指向
#    https://<resource>.openai.azure.com/openai/v1/,
#    Entra ID 驗證以 get_bearer_token_provider(DefaultAzureCredential(),
#    "https://ai.azure.com/.default") 直接當 api_key(自動換發 token,
#    不自行保存 credential / token);AZURE_OPENAI_API_KEY 僅作本機
#    測試的 fallback。v1 GA 不需要 api-version。
# 2. Web 搜尋 —— Azure OpenAI Responses API 沒有內建 web_search 工具
#    (2026-05 文件確認),因此以 function calling 實作:宣告
#    web_search function tool,模型決定要搜尋時由 DuckDuckGoWebSearch
#    (免 API key)執行,把結果回灌給模型再產生最終回答,
#    最多 _max_tool_rounds 輪;最後一輪以 tool_choice="none"
#    停用工具,強制模型以現有資訊作答(保證有 text 可回)。
# 3. client 延遲建立(首次呼叫才初始化),建構子可注入假 client /
#    假 search,方便測試。
# ============================================================

from __future__ import annotations

import html
import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any

import httpx

from .errors import ChatServiceError
from .settings import Settings

log = logging.getLogger(__name__)

TOKEN_SCOPE = "https://ai.azure.com/.default"

SYSTEM_PROMPT = (
    "你是部署在 Microsoft Foundry Hosted Agent 上的 Hermes Q&A Agent,"
    "請用繁體中文回答使用者問題。"
    "當問題涉及時事、最新資訊或你不確定的事實時,先用 web_search 工具搜尋再回答,"
    "並在回答中註明資訊來源。"
)

# Responses API 的 function tool 宣告(扁平格式,與 chat.completions 不同)
WEB_SEARCH_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "web_search",
    "description": "搜尋網路上的最新資訊。輸入搜尋關鍵字,回傳前幾筆搜尋結果的標題、網址與摘要。",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜尋關鍵字"},
        },
        "required": ["query"],
    },
}


class ChatService(ABC):
    """LLM 問答的抽象介面;handler 只依賴這個介面。"""

    @abstractmethod
    def complete(self, question: str) -> str:
        """輸入使用者問題,回傳助理回答文字;失敗時拋 ChatServiceError。"""


class DuckDuckGoWebSearch:
    """免 API key 的網頁搜尋:抓 DuckDuckGo HTML 端點並萃取結果。"""

    SEARCH_URL = "https://html.duckduckgo.com/html/"
    _RESULT_RE = re.compile(
        r'<a[^>]+class="result__a"[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
        re.DOTALL,
    )
    _SNIPPET_RE = re.compile(
        r'class="result__snippet"[^>]*>(?P<snippet>.*?)</a>', re.DOTALL
    )
    _TAG_RE = re.compile(r"<[^>]+>")

    def __init__(self, http_client: httpx.Client | None = None):
        self._http = http_client or httpx.Client(
            timeout=20.0,
            headers={"User-Agent": "foundry-hermes-qa-agent/0.1"},
            follow_redirects=True,
        )

    def _clean(self, fragment: str) -> str:
        return html.unescape(self._TAG_RE.sub("", fragment)).strip()

    def search(self, query: str, max_results: int = 5) -> str:
        """回傳純文字搜尋結果;失敗時回傳說明文字(不拋例外,
        讓模型仍能在沒有搜尋結果的情況下回答)。"""
        try:
            response = self._http.get(self.SEARCH_URL, params={"q": query})
        except httpx.HTTPError as exc:
            log.warning("web search failed for %r: %s", query, exc)
            return f"(web search failed: {exc})"
        if response.status_code != 200:
            # DuckDuckGo 反爬蟲時會回 202 等非 200 狀態;明講搜尋不可用,
            # 引導模型直接以既有知識作答,而不是不斷換關鍵字重試
            log.warning("web search returned HTTP %d for %r", response.status_code, query)
            return (
                f"(web search unavailable: HTTP {response.status_code}; "
                "do not retry — answer from your own knowledge and say the "
                "information could not be verified online)"
            )
        titles = list(self._RESULT_RE.finditer(response.text))[:max_results]
        snippets = [m.group("snippet") for m in self._SNIPPET_RE.finditer(response.text)]
        if not titles:
            return "(no search results)"
        lines = []
        for index, match in enumerate(titles):
            title = self._clean(match.group("title"))
            href = html.unescape(match.group("href"))
            snippet = self._clean(snippets[index]) if index < len(snippets) else ""
            lines.append(f"{index + 1}. {title}\n   {href}\n   {snippet}")
        return "\n".join(lines)


class AzureOpenAIChatService(ChatService):
    def __init__(
        self,
        settings: Settings | None = None,
        client: Any | None = None,
        search: DuckDuckGoWebSearch | None = None,
        max_tool_rounds: int = 3,
    ):
        self._settings = settings
        self._client = client
        self._search = search or DuckDuckGoWebSearch()
        self._max_tool_rounds = max_tool_rounds

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        if self._settings is None:
            self._settings = Settings.from_env()
        settings = self._settings
        from openai import OpenAI

        if settings.api_key:
            api_key: Any = settings.api_key
        else:
            from azure.identity import DefaultAzureCredential, get_bearer_token_provider

            # 官方 v1 API 模式:token provider 直接當 api_key,
            # OpenAI client 會自動取得並更新 token
            api_key = get_bearer_token_provider(DefaultAzureCredential(), TOKEN_SCOPE)
        kwargs: dict[str, Any] = {}
        if settings.api_version:
            kwargs["default_query"] = {"api-version": settings.api_version}
        self._client = OpenAI(base_url=settings.v1_base_url, api_key=api_key, **kwargs)
        return self._client

    def _run_tool_call(self, call: Any, question: str) -> str:
        if call.name != "web_search":
            return f"(unknown tool: {call.name})"
        try:
            arguments = json.loads(call.arguments or "{}")
        except (TypeError, ValueError):
            arguments = {}
        query = str(arguments.get("query") or question)
        log.info("web_search tool call: %r", query)
        return self._search.search(query)

    def _create_response(self, input_items: list[Any], allow_tools: bool) -> Any:
        assert self._client is not None and self._settings is not None
        kwargs: dict[str, Any] = {
            "model": self._settings.deployment_name,
            "instructions": SYSTEM_PROMPT,
            "input": input_items,
            "tools": [WEB_SEARCH_TOOL],
        }
        if not allow_tools:
            # 工具輪數用盡:停用工具,強制模型以現有資訊作答
            kwargs["tool_choice"] = "none"
        return self._client.responses.create(**kwargs)

    def complete(self, question: str) -> str:
        self._ensure_client()
        input_items: list[Any] = [{"role": "user", "content": question}]
        try:
            response = self._create_response(input_items, allow_tools=True)
            for round_index in range(self._max_tool_rounds):
                calls = [
                    item
                    for item in (response.output or [])
                    if getattr(item, "type", None) == "function_call"
                ]
                if not calls:
                    break
                input_items.extend(response.output)
                for call in calls:
                    input_items.append(
                        {
                            "type": "function_call_output",
                            "call_id": call.call_id,
                            "output": self._run_tool_call(call, question),
                        }
                    )
                is_last_round = round_index == self._max_tool_rounds - 1
                response = self._create_response(
                    input_items, allow_tools=not is_last_round
                )
            text = (response.output_text or "").strip()
            if not text:
                raise ChatServiceError("Model returned an empty answer.")
            return text
        except ChatServiceError:
            raise
        except Exception as exc:
            raise ChatServiceError(f"LLM call failed: {exc}") from exc
