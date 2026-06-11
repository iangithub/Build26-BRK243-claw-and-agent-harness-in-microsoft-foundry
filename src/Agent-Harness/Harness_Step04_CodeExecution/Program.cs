// Copyright (c) Microsoft. All rights reserved.

// ============================================================
// 【檔案說明】Step04:全功能代理 + Hyperlight 沙箱程式碼執行 + Skills
// 系列範例的集大成:HarnessAgent 所有內建功能全開(沒有任何 Disable* 旗標),
// 並額外加上兩個能力:
// 1. HyperlightCodeActProvider —— 讓 agent 透過 execute_code 工具
//    在 Hyperlight micro-VM 沙箱裡執行 Python(Wasm 後端),
//    用「實際跑程式驗證」取代「憑空推理」。需要 KVM 等虛擬化支援。
// 2. AgentSkillsProvider —— 自動探索 skills/ 資料夾下的技能
//   (本範例附 regex-tester),讓 agent 依 SKILL.md 的工作流程辦事。
// 建議試玩:「Help me write a regex that matches valid email addresses, then test it.」
// ============================================================

// This sample demonstrates a HarnessAgent with ALL features enabled, plus:
// - Hyperlight CodeAct (HyperlightCodeActProvider) for sandboxed Python code execution
// - Skills (AgentSkillsProvider) discovering a local "regex-tester" skill
//
// The agent can plan tasks with todos, manage modes, store memories, read/write files,
// search the web, approve sensitive tools, discover and use skills, and execute arbitrary
// Python code in a Hyperlight sandbox — all pre-configured by the HarnessAgent.
//
// Try asking: "Help me write a regex that matches valid email addresses, then test it."
//
// Special commands:
//   /todos  — Display the current todo list without invoking the agent.
//   /mode   — Get or set the current agent mode.
//   /exit   — End the session.

#pragma warning disable OPENAI001 // Suppress experimental API warnings for Responses API usage.
#pragma warning disable MAAI001  // Suppress experimental API warnings for Agents AI experiments.

using System.ClientModel.Primitives;
using Azure.AI.Projects;
using Azure.Identity;
using Harness.Shared.Console;
using HyperlightSandbox.Guest.Python;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hyperlight;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-5.4";

const int MaxContextWindowTokens = 1_050_000;
const int MaxOutputTokens = 128_000;
const string TracingSourceName = "Harness.CodeExecution";

// Set up OpenTelemetry tracing that writes spans to a text file.
using var tracerProvider = HarnessTracing.CreateFileTracerProvider(TracingSourceName);

// 建立 Hyperlight 程式碼執行 provider:Python 直譯器以 Wasm guest module 形式
// 載入 micro-VM,與宿主機完全隔離;模組路徑由 NuGet 套件自動解析。
// Create the HyperlightCodeActProvider with the Python/Wasm backend.
// The guest module path is resolved automatically from the Hyperlight.HyperlightSandbox.Guest.Python NuGet package.
using var codeAct = new HyperlightCodeActProvider(
    HyperlightCodeActProviderOptions.CreateForWasm(PythonGuestModule.GetModulePath()));

// instructions 的核心原則:需要計算/驗證/測試時一律寫 Python 用 execute_code
// 實際執行;任務符合某個 skill 的描述時依其指示與參考資料辦事;
// 複雜任務用 todo 拆解、用 web search 查資料、把重要發現存進 file memory。
var instructions =
    """
    ## Technical Assistant Instructions

    You are a code-powered technical assistant. You can execute Python code in a sandboxed environment
    to solve problems precisely rather than guessing. You also have access to skills that provide
    structured workflows for specific technical tasks.

    ### Code Execution

    When a problem requires computation, validation, or testing:
    - Write Python code and use `execute_code` to run it in the sandbox.
    - Always verify results by running the code rather than reasoning about what would happen.
    - If code fails, read the error message carefully, fix the issue, and retry.

    ### Skills

    You have access to discoverable skills. When a task matches a skill's description:
    - Follow the skill's instructions carefully.
    - Use the skill's reference materials for context.
    - Combine the skill's workflow with code execution when appropriate.

    ### Planning and Research

    For complex tasks:
    - Break the problem into steps using your todo list.
    - Research background information using web search when needed.
    - Save important findings to file memory for later reference.

    ### Presenting Results

    - Show your work: include the code you ran and its output.
    - Explain what each part of your solution does.
    - If applicable, save final results to file memory.
    """;

// 組裝 agent:不設任何 Disable* 旗標(全功能),
// 透過 AIContextProviders 掛上 Hyperlight CodeAct,
// FileMemoryStore 指向本機 agent-files/ 讓記憶跨 session 保留。
// Create the agent with ALL HarnessAgent features enabled plus Hyperlight CodeAct.
// No Disable* flags are set — TodoProvider, AgentModeProvider, FileMemory, FileAccess,
// ToolApproval, WebSearch, and AgentSkillsProvider are all active.
AIAgent agent =
    new AIProjectClient(
        new Uri(endpoint),
        new DefaultAzureCredential(),
        new AIProjectClientOptions { RetryPolicy = new ClientRetryPolicy(3) })
    .GetProjectOpenAIClient()
    .GetResponsesClient()
    .AsIChatClient(deploymentName)
    .AsHarnessAgent(MaxContextWindowTokens, MaxOutputTokens, new HarnessAgentOptions
    {
        Name = "CodeExecutionAgent",
        Description = "A technical assistant with sandboxed code execution and skill-based workflows.",
        OpenTelemetrySourceName = TracingSourceName,
        // Point the file memory at a local folder for persistent memory across sessions.
        FileMemoryStore = new FileSystemAgentFileStore(Path.Combine(AppContext.BaseDirectory, "agent-files")),
        // Add the HyperlightCodeActProvider so the agent can execute Python code in a sandbox.
        AIContextProviders = [codeAct],
        ChatOptions = new ChatOptions
        {
            Instructions = instructions,
            MaxOutputTokens = MaxOutputTokens,
            Reasoning = new() { Effort = ReasoningEffort.Medium },
        },
    });

// 啟動互動式 console 對話迴圈,套用 plan/execute 雙模式 observers
// 與預設斜線指令(/todos、/mode、/exit)。
// Run the interactive console session using the shared HarnessConsole helper.
await HarnessConsole.RunAgentAsync(
    agent,
    userPrompt: "Ask me a technical question, or try: \"Help me write a regex that matches valid email addresses.\"",
    new HarnessConsoleOptions
    {
        Observers = HarnessConsoleOptions.BuildObserversWithPlanning(
            agent,
            planModeName: "plan",
            executionModeName: "execute",
            maxContextWindowTokens: MaxContextWindowTokens,
            maxOutputTokens: MaxOutputTokens),
        CommandHandlers = HarnessConsoleOptions.BuildDefaultCommandHandlers(agent),
    });
