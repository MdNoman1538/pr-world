using Bank.Shared;
using Bank.Shared.Events;

namespace Bank.Modules.Customers.Domain;

public enum KycStatus
{
    Pending,
    Verified,
    Rejected,
}

public sealed class Customer
{
    public Customer()
    {
    }

    public string Id { get; set; } = "";
    public string FullName { get; set; } = "";
    public string Email { get; set; } = "";
    [Pii] public string NationalId { get; set; } = "";
    [Pii] public DateOnly DateOfBirth { get; set; }
    public KycStatus Status { get; private set; } = KycStatus.Pending;
    public string? DecidedBy { get; set; }
    public DateTimeOffset RegisteredAt { get; set; }

    public void Verify(string officerId)
    {
        if (Status != KycStatus.Pending)
            throw new InvalidOperationException($"Cannot verify customer in status {Status}.");
        Status = KycStatus.Verified;
        DecidedBy = officerId;
    }

    public void Reject(string officerId)
    {
        if (Status != KycStatus.Pending)
            throw new InvalidOperationException($"Cannot reject customer in status {Status}.");
        Status = KycStatus.Rejected;
        DecidedBy = officerId;
    }
}

public sealed record CustomerRegistered(string CustomerId, DateTimeOffset OccurredAt) : IDomainEvent;

public sealed record CustomerVerified(string CustomerId, string VerifiedBy, DateTimeOffset OccurredAt) : IDomainEvent;

public sealed record CustomerRejected(string CustomerId, string RejectedBy, DateTimeOffset OccurredAt) : IDomainEvent;
