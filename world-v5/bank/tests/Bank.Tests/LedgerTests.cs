using Bank.Modules.Ledger.Application;
using Bank.Modules.Ledger.Domain;
using Xunit;

namespace Bank.Tests;

public sealed class LedgerTests
{
    [Fact]
    public async Task Transfer_moves_money_and_writes_two_balanced_entries()
    {
        using var db = TestKit.Db();
        var a = TestKit.Account(db, "alice", 100m);
        var b = TestKit.Account(db, "bob");

        await TestKit.Ledger(db).PostTransferAsync(a, b, 40m, "rent");

        Assert.Equal(60m, TestKit.Balance(db, a));
        Assert.Equal(40m, TestKit.Balance(db, b));
        var entries = db.LedgerEntries.Where(e => e.Reference == "rent").ToList();
        Assert.Equal(2, entries.Count);
        Assert.Equal(0m, entries.Sum(e => e.Amount));
    }

    [Fact]
    public async Task Customer_account_cannot_go_below_zero()
    {
        using var db = TestKit.Db();
        var a = TestKit.Account(db, "alice", 10m);
        var b = TestKit.Account(db, "bob");

        await Assert.ThrowsAsync<InsufficientFundsException>(() => TestKit.Ledger(db).PostTransferAsync(a, b, 10.01m, "too much"));
        Assert.Equal(10m, TestKit.Balance(db, a));
    }

    [Fact]
    public async Task Currencies_must_match()
    {
        using var db = TestKit.Db();
        var eur = TestKit.Account(db, "alice", 100m, "EUR");
        var sek = TestKit.Account(db, "alice", 0m, "SEK");

        await Assert.ThrowsAsync<CurrencyMismatchException>(() => TestKit.Ledger(db).PostTransferAsync(eur, sek, 5m, "x"));
    }

    [Fact]
    public async Task Bank_accounts_may_go_below_zero()
    {
        using var db = TestKit.Db();
        var a = TestKit.Account(db, "alice");

        await TestKit.Ledger(db).PostTransferAsync(BankAccounts.For(BankAccountKind.LoanFunding, "EUR"), a, 500m, "loan");

        Assert.Equal(-500m, TestKit.Balance(db, BankAccounts.For(BankAccountKind.LoanFunding, "EUR")));
    }

    [Fact]
    public async Task Entries_are_returned_for_a_period_oldest_first()
    {
        using var db = TestKit.Db();
        var clock = new FakeClock();
        var a = TestKit.Account(db, "alice", 100m);
        var b = TestKit.Account(db, "bob");
        var ledger = TestKit.Ledger(db, clock: clock);
        await ledger.PostTransferAsync(a, b, 1m, "first");
        clock.Advance(TimeSpan.FromDays(1));
        await ledger.PostTransferAsync(a, b, 2m, "second");

        var all = await ledger.EntriesAsync(a, clock.UtcNow.AddDays(-2), clock.UtcNow.AddSeconds(1));
        var lastDayOnly = await ledger.EntriesAsync(a, clock.UtcNow, clock.UtcNow.AddSeconds(1));

        Assert.Equal(new[] { "first", "second" }, all.Where(e => e.Reference != "test funding").Select(e => e.Reference));
        Assert.Single(lastDayOnly);
    }
}
