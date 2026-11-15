using Bank.Shared.Events;

namespace Bank.Modules.Loans.Domain;

public enum LoanStatus
{
    Submitted,
    Rejected,
    Disbursed,
}

public sealed class Loan
{
    public Loan()
    {
    }

    public Guid Id { get; set; } = Guid.NewGuid();
    public string CustomerId { get; set; } = "";
    public Guid DisbursementAccountId { get; set; }
    public decimal Principal { get; set; }
    public int TermMonths { get; set; }
    public decimal AnnualRatePercent { get; set; }
    public decimal MonthlyPayment { get; set; }
    public LoanStatus Status { get; private set; } = LoanStatus.Submitted;
    public string? DecidedBy { get; set; }
    public string? DecisionNote { get; set; }
    public DateTimeOffset AppliedAt { get; set; }

    public void Approve(string officerId, string? note)
    {
        if (Status != LoanStatus.Submitted)
            throw new InvalidOperationException($"Cannot approve loan in status {Status}.");
        Status = LoanStatus.Disbursed;
        DecidedBy = officerId;
        DecisionNote = note;
    }

    public void Reject(string officerId, string reason)
    {
        if (Status != LoanStatus.Submitted)
            throw new InvalidOperationException($"Cannot reject loan in status {Status}.");
        Status = LoanStatus.Rejected;
        DecidedBy = officerId;
        DecisionNote = reason;
    }
}

public sealed record LoanSubmitted(Guid LoanId, string CustomerId, decimal Principal, DateTimeOffset OccurredAt) : IDomainEvent;

public sealed record LoanApproved(Guid LoanId, string CustomerId, decimal Principal, DateTimeOffset OccurredAt) : IDomainEvent;

public sealed record LoanRejected(Guid LoanId, string CustomerId, DateTimeOffset OccurredAt) : IDomainEvent;
