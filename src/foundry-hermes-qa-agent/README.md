# foundry-hermes-qa-agent

部署在 **Microsoft Foundry** 上的 Python **Hosted Agent**:透過 **Foundry Invocations
Protocol** 接收 [foundry-tui-proxy](../Hermes-Foundry-Simple)(Hermes TUI gateway proxy)
傳來的 JSON payload,呼叫 **Azure OpenAI**(v1 API + Responses API)產生回答,
並回傳:

```json
{"type": "message.complete", "text": "<LLM回答>"}
```

模型可使用 `web_search` 工具(function calling + DuckDuckGo,免 API key)搜尋網路
回答時事問題;搜尋不可用時會優雅降級,以既有知識作答並註明無法線上驗證。

## 架構

```
Hermes TUI ──stdin/stdout──▶ foundry-tui-proxy
                                   │  POST {"kind":"hermes.rpc","method":"prompt.submit","input":...}
                                   ▼
                     Foundry Invocations endpoint
                                   │
                                   ▼
                       foundry-hermes-qa-agent          ┌──────────────┐
                     (InvocationAgentServerHost)───────▶│ Azure OpenAI │
                                   │     ▲              │  (gpt-5.5)   │
                                   │     │ function call└──────────────┘
                                   │     ▼
                                   │  web_search(DuckDuckGo)
                                   ▼
                  {"type":"message.complete","text":"..."}
```

## 輸入 contract

`kind` 必須是 `hermes.rpc`,`method` 必須是 `prompt.submit`,input 依序從
`body.input` → `params.input` → `params.message` 取得:

```json
{"kind": "hermes.rpc", "method": "prompt.submit", "input": "使用者問題"}
{"kind": "hermes.rpc", "method": "prompt.submit", "params": {"input": "使用者問題"}}
{"kind": "hermes.rpc", "method": "prompt.submit", "params": {"message": "使用者問題"}}
```

錯誤回應:kind/method 不支援或 input 為空 → HTTP 400;環境變數缺少或 LLM 失敗
→ HTTP 500。一律回 `{"error": "<code>", "message": "..."}`,不會讓 server crash。

## 環境變數

| 變數 | 必填 | 說明 |
|---|---|---|
| `AZURE_OPENAI_ENDPOINT` | ✅ | Azure OpenAI 資源端點,例如 `https://<resource>.openai.azure.com`(已含 `/openai/v1` 的形式也接受,會自動正規化) |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | ✅ | 模型部署名稱,例如 `gpt-5.5` |
| `AZURE_OPENAI_API_VERSION` | ─ | 選填。v1 GA API 已**不需要** api-version(官方建議);有設定時才會以 query string 傳送 |
| `AZURE_OPENAI_API_KEY` | ─ | 選填,僅供本機測試。**建議不設定**,讓驗證走 Microsoft Entra ID(`DefaultAzureCredential`,token scope `https://ai.azure.com/.default`);部署後使用 hosted agent 的 managed identity |
| `PORT` | ─ | 監聽 port,預設 8088 |

程式碼與 container 內**不含任何 secret**;key 只能由環境變數注入。

## 安裝

需要 Python 3.11+。

```powershell
cd src/foundry-hermes-qa-agent
python -m venv .venv
.venv\Scripts\Activate.ps1        # Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
```

## 本機執行

```powershell
$env:AZURE_OPENAI_ENDPOINT = "https://<resource>.openai.azure.com"
$env:AZURE_OPENAI_DEPLOYMENT_NAME = "gpt-5.5"
az login                                    # Entra ID 驗證(建議)
python -m foundry_hermes_qa_agent           # 預設 http://localhost:8088
python -m foundry_hermes_qa_agent --port 8131   # 自訂 port
```

log 一律寫到 stderr,不會污染 protocol response。

## 本機 curl 測試

```bash
# health check(AgentServer 內建)
curl http://localhost:8088/readiness
# => {"status":"healthy"}

# 問答
curl -sS -X POST http://localhost:8088/invocations \
  -H "Content-Type: application/json" \
  -d '{"kind":"hermes.rpc","method":"prompt.submit","input":"1+1等於多少?"}'
# => {"type":"message.complete","text":"1+1等於2。"}
```

PowerShell:

```powershell
Invoke-RestMethod -Uri http://localhost:8088/invocations -Method Post `
  -ContentType "application/json" `
  -Body '{"kind":"hermes.rpc","method":"prompt.submit","input":"你好"}'
```

## 執行測試

測試全部離線(假 OpenAI client + respx 攔截 httpx),不碰真實 Azure:

