# ============================================================
# 【檔案說明】hermes_foundry_proxy 套件入口
# 一個最小可用的 stdin/stdout JSON-RPC proxy:
# 把 Hermes TUI gateway 送來的 JSON-RPC 2.0 請求(每行一筆,
# newline-delimited JSON)轉送到 Microsoft Foundry Hosted Agent
# 的 Invocations endpoint,再把 Foundry 回覆轉回 JSON-RPC response。
# 模組分工:
#   models.py  —— JSON-RPC / Foundry 回覆的資料模型與錯誤碼常數
#   config.py  —— 環境變數讀取與 invocation URL 組裝
#   foundry.py —— Foundry Invocations HTTP client(httpx + azure-identity)
#   proxy.py   —— stdin/stdout 主迴圈與 method dispatch
# ============================================================

__version__ = "0.1.0"
