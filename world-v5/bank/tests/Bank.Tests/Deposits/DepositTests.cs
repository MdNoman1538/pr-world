using Bank.Data;
using Bank.Modules.Accounts.Application;
using Bank.Modules.Auth;
using Bank.Modules.Deposits.Application;
using Bank.Modules.Deposits.Domain;
using Bank.Modules.Ledger.Application;
using Bank.Modules.Ledger.Domain;
using Xunit;

namespace Bank.Tests.Deposits;

public sealed class DepositTests
{
    private static (FakeUser User, FakeClock Clock, RecordingBus Bus, IDepositService Service) CreateSut(
        BankDbContext db,
        string userId = "alice",
        params string[] roles)
    {
        var user = new FakeUser(userId, roles.Length > 0 ? roles : new[] { Roles.Customer });
        var clock = new FakeClock();
        var bus = new RecordingBus();
        var ledger = TestKit.Ledger(db, bus, clock);
        var accounts = new AccountService(db, user, TestKit.Settings(), clock, bus, Array.Empty<IAccountOpeningRule>());
        IDepositService service = new DepositService(db, ledger, accounts, user, clock, bus);
        return (user, clock, bus, service);
    }

    [Fact]
    public async Task Open_3_month_deposit_at_minimum_principal_sets_rate_moves_funds_and_publishes_event()
    {
        using var db = TestKit.Db();
        var (_, clock, bus, service) = CreateSut(db, "alice");
        var accountId = TestKit.Account(db, "alice", 1000m, "EUR");

        var deposit = await service.OpenAsync(accountId, 500m, 3);

        db.ChangeTracker.Clear();
        var saved = db.TermDeposits.Single(d => d.Id == deposit.Id);
        Assert.Equal("alice", saved.CustomerId);
        Assert.Equal(accountId, saved.AccountId);
        Assert.Equal(500m, saved.Principal);
        Assert.Equal("EUR", saved.Currency);
        Assert.Equal(3, saved.TermMonths);
        Assert.Equal(2.0m, saved.AnnualRatePercent);
        Assert.Equal(clock.UtcNow, saved.OpenedAt);
        Assert.Equal(clock.UtcNow.AddMonths(3), saved.MaturesAt);
        Assert.Equal(DepositStatus.Open, saved.Status);
        Assert.Equal(0m, saved.InterestPaid);

        Assert.Equal(500m, TestKit.Balance(db, accountId));
        Assert.Equal(500m, TestKit.Balance(db, BankAccounts.For(BankAccountKind.DepositHolding, "EUR")));

        var opened = Assert.Single(bus.Events.OfType<DepositOpened>());
        Assert.Equal(saved.Id, opened.DepositId);
        Assert.Equal("alice", opened.CustomerId);
        Assert.Equal(500m, opened.Principal);
        Assert.Equal(3, opened.TermMonths);
        Assert.Equal(clock.UtcNow, opened.OccurredAt);
    }

    [Theory]
    [InlineData(3, 2.0)]
    [InlineData(6, 2.5)]
    [InlineData(12, 3.0)]
    public async Task Open_maps_term_months_to_expected_annual_rate_and_maturity_date(int termMonths, decimal expectedRate)
    {
        using var db = TestKit.Db();
        var (_, clock, _, service) = CreateSut(db, "alice");
        var accountId = TestKit.Account(db, "alice", 2000m, "EUR");

        var deposit = await service.OpenAsync(accountId, 1000m, termMonths);

        Assert.Equal(expectedRate, deposit.AnnualRatePercent);
        Assert.Equal(clock.UtcNow.AddMonths(termMonths), deposit.MaturesAt);
    }

