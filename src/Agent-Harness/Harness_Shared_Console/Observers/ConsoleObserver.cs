// Copyright (c) Microsoft. All rights reserved.

// ============================================================
// 【檔案說明】Observer 模式的抽象基底(ConsoleObserver)
// 整個顯示層的擴充點。Runner 在串流生命週期的五個時機點回呼:
// 1. ConfigureRunOptions —— agent 呼叫前(可設定 ResponseFormat 等)
// 2. OnResponseUpdateAsync —— 每個串流 update(含 provider 原始事件)
// 3. OnContentAsync —— 每個 AIContent(工具呼叫、錯誤、reasoning⋯)
// 4. OnTextAsync —— 每段文字 delta
// 5. OnStreamCompleteAsync —— 串流結束(可回傳 FollowUpAction
//    驅動「問使用者」或「自動續跑」)
// 全部方法都有 no-op 預設實作,子類別只需覆寫關心的時機點。
// ============================================================

using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace Harness.Shared.Console.Observers;

/// <summary>
/// Abstract base class for console observers that participate in the agent response
/// streaming lifecycle. Observers can configure run options, observe streamed content,
/// and return messages to re-invoke the agent after the stream completes.
/// All methods have default no-op implementations so subclasses only override what they need.
/// </summary>
public abstract class ConsoleObserver
{
    /// <summary>
    /// Configures <see cref="AgentRunOptions"/> before the agent is invoked.
    /// Override to set options such as <see cref="AgentRunOptions.ResponseFormat"/>.
    /// </summary>
    /// <param name="options">The run options to configure.</param>
    /// <param name="agent">The agent being interacted with.</param>
    /// <param name="session">The current agent session.</param>
    public virtual void ConfigureRunOptions(AgentRunOptions options, AIAgent agent, AgentSession session)
    {
    }

    /// <summary>
    /// Called for each <see cref="AgentResponseUpdate"/> in the response stream, regardless of
    /// whether it contains content. Override to inspect update-level metadata such as
    /// <see cref="AgentResponseUpdate.RawRepresentation"/> for provider-specific events.
    /// </summary>
    /// <param name="ux">The UX state driver, used for rendering output.</param>
    /// <param name="update">The streaming response update.</param>
    /// <param name="agent">The agent being interacted with.</param>
    /// <param name="session">The current agent session.</param>
    public virtual Task OnResponseUpdateAsync(IUXStateDriver ux, AgentResponseUpdate update, AIAgent agent, AgentSession session) => Task.CompletedTask;

    /// <summary>
    /// Called for each <see cref="AIContent"/> item in the response stream.
    /// </summary>
    /// <param name="ux">The UX state driver, used for rendering output.</param>
    /// <param name="content">The content item from the stream.</param>
    /// <param name="agent">The agent being interacted with.</param>
    /// <param name="session">The current agent session.</param>
    public virtual Task OnContentAsync(IUXStateDriver ux, AIContent content, AIAgent agent, AgentSession session) => Task.CompletedTask;

    /// <summary>
    /// Called for each text update in the response stream.
    /// </summary>
    /// <param name="ux">The UX state driver, used for rendering output.</param>
    /// <param name="text">The text from the update.</param>
    /// <param name="agent">The agent being interacted with.</param>
    /// <param name="session">The current agent session.</param>
    public virtual Task OnTextAsync(IUXStateDriver ux, string text, AIAgent agent, AgentSession session) => Task.CompletedTask;

    /// <summary>
    /// Called after the response stream completes. Returns a heterogeneous list of
    /// follow-up actions (questions to ask the user, and/or messages to add directly to
    /// the next agent invocation), or <see langword="null"/> if no follow-up is needed.
    /// </summary>
    /// <param name="ux">The UX state driver, used for rendering output.</param>
    /// <param name="agent">The agent being interacted with.</param>
    /// <param name="session">The current agent session.</param>
    /// <returns>Follow-up actions to process after the stream completes, or <see langword="null"/>.</returns>
    public virtual Task<IList<FollowUpAction>?> OnStreamCompleteAsync(
        IUXStateDriver ux,
        AIAgent agent,
        AgentSession session) => Task.FromResult<IList<FollowUpAction>?>(null);
}
