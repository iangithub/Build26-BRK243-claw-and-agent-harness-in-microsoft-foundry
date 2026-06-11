// Copyright (c) Microsoft. All rights reserved.

// ============================================================
// 【檔案說明】輸出區項目的內部資料型別
// OutputEntryType 區分項目種類(使用者輸入回顯/串流文字/資訊列/
// 串流結尾/排隊訊息),HarnessConsoleUXStateDriver 用「上一個項目
// 的型別」決定要不要在新項目前補空行,維持輸出的視覺節奏。
// ============================================================

namespace Harness.Shared.Console;

/// <summary>
/// Represents the type of an output entry in the console conversation.
/// </summary>
internal enum OutputEntryType
{
    /// <summary>User input echo (e.g. "You: hello").</summary>
    UserInput,

    /// <summary>In-progress streaming text from the agent (accumulated chunk by chunk).</summary>
    StreamingText,

    /// <summary>Informational line (tool calls, errors, usage, approval requests, etc.).</summary>
    InfoLine,

    /// <summary>Stream footer (e.g. "(no text response from agent)").</summary>
    StreamFooter,

    /// <summary>Pending injected message notification.</summary>
    PendingMessage,
}

/// <summary>
/// Represents a single output entry in the console conversation history.
/// Used internally by <see cref="HarnessConsoleUXStateDriver"/> to track
/// the in-progress streaming entry and last-entry type for spacing decisions.
/// </summary>
/// <param name="Type">The type of output entry.</param>
/// <param name="Text">The text content of the entry.</param>
/// <param name="Color">Optional foreground color for rendering.</param>
internal sealed record OutputEntry(OutputEntryType Type, string Text, ConsoleColor? Color = null);
