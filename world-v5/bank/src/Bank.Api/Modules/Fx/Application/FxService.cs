using Bank.Shared.Money;

namespace Bank.Modules.Fx.Application;

public interface IFxService
{
    decimal Rate(string fromCurrency, string toCurrency);
    decimal Convert(decimal amount, string fromCurrency, string toCurrency);
}

public sealed class FxService : IFxService
{
    private const decimal EurToSek = 11.50m;
    private const decimal EurToUsd = 1.08m;

    public decimal Rate(string fromCurrency, string toCurrency)
    {
        var from = NormalizeAndValidate(fromCurrency, nameof(fromCurrency));
        var to = NormalizeAndValidate(toCurrency, nameof(toCurrency));

        if (from == to)
            return 1m;

        if (from == "EUR")
            return FromEur(to);

        if (to == "EUR")
            return 1m / FromEur(from);

        return (1m / FromEur(from)) * FromEur(to);
    }

    public decimal Convert(decimal amount, string fromCurrency, string toCurrency)
    {
        var from = NormalizeAndValidate(fromCurrency, nameof(fromCurrency));
        var to = NormalizeAndValidate(toCurrency, nameof(toCurrency));

        var raw = (from, to) switch
        {
            _ when from == to => amount,
            ("EUR", _) => amount * FromEur(to),
            (_, "EUR") => amount / FromEur(from),
            _ => (amount / FromEur(from)) * FromEur(to),
        };

        return MoneyMath.ToCents(raw);
    }

    private static string NormalizeAndValidate(string currency, string paramName)
    {
        if (string.IsNullOrWhiteSpace(currency))
            throw new ArgumentException("Currency must not be null or empty.", paramName);

        var normalized = currency.ToUpperInvariant();
        if (normalized is not ("EUR" or "SEK" or "USD"))
            throw new ArgumentException($"Currency {currency} is not supported.", paramName);

        return normalized;
    }

    private static decimal FromEur(string currency) => currency switch
    {
        "SEK" => EurToSek,
        "USD" => EurToUsd,
        _ => throw new ArgumentException($"Currency {currency} is not supported.", nameof(currency)),
    };
}
