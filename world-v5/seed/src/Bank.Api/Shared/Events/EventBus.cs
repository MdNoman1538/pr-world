namespace Bank.Shared.Events;

/// <summary>Something that happened in the domain. Every event goes through <see cref="IEventBus"/>.</summary>
public interface IDomainEvent
{
    DateTimeOffset OccurredAt { get; }
}

public interface IEventHandler<in TEvent> where TEvent : IDomainEvent
{
    Task HandleAsync(TEvent e, CancellationToken ct = default);
}

public interface IEventBus
{
    Task PublishAsync<TEvent>(TEvent e, CancellationToken ct = default) where TEvent : IDomainEvent;
}

/// <summary>In-process bus: typed handlers first, then catch-all handlers (audit).</summary>
public sealed class InMemoryEventBus : IEventBus
{
    private readonly IServiceProvider _services;

    public InMemoryEventBus(IServiceProvider services) => _services = services;

    public async Task PublishAsync<TEvent>(TEvent e, CancellationToken ct = default) where TEvent : IDomainEvent
    {
        foreach (var handler in _services.GetServices<IEventHandler<TEvent>>())
            await handler.HandleAsync(e, ct);
        foreach (var handler in _services.GetServices<IEventHandler<IDomainEvent>>())
            await handler.HandleAsync(e, ct);
    }
}

public static class EventBusModule
{
    public static IServiceCollection AddEventBus(this IServiceCollection services)
    {
        services.AddScoped<IEventBus, InMemoryEventBus>();
        return services;
    }
}
