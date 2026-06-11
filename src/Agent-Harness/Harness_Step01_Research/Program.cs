// Copyright (c) Microsoft. All rights reserved.

// ============================================================
// 【檔案說明】Step01:互動式研究代理(Research Agent)
// 本範例示範如何用 AsHarnessAgent() 把一個 IChatClient 包裝成
// 功能完整的 HarnessAgent:內建 TodoProvider(待辦清單)、
// AgentModeProvider(plan/execute 模式)、FileMemoryProvider(檔案記憶)、
// ToolApproval(工具核准)、WebSearch 與 OpenTelemetry 追蹤。
// 範例本身只需要補上兩件事:研究助理的自訂 instructions,
// 以及一個把 HTML 轉成 Markdown 的本機 WebBrowsingTool。
// 執行流程:使用者輸入研究主題 → agent 規劃並建立 todo 清單 →
// 取得使用者核准 → 逐步執行研究 → 輸出含引用來源的報告。
// ============================================================

// This sample demonstrates how to use a HarnessAgent for interactive research tasks.
// The HarnessAgent comes pre-configured with TodoProvider, AgentModeProvider, FileMemoryProvider,
// ToolApproval, WebSearch, and OpenTelemetry — so this sample only needs custom instructions
// and a WebBrowsingTool.
// The agent plans research tasks, creates a todo list, gets user approval,
// and then executes each step — all within an interactive conversation loop.
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
using Harness.Shared.Console.OpenAI;
using Harness.Shared.Console.ToolFormatters;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using SampleApp;

// 從環境變數讀取 Azure AI Foundry 專案端點與模型部署名稱(未設定時預設 gpt-5.4)。
var endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-5.4";

// 模型的 context window 上限與單次輸出 token 上限;
// HarnessAgent 會依這兩個數值決定何時觸發 in-loop compaction(對話歷史壓縮)。
const int MaxContextWindowTokens = 1_050_000;
const int MaxOutputTokens = 128_000;
const string TracingSourceName = "Harness.Research";

// 建立 OpenTelemetry 追蹤,把 span 寫到本機文字檔(方便事後檢視 agent 的每一步行為)。
// Set up OpenTelemetry tracing that writes spans to a text file.
// This captures all agent activity (tool calls, model invocations, compaction, etc.)
// as well as HTTP requests made by the underlying HttpClient transport.
using var tracerProvider = HarnessTracing.CreateFileTracerProvider(TracingSourceName);

// 研究助理的系統指示(instructions):要求多來源交叉驗證、
// 以 Markdown 呈現結果、inline 引用來源,並把最終報告存進 file memory,
// 讓報告在對話歷史被 compaction 壓縮後仍可取回。
// Create a HarnessAgent with the Harness providers (TodoProvider and AgentModeProvider)
// and research-focused instructions including the mandatory planning workflow.
var instructions =
    """
    ## Research Assistant Instructions

    You are a research assistant. When given a research topic, research it thoroughly using web search and web browsing.
    Use your knowledge to form good search queries and hypotheses, but always verify claims with the tools available to you rather than relying on memory alone.

    ### Research quality

    Consult multiple sources when possible and cross-reference key claims.
    When sources disagree, note the discrepancy and explain which source you consider more reliable and why.
    If a web page fails to load or a search returns irrelevant results, try alternative search queries or sources before moving on.
    Track your sources — you will need them when presenting results.

    ### Presenting results

    When presenting your final findings:
    - Use Markdown formatting for clarity.
    - Use clear sections with headings for each major topic or sub-question.
    - Cite your sources inline (e.g., "According to [source name](URL), ...").
    - End with a brief summary of key takeaways.
    - In addition to returning the results to the user, save the final research report to file memory so it survives compaction and can be referenced later.
    """;

// 建立 agent 的呼叫鏈:AIProjectClient(連 Foundry 專案)→ OpenAI Responses client →
// AsIChatClient(指定模型部署)→ AsHarnessAgent(套上完整 Harness 能力)。
// 注意:DisableFileAccess = true 表示此範例刻意關閉檔案存取(Step03 才會示範)。
// Create the agent using AsHarnessAgent, which pre-configures function invocation,
// per-service-call chat history persistence, in-loop compaction, TodoProvider, AgentModeProvider,
// FileMemoryProvider, ToolApproval, WebSearch, AgentSkillsProvider, and OpenTelemetry.
// Only custom instructions, a WebBrowsingTool, and FileAccess opt-out are needed.
AIAgent agent =
    // Create an OpenAIClient that communicates with the Foundry responses service.
    new AIProjectClient(
        new Uri(endpoint),
        // WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
        // In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
        // latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
        new DefaultAzureCredential(),
        new AIProjectClientOptions { RetryPolicy = new ClientRetryPolicy(3) })  // Enable retries to improve resiliency.
    .GetProjectOpenAIClient()
    .GetResponsesClient()
    .AsIChatClient(deploymentName)
    .AsHarnessAgent(MaxContextWindowTokens, MaxOutputTokens, new HarnessAgentOptions
    {
        Name = "ResearchAgent",
        Description = "A research assistant that plans and executes research tasks.",
        DisableFileAccess = true,                           // If enabled, this would allow the agent to read/write files in a working directory
        OpenTelemetrySourceName = TracingSourceName,        // Use our custom source name so spans are captured by the TracerProvider above.
        FileMemoryStore = new FileSystemAgentFileStore(     // Configure the file memory provider to store files in a local folder called "agent-files".
            Path.Combine(AppContext.BaseDirectory, "agent-files")),
        ChatOptions = new ChatOptions
        {
            Instructions = instructions,
            Tools =
            [
                new WebBrowsingTool(                        // Add a local web browsing tool that converts html to markdown.
                    new WebBrowsingToolOptions { AllowPublicNetworks = true }),
            ],
            MaxOutputTokens = MaxOutputTokens,              // Set a high token limit for long research tasks with many tool calls and long outputs.
            Reasoning = new() { Effort = ReasoningEffort.Medium },
        },
    });

// 啟動互動式 console 對話迴圈(由共用的 HarnessConsole 程式庫負責 UI 與事件處理)。
// Observers 決定串流輸出要顯示哪些內容:web search 過程、錯誤、
// 以及 BuildObserversWithPlanning 建立的「plan/execute 雙模式」觀察器組合;
// CommandHandlers 則提供 /todos、/mode、/exit 等斜線指令。
// Run the interactive console session using the shared HarnessConsole helper.
await HarnessConsole.RunAgentAsync(
    agent,
    userPrompt: "Enter a research topic to get started.",
    new HarnessConsoleOptions
    {
        Observers = [
            new OpenAIResponsesWebSearchDisplayObserver(),
            new OpenAIResponsesErrorObserver(),
            .. HarnessConsoleOptions.BuildObserversWithPlanning(
                agent,
                planModeName: "plan",
                executionModeName: "execute",
                maxContextWindowTokens: MaxContextWindowTokens,
                maxOutputTokens: MaxOutputTokens,
                toolFormatters: [new DownloadUriToolFormatter(), .. ToolCallFormatter.BuildDefaultToolFormatters()])],
        CommandHandlers = HarnessConsoleOptions.BuildDefaultCommandHandlers(agent),
    });
