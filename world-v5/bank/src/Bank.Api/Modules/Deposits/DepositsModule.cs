using Bank.Modules.Deposits.Application;

namespace Bank.Modules.Deposits;

public static class DepositsModule
{
    public static IServiceCollection AddDepositsModule(this IServiceCollection services)
    {
        services.AddScoped<IDepositService, DepositService>();
        return services;
    }
}
