using Bank.Data;
using Bank.Modules.Accounts.Application;
using Bank.Modules.Auth;
using Bank.Modules.Auth.Application;
using Bank.Modules.Ledger.Domain;
using Bank.Modules.Statements.Application;
using Bank.Shared.Events;
using Bank.Shared.Time;
using Bank.Tests;
using Xunit;

namespace Bank.Tests.Statements;

public sealed class StatementTests
{
    private static StatementService CreateService(
        BankDbContext db,
        ICurrentUser user,
        IClock? clock = null,
        IEventBus? bus = null)
    {
        var effectiveClock = clock ?? new FakeClock();
        var effectiveBus = bus ?? new RecordingBus();
        var ledger = TestKit.Ledger(db, effectiveBus, effectiveClock);
        var accounts = new AccountService(
            db,
            user,
            TestKit.Settings(),
            effectiveClock,
            effectiveBus,
            Array.Empty<IAccountOpeningRule>());
        return new StatementService(ledger, accounts, user);
    }

    [Fact]
    public async Task Owner_can_retrieve_statement_with_opening_lines_and_closing_balance()
    {
        using var db = TestKit.Db();
        var clock = new FakeClock();
        var ledger = TestKit.Ledger(db, clock: clock);
        var aliceId = TestKit.Account(db, "alice");
        var bobId = TestKit.Account(db, "bob");
        var suspense = BankAccounts.For(BankAccountKind.Suspense, "EUR");

        clock.UtcNow = new DateTimeOffset(2026, 1, 15, 12, 0, 0, TimeSpan.Zero);
        await ledger.PostTransferAsync(suspense, aliceId, 1000.00m, "jan deposit");
        clock.UtcNow = new DateTimeOffset(2026, 1, 31, 23, 59, 59, TimeSpan.Zero);
        await ledger.PostTransferAsync(aliceId, bobId, 100.25m, "jan payment");

        clock.UtcNow = new DateTimeOffset(2026, 2, 5, 9, 0, 0, TimeSpan.Zero);
        await ledger.PostTransferAsync(suspense, aliceId, 200.50m, "feb salary");
        clock.UtcNow = new DateTimeOffset(2026, 2, 14, 15, 30, 0, TimeSpan.Zero);
        await ledger.PostTransferAsync(aliceId, bobId, 50.10m, "feb gift");

        clock.UtcNow = new DateTimeOffset(2026, 3, 2, 8, 0, 0, TimeSpan.Zero);
        await ledger.PostTransferAsync(suspense, aliceId, 500.00m, "mar bonus");

        var service = CreateService(db, new FakeUser("alice", Roles.Customer), clock);
        var statement = await service.ForMonthAsync(aliceId, 2026, 2);

        Assert.Equal(aliceId, statement.AccountId);
        Assert.Equal(2026, statement.Year);
        Assert.Equal(2, statement.Month);
        Assert.Equal("EUR", statement.Currency);
        Assert.Equal(899.75m, statement.OpeningBalance);
        Assert.Equal(1050.15m, statement.ClosingBalance);
        Assert.Equal(2, statement.Lines.Count);

        Assert.Equal(new DateTimeOffset(2026, 2, 5, 9, 0, 0, TimeSpan.Zero), statement.Lines[0].At);
        Assert.Equal(200.50m, statement.Lines[0].Amount);
        Assert.Equal(1100.25m, statement.Lines[0].BalanceAfter);
        Assert.Equal("feb salary", statement.Lines[0].Reference);

        Assert.Equal(new DateTimeOffset(2026, 2, 14, 15, 30, 0, TimeSpan.Zero), statement.Lines[1].At);
        Assert.Equal(-50.10m, statement.Lines[1].Amount);
        Assert.Equal(1050.15m, statement.Lines[1].BalanceAfter);
        Assert.Equal("feb gift", statement.Lines[1].Reference);
    }

