using Bank.Shared.Events;

namespace Bank.Modules.Ledger.Domain;

public sealed record TransferPosted(Guid TransferId, Guid FromAccountId, Guid ToAccountId, decimal Amount, string Currency,
    string Reference, DateTimeOffset OccurredAt) : IDomainEvent;
