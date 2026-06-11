// Copyright (c) Microsoft. All rights reserved.

// ============================================================
// 【檔案說明】Token 用量 observer —— 攔截 UsageContent,
// 把 input/output/total 對照預算(context window 與輸出上限)
// 算出百分比,更新到狀態列(📊 Tokens — ...)。
// 讓使用者隨時掌握 context 消耗、預判 compaction 何時觸發。
// ============================================================

using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace Harness.Shared.Console.Observers;

/// <summary>
/// Displays token usage statistics (📊) from the response stream.
/// </summary>
public sealed class UsageDisplayObserver : ConsoleObserver
{
    private readonly int? _maxContextWindowTokens;
    private readonly int? _maxOutputTokens;

    /// <summary>
    /// Initializes a new instance of the <see cref="UsageDisplayObserver"/> class.
    /// </summary>
    /// <param name="maxContextWindowTokens">Optional max context window size in tokens.</param>
    /// <param name="maxOutputTokens">Optional max output tokens.</param>
    public UsageDisplayObserver(int? maxContextWindowTokens, int? maxOutputTokens)
    {
        this._maxContextWindowTokens = maxContextWindowTokens;
        this._maxOutputTokens = maxOutputTokens;
    }

    /// <inheritdoc/>
    public override Task OnContentAsync(IUXStateDriver ux, AIContent content, AIAgent agent, AgentSession session)
    {
        if (content is UsageContent usage)
        {
            if (usage.Details is not null)
            {
                ux.SetUsageText(this.FormatUsageBreakdown(usage.Details));
            }
            else
            {
                ux.SetUsageText("📊 Tokens —");
            }
        }

        return Task.CompletedTask;
    }

    private string FormatUsageBreakdown(UsageDetails details)
    {
        int? inputBudget = (this._maxContextWindowTokens is not null && this._maxOutputTokens is not null)
            ? this._maxContextWindowTokens.Value - this._maxOutputTokens.Value
            : null;

        return $"📊 Tokens — input: {FormatTokenCount(details.InputTokenCount, inputBudget)}"
            + $" | output: {FormatTokenCount(details.OutputTokenCount, this._maxOutputTokens)}"
            + $" | total: {FormatTokenCount(details.TotalTokenCount, this._maxContextWindowTokens)}";
    }

    private static string FormatTokenCount(long? count, int? budget)
    {
        if (count is null)
        {
            return "—";
        }

        if (budget is not null && budget.Value > 0)
        {
            double pct = (double)count.Value / budget.Value * 100;
            return $"{count.Value:N0}/{budget.Value:N0} ({pct:F1}%)";
        }

        return $"{count.Value:N0}";
    }
}
