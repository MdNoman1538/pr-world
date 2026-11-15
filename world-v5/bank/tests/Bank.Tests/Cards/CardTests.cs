using Bank.Data;
using Bank.Modules.Accounts.Application;
using Bank.Modules.Audit.Application;
using Bank.Modules.Auth;
using Bank.Modules.Cards.Application;
using Bank.Modules.Cards.Domain;
using Bank.Modules.Ledger.Domain;
using Xunit;

namespace Bank.Tests.Cards;

public sealed class CardTests
{
    private static (BankDbContext Db, FakeUser User, FakeClock Clock, RecordingBus Bus, CardService Service) CreateSut(
        string userId = "alice",
        params string[] roles)
    {
        var db = TestKit.Db();
        var user = new FakeUser(userId, roles.Length == 0 ? [Roles.Customer] : roles);
        var clock = new FakeClock();
        var bus = new RecordingBus();
        var ledger = TestKit.Ledger(db, bus, clock);
        var accounts = new AccountService(db, user, TestKit.Settings(), clock, bus, Array.Empty<IAccountOpeningRule>());
        var service = new CardService(db, ledger, accounts, user, clock, bus);
        return (db, user, clock, bus, service);
    }

    [Fact]
    public async Task IssueAsync_creates_active_card_for_owner_and_publishes_CardIssued()
    {
        var (db, _, clock, bus, service) = CreateSut("alice", Roles.Customer);
        var accountId = TestKit.Account(db, "alice", 500m);

        var card = await service.IssueAsync(accountId);

        var saved = db.Cards.Single(c => c.Id == card.Id);
        Assert.Equal(accountId, saved.AccountId);
        Assert.Equal("alice", saved.CustomerId);
        Assert.Equal(CardStatus.Active, saved.Status);
        Assert.Equal(2000m, saved.PerTransactionLimit);
        Assert.Equal(16, saved.Number.Length);
        Assert.All(saved.Number, c => Assert.True(char.IsAsciiDigit(c)));
        Assert.Equal(saved.Number[^4..], saved.Last4);

        var evt = Assert.Single(bus.Events.OfType<CardIssued>());
        Assert.Equal(card.Id, evt.CardId);
        Assert.Equal("alice", evt.CustomerId);
        Assert.Equal(card.Last4, evt.Last4);
        Assert.Equal(clock.UtcNow, evt.OccurredAt);
    }

    [Fact]
    public async Task IssueAsync_rejects_non_owner_with_UnauthorizedAccessException()
    {
        var (db, user, _, bus, service) = CreateSut("alice", Roles.Customer);
        var accountId = TestKit.Account(db, "alice", 500m);
        user.UserId = "bob";

        await Assert.ThrowsAsync<UnauthorizedAccessException>(() => service.IssueAsync(accountId));

        Assert.Empty(db.Cards);
        Assert.Empty(bus.Events.OfType<CardIssued>());
    }

    [Fact]
    public async Task IssueAsync_rejects_unknown_account_with_UnauthorizedAccessException()
    {
        var (db, _, _, bus, service) = CreateSut("alice", Roles.Customer);

        await Assert.ThrowsAsync<UnauthorizedAccessException>(() => service.IssueAsync(Guid.NewGuid()));

        Assert.Empty(db.Cards);
        Assert.Empty(bus.Events.OfType<CardIssued>());
    }

    [Fact]
    public async Task FreezeAsync_and_UnfreezeAsync_transition_card_between_Active_and_Frozen()
    {
        var (db, _, _, _, service) = CreateSut("alice", Roles.Customer);
        var accountId = TestKit.Account(db, "alice", 500m);
        var card = await service.IssueAsync(accountId);

        var frozen = await service.FreezeAsync(card.Id);
        Assert.Equal(CardStatus.Frozen, frozen.Status);
        Assert.Equal(CardStatus.Frozen, db.Cards.Single(c => c.Id == card.Id).Status);

        var unfrozen = await service.UnfreezeAsync(card.Id);
        Assert.Equal(CardStatus.Active, unfrozen.Status);
        Assert.Equal(CardStatus.Active, db.Cards.Single(c => c.Id == card.Id).Status);
    }

