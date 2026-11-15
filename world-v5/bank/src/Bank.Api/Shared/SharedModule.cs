using Bank.Shared.Settings;
using Bank.Shared.Time;

namespace Bank.Shared;

public static class SharedModule
{
    public static IServiceCollection AddShared(this IServiceCollection services)
    {
        services.AddSingleton<IClock, SystemClock>();
        services.AddSingleton(new BankSettings());
        return services;
    }
}
