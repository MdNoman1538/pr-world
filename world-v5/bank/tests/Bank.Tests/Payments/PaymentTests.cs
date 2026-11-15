using Bank.Data;
using Bank.Modules.Accounts.Application;
using Bank.Modules.Auth;
using Bank.Modules.Ledger.Application;
using Bank.Modules.Payments.Application;
using Bank.Modules.Payments.Domain;
using Bank.Shared.Settings;
using Xunit;

namespace Bank.Tests.Payments;

public sealed class PaymentTests
{
    private static PaymentService CreateService(
        BankDbContext db,
        FakeUser user,
        FakeClock? clock = null,
        RecordingBus? bus = null,
        BankSettings? settings = null)
    {
        var effectiveClock = clock ?? new FakeClock();
        var effectiveBus = bus ?? new RecordingBus();
        var effectiveSettings = settings ?? TestKit.Settings();
        var ledger = TestKit.Ledger(db, clock: effectiveClock);
        var accounts = new AccountService(db, user, effectiveSettings, effectiveClock, new RecordingBus(), Array.Empty<IAccountOpeningRule>());
        return new PaymentService(db, ledger, accounts, user, effectiveClock, effectiveSettings, effectiveBus);
    }

    [Fact]
    public async Task PayAsync_valid_transfer_moves_money_persists_completed_payment_and_publishes_event()
    {
        using var db = TestKit.Db();
        var clock = new FakeClock();
        var bus = new RecordingBus();
        var user = new FakeUser("alice", Roles.Customer);
        var fromId = TestKit.Account(db, "alice", 500m, "EUR");
        var toId = TestKit.Account(db, "bob", 10m, "EUR");
        var service = CreateService(db, user, clock, bus);

        var payment = await service.PayAsync(new PaymentRequest("pay-1", fromId, toId, 125.50m, "dinner"));

        Assert.NotEqual(Guid.Empty, payment.Id);
        Assert.Equal("pay-1", payment.IdempotencyKey);
        Assert.Equal("alice", payment.CustomerId);
        Assert.Equal(fromId, payment.FromAccountId);
        Assert.Equal(toId, payment.ToAccountId);
        Assert.Equal(125.50m, payment.Amount);
        Assert.Equal("EUR", payment.Currency);
        Assert.Equal(PaymentStatus.Completed, payment.Status);
        Assert.NotNull(payment.TransferId);
        Assert.NotEqual(Guid.Empty, payment.TransferId!.Value);
        Assert.Equal("dinner", payment.Reference);
        Assert.Equal(clock.UtcNow, payment.CreatedAt);

        Assert.Equal(374.50m, TestKit.Balance(db, fromId));
        Assert.Equal(135.50m, TestKit.Balance(db, toId));

        var persisted = db.Payments.Single(p => p.Id == payment.Id);
        Assert.Equal(PaymentStatus.Completed, persisted.Status);
        Assert.Equal(payment.TransferId, persisted.TransferId);
        Assert.Equal("alice", persisted.CustomerId);
        Assert.Equal(125.50m, persisted.Amount);
        Assert.Equal("EUR", persisted.Currency);
        Assert.Equal(clock.UtcNow, persisted.CreatedAt);

        var ledgerEntries = db.LedgerEntries.Where(e => e.TransferId == payment.TransferId!.Value).ToList();
        Assert.Equal(2, ledgerEntries.Count);
        Assert.Equal(0m, ledgerEntries.Sum(e => e.Amount));

        var completedEvent = Assert.Single(bus.Events.OfType<PaymentCompleted>());
        Assert.Equal(payment.Id, completedEvent.PaymentId);
        Assert.Equal("alice", completedEvent.CustomerId);
        Assert.Equal(125.50m, completedEvent.Amount);
        Assert.Equal("EUR", completedEvent.Currency);
        Assert.Equal(clock.UtcNow, completedEvent.OccurredAt);
    }

