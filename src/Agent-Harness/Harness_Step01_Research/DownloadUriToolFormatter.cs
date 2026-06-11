// Copyright (c) Microsoft. All rights reserved.

// ============================================================
// 【檔案說明】DownloadUri 工具呼叫的顯示格式器
// 自訂 ToolCallFormatter:當 agent 呼叫 DownloadUri 工具時,
// 在 console 的工具呼叫列顯示目標 URI(例如「🔧 DownloadUri (https://...)」),
// 讓使用者一眼看出 agent 正在瀏覽哪個網頁。
// ============================================================

using Harness.Shared.Console.ToolFormatters;
using Microsoft.Extensions.AI;

namespace SampleApp;

/// <summary>
/// Formats <c>DownloadUri</c> tool calls, showing the target URI.
/// </summary>
public sealed class DownloadUriToolFormatter : ToolCallFormatter
{
    /// <inheritdoc/>
    public override bool CanFormat(FunctionCallContent call) =>
        call.Name is "DownloadUri";

    /// <inheritdoc/>
    public override string? FormatDetail(FunctionCallContent call)
    {
        string? value = GetStringArgumentValue(call, "uri");
        return value is not null ? $"({value})" : null;
    }
}
