using Bank.Modules.Notifications.Application;

namespace Bank.Modules.Notifications;

public static class NotificationsModule
{
    public static IServiceCollection AddNotificationsModule(this IServiceCollection services)
    {
        services.AddScoped<INotifier, LogNotifier>();
        return services;
    }
}
