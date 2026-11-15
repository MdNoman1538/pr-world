namespace Bank.Modules.Notifications.Application;

/// <summary>Sends a message to a customer (app push / e-mail). Messages must not contain [Pii] values.</summary>
public interface INotifier
{
    Task NotifyAsync(string customerId, string message, CancellationToken ct = default);
}

public sealed class LogNotifier : INotifier
{
    private readonly ILogger<LogNotifier> _log;

    public LogNotifier(ILogger<LogNotifier> log) => _log = log;

    public Task NotifyAsync(string customerId, string message, CancellationToken ct = default)
    {
        _log.LogInformation("Notify {Customer}: {Message}", customerId, message);
        return Task.CompletedTask;
    }
}
