// ============================================================
// 【檔案說明】把 AgentTokenHelper 包成 Azure SDK 的 TokenCredential
// 帶快取(到期前 5 分鐘視為失效)與 SemaphoreSlim 防止並發重複取 token。
// ⚠️ 注意:快取不以 scope 區分 —— 同一個實例混用不同 audience 會
// 拿到錯的 token,因此每種 scope 都要 new 一個新實例
//(見 ResponsesApiAgentLogicServiceFactory 的說明)。
// ============================================================

namespace WorkstreamManager.Services;

using System.IdentityModel.Tokens.Jwt;
using Azure.Core;
using WorkstreamManager.Models;

/// <summary>
/// TokenCredential implementation that calls AgentTokenHelper to acquire tokens.
/// Includes token caching and expiry handling with thread-safe token refresh.
/// </summary>
public class AgentTokenCredential(AgentTokenHelper agentTokenHelper, AgentMetadata agent) : TokenCredential
{
    private AccessToken? cachedToken;
    private readonly SemaphoreSlim tokenSemaphore = new(1, 1);

    public override AccessToken GetToken(TokenRequestContext requestContext, CancellationToken cancellationToken)
    {
        return GetTokenAsync(requestContext, cancellationToken).GetAwaiter().GetResult();
    }

    public override async ValueTask<AccessToken> GetTokenAsync(TokenRequestContext requestContext, CancellationToken cancellationToken)
    {
        if (cachedToken.HasValue && DateTimeOffset.UtcNow.AddMinutes(5) < cachedToken.Value.ExpiresOn)
        {
            return cachedToken.Value;
        }

        await tokenSemaphore.WaitAsync(cancellationToken);
        try
        {
            if (cachedToken.HasValue && DateTimeOffset.UtcNow.AddMinutes(5) < cachedToken.Value.ExpiresOn)
            {
                return cachedToken.Value;
            }

            var scopes = requestContext.Scopes.Length > 0
                ? requestContext.Scopes
                : ["https://canary.graph.microsoft.com/.default"];

            var token = await agentTokenHelper.GetAgenticUserTokenAsync(
                agent.AgentApplicationId.ToString(),
                agent.AgentId.ToString(),
                agent.EmailId ?? agent.UserId.ToString(),
                agent.TenantId.ToString(),
                scopes);

            var expiresOn = GetTokenExpiryTime(token);
            var accessToken = new AccessToken(token, expiresOn);

            cachedToken = accessToken;
            return accessToken;
        }
        finally
        {
            tokenSemaphore.Release();
        }
    }

    private static DateTimeOffset GetTokenExpiryTime(string token)
    {
        try
        {
            if (new JwtSecurityTokenHandler().CanReadToken(token))
            {
                var jwtToken = new JwtSecurityToken(token);
                return jwtToken.ValidTo;
            }
        }
        catch
        {
            // If parsing fails, default to 1 hour from now
        }

        return DateTimeOffset.UtcNow.AddHours(1);
    }
}

