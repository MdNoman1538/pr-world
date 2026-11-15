namespace Bank.Modules.Audit.Domain;

public sealed class AuditEntry
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public string EventType { get; set; } = "";
    /// <summary>The event as JSON, without any [Pii] property.</summary>
    public string Payload { get; set; } = "";
    public DateTimeOffset RecordedAt { get; set; }
}
