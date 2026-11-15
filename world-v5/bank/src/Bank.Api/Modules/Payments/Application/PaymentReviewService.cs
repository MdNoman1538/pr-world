using System.Collections.Concurrent;
using Bank.Data;
using Bank.Modules.Auth;
using Bank.Modules.Auth.Application;
using Bank.Modules.Ledger.Application;
using Bank.Modules.Ledger.Domain;
using Bank.Modules.Notifications.Application;
using Bank.Modules.Payments.Domain;
using Bank.Shared.Events;
using Bank.Shared.Time;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Storage;

namespace Bank.Modules.Payments.Application;

public interface IPaymentReviewService
{
    Task<IReadOnlyList<Payment>> HeldAsync(CancellationToken ct = default);
    Task<Payment> ReleaseAsync(Guid paymentId, CancellationToken ct = default);
    Task<Payment> RejectAsync(Guid paymentId, string reason, CancellationToken ct = default);
}

public sealed class PaymentReviewService(BankDbContext db, ILedger ledger, ICurrentUser user, IClock clock, IEventBus bus, INotifier notifier) : IPaymentReviewService
{
    private static readonly ConcurrentDictionary<Guid, SemaphoreSlim> PaymentLocks = new();

    public async Task<IReadOnlyList<Payment>> HeldAsync(CancellationToken ct = default)
    {
        EnsureComplianceOfficer();

        return await db.Payments
            .Where(p => p.Status == PaymentStatus.Held)
            .OrderBy(p => p.CreatedAt)
            .ToListAsync(ct);
    }

    public async Task<Payment> ReleaseAsync(Guid paymentId, CancellationToken ct = default)
    {
        EnsureComplianceOfficer();
        var officerId = user.UserId;

        var paymentLock = PaymentLocks.GetOrAdd(paymentId, _ => new SemaphoreSlim(1, 1));
        Payment payment;

        await paymentLock.WaitAsync(ct);
        try
        {
            IDbContextTransaction? transaction = null;
            if (db.Database.IsRelational() && db.Database.CurrentTransaction is null)
                transaction = await db.Database.BeginTransactionAsync(ct);

            try
            {
                payment = await db.Payments.FirstOrDefaultAsync(p => p.Id == paymentId, ct)
                    ?? throw new KeyNotFoundException($"Payment {paymentId} not found.");

                if (payment.Status != PaymentStatus.Held)
                    throw new InvalidOperationException($"Cannot release payment in status {payment.Status}.");

                if (payment.CustomerId == officerId)
                    throw new UnauthorizedAccessException("Compliance officers cannot release their own payment.");

                var reference = string.IsNullOrWhiteSpace(payment.Reference)
                    ? $"Payment {payment.Id} released"
                    : payment.Reference;

                Guid transferId;
                var sameCurrency = string.Equals(payment.Currency, payment.CreditedCurrency, StringComparison.OrdinalIgnoreCase);
                if (sameCurrency || payment.CreditedAmount <= 0m)
                {
                    transferId = await ledger.PostTransferAsync(
                        payment.FromAccountId,
                        payment.ToAccountId,
                        Math.Round(payment.Amount, 2, MidpointRounding.AwayFromZero),
                        reference,
                        ct);
                }
                else
                {
                    var fxClearingFrom = BankAccounts.For(BankAccountKind.FxClearing, payment.Currency);
                    var fxClearingTo = BankAccounts.For(BankAccountKind.FxClearing, payment.CreditedCurrency);

                    await ledger.PostTransferAsync(
                        payment.FromAccountId,
                        fxClearingFrom,
                        Math.Round(payment.Amount, 2, MidpointRounding.AwayFromZero),
                        reference,
                        ct);

                    transferId = await ledger.PostTransferAsync(
                        fxClearingTo,
                        payment.ToAccountId,
                        Math.Round(payment.CreditedAmount, 2, MidpointRounding.AwayFromZero),
                        reference,
                        ct);
                }

                if (payment.Fee > 0m)
                {
                    var feeIncomeAccountId = BankAccounts.For(BankAccountKind.FeeIncome, payment.Currency);
                    await ledger.PostTransferAsync(
                        payment.FromAccountId,
                        feeIncomeAccountId,
                        Math.Round(payment.Fee, 2, MidpointRounding.AwayFromZero),
                        reference,
                        ct);
                }

                payment.Complete(transferId);
                await db.SaveChangesAsync(ct);

                if (transaction is not null)
                {
                    await transaction.CommitAsync(ct);
                    await transaction.DisposeAsync();
                    transaction = null;
                }
            }
            catch
            {
                if (transaction is not null)
                {
                    await transaction.RollbackAsync(CancellationToken.None);
                    await transaction.DisposeAsync();
                    transaction = null;
                }

                DetachDirtyEntries();
                throw;
            }
            finally
            {
                if (transaction is not null)
                    await transaction.DisposeAsync();
            }
        }
        finally
        {
            paymentLock.Release();
        }

        var now = clock.UtcNow;
        await bus.PublishAsync(new PaymentReleased(payment.Id, officerId, now), ct);
        await notifier.NotifyAsync(payment.CustomerId, $"Payment {payment.Id} has been released.", ct);
        return payment;
    }

