// Copyright (c) Microsoft. All rights reserved.

// ============================================================
// 【檔案說明】Memoization 小工具(對應 React 的 useMemo 概念)
// 快取 mapper 的計算結果,只有輸入值改變時才重新計算,
// 供元件在 RenderCore 裡避免每次重繪都做昂貴的版面運算(例如換行切割)。
// ============================================================

namespace Harness.ConsoleReactiveFramework;

/// <summary>
/// Caches the result of a mapping function and only recomputes when the input changes.
/// </summary>
/// <typeparam name="TInput">The type of the input value.</typeparam>
/// <typeparam name="TOutput">The type of the mapped output value.</typeparam>
public class ConsoleReactiveMemo<TInput, TOutput>
{
    private TInput? _previousInput;
    private TOutput? _cachedOutput;
    private bool _hasValue;

    /// <summary>
    /// Returns the cached output if <paramref name="input"/> equals the previously stored input;
    /// otherwise invokes <paramref name="mapper"/> to compute and cache a new output.
    /// </summary>
    /// <param name="input">The current input value.</param>
    /// <param name="mapper">A function that maps the input to an output value.</param>
    /// <returns>The cached or newly computed output.</returns>
    public TOutput Map(TInput input, Func<TInput, TOutput> mapper)
    {
        ArgumentNullException.ThrowIfNull(mapper);

        if (!this._hasValue || !EqualityComparer<TInput>.Default.Equals(input, this._previousInput))
        {
            this._previousInput = input;
            this._cachedOutput = mapper(input);
            this._hasValue = true;
        }

        return this._cachedOutput!;
    }
}
