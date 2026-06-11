// Copyright (c) Microsoft. All rights reserved.

// ============================================================
// 【檔案說明】plan 模式回應的兩種型別:Clarification(需要澄清,
// 附選項讓使用者選)與 Approval(計畫完成,請求核准開始執行)。
// 以字串形式序列化進 JSON schema,[Description] 告訴模型何時該用哪種。
// ============================================================

using System.ComponentModel;
using System.Text.Json.Serialization;

namespace Harness.Shared.Console.Observers;

/// <summary>
/// Specifies the type of planning response from the agent.
/// </summary>
[JsonConverter(typeof(JsonStringEnumConverter<PlanningResponseType>))]
public enum PlanningResponseType
{
    /// <summary>
    /// The agent needs clarification and presents options for the user to choose from.
    /// </summary>
    [Description("Use this type when you need clarification around the user request and you want to present the user with options to choose from.")]
    Clarification,

    /// <summary>
    /// The agent is seeking approval to proceed with execution.
    /// </summary>
    [Description("Use this type when you are ready to start execution, but need approval to start executing.")]
    Approval,
}