    [Fact]
    public async Task CancelAsync_cancels_active_and_frozen_cards()
    {
        var (db, _, _, _, service) = CreateSut("alice", Roles.Customer);
        var accountId = TestKit.Account(db, "alice", 500m);
        var activeCard = await service.IssueAsync(accountId);
        var frozenCard = await service.IssueAsync(accountId);
        await service.FreezeAsync(frozenCard.Id);

        var cancelledFromActive = await service.CancelAsync(activeCard.Id);
        var cancelledFromFrozen = await service.CancelAsync(frozenCard.Id);

        Assert.Equal(CardStatus.Cancelled, cancelledFromActive.Status);
        Assert.Equal(CardStatus.Cancelled, cancelledFromFrozen.Status);
        Assert.Equal(CardStatus.Cancelled, db.Cards.Single(c => c.Id == activeCard.Id).Status);
        Assert.Equal(CardStatus.Cancelled, db.Cards.Single(c => c.Id == frozenCard.Id).Status);
    }

    [Fact]
    public async Task Lifecycle_operations_reject_non_owner_without_changing_status()
    {
        var (db, user, _, _, service) = CreateSut("alice", Roles.Customer);
        var accountId = TestKit.Account(db, "alice", 500m);
        var card = await service.IssueAsync(accountId);

        user.UserId = "bob";
        await Assert.ThrowsAsync<UnauthorizedAccessException>(() => service.FreezeAsync(card.Id));
        Assert.Equal(CardStatus.Active, db.Cards.Single(c => c.Id == card.Id).Status);

        user.UserId = "alice";
        await service.FreezeAsync(card.Id);

        user.UserId = "bob";
        await Assert.ThrowsAsync<UnauthorizedAccessException>(() => service.UnfreezeAsync(card.Id));
        await Assert.ThrowsAsync<UnauthorizedAccessException>(() => service.CancelAsync(card.Id));
        Assert.Equal(CardStatus.Frozen, db.Cards.Single(c => c.Id == card.Id).Status);
    }

    [Fact]
    public async Task Cancelled_is_terminal_for_service_and_domain_methods()
    {
        var (db, _, _, _, service) = CreateSut("alice", Roles.Customer);
        var accountId = TestKit.Account(db, "alice", 500m);
        var card = await service.IssueAsync(accountId);
        await service.CancelAsync(card.Id);

        await Assert.ThrowsAsync<InvalidOperationException>(() => service.FreezeAsync(card.Id));
        await Assert.ThrowsAsync<InvalidOperationException>(() => service.UnfreezeAsync(card.Id));
        await Assert.ThrowsAsync<InvalidOperationException>(() => service.CancelAsync(card.Id));

        Assert.Throws<InvalidOperationException>(() => card.Freeze());
        Assert.Throws<InvalidOperationException>(() => card.Unfreeze());
        Assert.Throws<InvalidOperationException>(() => card.Cancel());
        Assert.Equal(CardStatus.Cancelled, db.Cards.Single(c => c.Id == card.Id).Status);
    }

    [Fact]
    public async Task AuthoriseAsync_approves_payment_moves_funds_to_Suspense_and_publishes_event()
    {
        var (db, user, clock, bus, service) = CreateSut("alice", Roles.Customer);
        var accountId = TestKit.Account(db, "alice", 1000m, "EUR");
        var card = await service.IssueAsync(accountId);
        var suspenseId = BankAccounts.For(BankAccountKind.Suspense, "EUR");
        var suspenseBefore = TestKit.Balance(db, suspenseId);

        user.UserId = "card-network";
        clock.Advance(TimeSpan.FromMinutes(5));

        var result = await service.AuthoriseAsync(card.Id, 250m, "Coffee Shop");

        Assert.True(result.Approved);
        Assert.Null(result.DeclineReason);
        Assert.NotNull(result.TransferId);
        Assert.NotEqual(Guid.Empty, result.TransferId.Value);

        Assert.Equal(750m, TestKit.Balance(db, accountId));
        Assert.Equal(suspenseBefore + 250m, TestKit.Balance(db, suspenseId));

        var entries = db.LedgerEntries.Where(e => e.TransferId == result.TransferId.Value).ToList();
        Assert.Equal(2, entries.Count);
        Assert.Equal(0m, entries.Sum(e => e.Amount));

        var evt = Assert.Single(bus.Events.OfType<CardPaymentAuthorised>());
        Assert.Equal(card.Id, evt.CardId);
        Assert.Equal(250m, evt.Amount);
        Assert.Equal("EUR", evt.Currency);
        Assert.Equal("Coffee Shop", evt.Merchant);
        Assert.Equal(clock.UtcNow, evt.OccurredAt);
    }

