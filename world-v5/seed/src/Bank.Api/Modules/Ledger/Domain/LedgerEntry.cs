namespace Bank.Modules.Ledger.Domain;

/// <summary>One side of a double-entry posting. A transfer always writes two entries that sum to zero.</summary>
public sealed class LedgerEntry
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public Guid TransferId { get; set; }
    public Guid AccountId { get; set; }
    /// <summary>Negative = money out of the account, positive = money in.</summary>
    public decimal Amount { get; set; }
    public string Currency { get; set; } = "EUR";
    /// <summary>The account balance right after this entry.</summary>
    public decimal BalanceAfter { get; set; }
    public string Reference { get; set; } = "";
    public DateTimeOffset CreatedAt { get; set; }
}
