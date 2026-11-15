namespace Bank.Modules.Ledger.Domain;

/// <summary>What one of the bank's own accounts is for.</summary>
public enum BankAccountKind
{
    /// <summary>Pays out loans.</summary>
    LoanFunding = 1,
    /// <summary>Receives fees charged to customers.</summary>
    FeeIncome = 2,
    /// <summary>Middle account for currency exchange: money in one currency comes in, the other currency goes out.</summary>
    FxClearing = 3,
    /// <summary>Holds customers' money while it is locked in a term deposit.</summary>
    DepositHolding = 4,
    /// <summary>Pays interest to customers.</summary>
    InterestExpense = 5,
    /// <summary>Holds money that is waiting for a decision (e.g. a payment held for review).</summary>
    Suspense = 6,
}

/// <summary>The bank's own accounts: one per kind and currency. They may go below zero.</summary>
public static class BankAccounts
{
    public static readonly IReadOnlyList<string> Currencies = new[] { "EUR", "SEK", "USD" };

    public static Guid For(BankAccountKind kind, string currency)
    {
        var c = Array.IndexOf(Currencies.ToArray(), currency.ToUpperInvariant());
        if (c < 0)
            throw new ArgumentException($"The bank has no {currency} accounts.", nameof(currency));
        return Guid.Parse($"00000000-0000-0000-{(int)kind:D4}-{c + 1:D12}");
    }

    public static bool IsBankAccount(Guid accountId) => accountId.ToString().StartsWith("00000000-0000-0000-");
}