    [Theory]
    [InlineData(499.99)]
    [InlineData(0)]
    [InlineData(-100)]
    public async Task Open_rejects_principal_below_500(decimal principal)
    {
        using var db = TestKit.Db();
        var (_, _, bus, service) = CreateSut(db, "alice");
        var accountId = TestKit.Account(db, "alice", 1000m, "EUR");

        await Assert.ThrowsAsync<ArgumentException>(() => service.OpenAsync(accountId, principal, 3));

        Assert.Equal(1000m, TestKit.Balance(db, accountId));
        Assert.Empty(db.TermDeposits);
        Assert.Empty(bus.Events.OfType<DepositOpened>());
    }

    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    [InlineData(2)]
    [InlineData(4)]
    [InlineData(9)]
    [InlineData(13)]
    [InlineData(-6)]
    public async Task Open_rejects_unsupported_term_months(int termMonths)
    {
        using var db = TestKit.Db();
        var (_, _, bus, service) = CreateSut(db, "alice");
        var accountId = TestKit.Account(db, "alice", 1000m, "EUR");

        await Assert.ThrowsAsync<ArgumentException>(() => service.OpenAsync(accountId, 500m, termMonths));

        Assert.Equal(1000m, TestKit.Balance(db, accountId));
        Assert.Empty(db.TermDeposits);
        Assert.Empty(bus.Events.OfType<DepositOpened>());
    }

    [Fact]
    public async Task Open_by_non_owner_throws_UnauthorizedAccessException()
    {
        using var db = TestKit.Db();
        var (user, _, bus, service) = CreateSut(db, "alice");
        var alicesAccount = TestKit.Account(db, "alice", 1000m, "EUR");
        user.UserId = "bob";

        await Assert.ThrowsAsync<UnauthorizedAccessException>(() => service.OpenAsync(alicesAccount, 500m, 6));

        Assert.Equal(1000m, TestKit.Balance(db, alicesAccount));
        Assert.Empty(db.TermDeposits);
        Assert.Empty(bus.Events.OfType<DepositOpened>());
    }

    [Fact]
    public async Task Open_with_insufficient_funds_throws_and_does_not_create_deposit()
    {
        using var db = TestKit.Db();
        var (_, _, bus, service) = CreateSut(db, "alice");
        var accountId = TestKit.Account(db, "alice", 500m, "EUR");

        await Assert.ThrowsAsync<InsufficientFundsException>(() => service.OpenAsync(accountId, 500.01m, 3));

        Assert.Equal(500m, TestKit.Balance(db, accountId));
        Assert.Empty(db.TermDeposits);
        Assert.Empty(bus.Events.OfType<DepositOpened>());
    }

    [Theory]
    [InlineData(1005.00, 3, 5.03)]
    [InlineData(1002.00, 6, 12.53)]
    [InlineData(1001.00, 6, 12.51)]
    [InlineData(1000.00, 12, 30.00)]
    public async Task Mature_at_maturity_date_pays_principal_and_interest_rounded_half_away_from_zero(
        decimal principal,
        int termMonths,
        decimal expectedInterest)
    {
        using var db = TestKit.Db();
        var (user, clock, bus, service) = CreateSut(db, "alice");
        var initialBalance = 2000m;
        var accountId = TestKit.Account(db, "alice", initialBalance, "EUR");

        var deposit = await service.OpenAsync(accountId, principal, termMonths);

        clock.UtcNow = deposit.MaturesAt;
        user.UserId = "bank-maturity-job";

        var matured = await service.MatureAsync(deposit.Id);

        db.ChangeTracker.Clear();
        var saved = db.TermDeposits.Single(d => d.Id == deposit.Id);
        Assert.Equal(DepositStatus.Matured, matured.Status);
        Assert.Equal(DepositStatus.Matured, saved.Status);
        Assert.Equal(expectedInterest, saved.InterestPaid);

        Assert.Equal(initialBalance + expectedInterest, TestKit.Balance(db, accountId));
        Assert.Equal(0m, TestKit.Balance(db, BankAccounts.For(BankAccountKind.DepositHolding, "EUR")));
        Assert.Equal(-expectedInterest, TestKit.Balance(db, BankAccounts.For(BankAccountKind.InterestExpense, "EUR")));

        var closed = Assert.Single(bus.Events.OfType<DepositClosed>());
        Assert.Equal(saved.Id, closed.DepositId);
        Assert.Equal("alice", closed.CustomerId);
        Assert.Equal(expectedInterest, closed.InterestPaid);
        Assert.False(closed.Early);
        Assert.Equal(clock.UtcNow, closed.OccurredAt);
    }

