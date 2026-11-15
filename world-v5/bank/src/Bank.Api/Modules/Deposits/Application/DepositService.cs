using System.Collections.Concurrent;
using Bank.Data;
using Bank.Modules.Accounts.Application;
using Bank.Modules.Auth.Application;
using Bank.Modules.Deposits.Domain;
using Bank.Modules.Ledger.Application;
using Bank.Modules.Ledger.Domain;
using Bank.Shared.Events;
using Bank.Shared.Money;
using Bank.Shared.Time;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Storage;

namespace Bank.Modules.Deposits.Application;

public interface IDepositService
{
    Task<TermDeposit> OpenAsync(Guid accountId, decimal principal, int termMonths, CancellationToken ct = default);
    Task<TermDeposit> MatureAsync(Guid depositId, CancellationToken ct = default);
    Task<TermDeposit> BreakAsync(Guid depositId, CancellationToken ct = default);
}

public sealed class DepositService(BankDbContext db, ILedger ledger, IAccountService accounts, ICurrentUser user, IClock clock, IEventBus bus) : IDepositService
{
    private static readonly ConcurrentDictionary<Guid, SemaphoreSlim> DepositLocks = new();

    public async Task<TermDeposit> OpenAsync(Guid accountId, decimal principal, int termMonths, CancellationToken ct = default)
    {
        if (principal < 500m)
            throw new ArgumentException("Principal must be at least 500.", nameof(principal));
        if (MoneyMath.ToCents(principal) != principal)
            throw new ArgumentException("Principal must be whole cents.", nameof(principal));

        var annualRatePercent = termMonths switch
        {
            3 => 2.0m,
            6 => 2.5m,
            12 => 3.0m,
            _ => throw new ArgumentException("Term must be 3, 6, or 12 months.", nameof(termMonths)),
        };

        var customerId = user.UserId;
        if (!await accounts.IsOwnerAsync(accountId, customerId, ct))
            throw new UnauthorizedAccessException("Account is not owned by the caller.");

        var account = await accounts.GetAsync(accountId, ct)
            ?? throw new KeyNotFoundException($"Account {accountId} not found.");

        var now = clock.UtcNow;
        var depositId = Guid.NewGuid();
        var holdingAccountId = BankAccounts.For(BankAccountKind.DepositHolding, account.Currency);

        TermDeposit deposit;
        IDbContextTransaction? transaction = null;
        if (db.Database.IsRelational() && db.Database.CurrentTransaction is null)
            transaction = await db.Database.BeginTransactionAsync(ct);

        try
        {
            await ledger.PostTransferAsync(
                accountId,
                holdingAccountId,
                principal,
                $"Term deposit {depositId} opened ({termMonths}m)",
                ct);

            deposit = new TermDeposit
            {
                Id = depositId,
                CustomerId = customerId,
                AccountId = accountId,
                Principal = principal,
                Currency = account.Currency,
                TermMonths = termMonths,
                AnnualRatePercent = annualRatePercent,
                OpenedAt = now,
                MaturesAt = now.AddMonths(termMonths),
                InterestPaid = 0m,
            };

            db.TermDeposits.Add(deposit);
            await db.SaveChangesAsync(ct);

            if (transaction is not null)
                await transaction.CommitAsync(ct);
        }
        catch
        {
            if (transaction is not null)
                await transaction.RollbackAsync(ct);
            throw;
        }
        finally
        {
            if (transaction is not null)
                await transaction.DisposeAsync();
        }

        await bus.PublishAsync(new DepositOpened(deposit.Id, customerId, principal, termMonths, now), ct);
        return deposit;
    }

    public async Task<TermDeposit> MatureAsync(Guid depositId, CancellationToken ct = default)
    {
        var depositLock = DepositLocks.GetOrAdd(depositId, _ => new SemaphoreSlim(1, 1));
        TermDeposit deposit;
        DateTimeOffset now;

        await depositLock.WaitAsync(ct);
        try
        {
            IDbContextTransaction? transaction = null;
            if (db.Database.IsRelational() && db.Database.CurrentTransaction is null)
                transaction = await db.Database.BeginTransactionAsync(ct);

            try
            {
                deposit = await db.TermDeposits.FirstOrDefaultAsync(d => d.Id == depositId, ct)
                    ?? throw new KeyNotFoundException($"Term deposit {depositId} not found.");

                if (deposit.Status != DepositStatus.Open)
                    throw new InvalidOperationException($"Term deposit {depositId} is not open.");

                now = clock.UtcNow;
                if (now < deposit.MaturesAt)
                    throw new InvalidOperationException($"Term deposit {depositId} has not matured yet.");

                var interest = MoneyMath.ToCents(
                    deposit.Principal * (deposit.AnnualRatePercent / 100m) * deposit.TermMonths / 12m);

                var holdingAccountId = BankAccounts.For(BankAccountKind.DepositHolding, deposit.Currency);
                var interestExpenseAccountId = BankAccounts.For(BankAccountKind.InterestExpense, deposit.Currency);

                await ledger.PostTransferAsync(
                    holdingAccountId,
                    deposit.AccountId,
                    deposit.Principal,
                    $"Term deposit {deposit.Id} principal payout",
                    ct);

                if (interest > 0m)
                {
                    await ledger.PostTransferAsync(
                        interestExpenseAccountId,
                        deposit.AccountId,
                        interest,
                        $"Term deposit {deposit.Id} interest payout",
                        ct);
                }

                deposit.Mature(interest);
                await db.SaveChangesAsync(ct);

                if (transaction is not null)
                    await transaction.CommitAsync(ct);
            }
            catch
            {
                if (transaction is not null)
                    await transaction.RollbackAsync(ct);
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
            depositLock.Release();
        }

        await bus.PublishAsync(new DepositClosed(deposit.Id, deposit.CustomerId, deposit.InterestPaid, false, now), ct);
        return deposit;
    }

    public async Task<TermDeposit> BreakAsync(Guid depositId, CancellationToken ct = default)
    {
        var depositLock = DepositLocks.GetOrAdd(depositId, _ => new SemaphoreSlim(1, 1));
        TermDeposit deposit;
        DateTimeOffset now;

        await depositLock.WaitAsync(ct);
        try
        {
            IDbContextTransaction? transaction = null;
            if (db.Database.IsRelational() && db.Database.CurrentTransaction is null)
                transaction = await db.Database.BeginTransactionAsync(ct);

            try
            {
                deposit = await db.TermDeposits.FirstOrDefaultAsync(d => d.Id == depositId, ct)
                    ?? throw new KeyNotFoundException($"Term deposit {depositId} not found.");

                if (deposit.CustomerId != user.UserId)
                    throw new UnauthorizedAccessException("Term deposit is not owned by the caller.");

                if (deposit.Status != DepositStatus.Open)
                    throw new InvalidOperationException($"Term deposit {depositId} is not open.");

                var holdingAccountId = BankAccounts.For(BankAccountKind.DepositHolding, deposit.Currency);
                await ledger.PostTransferAsync(
                    holdingAccountId,
                    deposit.AccountId,
                    deposit.Principal,
                    $"Term deposit {deposit.Id} broken early",
                    ct);

                deposit.BreakEarly();
                now = clock.UtcNow;
                await db.SaveChangesAsync(ct);

                if (transaction is not null)
                    await transaction.CommitAsync(ct);
            }
            catch
            {
                if (transaction is not null)
                    await transaction.RollbackAsync(ct);
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
            depositLock.Release();
        }

        await bus.PublishAsync(new DepositClosed(deposit.Id, deposit.CustomerId, 0m, true, now), ct);
        return deposit;
    }
}
