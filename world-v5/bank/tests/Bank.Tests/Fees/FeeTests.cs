using Bank.Modules.Fees.Application;
using Bank.Modules.Ledger.Domain;
using Bank.Modules.Payments.Application;
using Xunit;

namespace Bank.Tests.Fees;

public sealed class FeeTests
{
    [Fact]
    public void Fee_record_preserves_amount_and_currency_and_value_equality()
    {
        var a = new Fee(1.50m, "EUR");
        var b = new Fee(1.50m, "EUR");
        var c = new Fee(2.00m, "EUR");

        Assert.Equal(1.50m, a.Amount);
        Assert.Equal("EUR", a.Currency);
        Assert.Equal(a, b);
        Assert.NotEqual(a, c);
    }

    [Fact]
    public void Fee_record_allows_zero_fee_for_same_currency()
    {
        var fee = new Fee(0m, "SEK");

        Assert.Equal(0m, fee.Amount);
        Assert.Equal("SEK", fee.Currency);
    }

    [Fact]
    public void PaymentQuote_record_preserves_all_fields_and_value_equality()
    {
        var quote = new PaymentQuote(1000m, "EUR", 2.00m, 11400.00m, "SEK", 11.40m);
        var same = new PaymentQuote(1000m, "EUR", 2.00m, 11400.00m, "SEK", 11.40m);

        Assert.Equal(1000m, quote.Amount);
        Assert.Equal("EUR", quote.Currency);
        Assert.Equal(2.00m, quote.Fee);
        Assert.Equal(11400.00m, quote.CreditedAmount);
        Assert.Equal("SEK", quote.CreditedCurrency);
        Assert.Equal(11.40m, quote.Rate);
        Assert.Equal(quote, same);
    }

    [Theory]
    [InlineData("EUR")]
    [InlineData("SEK")]
    [InlineData("USD")]
    public async Task FeeIncome_account_exists_and_accepts_fee_transfers_in_payer_currency(string currency)
    {
        using var db = TestKit.Db();
        var payer = TestKit.Account(db, "alice", 100m, currency);
        var feeIncome = BankAccounts.For(BankAccountKind.FeeIncome, currency);

        await TestKit.Ledger(db).PostTransferAsync(payer, feeIncome, 2.50m, $"fee-{currency}");

        Assert.Equal(97.50m, TestKit.Balance(db, payer));
        Assert.Equal(2.50m, TestKit.Balance(db, feeIncome));
    }
}
