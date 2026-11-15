using Bank.Shared.Events;

namespace Bank.Modules.Payments.Domain;

public enum PaymentStatus
{
    Completed,
    Held,
    Rejected,
}

public sealed class Payment
{
    public Payment()
    {
    }

    public Guid Id { get; set; } = Guid.NewGuid();
    public string IdempotencyKey { get; set; } = "";
    public string CustomerId { get; set; } = "";
    public Guid FromAccountId { get; set; }
    public Guid ToAccountId { get; set; }
    public decimal Amount { get; set; }
    public string Currency { get; set; } = "EUR";
    public decimal Fee { get; set; }
    public decimal CreditedAmount { get; set; }
    public string CreditedCurrency { get; set; } = "EUR";
    public decimal Rate { get; set; } = 1m;
    public PaymentStatus Status { get; private set; } = PaymentStatus.Completed;
    public Guid? TransferId { get; set; }
    public string? Reference { get; set; }
    public DateTimeOffset CreatedAt { get; set; }

    public void Complete(Guid transferId)
    {
        if (Status == PaymentStatus.Rejected || (Status == PaymentStatus.Completed && TransferId is not null))
            throw new InvalidOperationException($"Cannot complete payment in status {Status}.");
        Status = PaymentStatus.Completed;
        TransferId = transferId;
    }

    public void Hold()
    {
        if (Status == PaymentStatus.Held || Status == PaymentStatus.Rejected || (Status == PaymentStatus.Completed && TransferId is not null))
            throw new InvalidOperationException($"Cannot hold payment in status {Status}.");
        Status = PaymentStatus.Held;
    }

    public void Reject()
    {
        if (Status != PaymentStatus.Held)
            throw new InvalidOperationException($"Cannot reject payment in status {Status}.");
        Status = PaymentStatus.Rejected;
    }
}

public sealed record PaymentCompleted(Guid PaymentId, string CustomerId, decimal Amount, string Currency, DateTimeOffset OccurredAt) : IDomainEvent;

public sealed record PaymentHeld(Guid PaymentId, string CustomerId, decimal Amount, string Currency, DateTimeOffset OccurredAt) : IDomainEvent;

public sealed record PaymentReleased(Guid PaymentId, string ReleasedBy, DateTimeOffset OccurredAt) : IDomainEvent;

public sealed record PaymentRejected(Guid PaymentId, string RejectedBy, DateTimeOffset OccurredAt) : IDomainEvent;