    [Fact]
    public async Task AuthoriseAsync_uses_account_currency_for_Suspense_and_event()
    {
        var (db, user, _, bus, service) = CreateSut("alice", Roles.Customer);
        var accountId = TestKit.Account(db, "alice", 1000m, "SEK");
        var card = await service.IssueAsync(accountId);
        var sekSuspenseId = BankAccounts.For(BankAccountKind.Suspense, "SEK");
        var eurSuspenseId = BankAccounts.For(BankAccountKind.Suspense, "EUR");
        var sekBefore = TestKit.Balance(db, sekSuspenseId);
        var eurBefore = TestKit.Balance(db, eurSuspenseId);

        user.UserId = "teller";
        var result = await service.AuthoriseAsync(card.Id, 300m, "Stockholm Store");

        Assert.True(result.Approved);
        Assert.Equal(700m, TestKit.Balance(db, accountId));
        Assert.Equal(sekBefore + 300m, TestKit.Balance(db, sekSuspenseId));
        Assert.Equal(eurBefore, TestKit.Balance(db, eurSuspenseId));

        var evt = Assert.Single(bus.Events.OfType<CardPaymentAuthorised>());
        Assert.Equal("SEK", evt.Currency);
    }

    [Fact]
    public async Task AuthoriseAsync_succeeds_at_exact_2000_limit_and_exact_balance()
    {
        var (db, user, _, _, service) = CreateSut("alice", Roles.Customer);
        var accountId = TestKit.Account(db, "alice", 2000m);
        var card = await service.IssueAsync(accountId);

        user.UserId = "network";
        var result = await service.AuthoriseAsync(card.Id, 2000.00m, "Electronics");

        Assert.True(result.Approved);
        Assert.Null(result.DeclineReason);
        Assert.NotNull(result.TransferId);
        Assert.Equal(0m, TestKit.Balance(db, accountId));
    }

    [Theory]
    [InlineData(10.125, 10.13)]
    [InlineData(10.124, 10.12)]
    [InlineData(0.005, 0.01)]
    [InlineData(2000.004, 2000.00)]
    public async Task AuthoriseAsync_rounds_amount_AwayFromZero_to_two_decimal_places(decimal rawAmount, decimal expectedRounded)
    {
        var (db, user, _, bus, service) = CreateSut("alice", Roles.Customer);
        var accountId = TestKit.Account(db, "alice", 2500m);
        var card = await service.IssueAsync(accountId);

        user.UserId = "network";
        var result = await service.AuthoriseAsync(card.Id, rawAmount, "Merchant");

        Assert.True(result.Approved);
        Assert.Equal(2500m - expectedRounded, TestKit.Balance(db, accountId));
        var evt = Assert.Single(bus.Events.OfType<CardPaymentAuthorised>());
        Assert.Equal(expectedRounded, evt.Amount);
    }

    [Theory]
    [InlineData(0)]
    [InlineData(-10)]
    [InlineData(0.004)] 
    public async Task AuthoriseAsync_rejects_amounts_less_than_or_equal_to_zero_after_rounding(decimal amount)
    {
        var (db, user, _, bus, service) = CreateSut("alice", Roles.Customer);
        var accountId = TestKit.Account(db, "alice", 500m);
        var card = await service.IssueAsync(accountId);
        bus.Events.Clear();

        user.UserId = "network";
        await Assert.ThrowsAnyAsync<Exception>(() => service.AuthoriseAsync(card.Id, amount, "Merchant"));

        Assert.Equal(500m, TestKit.Balance(db, accountId));
        Assert.Empty(bus.Events);
    }

