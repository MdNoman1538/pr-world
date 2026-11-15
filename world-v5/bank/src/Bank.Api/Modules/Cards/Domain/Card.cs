using Bank.Shared;
using Bank.Shared.Events;

namespace Bank.Modules.Cards.Domain;

public enum CardStatus
{
    Active,
    Frozen,
    Cancelled,
}

public sealed class Card
{
    public Card()
    {
    }

    public Guid Id { get; set; } = Guid.NewGuid();
    public Guid AccountId { get; set; }
    public string CustomerId { get; set; } = "";
    [Pii] public string Number { get; set; } = "";
    public string Last4 { get; set; } = "";
    public CardStatus Status { get; private set; } = CardStatus.Active;
    public decimal PerTransactionLimit { get; set; } = 2000m;

    public void Freeze()
    {
        if (Status == CardStatus.Cancelled)
            throw new InvalidOperationException("Cancelled card cannot be frozen.");
        Status = CardStatus.Frozen;
    }

    public void Unfreeze()
    {
        if (Status == CardStatus.Cancelled)
            throw new InvalidOperationException("Cancelled card cannot be unfrozen.");
        Status = CardStatus.Active;
    }

    public void Cancel()
    {
        if (Status == CardStatus.Cancelled)
            throw new InvalidOperationException("Card is already cancelled.");
        Status = CardStatus.Cancelled;
    }
}

public sealed record CardIssued(Guid CardId, string CustomerId, string Last4, DateTimeOffset OccurredAt) : IDomainEvent;

public sealed record CardPaymentAuthorised(Guid CardId, decimal Amount, string Currency, string Merchant, DateTimeOffset OccurredAt) : IDomainEvent;

public sealed record CardPaymentDeclined(Guid CardId, string Reason, DateTimeOffset OccurredAt) : IDomainEvent;
