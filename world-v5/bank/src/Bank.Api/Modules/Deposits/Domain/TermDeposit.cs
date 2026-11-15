using Bank.Shared.Events;

namespace Bank.Modules.Deposits.Domain;

public enum DepositStatus
{
    Open,
    Matured,
    BrokenEarly,
}

public sealed class TermDeposit
{
    public TermDeposit()
    {
    }

    public Guid Id { get; set; } = Guid.NewGuid();
    public string CustomerId { get; set; } = "";
    public Guid AccountId { get; set; }
    public decimal Principal { get; set; }
    public string Currency { get; set; } = "EUR";
    public int TermMonths { get; set; }
    public decimal AnnualRatePercent { get; set; }
    public DateTimeOffset OpenedAt { get; set; }
    public DateTimeOffset MaturesAt { get; set; }
    public DepositStatus Status { get; private set; } = DepositStatus.Open;
    public decimal InterestPaid { get; set; }

    public void Mature(decimal interestPaid)
    {
        if (Status != DepositStatus.Open)
            throw new InvalidOperationException($"Cannot mature deposit in status {Status}.");
        if (interestPaid < 0m)
            throw new ArgumentOutOfRangeException(nameof(interestPaid), "Interest paid cannot be negative.");
        Status = DepositStatus.Matured;
        InterestPaid = interestPaid;
    }

    public void BreakEarly()
    {
        if (Status != DepositStatus.Open)
            throw new InvalidOperationException($"Cannot break deposit in status {Status}.");
        Status = DepositStatus.BrokenEarly;
        InterestPaid = 0m;
    }
}

public sealed record DepositOpened(Guid DepositId, string CustomerId, decimal Principal, int TermMonths, DateTimeOffset OccurredAt) : IDomainEvent;

public sealed record DepositClosed(Guid DepositId, string CustomerId, decimal InterestPaid, bool Early, DateTimeOffset OccurredAt) : IDomainEvent;
