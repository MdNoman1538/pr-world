namespace Bank.Shared.Settings;

/// <summary>Bank-wide business settings. Changing a value here changes behaviour for every customer.</summary>
public sealed class BankSettings
{
    /// <summary>Currency of a new account when the customer does not choose one.</summary>
    public string DefaultCurrency { get; init; } = "SEK";

    /// <summary>The currencies the bank holds accounts in.</summary>
    public IReadOnlyList<string> SupportedCurrencies { get; init; } = new[] { "EUR", "SEK", "USD" };

    /// <summary>Most a customer may send in outgoing payments per calendar day (UTC), in EUR equivalent.</summary>
    public decimal DailyTransferLimit { get; init; } = 5_000m;
}