```powershell
python -m pytest
```

## 部署到 Microsoft Foundry Hosted Agent

### 1. 安裝工具

```powershell
winget install Microsoft.Azd        # macOS: brew install azd;或見官方安裝文件
az --version                        # 需要 Azure CLI
```

安裝 Microsoft Foundry azd extension(新名稱 `microsoft.foundry`;
較舊文件與本 repo 的 Hermes-Foundry 用的是前一個名稱 `azure.ai.agents`):

```powershell
azd ext install microsoft.foundry
```

### 2. 登入

```powershell
azd auth login
az login
```

### 3. 設定 azd 環境(Foundry project 與模型設定)

```powershell
cd src/foundry-hermes-qa-agent
azd env new foundry-hermes-qa      # 建立 azd 環境
azd env set AZURE_SUBSCRIPTION_ID <subscription-id>
azd env set AZURE_LOCATION <region>

# agent.yaml 會把這兩個值注入 container 環境變數
azd env set AZURE_OPENAI_ENDPOINT "https://<resource>.openai.azure.com"
azd env set AZURE_OPENAI_DEPLOYMENT_NAME "gpt-5.5"
```

### 4. 部署

```powershell
azd up          # provision + package + deploy
# 或分開:azd provision 然後 azd deploy
```

`azd deploy` 完成後輸出會顯示 agent endpoint:

```
Agent endpoint: https://<account>.services.ai.azure.com/api/projects/<project>/agents/foundry-hermes-qa-agent/versions/1
```

### 5. 授權模型存取(重要)

Hosted agent 在雲端是用 **managed identity** 呼叫 Azure OpenAI,
需在你的 Azure OpenAI 資源上授與 **Cognitive Services OpenAI User** 角色:

```powershell
$agent = azd ai agent show --output json | ConvertFrom-Json
az role assignment create `
  --assignee-object-id $agent.instance_identity.principal_id `
  --assignee-principal-type ServicePrincipal `
  --role "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd" `
  --scope <你的 Azure OpenAI 資源的 resource id>
```

### 6. 取得 invocations endpoint 並驗證

invocations endpoint 格式:

```
https://<account>.services.ai.azure.com/api/projects/<project>/agents/foundry-hermes-qa-agent/invocations
```

驗證:

```powershell
azd ai agent show                  # 確認狀態 Active
azd ai agent invoke '{"kind":"hermes.rpc","method":"prompt.submit","input":"你好"}'
azd ai agent monitor --follow      # 串流 container log
```

本機開發迴圈也可以用 `azd ai agent run` + `azd ai agent invoke --local`。

## 讓 foundry-tui-proxy 呼叫它

[foundry-tui-proxy(Hermes-Foundry-Simple)](../Hermes-Foundry-Simple) 透過環境變數
指向這個 agent 的 invocations endpoint:

```powershell
$env:HERMES_FOUNDRY_INVOCATIONS_ENDPOINT = "https://<account>.services.ai.azure.com/api/projects/<project>/agents/foundry-hermes-qa-agent/invocations?api-version=2025-05-15-preview"
$env:HERMES_FOUNDRY_AGENT_SESSION_ID = "my-session"   # 選填
az login
cd ../Hermes-Foundry-Simple
python -m hermes_foundry_proxy
```

proxy 收到 `prompt.submit` 時會 POST `{"kind":"hermes.rpc","method":"prompt.submit","input":...}`
到這個 agent,並把 `{"type":"message.complete","text":...}` 轉成 JSON-RPC response
回給 Hermes TUI。

## 專案結構

```
foundry-hermes-qa-agent/
├── pyproject.toml          # 相依套件與 pytest 設定
├── README.md
├── Dockerfile              # python:3.12-slim,無 secret,CMD python -m foundry_hermes_qa_agent
├── azure.yaml              # azd 服務定義(host: azure.ai.agent)
├── agent.yaml              # Hosted Agent 定義(protocol: invocations)
├── src/foundry_hermes_qa_agent/
│   ├── __main__.py         # CLI 入口(--port、log→stderr)
│   ├── app.py              # InvocationAgentServerHost 組裝
│   ├── handlers.py         # invoke handler(request.json() → JSONResponse)
│   ├── models.py           # payload 解析與回覆形狀
│   ├── settings.py         # AZURE_OPENAI_* 環境變數
│   ├── chat_service.py     # ChatService 抽象 + AzureOpenAIChatService + web_search
│   └── errors.py           # 錯誤階層(400/500 對應)
└── tests/                  # pytest(全離線)
```
