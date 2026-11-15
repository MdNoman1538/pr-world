using Bank.Modules.Audit.Application;
using Bank.Shared;
using Bank.Shared.Events;
using Xunit;

namespace Bank.Tests;

public sealed class AuditTests
{
    private sealed record Sample(string Name, [property: Pii] string Iban, DateTimeOffset OccurredAt) : IDomainEvent;

    [Fact]
    public void Personal_data_is_removed_from_the_audit_payload()
    {
        var json = AuditLog.Redact(new Sample("ok", "FI123", DateTimeOffset.UnixEpoch));
        Assert.Contains("ok", json);
        Assert.DoesNotContain("FI123", json);
    }
}