    [Fact]
    public async Task PayAsync_allows_null_reference()
    {
        using var db = TestKit.Db();
        var user = new FakeUser("alice", Roles.Customer);
        var fromId = TestKit.Account(db, "alice", 100m, "EUR");
        var toId = TestKit.Account(db, "bob", 0m, "EUR");
        var service = CreateService(db, user);

        var payment = await service.PayAsync(new PaymentRequest("pay-null-ref", fromId, toId, 25m, null));

        Assert.Equal(PaymentStatus.Completed, payment.Status);
        Assert.Null(payment.Reference);
        Assert.Equal(75m, TestKit.Balance(db, fromId));
        Assert.Equal(25m, TestKit.Balance(db, toId));
    }

    [Fact]
    public async Task PayAsync_allows_transfer_between_customers_own_accounts()
    {
        using var db = TestKit.Db();
        var user = new FakeUser("alice", Roles.Customer);
        var checkingId = TestKit.Account(db, "alice", 200m, "EUR");
        var savingsId = TestKit.Account(db, "alice", 50m, "EUR");
        var service = CreateService(db, user);

        var payment = await service.PayAsync(new PaymentRequest("own-transfer", checkingId, savingsId, 75m, "savings"));

        Assert.Equal(PaymentStatus.Completed, payment.Status);
        Assert.Equal(125m, TestKit.Balance(db, checkingId));
        Assert.Equal(125m, TestKit.Balance(db, savingsId));
    }

    [Fact]
    public async Task PayAsync_from_account_not_owned_by_caller_throws_UnauthorizedAccessException()
    {
        using var db = TestKit.Db();
        var bus = new RecordingBus();
        var user = new FakeUser("alice", Roles.Customer);
        var bobsAccount = TestKit.Account(db, "bob", 500m, "EUR");
        var alicesAccount = TestKit.Account(db, "alice", 10m, "EUR");
        var service = CreateService(db, user, bus: bus);

        await Assert.ThrowsAsync<UnauthorizedAccessException>(() =>
            service.PayAsync(new PaymentRequest("steal-1", bobsAccount, alicesAccount, 100m, "nope")));

        Assert.Equal(500m, TestKit.Balance(db, bobsAccount));
        Assert.Equal(10m, TestKit.Balance(db, alicesAccount));
        Assert.Empty(db.Payments);
        Assert.Empty(bus.Events.OfType<PaymentCompleted>());
    }

    [Fact]
    public async Task PayAsync_from_nonexistent_account_throws_UnauthorizedAccessException()
    {
        using var db = TestKit.Db();
        var bus = new RecordingBus();
        var user = new FakeUser("alice", Roles.Customer);
        var toId = TestKit.Account(db, "bob", 10m, "EUR");
        var service = CreateService(db, user, bus: bus);

        await Assert.ThrowsAsync<UnauthorizedAccessException>(() =>
            service.PayAsync(new PaymentRequest("missing-src", Guid.NewGuid(), toId, 10m, "nope")));

        Assert.Equal(10m, TestKit.Balance(db, toId));
        Assert.Empty(db.Payments);
        Assert.Empty(bus.Events.OfType<PaymentCompleted>());
    }

    [Fact]
    public async Task PayAsync_uses_current_user_identity_when_caller_switches()
    {
        using var db = TestKit.Db();
        var user = new FakeUser("alice", Roles.Customer);
        var aliceAccount = TestKit.Account(db, "alice", 200m, "EUR");
        var bobAccount = TestKit.Account(db, "bob", 200m, "EUR");
        var recipient = TestKit.Account(db, "charlie", 0m, "EUR");
        var service = CreateService(db, user);

        var p1 = await service.PayAsync(new PaymentRequest("k-alice", aliceAccount, recipient, 50m, "from alice"));
        Assert.Equal("alice", p1.CustomerId);

        user.UserId = "bob";

        await Assert.ThrowsAsync<UnauthorizedAccessException>(() =>
            service.PayAsync(new PaymentRequest("k-bob-bad", aliceAccount, recipient, 10m, "hijack")));

        var p2 = await service.PayAsync(new PaymentRequest("k-bob-ok", bobAccount, recipient, 30m, "from bob"));
        Assert.Equal("bob", p2.CustomerId);
        Assert.Equal(80m, TestKit.Balance(db, recipient));
    }

