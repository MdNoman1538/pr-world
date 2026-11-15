using Bank.Modules.Fx.Application;
using Bank.Modules.Ledger.Domain;
using Xunit;

namespace Bank.Tests.Fx;

public sealed class FxTests
{
    [Theory]
    [InlineData("EUR")]
    [InlineData("SEK")]
    [InlineData("USD")]
    public void Rate_returns_1_for_identical_supported_currencies(string currency)
    {
        IFxService fx = new FxService();

        var rate = fx.Rate(currency, currency);

        Assert.Equal(1m, rate);
    }

    [Fact]
    public void Rate_returns_fixed_base_rates_for_eur_pairs()
    {
        IFxService fx = new FxService();

        Assert.Equal(11.50m, fx.Rate("EUR", "SEK"));
        Assert.Equal(1.08m, fx.Rate("EUR", "USD"));
    }

    [Fact]
    public void Rate_returns_inverse_rates_for_pairs_to_eur()
    {
        IFxService fx = new FxService();

        Assert.Equal(1m / 11.50m, fx.Rate("SEK", "EUR"), 18);
        Assert.Equal(1m / 1.08m, fx.Rate("USD", "EUR"), 18);
    }

    [Fact]
    public void Rate_triangulates_cross_pairs_through_eur()
    {
        IFxService fx = new FxService();

        Assert.Equal((1m / 11.50m) * 1.08m, fx.Rate("SEK", "USD"), 18);
        Assert.Equal((1m / 1.08m) * 11.50m, fx.Rate("USD", "SEK"), 18);
    }

    [Theory]
    [InlineData("GBP", "EUR")]
    [InlineData("EUR", "GBP")]
    [InlineData("GBP", "GBP")]
    [InlineData("NOK", "USD")]
    [InlineData("", "EUR")]
    [InlineData("EUR", "")]
    [InlineData("   ", "USD")]
    [InlineData("USD", "   ")]
    [InlineData(null, "EUR")]
    [InlineData("EUR", null)]
    [InlineData(null, null)]
    public void Rate_throws_argument_exception_for_invalid_or_unknown_currencies(string? fromCurrency, string? toCurrency)
    {
        IFxService fx = new FxService();

        Assert.ThrowsAny<ArgumentException>(() => fx.Rate(fromCurrency!, toCurrency!));
    }

    [Theory]
    [InlineData(100.00, "EUR", 100.00)]
    [InlineData(123.45, "SEK", 123.45)]
    [InlineData(0.01, "USD", 0.01)]
    [InlineData(0.00, "EUR", 0.00)]
    public void Convert_returns_same_amount_for_identical_supported_currencies(double amount, string currency, double expected)
    {
        IFxService fx = new FxService();

        var converted = fx.Convert((decimal)amount, currency, currency);

        Assert.Equal((decimal)expected, converted);
    }

    [Theory]
    [InlineData(100, "EUR", "SEK", 1150.00)]
    [InlineData(1, "EUR", "SEK", 11.50)]
    [InlineData(100, "EUR", "USD", 108.00)]
    [InlineData(1, "EUR", "USD", 1.08)]
    [InlineData(1150, "SEK", "EUR", 100.00)]
    [InlineData(100, "SEK", "EUR", 8.70)]
    [InlineData(108, "USD", "EUR", 100.00)]
    [InlineData(100, "USD", "EUR", 92.59)]
    [InlineData(10, "USD", "EUR", 9.26)]
    public void Convert_handles_direct_and_inverse_eur_pairs(double amount, string fromCurrency, string toCurrency, double expected)
    {
        IFxService fx = new FxService();

        var converted = fx.Convert((decimal)amount, fromCurrency, toCurrency);

        Assert.Equal((decimal)expected, converted);
    }

