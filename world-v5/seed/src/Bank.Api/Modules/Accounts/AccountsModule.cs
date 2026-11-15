using Bank.Modules.Accounts.Application;

namespace Bank.Modules.Accounts;

public static class AccountsModule
{
    public static IServiceCollection AddAccountsModule(this IServiceCollection services)
    {
        services.AddScoped<IAccountService, AccountService>();
        return services;
    }
}