    [Theory]
    [InlineData(0)]
    [InlineData(-0.01)]
    [InlineData(-100)]
    public async Task PayAsync_zero_or_negative_amount_throws_ArgumentException(decimal invalidAmount)
    {
        using var db = TestKit.Db();
        var bus = new RecordingBus();
        var user = new FakeUser("alice", Roles.Customer);
        var fromId = TestKit.Account(db, "alice", 500m, "EUR");
        var toId = TestKit.Account(db, "bob", 10m, "EUR");
        var service = CreateService(db, user, bus: bus);

        await Assert.ThrowsAsync<ArgumentException>(() =>
            service.PayAsync(new PaymentRequest("bad-amt", fromId, toId, invalidAmount, "invalid")));

        Assert.Equal(500m, TestKit.Balance(db, fromId));
        Assert.Equal(10m, TestKit.Balance(db, toId));
        Assert.Empty(db.Payments);
        Assert.Empty(bus.Events.OfType<PaymentCompleted>());
    }

    [Theory]
    [InlineData(10.001)]
    [InlineData(0.005)]
    [InlineData(1.234)]
    public async Task PayAsync_fractional_cents_throws_ArgumentException(decimal fractionalAmount)
    {
        using var db = TestKit.Db();
        var bus = new RecordingBus();
        var user = new FakeUser("alice", Roles.Customer);
        var fromId = TestKit.Account(db, "alice", 500m, "EUR");
        var toId = TestKit.Account(db, "bob", 10m, "EUR");
        var service = CreateService(db, user, bus: bus);

        await Assert.ThrowsAsync<ArgumentException>(() =>
            service.PayAsync(new PaymentRequest("frac-amt", fromId, toId, fractionalAmount, "fractional")));

        Assert.Equal(500m, TestKit.Balance(db, fromId));
        Assert.Equal(10m, TestKit.Balance(db, toId));
        Assert.Empty(db.Payments);
        Assert.Empty(bus.Events.OfType<PaymentCompleted>());
    }

    [Fact]
    public async Task PayAsync_smallest_valid_amount_one_cent_succeeds()
    {
        using var db = TestKit.Db();
        var user = new FakeUser("alice", Roles.Customer);
        var fromId = TestKit.Account(db, "alice", 1.00m, "EUR");
        var toId = TestKit.Account(db, "bob", 0m, "EUR");
        var service = CreateService(db, user);

        var payment = await service.PayAsync(new PaymentRequest("one-cent", fromId, toId, 0.01m, "penny"));

        Assert.Equal(0.01m, payment.Amount);
        Assert.Equal(PaymentStatus.Completed, payment.Status);
        Assert.Equal(0.99m, TestKit.Balance(db, fromId));
        Assert.Equal(0.01m, TestKit.Balance(db, toId));
    }

    [Fact]
    public async Task PayAsync_different_currencies_throws_CurrencyMismatchException()
    {
        using var db = TestKit.Db();
        var bus = new RecordingBus();
        var user = new FakeUser("alice", Roles.Customer);
        var eurId = TestKit.Account(db, "alice", 500m, "EUR");
        var sekId = TestKit.Account(db, "bob", 100m, "SEK");
        var service = CreateService(db, user, bus: bus);

        await Assert.ThrowsAsync<CurrencyMismatchException>(() =>
            service.PayAsync(new PaymentRequest("fx-nope", eurId, sekId, 50m, "cross currency")));

        Assert.Equal(500m, TestKit.Balance(db, eurId));
        Assert.Equal(100m, TestKit.Balance(db, sekId));
        Assert.Empty(db.Payments);
        Assert.Empty(bus.Events.OfType<PaymentCompleted>());
    }

