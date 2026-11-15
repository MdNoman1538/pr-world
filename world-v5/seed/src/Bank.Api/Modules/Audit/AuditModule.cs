using Bank.Modules.Audit.Application;
using Bank.Shared.Events;

namespace Bank.Modules.Audit;

public static class AuditModule
{
    public static IServiceCollection AddAuditModule(this IServiceCollection services)
    {
        services.AddScoped<IAuditLog, AuditLog>();
        services.AddScoped<IEventHandler<IDomainEvent>, AuditEventHandler>();
        return services;
    }
}
