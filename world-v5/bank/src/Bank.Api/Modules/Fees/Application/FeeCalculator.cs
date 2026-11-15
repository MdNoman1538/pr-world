using Bank.Modules.Fx.Application;
using Bank.Shared.Money;

namespace Bank.Modules.Fees.Application;

public sealed class FeeCalculator(IFxService fx) : IFeeCalculator
{
    private const decimal FeeRate = 0.002m;
    private const decimal MinFeeEur = 0.50m;
    private const decimal MaxFeeEur = 20.00m;

    public Fee Quote(decimal amount, string fromCurrency, string toCurrency)
    {
        if (amount <= 0m)
            throw new ArgumentOutOfRangeException(nameof(amount), "Amount must be positive.");
        if (string.IsNullOrWhiteSpace(fromCurrency))
            throw new ArgumentException("Currency must not be null or empty.", nameof(fromCurrency));
        if (string.IsNullOrWhiteSpace(toCurrency))
            throw new ArgumentException("Currency must not be null or empty.", nameof(toCurrency));

        var from = fromCurrency.ToUpperInvariant();
        var to = toCurrency.ToUpperInvariant();

        if (from == to)
            return new Fee(0m, from);

        var rawFee = MoneyMath.ToCents(amount * FeeRate);
        var minFee = MoneyMath.ToCents(fx.Convert(MinFeeEur, "EUR", from));
        var maxFee = MoneyMath.ToCents(fx.Convert(MaxFeeEur, "EUR", from));
        var fee = Math.Clamp(rawFee, minFee, maxFee);

        return new Fee(fee, from);
    }
}