    [Fact]
    public async Task PayAsync_duplicate_idempotency_key_for_same_customer_returns_existing_payment_without_moving_money_or_republishing()
    {
        using var db = TestKit.Db();
        var bus = new RecordingBus();
        var user = new FakeUser("alice", Roles.Customer);
        var fromId = TestKit.Account(db, "alice", 500m, "EUR");
        var toId = TestKit.Account(db, "bob", 0m, "EUR");
        var service = CreateService(db, user, bus: bus);

        var first = await service.PayAsync(new PaymentRequest("idem-1", fromId, toId, 100m, "rent"));
        var second = await service.PayAsync(new PaymentRequest("idem-1", fromId, toId, 100m, "rent"));

        Assert.Equal(first.Id, second.Id);
        Assert.Equal(first.TransferId, second.TransferId);
        Assert.Equal(400m, TestKit.Balance(db, fromId));
        Assert.Equal(100m, TestKit.Balance(db, toId));
        Assert.Single(db.Payments);
        Assert.Single(bus.Events.OfType<PaymentCompleted>());
    }

    [Fact]
    public async Task PayAsync_duplicate_idempotency_key_does_not_count_twice_toward_daily_limit()
    {
        using var db = TestKit.Db();
        var user = new FakeUser("alice", Roles.Customer);
        var fromId = TestKit.Account(db, "alice", 500m, "EUR");
        var toId = TestKit.Account(db, "bob", 0m, "EUR");
        var settings = TestKit.Settings(dailyTransferLimit: 100m);
        var service = CreateService(db, user, settings: settings);

        var first = await service.PayAsync(new PaymentRequest("k1", fromId, toId, 80m, "part 1"));
        var retry = await service.PayAsync(new PaymentRequest("k1", fromId, toId, 80m, "part 1"));
        var second = await service.PayAsync(new PaymentRequest("k2", fromId, toId, 20m, "part 2"));

        Assert.Equal(first.Id, retry.Id);
        Assert.NotEqual(first.Id, second.Id);
        Assert.Equal(400m, TestKit.Balance(db, fromId));
        Assert.Equal(100m, TestKit.Balance(db, toId));
        Assert.Equal(2, db.Payments.Count());
    }

    [Fact]
    public async Task PayAsync_same_idempotency_key_for_different_customers_executes_independently()
    {
        using var db = TestKit.Db();
        var bus = new RecordingBus();
        var user = new FakeUser("alice", Roles.Customer);
        var aliceAcc = TestKit.Account(db, "alice", 300m, "EUR");
        var bobAcc = TestKit.Account(db, "bob", 300m, "EUR");
        var recipient = TestKit.Account(db, "charlie", 0m, "EUR");
        var service = CreateService(db, user, bus: bus);

        var alicePayment = await service.PayAsync(new PaymentRequest("shared-key", aliceAcc, recipient, 40m, "alice"));

        user.UserId = "bob";
        var bobPayment = await service.PayAsync(new PaymentRequest("shared-key", bobAcc, recipient, 60m, "bob"));

        Assert.NotEqual(alicePayment.Id, bobPayment.Id);
        Assert.Equal("alice", alicePayment.CustomerId);
        Assert.Equal("bob", bobPayment.CustomerId);
        Assert.Equal(260m, TestKit.Balance(db, aliceAcc));
        Assert.Equal(240m, TestKit.Balance(db, bobAcc));
        Assert.Equal(100m, TestKit.Balance(db, recipient));
        Assert.Equal(2, db.Payments.Count());
        Assert.Equal(2, bus.Events.OfType<PaymentCompleted>().Count());
    }

    [Fact]
    public async Task PayAsync_exactly_at_daily_transfer_limit_succeeds()
    {
        using var db = TestKit.Db();
        var user = new FakeUser("alice", Roles.Customer);
        var fromId = TestKit.Account(db, "alice", 1_000m, "EUR");
        var toId = TestKit.Account(db, "bob", 0m, "EUR");
        var settings = TestKit.Settings(dailyTransferLimit: 500m);
        var service = CreateService(db, user, settings: settings);

        var payment = await service.PayAsync(new PaymentRequest("exact-limit", fromId, toId, 500m, "max"));

        Assert.Equal(PaymentStatus.Completed, payment.Status);
        Assert.Equal(500m, TestKit.Balance(db, fromId));
        Assert.Equal(500m, TestKit.Balance(db, toId));
    }