    [Fact]
    public async Task AuthoriseAsync_declines_frozen_card_without_moving_funds()
    {
        var (db, user, clock, bus, service) = CreateSut("alice", Roles.Customer);
        var accountId = TestKit.Account(db, "alice", 500m);
        var card = await service.IssueAsync(accountId);
        await service.FreezeAsync(card.Id);
        bus.Events.Clear();

        user.UserId = "network";
        clock.Advance(TimeSpan.FromMinutes(2));
        var result = await service.AuthoriseAsync(card.Id, 25m, "Cafe");

        Assert.False(result.Approved);
        Assert.Equal("card not active", result.DeclineReason);
        Assert.Null(result.TransferId);
        Assert.Equal(500m, TestKit.Balance(db, accountId));

        var declined = Assert.Single(bus.Events.OfType<CardPaymentDeclined>());
        Assert.Equal(card.Id, declined.CardId);
        Assert.Equal("card not active", declined.Reason);
        Assert.Equal(clock.UtcNow, declined.OccurredAt);
        Assert.Empty(bus.Events.OfType<CardPaymentAuthorised>());
    }

    [Fact]
    public async Task AuthoriseAsync_declines_cancelled_card_without_moving_funds()
    {
        var (db, user, clock, bus, service) = CreateSut("alice", Roles.Customer);
        var accountId = TestKit.Account(db, "alice", 500m);
        var card = await service.IssueAsync(accountId);
        await service.CancelAsync(card.Id);
        bus.Events.Clear();

        user.UserId = "network";
        var result = await service.AuthoriseAsync(card.Id, 25m, "Cafe");

        Assert.False(result.Approved);
        Assert.Equal("card not active", result.DeclineReason);
        Assert.Null(result.TransferId);
        Assert.Equal(500m, TestKit.Balance(db, accountId));

        var declined = Assert.Single(bus.Events.OfType<CardPaymentDeclined>());
        Assert.Equal(card.Id, declined.CardId);
        Assert.Equal("card not active", declined.Reason);
        Assert.Equal(clock.UtcNow, declined.OccurredAt);
    }

    [Theory]
    [InlineData(2000.01)]
    [InlineData(2000.005)]
    public async Task AuthoriseAsync_declines_when_rounded_amount_exceeds_per_transaction_limit(decimal amount)
    {
        var (db, user, clock, bus, service) = CreateSut("alice", Roles.Customer);
        var accountId = TestKit.Account(db, "alice", 5000m);
        var card = await service.IssueAsync(accountId);
        bus.Events.Clear();

        user.UserId = "network";
        var result = await service.AuthoriseAsync(card.Id, amount, "Luxury Store");

        Assert.False(result.Approved);
        Assert.Equal("over limit", result.DeclineReason);
        Assert.Null(result.TransferId);
        Assert.Equal(5000m, TestKit.Balance(db, accountId));

        var declined = Assert.Single(bus.Events.OfType<CardPaymentDeclined>());
        Assert.Equal(card.Id, declined.CardId);
        Assert.Equal("over limit", declined.Reason);
        Assert.Equal(clock.UtcNow, declined.OccurredAt);
    }

    [Fact]
    public async Task AuthoriseAsync_declines_when_account_has_insufficient_funds()
    {
        var (db, user, clock, bus, service) = CreateSut("alice", Roles.Customer);
        var accountId = TestKit.Account(db, "alice", 100.00m);
        var card = await service.IssueAsync(accountId);
        bus.Events.Clear();

        user.UserId = "network";
        var result = await service.AuthoriseAsync(card.Id, 100.01m, "Grocery");

        Assert.False(result.Approved);
        Assert.Equal("insufficient funds", result.DeclineReason);
        Assert.Null(result.TransferId);
        Assert.Equal(100.00m, TestKit.Balance(db, accountId));

        var declined = Assert.Single(bus.Events.OfType<CardPaymentDeclined>());
        Assert.Equal(card.Id, declined.CardId);
        Assert.Equal("insufficient funds", declined.Reason);
        Assert.Equal(clock.UtcNow, declined.OccurredAt);
    }

    [Fact]
    public async Task Domain_events_and_audit_redaction_never_expose_full_card_number()
    {
        var (db, user, _, bus, service) = CreateSut("alice", Roles.Customer);
        var accountId = TestKit.Account(db, "alice", 500m);
        var card = await service.IssueAsync(accountId);

        user.UserId = "network";
        await service.AuthoriseAsync(card.Id, 50m, "Bookshop");

        foreach (var evt in bus.Events)
        {
            var redacted = AuditLog.Redact(evt);
            Assert.DoesNotContain(card.Number, redacted);
        }

        var issued = Assert.Single(bus.Events.OfType<CardIssued>());
        Assert.Contains(card.Last4, AuditLog.Redact(issued));
    }
}
