using Bank.Shared;

namespace Bank.Modules.Accounts.Domain;

public enum AccountKind
{
    Customer,
    Internal,
}

/// <summary>A money account. The balance changes only through the Ledger.</summary>
public sealed class Account
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public string OwnerId { get; set; } = "";
    [Pii] public string Iban { get; set; } = "";
    public string Currency { get; set; } = "EUR";
    public decimal Balance { get; set; }
    public AccountKind Kind { get; set; } = AccountKind.Customer;
    /// <summary>Only the bank's own accounts may go below zero.</summary>
    public bool AllowOverdraft { get; set; }
    public DateTimeOffset OpenedAt { get; set; }
}

public sealed record AccountOpened(Guid AccountId, string OwnerId, string Currency, DateTimeOffset OccurredAt) : Bank.Shared.Events.IDomainEvent;
