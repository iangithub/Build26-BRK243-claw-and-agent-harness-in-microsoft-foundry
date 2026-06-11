# ============================================================
# 【檔案說明】Hosted Agent server 組裝
# 用 azure-ai-agentserver-invocations 的 InvocationAgentServerHost
# 架起 Invocations Protocol server(底層是 Starlette,內建
# health check 等基礎能力),把 invoke 請求交給 handlers.handle_invoke。
# create_app 可注入 ChatService(測試用);正式執行時用
# AzureOpenAIChatService,client 延遲建立,所以缺環境變數時
# server 仍能啟動,呼叫時才回清楚的 500 錯誤。
# ============================================================

from __future__ import annotations

from azure.ai.agentserver.invocations import InvocationAgentServerHost
from starlette.requests import Request

from . import handlers
from .chat_service import AzureOpenAIChatService, ChatService


def create_app(chat_service: ChatService | None = None) -> InvocationAgentServerHost:
    app = InvocationAgentServerHost()
    service = chat_service or AzureOpenAIChatService()

    @app.invoke_handler
    async def handle_invoke(request: Request):
        return await handlers.handle_invoke(request, service)

    return app
