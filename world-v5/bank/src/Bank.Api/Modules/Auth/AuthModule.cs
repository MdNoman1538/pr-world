using Bank.Modules.Auth.Api;
using Bank.Modules.Auth.Application;
using Microsoft.AspNetCore.Authentication;

namespace Bank.Modules.Auth;

/// <summary>Role names carried in the X-Roles header (demo sign-in).</summary>
public static class Roles
{
    public const string Customer = "customer";
    public const string Teller = "teller";
    public const string LoanOfficer = "loan-officer";
    public const string ComplianceOfficer = "compliance-officer";
    public const string Admin = "admin";
}

/// <summary>Authorization policies for [Authorize(Policy = ...)].</summary>
public static class Policies
{
    /// <summary>Any signed-in user acting for themselves.</summary>
    public const string Customer = "customer";
    /// <summary>Bank staff: teller, loan officer, compliance officer or admin.</summary>
    public const string Staff = "staff";
    public const string LoanOfficer = "loan-officer";
    public const string Compliance = "compliance";
    public const string Admin = "admin";
}

public static class AuthModule
{
    public static IServiceCollection AddAuthModule(this IServiceCollection services)
    {
        services.AddHttpContextAccessor();
        services.AddAuthentication(DemoAuthHandler.Scheme)
            .AddScheme<AuthenticationSchemeOptions, DemoAuthHandler>(DemoAuthHandler.Scheme, _ => { });
        services.AddAuthorization(o =>
        {
            o.AddPolicy(Policies.Customer, p => p.RequireAuthenticatedUser());
            o.AddPolicy(Policies.Staff, p => p.RequireRole(Roles.Teller, Roles.LoanOfficer, Roles.ComplianceOfficer, Roles.Admin));
            o.AddPolicy(Policies.LoanOfficer, p => p.RequireRole(Roles.LoanOfficer));
            o.AddPolicy(Policies.Compliance, p => p.RequireRole(Roles.ComplianceOfficer));
            o.AddPolicy(Policies.Admin, p => p.RequireRole(Roles.Admin));
        });
        services.AddScoped<ICurrentUser, CurrentUser>();
        return services;
    }
}
