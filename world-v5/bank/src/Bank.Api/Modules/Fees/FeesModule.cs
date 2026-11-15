using Bank.Modules.Fees.Application;

namespace Bank.Modules.Fees;

public static class FeesModule
{
    public static IServiceCollection AddFeesModule(this IServiceCollection services)
    {
        services.AddScoped<IFeeCalculator, FeeCalculator>();
        return services;
    }
}
