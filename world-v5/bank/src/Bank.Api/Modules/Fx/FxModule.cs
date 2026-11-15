using Bank.Modules.Fx.Application;

namespace Bank.Modules.Fx;

public static class FxModule
{
    public static IServiceCollection AddFxModule(this IServiceCollection services)
    {
        services.AddScoped<IFxService, FxService>();
        return services;
    }
}