    [Fact]
    public async Task Month_boundaries_are_strictly_utc_inclusive_start_and_exclusive_end()
    {
        using var db = TestKit.Db();
        var clock = new FakeClock();
        var ledger = TestKit.Ledger(db, clock: clock);
        var aliceId = TestKit.Account(db, "alice");
        var suspense = BankAccounts.For(BankAccountKind.Suspense, "EUR");

        clock.UtcNow = new DateTimeOffset(2026, 1, 31, 23, 59, 59, TimeSpan.Zero);
        await ledger.PostTransferAsync(suspense, aliceId, 10m, "jan-last-second");

        clock.UtcNow = new DateTimeOffset(2026, 2, 1, 0, 0, 0, TimeSpan.Zero);
        await ledger.PostTransferAsync(suspense, aliceId, 20m, "feb-exact-start");

        clock.UtcNow = new DateTimeOffset(2026, 2, 28, 23, 59, 59, TimeSpan.Zero);
        await ledger.PostTransferAsync(suspense, aliceId, 30m, "feb-last-second");

        clock.UtcNow = new DateTimeOffset(2026, 3, 1, 0, 0, 0, TimeSpan.Zero);
        await ledger.PostTransferAsync(suspense, aliceId, 40m, "mar-exact-start");

        var service = CreateService(db, new FakeUser("alice", Roles.Customer), clock);

        var jan = await service.ForMonthAsync(aliceId, 2026, 1);
        Assert.Equal(0m, jan.OpeningBalance);
        Assert.Equal(10m, jan.ClosingBalance);
        Assert.Equal(new[] { "jan-last-second" }, jan.Lines.Select(l => l.Reference));

        var feb = await service.ForMonthAsync(aliceId, 2026, 2);
        Assert.Equal(10m, feb.OpeningBalance);
        Assert.Equal(60m, feb.ClosingBalance);
        Assert.Equal(new[] { "feb-exact-start", "feb-last-second" }, feb.Lines.Select(l => l.Reference));

        var mar = await service.ForMonthAsync(aliceId, 2026, 3);
        Assert.Equal(60m, mar.OpeningBalance);
        Assert.Equal(100m, mar.ClosingBalance);
        Assert.Equal(new[] { "mar-exact-start" }, mar.Lines.Select(l => l.Reference));
    }

    [Fact]
    public async Task Year_rollover_december_to_january_respects_utc_boundaries()
    {
        using var db = TestKit.Db();
        var clock = new FakeClock();
        var ledger = TestKit.Ledger(db, clock: clock);
        var aliceId = TestKit.Account(db, "alice");
        var suspense = BankAccounts.For(BankAccountKind.Suspense, "EUR");

        clock.UtcNow = new DateTimeOffset(2025, 12, 31, 23, 59, 59, TimeSpan.Zero);
        await ledger.PostTransferAsync(suspense, aliceId, 100m, "dec-31");

        clock.UtcNow = new DateTimeOffset(2026, 1, 1, 0, 0, 0, TimeSpan.Zero);
        await ledger.PostTransferAsync(suspense, aliceId, 50m, "jan-1");

        var service = CreateService(db, new FakeUser("alice", Roles.Customer), clock);

        var dec = await service.ForMonthAsync(aliceId, 2025, 12);
        Assert.Equal(0m, dec.OpeningBalance);
        Assert.Equal(100m, dec.ClosingBalance);
        Assert.Equal(new[] { "dec-31" }, dec.Lines.Select(l => l.Reference));

        var jan = await service.ForMonthAsync(aliceId, 2026, 1);
        Assert.Equal(100m, jan.OpeningBalance);
        Assert.Equal(150m, jan.ClosingBalance);
        Assert.Equal(new[] { "jan-1" }, jan.Lines.Select(l => l.Reference));
    }

    [Fact]
    public async Task Leap_year_february_includes_feb_29_and_excludes_mar_1()
    {
        using var db = TestKit.Db();
        var clock = new FakeClock();
        var ledger = TestKit.Ledger(db, clock: clock);
        var aliceId = TestKit.Account(db, "alice");
        var suspense = BankAccounts.For(BankAccountKind.Suspense, "EUR");

        clock.UtcNow = new DateTimeOffset(2024, 2, 29, 23, 59, 59, TimeSpan.Zero);
        await ledger.PostTransferAsync(suspense, aliceId, 75m, "leap-day");

        clock.UtcNow = new DateTimeOffset(2024, 3, 1, 0, 0, 0, TimeSpan.Zero);
        await ledger.PostTransferAsync(suspense, aliceId, 25m, "mar-1");

        var service = CreateService(db, new FakeUser("alice", Roles.Customer), clock);
        var feb = await service.ForMonthAsync(aliceId, 2024, 2);

        Assert.Equal(0m, feb.OpeningBalance);
        Assert.Equal(75m, feb.ClosingBalance);
        Assert.Equal(new[] { "leap-day" }, feb.Lines.Select(l => l.Reference));
    }