    [Fact]
    public async Task PayAsync_one_cent_over_daily_transfer_limit_throws_DailyLimitExceededException()
    {
        using var db = TestKit.Db();
        var bus = new RecordingBus();
        var user = new FakeUser("alice", Roles.Customer);
        var fromId = TestKit.Account(db, "alice", 1_000m, "EUR");
        var toId = TestKit.Account(db, "bob", 0m, "EUR");
        var settings = TestKit.Settings(dailyTransferLimit: 500m);
        var service = CreateService(db, user, bus: bus, settings: settings);

        await Assert.ThrowsAsync<DailyLimitExceededException>(() =>
            service.PayAsync(new PaymentRequest("over-limit", fromId, toId, 500.01m, "too much")));

        Assert.Equal(1_000m, TestKit.Balance(db, fromId));
        Assert.Equal(0m, TestKit.Balance(db, toId));
        Assert.Empty(db.Payments);
        Assert.Empty(bus.Events.OfType<PaymentCompleted>());
    }

    [Fact]
    public async Task PayAsync_cumulative_payments_exceeding_daily_limit_throw_DailyLimitExceededException()
    {
        using var db = TestKit.Db();
        var bus = new RecordingBus();
        var user = new FakeUser("alice", Roles.Customer);
        var fromId = TestKit.Account(db, "alice", 1_000m, "EUR");
        var toId = TestKit.Account(db, "bob", 0m, "EUR");
        var settings = TestKit.Settings(dailyTransferLimit: 500m);
        var service = CreateService(db, user, bus: bus, settings: settings);

        await service.PayAsync(new PaymentRequest("p1", fromId, toId, 300m, "first"));

        await Assert.ThrowsAsync<DailyLimitExceededException>(() =>
            service.PayAsync(new PaymentRequest("p2", fromId, toId, 200.01m, "second")));

        Assert.Equal(700m, TestKit.Balance(db, fromId));
        Assert.Equal(300m, TestKit.Balance(db, toId));
        Assert.Single(db.Payments);
        Assert.Single(bus.Events.OfType<PaymentCompleted>());
    }

    [Fact]
    public async Task PayAsync_daily_limit_resets_at_utc_midnight()
    {
        using var db = TestKit.Db();
        var clock = new FakeClock { UtcNow = new DateTimeOffset(2026, 3, 15, 23, 59, 59, TimeSpan.Zero) };
        var user = new FakeUser("alice", Roles.Customer);
        var fromId = TestKit.Account(db, "alice", 2_000m, "EUR");
        var toId = TestKit.Account(db, "bob", 0m, "EUR");
        var settings = TestKit.Settings(dailyTransferLimit: 500m);
        var service = CreateService(db, user, clock: clock, settings: settings);

        await service.PayAsync(new PaymentRequest("day1-full", fromId, toId, 500m, "day 1"));

        await Assert.ThrowsAsync<DailyLimitExceededException>(() =>
            service.PayAsync(new PaymentRequest("day1-extra", fromId, toId, 0.01m, "still day 1")));

        clock.Advance(TimeSpan.FromSeconds(1));

        var day2Payment = await service.PayAsync(new PaymentRequest("day2-full", fromId, toId, 500m, "day 2"));

        Assert.Equal(PaymentStatus.Completed, day2Payment.Status);
        Assert.Equal(1_000m, TestKit.Balance(db, fromId));
        Assert.Equal(1_000m, TestKit.Balance(db, toId));
    }

