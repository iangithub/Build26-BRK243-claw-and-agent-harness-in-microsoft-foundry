// ============================================================
// 【檔案說明】Workstream Manager Agent 的 ASP.NET Core 進入點
// 這是一個 Microsoft Agent 365(A365)agent,部署到 Azure AI Foundry
// 後發布進 Teams。本檔負責主機組態與 DI 註冊:
// - 正式環境掛 Azure Key Vault 作為組態來源(DefaultAzureCredential)
// - Agent SDK 三件套:HttpClient、IStorage(預設 in-memory)、
//   AddAgent<A365AgentApplication>() 註冊 agent 本體
// - 業務服務:ResponsesApiAgentLogicServiceFactory(LLM 邏輯)、
//   AgentTokenHelper(token 取得)、WorkItemService(工作項目儲存)
// - 可觀測性:A365 Kairo tracing(EnableKairoTracing)+ App Insights
// - 端點:POST /api/messages 接收 Teams/A365 activity(交給
//   IAgentHttpAdapter 處理),另有 /liveness、/readiness 探針
//   與開發環境的 Swagger UI。
// ============================================================

using Azure.Identity;
using WorkstreamManager.AgentLogic;
using WorkstreamManager.AgentLogic.ResponsesApi;
using WorkstreamManager.Models;
using WorkstreamManager.Services;
using Microsoft.Agents.Builder;
using Microsoft.Agents.Hosting.AspNetCore;
using Microsoft.Agents.Storage;

using Microsoft.ApplicationInsights.Extensibility;
using System.Text;
using Microsoft.Agents.A365.Observability.Runtime;

var builder = WebApplication.CreateBuilder(args);

// Add Azure Key Vault as configuration provider when running in production (not locally)
var keyVaultName = builder.Configuration["KeyVaultName"];
if (!string.IsNullOrEmpty(keyVaultName))
{
    var keyVaultUri = $"https://{keyVaultName}.vault.azure.net/";

    // Use DefaultAzureCredential which will use Managed Service Identity in production
    builder.Configuration.AddAzureKeyVault(
        new Uri(keyVaultUri),
        new DefaultAzureCredential());

    Console.WriteLine($"Azure Key Vault configured: {keyVaultUri}");
}
else
{
    Console.WriteLine("KeyVaultName not configured. Key Vault integration skipped.");
}

// Add controllers support
builder.Services.AddControllers();

// ===================================
// These are needed for Agent SDK
// ===================================
builder.Services.AddHttpClient();
builder.Services.AddSingleton<IStorage, MemoryStorage>();
builder.AddAgentApplicationOptions();

builder.AddAgent<A365AgentApplication>();
// Uncomment this so you can get logs of activities.
// builder.Services.AddSingleton<Microsoft.Agents.Builder.IMiddleware[]>([new TranscriptLoggerMiddleware(new FileTranscriptLogger())]);

builder.Services.AddSingleton<ResponsesApiAgentLogicServiceFactory>();

// Register auth helper
builder.Services.AddSingleton<AgentTokenHelper>();

// Register work item tracking service
builder.Services.AddSingleton<WorkItemService>();

// Register OpenAPI for external agents
builder.Services.AddOpenApi();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();
builder.Services.AddLogging();

#region Setup A365


AppContext.SetSwitch("Azure.Experimental.TraceGenAIMessageContent", true);
AppContext.SetSwitch("System.Net.Http.SocketsHttpHandler.Http2UnencryptedSupport", true);

if (Environment.GetEnvironmentVariable("EnableKairoTracing") == "true")
{
    builder.AddA365Tracing(config => { });
}

#endregion


builder.Services.AddApplicationInsightsTelemetry(options =>
{
    var connectionString =
        builder.Configuration["APPLICATIONINSIGHTS_CONNECTION_STRING"] ??
        builder.Configuration["ApplicationInsights:ConnectionString"];

    if (!string.IsNullOrWhiteSpace(connectionString))
    {
        Console.WriteLine("Application Insights connection string configured.");
        options.ConnectionString = connectionString;
    }
    else
    {
        Console.WriteLine("Application Insights connection string not configured.");
    }

    options.EnableAdaptiveSampling = false; // Disable adaptive sampling to capture all traces
});

builder.Logging.AddApplicationInsights();


var app = builder.Build();

var telemetryConfig = app.Services.GetRequiredService<TelemetryConfiguration>();
Console.WriteLine($"AI ConnectionString: {telemetryConfig.ConnectionString}");

var logger = app.Services.GetRequiredService<ILogger<Program>>();
logger.LogWarning("Application starting...");

// ===================================
// These are needed for Agent SDK
// ===================================
app.UseRouting();
// Enable buffering globally - this allows request body to be read multiple times
app.Use(next => context =>
{
    context.Request.EnableBuffering();
    return next(context);
});


app.MapPost("/api/messages", async (HttpRequest request, HttpResponse response, IAgentHttpAdapter adapter, IAgent agent, CancellationToken cancellationToken) =>
{
    // Comment out this line to disable request logging
    // await request.LogRequestAsync();

    request.EnableBuffering();

    using var reader = new StreamReader(request.Body, encoding: Encoding.UTF8, detectEncodingFromByteOrderMarks: false, leaveOpen: true);
    string body = await reader.ReadToEndAsync();

    // Reset stream position so ASP.NET can read it again
    request.Body.Position = 0;

    await adapter.ProcessAsync(request, response, agent, cancellationToken);
});

app.MapGet("/", () => "Hello World from WorkstreamManagerAgent!");

app.MapGet("/liveness", () => "Hello World from WorkstreamManagerAgent!");

app.MapGet("/readiness", () => "Hello World from WorkstreamManagerAgent!");


if (!app.Environment.IsDevelopment())
{
    app.UseHsts();
}

app.Use(next => context =>
{
    context.Request.EnableBuffering();
    return next(context);
});

// Configure the HTTP request pipeline.
if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

app.UseHttpsRedirection();

// Map controllers
app.MapControllers();

app.Run();

