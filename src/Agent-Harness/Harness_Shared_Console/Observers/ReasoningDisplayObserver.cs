// Copyright (c) Microsoft. All rights reserved.

// ============================================================
// 【檔案說明】Reasoning 顯示 observer —— 把推理模型的思考過程
//(TextReasoningContent)以深洋紅色串流顯示,與一般回答區隔。
// ============================================================

using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace Harness.Shared.Console.Observers;

/// <summary>
/// Displays reasoning content in dark magenta from the response stream.
/// </summary>
public sealed class ReasoningDisplayObserver : ConsoleObserver
{
    /// <inheritdoc/>
    public override async Task OnContentAsync(IUXStateDriver ux, AIContent content, AIAgent agent, AgentSession session)
    {
        if (content is TextReasoningContent reasoning && !string.IsNullOrEmpty(reasoning.Text))
        {
            await ux.WriteTextAsync(reasoning.Text, ConsoleColor.DarkMagenta);
        }
    }
}