    [Fact]
    public async Task PayAsync_daily_limit_is_isolated_per_customer()
    {
        using var db = TestKit.Db();
        var user = new FakeUser("alice", Roles.Customer);
        var aliceAcc = TestKit.Account(db, "alice", 1_000m, "EUR");
        var bobAcc = TestKit.Account(db, "bob", 1_000m, "EUR");
        var recipient = TestKit.Account(db, "charlie", 0m, "EUR");
        var settings = TestKit.Settings(dailyTransferLimit: 500m);
        var service = CreateService(db, user, settings: settings);

        await service.PayAsync(new PaymentRequest("alice-max", aliceAcc, recipient, 500m, "alice"));

        user.UserId = "bob";
        var bobPayment = await service.PayAsync(new PaymentRequest("bob-max", bobAcc, recipient, 500m, "bob"));

        Assert.Equal(PaymentStatus.Completed, bobPayment.Status);
        Assert.Equal(1_000m, TestKit.Balance(db, recipient));
    }

    [Fact]
    public async Task PayAsync_insufficient_funds_throws_InsufficientFundsException_and_persists_nothing()
    {
        using var db = TestKit.Db();
        var bus = new RecordingBus();
        var user = new FakeUser("alice", Roles.Customer);
        var fromId = TestKit.Account(db, "alice", 50m, "EUR");
        var toId = TestKit.Account(db, "bob", 10m, "EUR");
        var service = CreateService(db, user, bus: bus);

        await Assert.ThrowsAsync<InsufficientFundsException>(() =>
            service.PayAsync(new PaymentRequest("nsf-1", fromId, toId, 50.01m, "overdraft")));

        Assert.Equal(50m, TestKit.Balance(db, fromId));
        Assert.Equal(10m, TestKit.Balance(db, toId));
        Assert.Empty(db.Payments);
        Assert.Empty(bus.Events.OfType<PaymentCompleted>());
    }

    [Fact]
    public async Task PayAsync_exact_account_balance_succeeds()
    {
        using var db = TestKit.Db();
        var user = new FakeUser("alice", Roles.Customer);
        var fromId = TestKit.Account(db, "alice", 50m, "EUR");
        var toId = TestKit.Account(db, "bob", 10m, "EUR");
        var service = CreateService(db, user);

        var payment = await service.PayAsync(new PaymentRequest("drain", fromId, toId, 50m, "all"));

        Assert.Equal(PaymentStatus.Completed, payment.Status);
        Assert.Equal(0m, TestKit.Balance(db, fromId));
        Assert.Equal(60m, TestKit.Balance(db, toId));
    }

    [Fact]
    public async Task ForCustomerAsync_returns_only_specified_customers_payments()
    {
        using var db = TestKit.Db();
        var user = new FakeUser("alice", Roles.Customer);
        var aliceAcc = TestKit.Account(db, "alice", 500m, "EUR");
        var bobAcc = TestKit.Account(db, "bob", 500m, "EUR");
        var recipient = TestKit.Account(db, "charlie", 0m, "EUR");
        var service = CreateService(db, user);

        var a1 = await service.PayAsync(new PaymentRequest("a1", aliceAcc, recipient, 10m, "a1"));
        var a2 = await service.PayAsync(new PaymentRequest("a2", aliceAcc, recipient, 20m, "a2"));

        user.UserId = "bob";
        var b1 = await service.PayAsync(new PaymentRequest("b1", bobAcc, recipient, 30m, "b1"));

        var alicePayments = await service.ForCustomerAsync("alice");
        var bobPayments = await service.ForCustomerAsync("bob");
        var charliePayments = await service.ForCustomerAsync("charlie");

        Assert.Equal(2, alicePayments.Count);
        Assert.All(alicePayments, p => Assert.Equal("alice", p.CustomerId));
        Assert.Contains(alicePayments, p => p.Id == a1.Id);
        Assert.Contains(alicePayments, p => p.Id == a2.Id);

        var singleBob = Assert.Single(bobPayments);
        Assert.Equal(b1.Id, singleBob.Id);
        Assert.Equal("bob", singleBob.CustomerId);

        Assert.Empty(charliePayments);
    }
}
