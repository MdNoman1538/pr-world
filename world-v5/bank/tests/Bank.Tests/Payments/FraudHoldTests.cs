using Bank.Data;
using Bank.Modules.Audit.Application;
using Bank.Modules.Auth;
using Bank.Modules.Payments.Application;
using Bank.Modules.Payments.Domain;
using Bank.Tests;
using Xunit;

namespace Bank.Tests.Payments;

public sealed class FraudHoldTests
{
    private static (IPaymentReviewService Service, FakeUser User, FakeClock Clock, RecordingBus Bus, RecordingNotifier Notifier) CreateReviewService(
        BankDbContext db,
        string userId = "compliance-1",
        params string[] roles)
    {
        var user = new FakeUser(userId, roles);
        var clock = new FakeClock();
        var bus = new RecordingBus();
        var notifier = new RecordingNotifier();
        var ledger = TestKit.Ledger(db, bus, clock);
        IPaymentReviewService service = new PaymentReviewService(db, ledger, user, clock, bus, notifier);
        return (service, user, clock, bus, notifier);
    }

    [Theory]
    [InlineData(Roles.Customer)]
    [InlineData(Roles.Teller)]
    [InlineData(Roles.LoanOfficer)]
    [InlineData(Roles.Admin)]
    public async Task HeldAsync_throws_UnauthorizedAccessException_for_non_compliance_roles(string role)
    {
        using var db = TestKit.Db();
        var (service, _, _, _, _) = CreateReviewService(db, "user-1", role);

        await Assert.ThrowsAsync<UnauthorizedAccessException>(() => service.HeldAsync());
    }

    [Fact]
    public async Task HeldAsync_throws_UnauthorizedAccessException_when_user_has_no_roles()
    {
        using var db = TestKit.Db();
        var (service, _, _, _, _) = CreateReviewService(db, "user-1");

        await Assert.ThrowsAsync<UnauthorizedAccessException>(() => service.HeldAsync());
    }

    [Fact]
    public async Task HeldAsync_returns_empty_list_when_no_payments_are_held()
    {
        using var db = TestKit.Db();
        var (service, _, _, _, _) = CreateReviewService(db, "officer-1", Roles.ComplianceOfficer);

        var held = await service.HeldAsync();

        Assert.Empty(held);
    }

    [Theory]
    [InlineData(Roles.Customer)]
    [InlineData(Roles.Teller)]
    [InlineData(Roles.LoanOfficer)]
    [InlineData(Roles.Admin)]
    public async Task ReleaseAsync_throws_UnauthorizedAccessException_for_non_compliance_roles(string role)
    {
        using var db = TestKit.Db();
        var (service, _, _, bus, notifier) = CreateReviewService(db, "user-1", role);

        await Assert.ThrowsAsync<UnauthorizedAccessException>(() => service.ReleaseAsync(Guid.NewGuid()));
        Assert.Empty(bus.Events);
        Assert.Empty(notifier.Sent);
    }

    [Fact]
    public async Task ReleaseAsync_throws_KeyNotFoundException_when_payment_does_not_exist()
    {
        using var db = TestKit.Db();
        var (service, _, _, bus, notifier) = CreateReviewService(db, "officer-1", Roles.ComplianceOfficer);

        await Assert.ThrowsAsync<KeyNotFoundException>(() => service.ReleaseAsync(Guid.NewGuid()));
        Assert.Empty(bus.Events);
        Assert.Empty(notifier.Sent);
    }

    [Theory]
    [InlineData(Roles.Customer)]
    [InlineData(Roles.Teller)]
    [InlineData(Roles.LoanOfficer)]
    [InlineData(Roles.Admin)]
    public async Task RejectAsync_throws_UnauthorizedAccessException_for_non_compliance_roles(string role)
    {
        using var db = TestKit.Db();
        var (service, _, _, bus, notifier) = CreateReviewService(db, "user-1", role);

        await Assert.ThrowsAsync<UnauthorizedAccessException>(() => service.RejectAsync(Guid.NewGuid(), "Suspected fraud"));
        Assert.Empty(bus.Events);
        Assert.Empty(notifier.Sent);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    public async Task RejectAsync_throws_ArgumentException_when_reason_is_null_or_whitespace(string? reason)
    {
        using var db = TestKit.Db();
        var (service, _, _, bus, notifier) = CreateReviewService(db, "officer-1", Roles.ComplianceOfficer);

        await Assert.ThrowsAsync<ArgumentException>(() => service.RejectAsync(Guid.NewGuid(), reason!));
        Assert.Empty(bus.Events);
        Assert.Empty(notifier.Sent);
    }

    [Fact]
    public async Task RejectAsync_throws_KeyNotFoundException_when_payment_does_not_exist()
    {
        using var db = TestKit.Db();
        var (service, _, _, bus, notifier) = CreateReviewService(db, "officer-1", Roles.ComplianceOfficer);

        await Assert.ThrowsAsync<KeyNotFoundException>(() => service.RejectAsync(Guid.NewGuid(), "Unverified beneficiary"));
        Assert.Empty(bus.Events);
        Assert.Empty(notifier.Sent);
    }

    [Fact]
    public void Domain_events_preserve_payload_and_redact_cleanly_for_audit_log()
    {
        var clock = new FakeClock();
        var paymentId = Guid.NewGuid();

        var held = new PaymentHeld(paymentId, "cust-1", 5000.00m, "EUR", clock.UtcNow);
        clock.Advance(TimeSpan.FromMinutes(15));
        var released = new PaymentReleased(paymentId, "officer-1", clock.UtcNow);
        clock.Advance(TimeSpan.FromMinutes(5));
        var rejected = new PaymentRejected(paymentId, "officer-2", clock.UtcNow);

        Assert.Equal(paymentId, held.PaymentId);
        Assert.Equal("cust-1", held.CustomerId);
        Assert.Equal(5000.00m, held.Amount);
        Assert.Equal("EUR", held.Currency);
        Assert.Equal(released.PaymentId, paymentId);
        Assert.Equal("officer-1", released.ReleasedBy);
        Assert.Equal(rejected.PaymentId, paymentId);
        Assert.Equal("officer-2", rejected.RejectedBy);

        Assert.Contains(paymentId.ToString(), AuditLog.Redact(held));
        Assert.Contains(paymentId.ToString(), AuditLog.Redact(released));
        Assert.Contains(paymentId.ToString(), AuditLog.Redact(rejected));
    }
}
