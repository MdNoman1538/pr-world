using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using Bank.Data;
using Bank.Modules.Audit.Domain;
using Bank.Shared;
using Bank.Shared.Events;
using Bank.Shared.Time;

namespace Bank.Modules.Audit.Application;

public interface IAuditLog
{
    Task RecordAsync(IDomainEvent e, CancellationToken ct = default);
}

public sealed class AuditLog : IAuditLog
{
    private readonly BankDbContext _db;
    private readonly IClock _clock;

    public AuditLog(BankDbContext db, IClock clock)
    {
        _db = db;
        _clock = clock;
    }

    public async Task RecordAsync(IDomainEvent e, CancellationToken ct = default)
    {
        _db.AuditEntries.Add(new AuditEntry { EventType = e.GetType().Name, Payload = Redact(e), RecordedAt = _clock.UtcNow });
        await _db.SaveChangesAsync(ct);
    }

    /// <summary>Serialises the event and drops every property marked [Pii]. Personal data must not be IN events
    /// at all; this is the last line of defence.</summary>
    public static string Redact(IDomainEvent e)
    {
        var node = JsonSerializer.SerializeToNode(e, e.GetType())!.AsObject();
        foreach (var p in e.GetType().GetProperties(BindingFlags.Public | BindingFlags.Instance))
            if (p.GetCustomAttribute<PiiAttribute>() is not null || IsPiiParameter(e.GetType(), p.Name))
                node.Remove(p.Name);
        return node.ToJsonString();
    }

    // [Pii] on a record's positional parameter lands on the parameter, not the property.
    private static bool IsPiiParameter(Type t, string name) =>
        t.GetConstructors().SelectMany(c => c.GetParameters())
            .Any(p => string.Equals(p.Name, name, StringComparison.OrdinalIgnoreCase) && p.GetCustomAttribute<PiiAttribute>() is not null);
}

/// <summary>Writes every domain event to the audit trail.</summary>
public sealed class AuditEventHandler : IEventHandler<IDomainEvent>
{
    private readonly IAuditLog _audit;

    public AuditEventHandler(IAuditLog audit) => _audit = audit;

    public Task HandleAsync(IDomainEvent e, CancellationToken ct = default) => _audit.RecordAsync(e, ct);
}
