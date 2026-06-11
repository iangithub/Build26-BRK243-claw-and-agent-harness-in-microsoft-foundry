// ============================================================
// 【檔案說明】MCP server 設定的資料模型 —— 對應 ToolingManifest.json
// 或 Agent365 API 回傳的 MCP server 清單(名稱、URL、scope、audience),
// ResponsesApiClient 會把每筆轉成 Responses API 的 type="mcp" 工具。
// ============================================================

namespace WorkstreamManager.Models;

using System.Text.Json.Serialization;

public class ToolingManifest
{
    [JsonPropertyName("mcpServers")]
    public List<McpServerConfig> McpServers { get; set; } = [];
}

public class McpServerConfig
{
    [JsonPropertyName("mcpServerName")]
    public string McpServerName { get; set; } = string.Empty;

    [JsonPropertyName("id")]
    public string Id { get; set; } = string.Empty;

    [JsonPropertyName("url")]
    public string Url { get; set; } = string.Empty;

    [JsonPropertyName("scope")]
    public string Scope { get; set; } = string.Empty;

    [JsonPropertyName("audience")]
    public string Audience { get; set; } = string.Empty;

    [JsonPropertyName("publisher")]
    public string Publisher { get; set; } = string.Empty;
}

