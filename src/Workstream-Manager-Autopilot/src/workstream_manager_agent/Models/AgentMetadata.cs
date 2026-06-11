// ============================================================
// 【檔案說明】agent 身分中繼資料 —— 從 activity 的 recipient 解析而來:
// agentic user id、agent instance id、blueprint(application)id、
// 租戶 id 與 email,貫穿存取控制與 token 取得流程。
// ============================================================

namespace WorkstreamManager.Models;

public class AgentMetadata 
{
    public Guid UserId { get; set; }
    public Guid AgentId { get; set; }
    public Guid AgentApplicationId { get; set; }
    public Guid TenantId { get; set; }
    public string EmailId { get; set; } = string.Empty;
    public bool IsMessagingEnabled { get; set; } = false;
}