    [Fact]
    public async Task Empty_month_returns_empty_lines_and_closing_balance_equals_opening_balance()
    {
        using var db = TestKit.Db();
        var clock = new FakeClock();
        var ledger = TestKit.Ledger(db, clock: clock);
        var aliceId = TestKit.Account(db, "alice");
        var suspense = BankAccounts.For(BankAccountKind.Suspense, "EUR");

        clock.UtcNow = new DateTimeOffset(2026, 1, 10, 12, 0, 0, TimeSpan.Zero);
        await ledger.PostTransferAsync(suspense, aliceId, 250.00m, "jan");

        clock.UtcNow = new DateTimeOffset(2026, 3, 10, 12, 0, 0, TimeSpan.Zero);
        await ledger.PostTransferAsync(suspense, aliceId, 50.00m, "mar");

        var service = CreateService(db, new FakeUser("alice", Roles.Customer), clock);

        var beforeAny = await service.ForMonthAsync(aliceId, 2025, 12);
        Assert.Empty(beforeAny.Lines);
        Assert.Equal(0m, beforeAny.OpeningBalance);
        Assert.Equal(0m, beforeAny.ClosingBalance);

        var emptyFeb = await service.ForMonthAsync(aliceId, 2026, 2);
        Assert.Empty(emptyFeb.Lines);
        Assert.Equal(250.00m, emptyFeb.OpeningBalance);
        Assert.Equal(250.00m, emptyFeb.ClosingBalance);
    }

    [Fact]
    public async Task Statement_currency_matches_account_currency()
    {
        using var db = TestKit.Db();
        var clock = new FakeClock();
        var ledger = TestKit.Ledger(db, clock: clock);
        var sekId = TestKit.Account(db, "alice", currency: "SEK");
        var suspenseSek = BankAccounts.For(BankAccountKind.Suspense, "SEK");

        clock.UtcNow = new DateTimeOffset(2026, 3, 5, 12, 0, 0, TimeSpan.Zero);
        await ledger.PostTransferAsync(suspenseSek, sekId, 300.00m, "sek funding");

        var service = CreateService(db, new FakeUser("alice", Roles.Customer), clock);
        var statement = await service.ForMonthAsync(sekId, 2026, 3);

        Assert.Equal("SEK", statement.Currency);
        Assert.Equal(300.00m, statement.ClosingBalance);
    }

    [Fact]
    public async Task Lines_are_ordered_chronologically_and_balance_after_tracks_running_total()
    {
        using var db = TestKit.Db();
        var clock = new FakeClock();
        var ledger = TestKit.Ledger(db, clock: clock);
        var aliceId = TestKit.Account(db, "alice");
        var bobId = TestKit.Account(db, "bob");
        var suspense = BankAccounts.For(BankAccountKind.Suspense, "EUR");

        clock.UtcNow = new DateTimeOffset(2026, 3, 10, 10, 0, 0, TimeSpan.Zero);
        await ledger.PostTransferAsync(suspense, aliceId, 100.00m, "first");
        await ledger.PostTransferAsync(aliceId, bobId, 30.00m, "second");

        clock.UtcNow = new DateTimeOffset(2026, 3, 10, 10, 0, 1, TimeSpan.Zero);
        await ledger.PostTransferAsync(suspense, aliceId, 15.55m, "third");

        var service = CreateService(db, new FakeUser("alice", Roles.Customer), clock);
        var statement = await service.ForMonthAsync(aliceId, 2026, 3);

        Assert.Equal(3, statement.Lines.Count);
        var running = statement.OpeningBalance;
        DateTimeOffset? previousAt = null;
        foreach (var line in statement.Lines)
        {
            if (previousAt is not null)
                Assert.True(line.At >= previousAt.Value);
            running = Math.Round(running + line.Amount, 2, MidpointRounding.AwayFromZero);
            Assert.Equal(running, line.BalanceAfter);
            previousAt = line.At;
        }

        Assert.Equal(85.55m, statement.ClosingBalance);
        Assert.Equal(statement.ClosingBalance, statement.Lines[^1].BalanceAfter);
    }

    [Fact]
    public async Task Entries_from_other_accounts_are_isolated()
    {
        using var db = TestKit.Db();
        var clock = new FakeClock();
        var ledger = TestKit.Ledger(db, clock: clock);
        var checking = TestKit.Account(db, "alice");
        var savings = TestKit.Account(db, "alice");
        var suspense = BankAccounts.For(BankAccountKind.Suspense, "EUR");

        clock.UtcNow = new DateTimeOffset(2026, 3, 4, 12, 0, 0, TimeSpan.Zero);
        await ledger.PostTransferAsync(suspense, checking, 200m, "fund checking");
        await ledger.PostTransferAsync(suspense, savings, 900m, "fund savings");
        await ledger.PostTransferAsync(checking, savings, 50m, "to savings");

        var service = CreateService(db, new FakeUser("alice", Roles.Customer), clock);

        var checkingStmt = await service.ForMonthAsync(checking, 2026, 3);
        Assert.Equal(150m, checkingStmt.ClosingBalance);
        Assert.Equal(new[] { "fund checking", "to savings" }, checkingStmt.Lines.Select(l => l.Reference));

        var savingsStmt = await service.ForMonthAsync(savings, 2026, 3);
        Assert.Equal(950m, savingsStmt.ClosingBalance);
        Assert.Equal(new[] { "fund savings", "to savings" }, savingsStmt.Lines.Select(l => l.Reference));
    }

