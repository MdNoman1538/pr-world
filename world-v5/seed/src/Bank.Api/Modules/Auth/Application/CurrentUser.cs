using System.Security.Claims;

namespace Bank.Modules.Auth.Application;

/// <summary>Who is calling. Never take a user id from a request body: use this.</summary>
public interface ICurrentUser
{
    string UserId { get; }
    bool IsInRole(string role);
}

public sealed class CurrentUser : ICurrentUser
{
    private readonly IHttpContextAccessor _http;

    public CurrentUser(IHttpContextAccessor http) => _http = http;

    public string UserId =>
        _http.HttpContext?.User.FindFirst(ClaimTypes.NameIdentifier)?.Value
        ?? throw new UnauthorizedAccessException("No signed-in user.");

    public bool IsInRole(string role) => _http.HttpContext?.User.IsInRole(role) ?? false;
}
