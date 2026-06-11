# ============================================================
# 【檔案說明】foundry-hermes-qa-agent 套件入口
# 部署在 Microsoft Foundry 上的 Python Hosted Agent:
# 透過 Foundry Invocations Protocol 接收 foundry-tui-proxy 傳來的
# {"kind": "hermes.rpc", "method": "prompt.submit", "input": ...}
# payload,呼叫 Azure OpenAI(v1 API + Responses API)產生回答,
# 回傳 {"type": "message.complete", "text": "<LLM回答>"}。
# 模組分工:
#   settings.py     —— AZURE_OPENAI_* 環境變數讀取與 v1 base_url 組裝
#   errors.py       —— 錯誤階層(對應 HTTP status code)
#   models.py       —— payload 解析(input / params.input / params.message)
#   chat_service.py —— ChatService 抽象 + AzureOpenAIChatService 實作
#                      (含 web_search function-calling 工具迴圈)
#   handlers.py     —— invoke handler:request.json() → 回 JSONResponse
#   app.py          —— InvocationAgentServerHost 組裝
# ============================================================

__version__ = "0.1.0"
