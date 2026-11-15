using Bank.Modules.Ledger.Application;

namespace Bank.Modules.Ledger;

public static class LedgerModule
{
    public static IServiceCollection AddLedgerModule(this IServiceCollection services)
    {
        services.AddScoped<ILedger, Bank.Modules.Ledger.Application.Ledger>();
        return services;
    }
}
