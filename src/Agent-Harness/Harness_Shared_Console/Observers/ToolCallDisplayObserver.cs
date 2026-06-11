// Copyright (c) Microsoft. All rights reserved.

// ============================================================
// 【檔案說明】工具呼叫顯示 observer —— agent 每次呼叫工具時
// 顯示「🔧 Calling tool: ...」,細節文字交給 ToolCallFormatter 鏈
// 決定(例如 Todo 工具顯示待辦摘要、DownloadUri 顯示目標網址)。
// WebSearchToolCallContent 刻意略過,避免與 OpenAI 專用 observer 重複。
// ============================================================

using Harness.Shared.Console.ToolFormatters;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace Harness.Shared.Console.Observers;

/// <summary>
/// Displays tool call notifications (🔧) for <see cref="FunctionCallContent"/>
/// and <see cref="ToolCallContent"/> items in the response stream.
/// </summary>
public sealed class ToolCallDisplayObserver : ConsoleObserver
{
    private readonly IReadOnlyList<ToolCallFormatter> _formatters;

    /// <summary>
    /// Initializes a new instance of the <see cref="ToolCallDisplayObserver"/> class.
    /// </summary>
    /// <param name="formatters">Optional list of tool formatters. When <see langword="null"/>,
    /// the default formatters from <see cref="ToolCallFormatter.BuildDefaultToolFormatters"/> are used.</param>
    public ToolCallDisplayObserver(IReadOnlyList<ToolCallFormatter>? formatters = null)
    {
        this._formatters = formatters ?? ToolCallFormatter.BuildDefaultToolFormatters();
    }

    /// <inheritdoc/>
    public override async Task OnContentAsync(IUXStateDriver ux, AIContent content, AIAgent agent, AgentSession session)
    {
        if (content is FunctionCallContent functionCall)
        {
            await ux.WriteInfoLineAsync($"🔧 Calling tool: {ToolCallFormatter.Format(this._formatters, functionCall)}...", ConsoleColor.DarkYellow);
        }
        else if (content is WebSearchToolCallContent)
        {
            // Handled by OpenAIResponsesWebSearchDisplayObserver when present; skip here to avoid duplication.
        }
        else if (content is ToolCallContent toolCall)
        {
            await ux.WriteInfoLineAsync($"🔧 Calling tool: {toolCall}...", ConsoleColor.DarkYellow);
        }
    }
}