    [Theory]
    [InlineData(Roles.Teller)]
    [InlineData(Roles.LoanOfficer)]
    [InlineData(Roles.ComplianceOfficer)]
    [InlineData(Roles.Admin)]
    public async Task Staff_roles_can_read_any_customer_statement(string staffRole)
    {
        using var db = TestKit.Db();
        var clock = new FakeClock();
        var ledger = TestKit.Ledger(db, clock: clock);
        var aliceId = TestKit.Account(db, "alice");
        var suspense = BankAccounts.For(BankAccountKind.Suspense, "EUR");

        clock.UtcNow = new DateTimeOffset(2026, 3, 12, 10, 0, 0, TimeSpan.Zero);
        await ledger.PostTransferAsync(suspense, aliceId, 42m, "deposit");

        var staffService = CreateService(db, new FakeUser("staff-1", staffRole), clock);
        var statement = await staffService.ForMonthAsync(aliceId, 2026, 3);

        Assert.Equal(aliceId, statement.AccountId);
        Assert.Equal(42m, statement.ClosingBalance);
    }

    [Theory]
    [InlineData(Roles.Customer)]
    [InlineData("")]
    [InlineData("auditor")]
    public async Task Non_owner_customer_and_unauthorized_users_are_rejected(string role)
    {
        using var db = TestKit.Db();
        var aliceId = TestKit.Account(db, "alice", 100m);
        var otherUser = string.IsNullOrEmpty(role)
            ? new FakeUser("bob")
            : new FakeUser("bob", role);

        var service = CreateService(db, otherUser);

        await Assert.ThrowsAsync<UnauthorizedAccessException>(() => service.ForMonthAsync(aliceId, 2026, 3));
    }

    [Theory]
    [InlineData(Roles.Customer)]
    [InlineData(Roles.Admin)]
    public async Task Unknown_account_throws_KeyNotFoundException(string role)
    {
        using var db = TestKit.Db();
        var service = CreateService(db, new FakeUser("user-1", role));

        await Assert.ThrowsAsync<KeyNotFoundException>(() => service.ForMonthAsync(Guid.NewGuid(), 2026, 3));
    }

    [Theory]
    [InlineData(2026, 0)]
    [InlineData(2026, -1)]
    [InlineData(2026, 13)]
    [InlineData(0, 1)]
    [InlineData(-1, 6)]
    [InlineData(10000, 1)]
    public async Task Invalid_year_or_month_throws_ArgumentOutOfRangeException(int year, int month)
    {
        using var db = TestKit.Db();
        var aliceId = TestKit.Account(db, "alice", 100m);
        var service = CreateService(db, new FakeUser("alice", Roles.Customer));

        await Assert.ThrowsAsync<ArgumentOutOfRangeException>(() => service.ForMonthAsync(aliceId, year, month));
    }

    [Fact]
    public async Task Generating_statement_is_read_only_and_emits_no_events_or_ledger_entries()
    {
        using var db = TestKit.Db();
        var clock = new FakeClock();
        var bus = new RecordingBus();
        var ledger = TestKit.Ledger(db, bus, clock);
        var aliceId = TestKit.Account(db, "alice");
        var suspense = BankAccounts.For(BankAccountKind.Suspense, "EUR");

        clock.UtcNow = new DateTimeOffset(2026, 3, 15, 10, 0, 0, TimeSpan.Zero);
        await ledger.PostTransferAsync(suspense, aliceId, 123.45m, "deposit");

        var balanceBefore = TestKit.Balance(db, aliceId);
        var entryCountBefore = db.LedgerEntries.Count();
        var eventCountBefore = bus.Events.Count;

        var service = CreateService(db, new FakeUser("alice", Roles.Customer), clock, bus);
        var statement = await service.ForMonthAsync(aliceId, 2026, 3);

        Assert.Equal(123.45m, statement.ClosingBalance);
        Assert.Equal(balanceBefore, TestKit.Balance(db, aliceId));
        Assert.Equal(entryCountBefore, db.LedgerEntries.Count());
        Assert.Equal(eventCountBefore, bus.Events.Count);
    }
}
