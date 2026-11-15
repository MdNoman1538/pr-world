using Bank.Modules.Accounts.Application;
using Bank.Modules.Accounts.Domain;
using Xunit;

namespace Bank.Tests;

public sealed class AccountsTests
{
    [Fact]
    public async Task New_account_uses_the_default_currency_and_belongs_to_the_caller()
    {
        using var db = TestKit.Db();
        var bus = new RecordingBus();
        var service = new AccountService(db, new FakeUser("alice"), TestKit.Settings(), new FakeClock(), bus, Array.Empty<IAccountOpeningRule>());

        var account = await service.OpenAsync(null);

        Assert.Equal("EUR", account.Currency);
        Assert.Equal("alice", account.OwnerId);
        Assert.IsType<AccountOpened>(Assert.Single(bus.Events));
    }

    [Fact]
    public async Task Unsupported_currency_is_refused()
    {
        using var db = TestKit.Db();
        var service = new AccountService(db, new FakeUser("alice"), TestKit.Settings(), new FakeClock(), new RecordingBus(), Array.Empty<IAccountOpeningRule>());

        await Assert.ThrowsAsync<ArgumentException>(() => service.OpenAsync("JPY"));
    }
}
