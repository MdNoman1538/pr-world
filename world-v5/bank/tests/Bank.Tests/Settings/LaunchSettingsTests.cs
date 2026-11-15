using Bank.Modules.Accounts.Application;
using Bank.Modules.Accounts.Domain;
using Bank.Modules.Auth;
using Bank.Modules.Ledger.Application;
using Bank.Modules.Ledger.Domain;
using Bank.Shared.Settings;
using Microsoft.EntityFrameworkCore;
using Xunit;

namespace Bank.Tests.Settings;

public sealed class LaunchSettingsTests
{
    [Fact]
    public void BankSettings_defaults_to_SEK_currency_and_5000_daily_transfer_limit()
    {
        var settings = new BankSettings();

        Assert.Equal("SEK", settings.DefaultCurrency);
        Assert.Equal(5_000m, settings.DailyTransferLimit);
    }

    [Fact]
    public void BankSettings_supported_currencies_remain_EUR_SEK_and_USD()
    {
        var settings = new BankSettings();

        Assert.Equal(3, settings.SupportedCurrencies.Count);
        Assert.Contains("EUR", settings.SupportedCurrencies);
        Assert.Contains("SEK", settings.SupportedCurrencies);
        Assert.Contains("USD", settings.SupportedCurrencies);
    }

    [Fact]
    public async Task Customer_opening_account_without_currency_uses_default_SEK()
    {
        using var db = TestKit.Db();
        var user = new FakeUser("alice", Roles.Customer);
        var clock = new FakeClock();
        var bus = new RecordingBus();
        var service = new AccountService(db, user, new BankSettings(), clock, bus, Array.Empty<IAccountOpeningRule>());

        var created = await service.OpenAsync(null);

        Assert.Equal("SEK", created.Currency);
        Assert.Equal("alice", created.OwnerId);
        Assert.Equal(0m, created.Balance);
        Assert.Equal(AccountKind.Customer, created.Kind);
        Assert.Equal(clock.UtcNow, created.OpenedAt);

        db.ChangeTracker.Clear();
        var persisted = db.Accounts.AsNoTracking().Single(a => a.Id == created.Id);
        Assert.Equal("SEK", persisted.Currency);
        Assert.Equal("alice", persisted.OwnerId);
        Assert.Equal(0m, persisted.Balance);
        Assert.Single(bus.Events);
    }

    [Theory]
    [InlineData("EUR")]
    [InlineData("USD")]
    [InlineData("SEK")]
    public async Task Customer_opening_account_with_explicit_supported_currency_uses_requested_currency(string requestedCurrency)
    {
        using var db = TestKit.Db();
        var user = new FakeUser("alice", Roles.Customer);
        var service = new AccountService(db, user, new BankSettings(), new FakeClock(), new RecordingBus(), Array.Empty<IAccountOpeningRule>());

        var created = await service.OpenAsync(requestedCurrency);

        Assert.Equal(requestedCurrency, created.Currency);
        db.ChangeTracker.Clear();
        var persisted = db.Accounts.AsNoTracking().Single(a => a.Id == created.Id);
        Assert.Equal(requestedCurrency, persisted.Currency);
    }

    [Theory]
    [InlineData("GBP")]
    [InlineData("NOK")]
    public async Task Customer_opening_account_with_unsupported_currency_is_rejected(string unsupportedCurrency)
    {
        using var db = TestKit.Db();
        var user = new FakeUser("alice", Roles.Customer);
        var bus = new RecordingBus();
        var service = new AccountService(db, user, new BankSettings(), new FakeClock(), bus, Array.Empty<IAccountOpeningRule>());

        await Assert.ThrowsAnyAsync<Exception>(() => service.OpenAsync(unsupportedCurrency));

        Assert.Empty(db.Accounts.Where(a => a.OwnerId == "alice"));
        Assert.Empty(bus.Events);
    }

