// Copyright (c) Microsoft. All rights reserved.

// ============================================================
// 【檔案說明】mode_* 工具呼叫的格式器 —— agent 自己切換模式時
//(mode_set)在工具呼叫列顯示目標模式名稱,例如「mode_set (execute)」。
// ============================================================

using Microsoft.Extensions.AI;

namespace Harness.Shared.Console.ToolFormatters;

/// <summary>
/// Formats <c>mode_*</c> tool calls, showing the target mode for Set operations.
/// </summary>
public sealed class ModeToolFormatter : ToolCallFormatter
{
    /// <inheritdoc/>
    public override bool CanFormat(FunctionCallContent call) => call.Name.StartsWith("mode_", StringComparison.Ordinal);

    /// <inheritdoc/>
    public override string? FormatDetail(FunctionCallContent call) => call.Name switch
    {
        "mode_set" => FormatStringArg(call, "mode"),
        _ => null,
    };

    private static string? FormatStringArg(FunctionCallContent call, string paramName)
    {
        string? value = GetStringArgumentValue(call, paramName);
        return value is not null ? $"({value})" : null;
    }
}