    [Fact]
    public async Task Mature_succeeds_without_owner_check_when_called_by_different_user()
    {
        using var db = TestKit.Db();
        var (user, clock, _, service) = CreateSut(db, "alice");
        var accountId = TestKit.Account(db, "alice", 1000m, "EUR");
        var deposit = await service.OpenAsync(accountId, 1000m, 3);

        clock.UtcNow = deposit.MaturesAt;
        user.UserId = "teller-staff";

        var matured = await service.MatureAsync(deposit.Id);

        Assert.Equal(DepositStatus.Matured, matured.Status);
        Assert.Equal(5.00m, matured.InterestPaid);
    }

    [Fact]
    public async Task Mature_before_MaturesAt_throws_InvalidOperationException_and_leaves_balances_intact()
    {
        using var db = TestKit.Db();
        var (_, clock, bus, service) = CreateSut(db, "alice");
        var accountId = TestKit.Account(db, "alice", 1000m, "EUR");
        var deposit = await service.OpenAsync(accountId, 600m, 6);

        clock.UtcNow = deposit.MaturesAt.AddSeconds(-1);

        await Assert.ThrowsAsync<InvalidOperationException>(() => service.MatureAsync(deposit.Id));

        db.ChangeTracker.Clear();
        var saved = db.TermDeposits.Single(d => d.Id == deposit.Id);
        Assert.Equal(DepositStatus.Open, saved.Status);
        Assert.Equal(0m, saved.InterestPaid);
        Assert.Equal(400m, TestKit.Balance(db, accountId));
        Assert.Equal(600m, TestKit.Balance(db, BankAccounts.For(BankAccountKind.DepositHolding, "EUR")));
        Assert.Equal(0m, TestKit.Balance(db, BankAccounts.For(BankAccountKind.InterestExpense, "EUR")));
        Assert.Empty(bus.Events.OfType<DepositClosed>());
    }

    [Fact]
    public async Task Break_by_owner_returns_principal_only_with_zero_interest_and_publishes_early_closed_event()
    {
        using var db = TestKit.Db();
        var (_, clock, bus, service) = CreateSut(db, "alice");
        var accountId = TestKit.Account(db, "alice", 1500m, "EUR");
        var deposit = await service.OpenAsync(accountId, 1000m, 12);

        clock.Advance(TimeSpan.FromDays(30));

        var broken = await service.BreakAsync(deposit.Id);

        db.ChangeTracker.Clear();
        var saved = db.TermDeposits.Single(d => d.Id == deposit.Id);
        Assert.Equal(DepositStatus.BrokenEarly, broken.Status);
        Assert.Equal(DepositStatus.BrokenEarly, saved.Status);
        Assert.Equal(0m, saved.InterestPaid);

        Assert.Equal(1500m, TestKit.Balance(db, accountId));
        Assert.Equal(0m, TestKit.Balance(db, BankAccounts.For(BankAccountKind.DepositHolding, "EUR")));
        Assert.Equal(0m, TestKit.Balance(db, BankAccounts.For(BankAccountKind.InterestExpense, "EUR")));

        var closed = Assert.Single(bus.Events.OfType<DepositClosed>());
        Assert.Equal(saved.Id, closed.DepositId);
        Assert.Equal("alice", closed.CustomerId);
        Assert.Equal(0m, closed.InterestPaid);
        Assert.True(closed.Early);
        Assert.Equal(clock.UtcNow, closed.OccurredAt);
    }