    [Fact]
    public async Task Existing_accounts_retain_currencies_and_balances_when_new_default_SEK_account_is_opened()
    {
        using var db = TestKit.Db();
        var eurAccountId = TestKit.Account(db, "alice", 250.50m, "EUR");
        var usdAccountId = TestKit.Account(db, "alice", 100.25m, "USD");
        var user = new FakeUser("alice", Roles.Customer);
        var service = new AccountService(db, user, new BankSettings(), new FakeClock(), new RecordingBus(), Array.Empty<IAccountOpeningRule>());

        var sekAccount = await service.OpenAsync(null);

        Assert.Equal("SEK", sekAccount.Currency);
        Assert.Equal(0m, TestKit.Balance(db, sekAccount.Id));
        Assert.Equal(250.50m, TestKit.Balance(db, eurAccountId));
        Assert.Equal(100.25m, TestKit.Balance(db, usdAccountId));

        db.ChangeTracker.Clear();
        var aliceAccounts = db.Accounts.AsNoTracking().Where(a => a.OwnerId == "alice").ToList();
        Assert.Equal(3, aliceAccounts.Count);
        Assert.Equal("EUR", aliceAccounts.Single(a => a.Id == eurAccountId).Currency);
        Assert.Equal("USD", aliceAccounts.Single(a => a.Id == usdAccountId).Currency);
        Assert.Equal("SEK", aliceAccounts.Single(a => a.Id == sekAccount.Id).Currency);
    }

    [Fact]
    public async Task Opening_rule_rejection_prevents_creating_default_SEK_account()
    {
        using var db = TestKit.Db();
        var user = new FakeUser("alice", Roles.Customer);
        var bus = new RecordingBus();
        var rules = new IAccountOpeningRule[] { new RejectingOpeningRule() };
        var service = new AccountService(db, user, new BankSettings(), new FakeClock(), bus, rules);

        await Assert.ThrowsAsync<InvalidOperationException>(() => service.OpenAsync(null));

        Assert.Empty(db.Accounts.Where(a => a.OwnerId == "alice"));
        Assert.Empty(bus.Events);
    }

    [Fact]
    public async Task New_default_SEK_account_is_owned_by_current_user_and_queries_match()
    {
        using var db = TestKit.Db();
        var user = new FakeUser("alice", Roles.Customer);
        var service = new AccountService(db, user, new BankSettings(), new FakeClock(), new RecordingBus(), Array.Empty<IAccountOpeningRule>());

        var created = await service.OpenAsync(null);

        Assert.True(await service.IsOwnerAsync(created.Id, "alice"));
        Assert.False(await service.IsOwnerAsync(created.Id, "bob"));
        var fetched = await service.GetAsync(created.Id);
        Assert.NotNull(fetched);
        Assert.Equal("SEK", fetched.Currency);
        var owned = await service.ForOwnerAsync("alice");
        Assert.Single(owned);
        Assert.Equal("SEK", owned[0].Currency);
    }

    [Fact]
    public async Task New_default_SEK_account_transacts_in_SEK_and_rejects_EUR_ledger_transfer()
    {
        using var db = TestKit.Db();
        var eurAccountId = TestKit.Account(db, "bob", 100m, "EUR");
        var user = new FakeUser("alice", Roles.Customer);
        var service = new AccountService(db, user, new BankSettings(), new FakeClock(), new RecordingBus(), Array.Empty<IAccountOpeningRule>());
        var sekAccount = await service.OpenAsync(null);
        var ledger = TestKit.Ledger(db);

        await ledger.PostTransferAsync(BankAccounts.For(BankAccountKind.Suspense, "SEK"), sekAccount.Id, 5_000m, "sek funding");

        Assert.Equal(5_000m, TestKit.Balance(db, sekAccount.Id));
        await Assert.ThrowsAsync<CurrencyMismatchException>(() => ledger.PostTransferAsync(eurAccountId, sekAccount.Id, 10m, "mismatch"));
        Assert.Equal(100m, TestKit.Balance(db, eurAccountId));
        Assert.Equal(5_000m, TestKit.Balance(db, sekAccount.Id));
    }

    private sealed class RejectingOpeningRule : IAccountOpeningRule
    {
        public Task EnsureMayOpenAsync(string ownerId, CancellationToken ct = default) =>
            throw new InvalidOperationException("Opening not permitted");
    }
}
