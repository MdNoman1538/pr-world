using System.Security.Claims;
using System.Text.Encodings.Web;
using Microsoft.AspNetCore.Authentication;
using Microsoft.Extensions.Options;

namespace Bank.Modules.Auth.Api;

/// <summary>Demo sign-in: the caller sends X-User-Id and optional X-Roles headers. Not for production.</summary>
public sealed class DemoAuthHandler : AuthenticationHandler<AuthenticationSchemeOptions>
{
    public new const string Scheme = "Demo";

    public DemoAuthHandler(IOptionsMonitor<AuthenticationSchemeOptions> options, ILoggerFactory logger, UrlEncoder encoder)
        : base(options, logger, encoder)
    {
    }

    protected override Task<AuthenticateResult> HandleAuthenticateAsync()
    {
        var userId = Request.Headers["X-User-Id"].ToString();
        if (string.IsNullOrWhiteSpace(userId))
            return Task.FromResult(AuthenticateResult.NoResult());

        var claims = new List<Claim> { new(ClaimTypes.NameIdentifier, userId) };
        var roles = Request.Headers["X-Roles"].ToString()
            .Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        foreach (var role in roles)
            claims.Add(new Claim(ClaimTypes.Role, role));

        var principal = new ClaimsPrincipal(new ClaimsIdentity(claims, Scheme));
        return Task.FromResult(AuthenticateResult.Success(new AuthenticationTicket(principal, Scheme)));
    }
}
