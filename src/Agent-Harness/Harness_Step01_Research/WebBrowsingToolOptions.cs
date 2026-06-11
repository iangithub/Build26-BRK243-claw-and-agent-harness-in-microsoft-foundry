// Copyright (c) Microsoft. All rights reserved.

// ============================================================
// 【檔案說明】WebBrowsingTool 的存取政策設定
// 採「預設拒絕(deny by default)」設計:四個選項全部預設關閉,
// 必須明確開啟才允許連線。AllowedHosts 白名單優先權最高,
// 其次依公網/內網位址分流,AllowAllHosts 則完全停用邊界檢查
//(僅適合隔離環境)。本範例(Program.cs)只開啟 AllowPublicNetworks。
// ============================================================

namespace SampleApp;

/// <summary>
/// Options that control which URLs the <see cref="WebBrowsingTool"/> is permitted to access.
/// </summary>
/// <remarks>
/// <para>
/// By default, <b>no hosts are accessible</b>. You must explicitly opt in to one or more
/// of the access modes below. The validation order is:
/// </para>
/// <list type="number">
/// <item><description>If the host matches an entry in <see cref="AllowedHosts"/>, the request is allowed.</description></item>
/// <item><description>If the resolved IP is a public address and <see cref="AllowPublicNetworks"/> is <see langword="true"/>, the request is allowed.</description></item>
/// <item><description>If the resolved IP is a private/loopback/link-local address and <see cref="AllowPrivateNetworks"/> is <see langword="true"/>, the request is allowed.</description></item>
/// <item><description>If <see cref="AllowAllHosts"/> is <see langword="true"/>, the request is allowed.</description></item>
/// <item><description>Otherwise, the request is blocked.</description></item>
/// </list>
/// </remarks>
internal sealed class WebBrowsingToolOptions
{
    /// <summary>
    /// Gets or sets a list of host patterns that are always permitted, regardless of other settings.
    /// Patterns support wildcard prefix matching (e.g., <c>"*.example.com"</c> matches <c>"docs.example.com"</c>).
    /// Exact host names (e.g., <c>"docs.microsoft.com"</c>) are also supported.
    /// </summary>
    /// <remarks>This has the highest priority — if a host matches, it is allowed immediately.</remarks>
    public IReadOnlyList<string>? AllowedHosts { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether public internet hosts (non-private, non-loopback, non-link-local IPs) are permitted.
    /// Default is <see langword="false"/>.
    /// </summary>
    public bool AllowPublicNetworks { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether private network hosts are permitted.
    /// This includes RFC 1918 addresses (10.x.x.x, 172.16-31.x.x, 192.168.x.x),
    /// loopback (127.x.x.x, ::1), link-local (169.254.x.x, fe80::),
    /// and cloud metadata endpoints (169.254.169.254).
    /// Default is <see langword="false"/>.
    /// </summary>
    /// <remarks>
    /// <b>Warning:</b> Enabling this allows the agent to make requests to internal services,
    /// localhost, and cloud metadata endpoints. Only enable this if you understand the SSRF risks.
    /// </remarks>
    public bool AllowPrivateNetworks { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether all hosts are permitted without any restriction.
    /// Default is <see langword="false"/>.
    /// </summary>
    /// <remarks>
    /// <b>⚠️ UNSAFE:</b> Enabling this disables all network boundary checks and allows the agent
    /// to access any URL, including internal services, cloud metadata endpoints, and localhost.
    /// Only use this for trusted, isolated environments where SSRF is not a concern.
    /// </remarks>
    public bool AllowAllHosts { get; set; }
}
