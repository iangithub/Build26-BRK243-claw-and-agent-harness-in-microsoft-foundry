// Copyright (c) Microsoft. All rights reserved.

// ============================================================
// 【檔案說明】鍵盤輸入的事件來源
// singleton 背景迴圈每 16ms 輪詢 Console.KeyAvailable,
// 以 ReadKey(intercept: true) 攔截按鍵(不回顯到畫面),
// 再透過 KeyPressed 事件廣播給訂閱的元件(例如 TextInput、ListSelection)。
// 事件化之後,多個元件可以共用同一個輸入來源而不互相搶 ReadKey。
// ============================================================

namespace Harness.ConsoleReactiveFramework;

/// <summary>
/// Event args for key press events, wrapping a <see cref="ConsoleKeyInfo"/>.
/// </summary>
public class KeyPressEventArgs : EventArgs
{
    /// <summary>Gets the key information for the pressed key.</summary>
    public ConsoleKeyInfo KeyInfo { get; }

    /// <summary>
    /// Initializes a new instance of the <see cref="KeyPressEventArgs"/> class.
    /// </summary>
    /// <param name="keyInfo">The key information.</param>
    public KeyPressEventArgs(ConsoleKeyInfo keyInfo)
    {
        this.KeyInfo = keyInfo;
    }
}

/// <summary>
/// Singleton that polls for console key presses every 16ms and raises the
/// <see cref="KeyPressed"/> event when a key is detected.
/// </summary>
public sealed class KeyEventListener
{
#pragma warning disable IDE0052 // Remove unread private members
    private readonly Task _task;
#pragma warning restore IDE0052 // Remove unread private members

    private KeyEventListener()
    {
        this._task = this.ListenForKeyPressesAsync();
    }

    /// <summary>Gets the singleton instance of <see cref="KeyEventListener"/>.</summary>
    public static KeyEventListener Instance { get; } = new KeyEventListener();

    /// <summary>Raised when a key is pressed in the console.</summary>
    public event EventHandler<KeyPressEventArgs>? KeyPressed;

    private async Task ListenForKeyPressesAsync()
    {
        while (true)
        {
            while (Console.KeyAvailable)
            {
                var keyInfo = Console.ReadKey(intercept: true);
                this.KeyPressed?.Invoke(this, new KeyPressEventArgs(keyInfo));
            }

            await Task.Delay(16);
        }
    }
}
