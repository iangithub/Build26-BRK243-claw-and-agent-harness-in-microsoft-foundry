# Hermes-Foundry-Simple

一個最小可用的 stdin/stdout JSON-RPC proxy:接收 Hermes TUI gateway 送來的
JSON-RPC 2.0 請求(每行一筆,newline-delimited JSON),把 `prompt.submit`
轉送到 Microsoft Foundry Hosted Agent 的 **Invocations endpoint**,
再把 Foundry 回覆轉成 JSON-RPC response 寫回 stdout。

這是 [`src/Hermes-Foundry`](../Hermes-Foundry) 完整版的簡化教學版本:
不做 SSE streaming(`config.get` 回 `streaming: false`)、不做 isolation headers、
不做 `session.events` 事件續傳,只保留「請求進、回覆出」的最小骨架。

```
Hermes TUI gateway ──stdin──▶ hermes_foundry_proxy ──HTTPS──▶ Foundry Invocations
                  ◀─stdout──                       ◀──JSON──
```

## 安裝

需要 Python 3.11+。

```powershell
cd src/Hermes-Foundry-Simple
python -m venv .venv
.venv\Scripts\Activate.ps1        # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

## 設定

| 環境變數 | 必填 | 說明 |
|---|---|---|
| `HERMES_FOUNDRY_INVOCATIONS_ENDPOINT` | ✅ | Foundry Hosted Agent 的 Invocations endpoint URL |
| `HERMES_FOUNDRY_AGENT_SESSION_ID` | ─ | 選填;若有設定且 endpoint 的 query string 尚未包含 `agent_session_id`,proxy 會自動附加 |

```powershell
$env:HERMES_FOUNDRY_INVOCATIONS_ENDPOINT = "https://<your-project>.services.ai.azure.com/api/projects/<project>/agents/<agent>/invocations?api-version=2025-05-15-preview"
$env:HERMES_FOUNDRY_AGENT_SESSION_ID = "my-session"   # 選填
```

### Azure 認證

proxy 透過 `azure.identity.DefaultAzureCredential` 取得 token
(scope:`https://ai.azure.com/.default`),執行前請先登入:

```powershell
az login
```

## 執行

```powershell
python -m hermes_foundry_proxy
```

啟動後從 stdin 持續讀取 JSON-RPC request(每行一筆),response 逐行寫到 stdout;
log 一律寫到 stderr,不會污染 stdout。Ctrl+C 或 stdin EOF 即結束。

### 手動測試(不需 Azure)

```powershell
echo '{"jsonrpc":"2.0","id":1,"method":"gateway.ready"}' | python -m hermes_foundry_proxy
# stdout:{"jsonrpc": "2.0", "id": 1, "result": {"ready": true, "backend": "foundry"}}
```

### 端到端測試(需 az login 與真實 endpoint)

```powershell
echo '{"jsonrpc":"2.0","id":2,"method":"prompt.submit","params":{"input":"你好"}}' | python -m hermes_foundry_proxy
# stdout:{"jsonrpc": "2.0", "id": 2, "result": {"type": "message.complete", "text": "..."}}
```

## 支援的 JSON-RPC method

| Method | 行為 |
|---|---|
| `gateway.ready` | 回 `{"ready": true, "backend": "foundry"}` |
| `commands.catalog` | 回 `{"commands": []}` |
| `config.get` | 回 `{"backend": "foundry", "streaming": false}` |
| `session.create` | 回本機產生的 `{"session_id": "local-..."}` |
| `session.status` | 回 `{"status": "ready"}` |
| `session.close` | 回 `{"closed": true}` |
| `prompt.submit` | 取 `params.input`(fallback `params.message`),POST 到 Foundry Invocations endpoint,回 `{"type": "message.complete", "text": "..."}` |

`prompt.submit` 對 Foundry 的 request body:

```json
{"kind": "hermes.rpc", "method": "prompt.submit", "input": "<user input>"}
```

HTTP headers:`Authorization: Bearer <token>`、`Content-Type: application/json`、
`Foundry-Features: HostedAgents=V1Preview`。

## 錯誤碼

任何錯誤都只會回 JSON-RPC error,不會讓 proxy process crash。

| Code | 情境 |
|---|---|
| `-32700` | stdin 該行不是合法 JSON |
| `-32600` | 缺 `jsonrpc` / `method` 等必要欄位 |
| `-32601` | 未支援的 method |
| `-32602` | `prompt.submit` 缺 `input` 與 `message` |
| `-32000` | 未設定 `HERMES_FOUNDRY_INVOCATIONS_ENDPOINT` |
| `-32001` | `DefaultAzureCredential` 取 token 失敗(請先 `az login`) |
| `-32002` | Foundry 回非 2xx(`data` 含 status code 與 body 摘要)或連線失敗 |
| `-32003` | Foundry 回應無法解析成 JSON |
| `-32004` | Foundry 回應缺 `text` 欄位 |
| `-32603` | 其他未預期錯誤 |

## 執行測試

測試全部離線執行,不會碰真實 Azure 或發出網路請求:

```powershell
python -m pytest tests/ -v
```