    [Theory]
    [InlineData(1150, "SEK", "USD", 108.00)]
    [InlineData(11.50, "SEK", "USD", 1.08)]
    [InlineData(108, "USD", "SEK", 1150.00)]
    [InlineData(1.08, "USD", "SEK", 11.50)]
    [InlineData(100, "SEK", "USD", 9.39)]
    [InlineData(100, "USD", "SEK", 1064.81)]
    [InlineData(0, "SEK", "USD", 0.00)]
    public void Convert_triangulates_sek_and_usd_without_intermediate_rounding(double amount, string fromCurrency, string toCurrency, double expected)
    {
        IFxService fx = new FxService();

        var converted = fx.Convert((decimal)amount, fromCurrency, toCurrency);

        Assert.Equal((decimal)expected, converted);
    }

    [Fact]
    public void Convert_rounds_half_away_from_zero_to_two_decimal_places()
    {
        IFxService fx = new FxService();

        Assert.Equal(11.85m, fx.Convert(1.03m, "EUR", "SEK"));
        Assert.Equal(0.35m, fx.Convert(0.03m, "EUR", "SEK"));
        Assert.Equal(0.41m, fx.Convert(0.375m, "EUR", "USD"));
        Assert.Equal(0.03m, fx.Convert(0.027m, "USD", "EUR"));
        Assert.Equal(0.23m, fx.Convert(0.243m, "USD", "EUR"));
        Assert.Equal(10.01m, fx.Convert(10.005m, "EUR", "EUR"));
    }

    [Theory]
    [InlineData("GBP", "EUR")]
    [InlineData("EUR", "GBP")]
    [InlineData("GBP", "GBP")]
    [InlineData("", "USD")]
    [InlineData("SEK", "")]
    [InlineData("   ", "EUR")]
    [InlineData(null, "EUR")]
    [InlineData("USD", null)]
    public void Convert_throws_argument_exception_for_invalid_or_unknown_currencies(string? fromCurrency, string? toCurrency)
    {
        IFxService fx = new FxService();

        Assert.ThrowsAny<ArgumentException>(() => fx.Convert(100m, fromCurrency!, toCurrency!));
    }

    [Fact]
    public async Task FxClearing_accounts_exist_for_eur_sek_and_usd_and_settle_cross_currency_ledger_legs()
    {
        using var db = TestKit.Db();
        IFxService fx = new FxService();
        var ledger = TestKit.Ledger(db);
        var aliceEur = TestKit.Account(db, "alice", 100m, "EUR");
        var bobSek = TestKit.Account(db, "bob", 0m, "SEK");
        var carolUsd = TestKit.Account(db, "carol", 0m, "USD");

        var sekAmount = fx.Convert(100m, "EUR", "SEK");
        await ledger.PostTransferAsync(aliceEur, BankAccounts.For(BankAccountKind.FxClearing, "EUR"), 100m, "fx-debit");
        await ledger.PostTransferAsync(BankAccounts.For(BankAccountKind.FxClearing, "SEK"), bobSek, sekAmount, "fx-credit");

        var usdAmount = fx.Convert(100m, "SEK", "USD");
        await ledger.PostTransferAsync(bobSek, BankAccounts.For(BankAccountKind.FxClearing, "SEK"), 100m, "fx-debit-2");
        await ledger.PostTransferAsync(BankAccounts.For(BankAccountKind.FxClearing, "USD"), carolUsd, usdAmount, "fx-credit-2");

        Assert.Equal(0m, TestKit.Balance(db, aliceEur));
        Assert.Equal(1050.00m, TestKit.Balance(db, bobSek));
        Assert.Equal(9.39m, TestKit.Balance(db, carolUsd));
        Assert.Equal(100m, TestKit.Balance(db, BankAccounts.For(BankAccountKind.FxClearing, "EUR")));
        Assert.Equal(-1050.00m, TestKit.Balance(db, BankAccounts.For(BankAccountKind.FxClearing, "SEK")));
        Assert.Equal(-9.39m, TestKit.Balance(db, BankAccounts.For(BankAccountKind.FxClearing, "USD")));
    }
}
