// ============================================================
// 【檔案說明】Agentic User Identity 的三段式 token 取得
// A365 agent 以「agentic user」身分呼叫下游 API(Graph、MCP),
// token 鏈分三步:
// 1. 用 managed identity 取 blueprint token(agent 藍圖身分)
// 2. 以 blueprint token 當 client assertion,換 agent instance 的
//    AAD token(api://AzureAdTokenExchange)
// 3. 再以兩者組合走 federated identity 流程,換出綁定特定使用者
//   (UPN)與目標 scope 的最終 token
// 這是 A365 平台的核心認證模式,值得單獨研讀。
// ============================================================

namespace WorkstreamManager.Services;

using Azure.Core;
using Azure.Identity;
using Microsoft.Identity.Client;
using System.Text.Json;

public class AgentTokenHelper(ILogger<AgentTokenHelper> logger)
{
    /// <summary>
    /// Performs the three-step agentic user identity token acquisition process using managed identity.
    /// </summary>
    public async Task<string> GetAgenticUserTokenAsync(string agentAppId, string agentAppInstanceId, string userUpn, string tenantId, string[] scopes)
    {
        try
        {
            // FIRST: Get blueprint token via managed identity
            var blueprintToken = await GetBlueprintToken(agentAppId);

            // SECOND: Get AAD token for AgentAppInstanceId
            var instanceApp = ConfidentialClientApplicationBuilder
                .Create(agentAppInstanceId)
                .WithClientAssertion((AssertionRequestOptions _) => Task.FromResult(blueprintToken.Token))
                .WithAuthority(new Uri($"https://login.microsoftonline.com/{tenantId}"))
                .Build();

            var instanceTokenResult = await instanceApp
                .AcquireTokenForClient(["api://AzureAdTokenExchange/.default"])
                .ExecuteAsync();

            // THIRD: Get combined user token
            var userToken = await GetUserFederatedIdentityTokenAsync(
                agentAppInstanceId,
                tenantId,
                blueprintToken.Token,
                instanceTokenResult.AccessToken,
                userUpn,
                scopes);

            return userToken;
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Error acquiring agentic user token");
            throw;
        }
    }

    private async Task<AccessToken> GetBlueprintToken(string clientId)
    {
        var credential = new DefaultAzureCredential(new DefaultAzureCredentialOptions
        {
            ManagedIdentityClientId = clientId,
        });
        return await credential.GetTokenAsync(new TokenRequestContext(["api://AzureADTokenExchange/.default"]));
    }

    private async Task<string> GetUserFederatedIdentityTokenAsync(
        string clientId,
        string tenantId,
        string clientAssertion,
        string userFederatedIdentityCredential,
        string username,
        string[] scopes)
    {
        using var httpClient = new HttpClient();

        var tokenEndpoint = $"https://login.microsoftonline.com/{tenantId}/oauth2/v2.0/token";

        var parameters = new Dictionary<string, string>
        {
            { "client_id", clientId },
            { "scope", string.Join(" ", scopes) },
            { "client_assertion_type", "urn:ietf:params:oauth:client-assertion-type:jwt-bearer" },
            { "client_assertion", clientAssertion },
            { "user_federated_identity_credential", userFederatedIdentityCredential },
            { "grant_type", "user_fic" }
        };

        if (username.Contains('@'))
        {
            parameters["username"] = username;
        }
        else
        {
            parameters["user_id"] = username;
        }

        var content = new FormUrlEncodedContent(parameters);
        var response = await httpClient.PostAsync(tokenEndpoint, content);

        if (!response.IsSuccessStatusCode)
        {
            var errorContent = await response.Content.ReadAsStringAsync();
            throw new InvalidOperationException($"Failed to acquire user federated identity token: {errorContent}");
        }

        var responseContent = await response.Content.ReadAsStringAsync();
        var tokenResponse = JsonSerializer.Deserialize<Dictionary<string, object>>(responseContent);

        if (tokenResponse != null && tokenResponse.TryGetValue("access_token", out var accessToken))
        {
            var token = accessToken?.ToString();
            return token ?? throw new InvalidOperationException("Access token is null");
        }

        throw new InvalidOperationException("Failed to parse access token from response");
    }
}
