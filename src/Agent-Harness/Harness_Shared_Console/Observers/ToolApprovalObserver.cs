// Copyright (c) Microsoft. All rights reserved.

// ============================================================
// 【檔案說明】工具核准 observer —— human-in-the-loop 的核心範例
// 串流期間收集 ToolApprovalRequestContent(敏感工具的核准請求),
// 即時顯示「⚠️ Approval needed」;串流結束後為每筆請求產生一個
// ChoiceFollowUpQuestion 選單,提供四種選項:
// 核准這次 / 永遠核准此工具 / 永遠核准此工具+這組參數 / 拒絕。
// Continuation 把使用者的選擇轉成核准回應 content,包進 ChatMessage
// 送回 agent,讓被擋下的工具呼叫繼續或中止 ——
// 「don't-ask-again」就是靠 CreateAlwaysApprove* 回應實現的。
// ============================================================

using Harness.ConsoleReactiveComponents;
using Harness.Shared.Console.ToolFormatters;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace Harness.Shared.Console.Observers;

/// <summary>
/// Collects <see cref="ToolApprovalRequestContent"/> items during the response stream,
/// displays approval-needed notifications inline, and after the stream completes returns
/// one <see cref="ChoiceFollowUpQuestion"/> per pending approval request. Each question's
/// continuation produces a separate <see cref="ChatMessage"/> carrying the approval
/// response content.
/// </summary>
public sealed class ToolApprovalObserver : ConsoleObserver
{
    private readonly List<ToolApprovalRequestContent> _approvalRequests = [];
    private readonly IReadOnlyList<ToolCallFormatter> _formatters;

    /// <summary>
    /// Initializes a new instance of the <see cref="ToolApprovalObserver"/> class.
    /// </summary>
    /// <param name="formatters">Optional list of tool formatters. When <see langword="null"/>,
    /// the default formatters from <see cref="ToolCallFormatter.BuildDefaultToolFormatters"/> are used.</param>
    public ToolApprovalObserver(IReadOnlyList<ToolCallFormatter>? formatters = null)
    {
        this._formatters = formatters ?? ToolCallFormatter.BuildDefaultToolFormatters();
    }

    /// <inheritdoc/>
    public override async Task OnContentAsync(IUXStateDriver ux, AIContent content, AIAgent agent, AgentSession session)
    {
        if (content is ToolApprovalRequestContent approvalRequest)
        {
            this._approvalRequests.Add(approvalRequest);
            string toolName = approvalRequest.ToolCall is FunctionCallContent fc
                ? ToolCallFormatter.Format(this._formatters, fc)
                : approvalRequest.ToolCall?.ToString() ?? "unknown";
            await ux.WriteInfoLineAsync($"⚠️ Approval needed: {toolName}", ConsoleColor.Yellow);
        }
    }

    /// <inheritdoc/>
    public override Task<IList<FollowUpAction>?> OnStreamCompleteAsync(
        IUXStateDriver ux,
        AIAgent agent,
        AgentSession session)
    {
        if (this._approvalRequests.Count == 0)
        {
            return Task.FromResult<IList<FollowUpAction>?>(null);
        }

        var actions = new List<FollowUpAction>(this._approvalRequests.Count);
        foreach (var request in this._approvalRequests)
        {
            actions.Add(this.BuildApprovalQuestion(request));
        }

        this._approvalRequests.Clear();
        return Task.FromResult<IList<FollowUpAction>?>(actions);
    }

    private ChoiceFollowUpQuestion BuildApprovalQuestion(ToolApprovalRequestContent request)
    {
        string toolName = request.ToolCall is FunctionCallContent fc
            ? ToolCallFormatter.Format(this._formatters, fc)
            : request.ToolCall?.ToString() ?? "unknown";

        var choices = new List<string>
        {
            "Approve this call",
            "Always approve this tool (any arguments)",
            "Always approve this tool with these arguments",
            "Deny",
        };

        string prompt = $"🔐 Tool approval: {toolName}";

        return new ChoiceFollowUpQuestion(
            Prompt: prompt,
            Choices: choices,
            AllowCustomText: false,
            Continuation: async (selection, ux) =>
            {
                AIContent response = selection switch
                {
                    "Always approve this tool (any arguments)" => request.CreateAlwaysApproveToolResponse("User chose to always approve this tool"),
                    "Always approve this tool with these arguments" => request.CreateAlwaysApproveToolWithArgumentsResponse("User chose to always approve this tool with these arguments"),
                    "Deny" => request.CreateResponse(approved: false, reason: "User denied"),
                    _ => request.CreateResponse(approved: true, reason: "User approved"),
                };

                string action = selection switch
                {
                    "Always approve this tool (any arguments)" => "✅ Always approved (any args)",
                    "Always approve this tool with these arguments" => "✅ Always approved (these args)",
                    "Deny" => "❌ Denied",
                    _ => "✅ Approved",
                };

                ConsoleColor answerColor = selection == "Deny" ? ConsoleColor.Red : ConsoleColor.Green;
                string formatted = $"🔹 {prompt}\n   └─ {AnsiEscapes.SetForegroundColor(answerColor)}{action}{AnsiEscapes.ResetAttributes}";
                await ux.WriteInfoLineAsync(formatted, ConsoleColor.Gray).ConfigureAwait(false);

                return new ChatMessage(ChatRole.User, [response]);
            });
    }
}
