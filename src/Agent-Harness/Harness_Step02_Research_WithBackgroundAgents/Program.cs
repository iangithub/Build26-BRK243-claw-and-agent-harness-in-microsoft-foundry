// Copyright (c) Microsoft. All rights reserved.

// ============================================================
// 【檔案說明】Step02:背景代理(Background Agents)的委派模式
// 本範例示範「父 agent + 背景 agent」的多代理協作架構:
// 1. 先建立一個只開啟 WebSearch 的背景 agent(WebSearchAgent),
//    其餘功能(Todo、Mode、FileMemory、FileAccess、ToolApproval)全部關閉。
// 2. 父 agent(StockPriceResearcher)透過 BackgroundAgents = [webSearchAgent]
//    取得 BackgroundAgentsProvider 提供的委派工具:可同時啟動多個
//    背景任務(並行查詢多檔股票)、等待完成、取回結果、再清除任務。
// 對照 Step01:這裡的重點不是單一 agent 的能力,而是「任務分工與並行」。
// ============================================================

// This sample demonstrates how to use the BackgroundAgentsProvider to delegate work to background agents.
// A parent agent is given a list of stock tickers and instructed to find the closing price
// for each ticker on December 31, 2025. It delegates the web searches to a background agent.
// The HarnessAgent provides built-in WebSearch (HostedWebSearchTool) so no manual web search
// tool configuration is needed on the background agent.
//
// Special commands:
//   /exit    — End the session.

#pragma warning disable OPENAI001 // Suppress experimental API warnings for Responses API usage.
#pragma warning disable MAAI001  // Suppress experimental API warnings for Agents AI experiments.

using System.ClientModel.Primitives;
using Azure.AI.Projects;
using Azure.Identity;
using Harness.Shared.Console;
using Harness.Shared.Console.OpenAI;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-5.4";

const int MaxContextWindowTokens = 1_050_000;
const int MaxOutputTokens = 128_000;
const string TracingSourceName = "Harness.SubAgents";

// Set up OpenTelemetry tracing that writes spans to a text file.
using var tracerProvider = HarnessTracing.CreateFileTracerProvider(TracingSourceName);

// Create the AIProjectClient for communicating with the Foundry responses service.
var projectClient = new AIProjectClient(
    new Uri(endpoint),
    new DefaultAzureCredential(),
    new AIProjectClientOptions { RetryPolicy = new ClientRetryPolicy(3) });

// --- Background agent: Web Search Agent ---
// 背景 agent:只保留內建的 HostedWebSearchTool(網頁搜尋),
// 用 Disable* 旗標關閉所有用不到的功能,讓它保持單純、便宜、可並行。
// This agent uses the HarnessAgent's built-in HostedWebSearchTool to search the web.
// Features not needed by this sub-agent are disabled.
AIAgent webSearchAgent =
    projectClient
    .GetProjectOpenAIClient()
    .GetResponsesClient()
    .AsIChatClient(deploymentName)
    .AsHarnessAgent(MaxContextWindowTokens, MaxOutputTokens, new HarnessAgentOptions
    {
        Name = "WebSearchAgent",
        Description = "An agent that can search the web to find information.",
        OpenTelemetrySourceName = TracingSourceName,
        DisableTodoProvider = true,
        DisableAgentModeProvider = true,
        DisableFileMemory = true,   // If enabled, this would allow the agent to store memories as files in a directory associated with the current session
        DisableFileAccess = true,   // If enabled, this would allow the agent to read/write files in a working directory
        DisableToolApproval = true, // If enabled, this allows don't-ask-again approval functionality.
        ChatOptions = new ChatOptions
        {
            Instructions = "You are a web search assistant. When asked to find information, use the web search tool to look it up and return a concise, factual answer.",
        },
    });

// --- Parent agent: Stock Price Researcher ---
// 父 agent 的 instructions 明確定義五步驟工作流程:
// 一次啟動所有背景任務(並行)→ 等待全部完成 → 取回結果 →
// 以 Markdown 表格彙整 → 清除已完成任務釋放記憶體。
// 並要求一律委派給 WebSearchAgent 查證,不可憑記憶回答。
// This agent orchestrates the background agent to look up stock prices in parallel.
var parentInstructions =
    """
    You are a stock price research assistant. You have access to a web search background agent that can look up information on the web.

    When given a list of stock tickers, your job is to find the closing price for each ticker on December 31, 2025.

    ## Workflow

    1. For each ticker, start a background task on the WebSearchAgent asking it to find the closing price on December 31, 2025.
       - Start all background tasks before waiting for any of them to complete, so they run concurrently.
    2. Wait for all background tasks to complete.
    3. Retrieve the results from each background task.
    4. Present a summary table with the ticker symbol and closing price for each stock.
    5. Clear all completed tasks to free memory.

    ## Important

    - Always delegate web searches to the WebSearchAgent background agent. Do not try to answer from memory.
    - If a background task fails or returns unclear results, continue the task with a more specific query.
    - Present results in a clean markdown table format.
    """;

// --- Parent agent: Stock Price Researcher ---
// 父 agent 連自己的 WebSearch 都關閉(DisableWebSearch = true),
// 確保所有查詢都走背景 agent;BackgroundAgents 清單就是它唯一的「工具來源」。
// This agent orchestrates the sub-agent to look up stock prices in parallel.
// Most features are disabled since the parent only needs SubAgentsProvider.
AIAgent parentAgent =
    projectClient
    .GetProjectOpenAIClient()
    .GetResponsesClient()
    .AsIChatClient(deploymentName)
    .AsHarnessAgent(MaxContextWindowTokens, MaxOutputTokens, new HarnessAgentOptions
    {
        Name = "StockPriceResearcher",
        Description = "An agent that researches stock prices using background agents.",
        OpenTelemetrySourceName = TracingSourceName,
        DisableTodoProvider = true,
        DisableAgentModeProvider = true,
        DisableFileMemory = true,   // If enabled, this would allow the agent to store memories as files in a directory associated with the current session
        DisableFileAccess = true,   // If enabled, this would allow the agent to read/write files in a working directory
        DisableToolApproval = true, // If enabled, this allows don't-ask-again approval functionality.
        DisableWebSearch = true,
        BackgroundAgents = [webSearchAgent],
        ChatOptions = new ChatOptions
        {
            Instructions = parentInstructions,
            MaxOutputTokens = 16_000,
        },
    });

// 啟動互動式 console 對話迴圈;此範例不需要 plan/execute 模式,
// 使用預設 observers 組合即可(BackgroundAgentToolFormatter 會把背景任務的
// 啟動/等待/取回呼叫格式化顯示)。
// Run the interactive console session.
await HarnessConsole.RunAgentAsync(
    parentAgent,
    userPrompt: "Enter a list of stock tickers (e.g., BAC, MSFT, BA):",
    options: new HarnessConsoleOptions
    {
        Observers = [new OpenAIResponsesErrorObserver(), .. HarnessConsoleOptions.BuildDefaultObservers()],
    });