    [Fact]
    public async Task Break_by_non_owner_throws_UnauthorizedAccessException()
    {
        using var db = TestKit.Db();
        var (user, _, bus, service) = CreateSut(db, "alice");
        var accountId = TestKit.Account(db, "alice", 1000m, "EUR");
        var deposit = await service.OpenAsync(accountId, 500m, 6);

        user.UserId = "bob";

        await Assert.ThrowsAsync<UnauthorizedAccessException>(() => service.BreakAsync(deposit.Id));

        db.ChangeTracker.Clear();
        var saved = db.TermDeposits.Single(d => d.Id == deposit.Id);
        Assert.Equal(DepositStatus.Open, saved.Status);
        Assert.Equal(500m, TestKit.Balance(db, accountId));
        Assert.Equal(500m, TestKit.Balance(db, BankAccounts.For(BankAccountKind.DepositHolding, "EUR")));
        Assert.Empty(bus.Events.OfType<DepositClosed>());
    }

    [Fact]
    public async Task Cannot_mature_or_break_an_already_matured_deposit()
    {
        using var db = TestKit.Db();
        var (_, clock, _, service) = CreateSut(db, "alice");
        var accountId = TestKit.Account(db, "alice", 1000m, "EUR");
        var deposit = await service.OpenAsync(accountId, 1000m, 3);

        clock.UtcNow = deposit.MaturesAt;
        await service.MatureAsync(deposit.Id);

        await Assert.ThrowsAsync<InvalidOperationException>(() => service.MatureAsync(deposit.Id));
        await Assert.ThrowsAsync<InvalidOperationException>(() => service.BreakAsync(deposit.Id));

        Assert.Equal(1005m, TestKit.Balance(db, accountId));
        Assert.Equal(0m, TestKit.Balance(db, BankAccounts.For(BankAccountKind.DepositHolding, "EUR")));
        Assert.Equal(-5m, TestKit.Balance(db, BankAccounts.For(BankAccountKind.InterestExpense, "EUR")));
    }

    [Fact]
    public async Task Cannot_break_or_mature_an_already_broken_deposit()
    {
        using var db = TestKit.Db();
        var (_, clock, _, service) = CreateSut(db, "alice");
        var accountId = TestKit.Account(db, "alice", 1000m, "EUR");
        var deposit = await service.OpenAsync(accountId, 1000m, 3);

        await service.BreakAsync(deposit.Id);
        clock.UtcNow = deposit.MaturesAt;

        await Assert.ThrowsAsync<InvalidOperationException>(() => service.BreakAsync(deposit.Id));
        await Assert.ThrowsAsync<InvalidOperationException>(() => service.MatureAsync(deposit.Id));

        Assert.Equal(1000m, TestKit.Balance(db, accountId));
        Assert.Equal(0m, TestKit.Balance(db, BankAccounts.For(BankAccountKind.DepositHolding, "EUR")));
        Assert.Equal(0m, TestKit.Balance(db, BankAccounts.For(BankAccountKind.InterestExpense, "EUR")));
    }

    [Fact]
    public async Task Multi_currency_deposit_uses_account_currency_for_holding_and_interest_expense()
    {
        using var db = TestKit.Db();
        var (_, clock, _, service) = CreateSut(db, "alice");
        var sekAccountId = TestKit.Account(db, "alice", 2000m, "SEK");

        var deposit = await service.OpenAsync(sekAccountId, 1000m, 12);

        Assert.Equal("SEK", deposit.Currency);
        Assert.Equal(1000m, TestKit.Balance(db, sekAccountId));
        Assert.Equal(1000m, TestKit.Balance(db, BankAccounts.For(BankAccountKind.DepositHolding, "SEK")));
        Assert.Equal(0m, TestKit.Balance(db, BankAccounts.For(BankAccountKind.DepositHolding, "EUR")));

        clock.UtcNow = deposit.MaturesAt;
        await service.MatureAsync(deposit.Id);

        Assert.Equal(2030m, TestKit.Balance(db, sekAccountId));
        Assert.Equal(0m, TestKit.Balance(db, BankAccounts.For(BankAccountKind.DepositHolding, "SEK")));
        Assert.Equal(-30m, TestKit.Balance(db, BankAccounts.For(BankAccountKind.InterestExpense, "SEK")));
        Assert.Equal(0m, TestKit.Balance(db, BankAccounts.For(BankAccountKind.InterestExpense, "EUR")));
    }
}