    public async Task<Payment> RejectAsync(Guid paymentId, string reason, CancellationToken ct = default)
    {
        EnsureComplianceOfficer();
        var officerId = user.UserId;

        if (string.IsNullOrWhiteSpace(reason))
            throw new ArgumentException("Rejection reason is required.", nameof(reason));

        var paymentLock = PaymentLocks.GetOrAdd(paymentId, _ => new SemaphoreSlim(1, 1));
        Payment payment;

        await paymentLock.WaitAsync(ct);
        try
        {
            IDbContextTransaction? transaction = null;
            if (db.Database.IsRelational() && db.Database.CurrentTransaction is null)
                transaction = await db.Database.BeginTransactionAsync(ct);

            try
            {
                payment = await db.Payments.FirstOrDefaultAsync(p => p.Id == paymentId, ct)
                    ?? throw new KeyNotFoundException($"Payment {paymentId} not found.");

                if (payment.Status != PaymentStatus.Held)
                    throw new InvalidOperationException($"Cannot reject payment in status {payment.Status}.");

                if (payment.CustomerId == officerId)
                    throw new UnauthorizedAccessException("Compliance officers cannot reject their own payment.");

                payment.Reject();
                await db.SaveChangesAsync(ct);

                if (transaction is not null)
                {
                    await transaction.CommitAsync(ct);
                    await transaction.DisposeAsync();
                    transaction = null;
                }
            }
            catch
            {
                if (transaction is not null)
                {
                    await transaction.RollbackAsync(CancellationToken.None);
                    await transaction.DisposeAsync();
                    transaction = null;
                }

                DetachDirtyEntries();
                throw;
            }
            finally
            {
                if (transaction is not null)
                    await transaction.DisposeAsync();
            }
        }
        finally
        {
            paymentLock.Release();
        }

        var now = clock.UtcNow;
        await bus.PublishAsync(new PaymentRejected(payment.Id, officerId, now), ct);
        await notifier.NotifyAsync(payment.CustomerId, $"Payment {payment.Id} has been rejected and funds have been returned.", ct);
        return payment;
    }

    private void EnsureComplianceOfficer()
    {
        if (!user.IsInRole(Roles.ComplianceOfficer))
            throw new UnauthorizedAccessException("Only a compliance officer may review held payments.");
    }

    private void DetachDirtyEntries()
    {
        foreach (var entry in db.ChangeTracker.Entries()
                     .Where(e => e.State is EntityState.Added or EntityState.Modified or EntityState.Deleted)
                     .ToList())
        {
            entry.State = EntityState.Detached;
        }
    }
}
