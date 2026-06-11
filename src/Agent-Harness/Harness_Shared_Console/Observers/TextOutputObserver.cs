// Copyright (c) Microsoft. All rights reserved.

// ============================================================
// 【檔案說明】最簡單的 observer —— 把 agent 的文字 delta 原樣
// 串流到輸出區。非規劃模式的預設文字輸出;規劃模式則由
// PlanningOutputObserver 取代(因為要先解析 JSON 結構再決定顯示)。
// ============================================================

using Microsoft.Agents.AI;

namespace Harness.Shared.Console.Observers;

/// <summary>
/// Streams agent text output directly to the console.
/// Used in normal (non-planning) mode.
/// </summary>
public sealed class TextOutputObserver : ConsoleObserver
{
    /// <inheritdoc/>
    public override async Task OnTextAsync(IUXStateDriver ux, string text, AIAgent agent, AgentSession session)
    {
        await ux.WriteTextAsync(text);
    }
}
