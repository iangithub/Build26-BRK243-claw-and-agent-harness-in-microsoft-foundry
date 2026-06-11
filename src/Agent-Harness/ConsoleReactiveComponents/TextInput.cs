// Copyright (c) Microsoft. All rights reserved.

// ============================================================
// 【檔案說明】文字輸入列元件(TextInput)
// 渲染「提示字串 + 使用者輸入文字」的輸入列:文字超過寬度時自動折行,
// 續行會縮排對齊到提示字串之後;文字為空時以深灰色顯示 placeholder。
// CalculateHeight() 讓父元件(HarnessAppComponent)能在排版前
// 預先算出輸入列需要幾列,動態調整捲動區的高度。
// 注意:此元件只負責「畫」,按鍵處理在 HarnessAppComponent 的
// KeyEventListener 訂閱中完成,輸入內容由 props 傳入。
// ============================================================

using Harness.ConsoleReactiveFramework;

namespace Harness.ConsoleReactiveComponents;

/// <summary>
/// Props for <see cref="TextInput"/>.
/// </summary>
public record TextInputProps : ConsoleReactiveProps
{
    /// <summary>Gets the prompt string displayed on the left (e.g. "&gt; " or "user &gt; ").</summary>
    public string Prompt { get; init; } = "> ";

    /// <summary>Gets the text content to render to the right of the prompt.</summary>
    public string Text { get; init; } = "";

    /// <summary>Gets the placeholder text shown in dark grey when <see cref="Text"/> is empty.</summary>
    public string Placeholder { get; init; } = "";
}

/// <summary>
/// A component that renders a prompt with text input. Supports multi-line text
/// where continuation lines are indented to align with the text start position
/// (i.e. the column after the prompt).
/// </summary>
public class TextInput : ConsoleReactiveComponent<TextInputProps, ConsoleReactiveState>
{
    /// <summary>
    /// Calculates the height (in rows) required to render the prompt and text
    /// given the available width.
    /// </summary>
    /// <param name="props">The text input props.</param>
    /// <param name="availableWidth">The total available width in columns.</param>
    /// <returns>The number of rows needed.</returns>
    public static int CalculateHeight(TextInputProps props, int availableWidth)
    {
        int promptLength = props.Prompt.Length;
        int textWidth = availableWidth - promptLength;

        if (textWidth <= 0 || props.Text.Length == 0)
        {
            return 1;
        }

        int lines = 1;
        int remaining = props.Text.Length - textWidth;
        while (remaining > 0)
        {
            lines++;
            remaining -= textWidth;
        }

        return lines;
    }

    /// <inheritdoc />
    public override void RenderCore(TextInputProps props, ConsoleReactiveState state)
    {
        int promptLength = props.Prompt.Length;
        int textWidth = props.Width - promptLength;
        string indent = new(' ', promptLength);

        // First line: prompt + start of text
        Console.Write(AnsiEscapes.MoveCursor(props.Y, props.X));
        Console.Write(AnsiEscapes.EraseEntireLine);
        Console.Write(props.Prompt);

        if (textWidth <= 0 || props.Text.Length == 0)
        {
            // Show placeholder if text is empty
            if (props.Text.Length == 0 && props.Placeholder.Length > 0 && textWidth > 0)
            {
                Console.Write(AnsiEscapes.SetForegroundColor(ConsoleColor.DarkGray));
                Console.Write(" ");
                Console.Write(props.Placeholder[..Math.Min(props.Placeholder.Length, textWidth - 1)]);
                Console.Write(AnsiEscapes.ResetAttributes);
            }

            return;
        }

        int offset = 0;
        int firstChunk = Math.Min(textWidth, props.Text.Length);
        Console.Write(props.Text[offset..firstChunk]);
        offset = firstChunk;

        // Continuation lines: indented to align with text start
        int row = 1;
        while (offset < props.Text.Length)
        {
            int chunk = Math.Min(textWidth, props.Text.Length - offset);
            Console.Write(AnsiEscapes.MoveCursor(props.Y + row, props.X));
            Console.Write(AnsiEscapes.EraseEntireLine);
            Console.Write(indent);
            Console.Write(props.Text[offset..(offset + chunk)]);
            offset += chunk;
            row++;
        }
    }
}
