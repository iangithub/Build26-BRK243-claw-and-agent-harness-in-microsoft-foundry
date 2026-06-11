// Copyright (c) Microsoft. All rights reserved.

// ============================================================
// 【檔案說明】模式名稱 → console 顏色的查表 helper
// 依模式名稱(plan/execute 等)查色彩對照表,查不到一律回 Gray。
// UI 的分隔線、模式標籤、串流文字顏色都由此決定。
// ============================================================

namespace Harness.Shared.Console;

/// <summary>
/// Helpers for resolving console colours associated with agent modes.
/// </summary>
internal static class ModeColors
{
    /// <summary>
    /// Gets the console color associated with a mode name, using the provided color map.
    /// Falls back to <see cref="ConsoleColor.Gray"/> when the mode is <see langword="null"/>
    /// or not present in the map.
    /// </summary>
    /// <param name="mode">The mode name, or <see langword="null"/> if no mode is active.</param>
    /// <param name="modeColors">Optional mapping of mode names to console colors.</param>
    public static ConsoleColor Get(string? mode, IReadOnlyDictionary<string, ConsoleColor>? modeColors = null)
    {
        if (mode is null)
        {
            return ConsoleColor.Gray;
        }

        if (modeColors is not null && modeColors.TryGetValue(mode, out var color))
        {
            return color;
        }

        return ConsoleColor.Gray;
    }
}
