using System.Collections.Concurrent;
using Bank.Data;
using Bank.Modules.Accounts.Application;
using Bank.Modules.Auth;
using Bank.Modules.Auth.Application;
using Bank.Modules.Ledger.Application;
using Bank.Modules.Ledger.Domain;
using Bank.Modules.Loans.Domain;
using Bank.Modules.Notifications.Application;
using Bank.Shared.Events;
using Bank.Shared.Money;
using Bank.Shared.Time;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Storage;

namespace Bank.Modules.Loans.Application;

public sealed record LoanApplication(Guid DisbursementAccountId, decimal Principal, int TermMonths);

public interface ILoanService
{
    Task<Loan> ApplyAsync(LoanApplication application, CancellationToken ct = default);
    Task<Loan> GetAsync(Guid loanId, CancellationToken ct = default);
    Task<Loan> ApproveAsync(Guid loanId, string? note, CancellationToken ct = default);
    Task<Loan> RejectAsync(Guid loanId, string reason, CancellationToken ct = default);
}

public sealed class LoanService : ILoanService
{
    private const decimal MinPrincipal = 1000m;
    private const decimal MaxPrincipal = 50000m;
    private const int MinTermMonths = 6;
    private const int MaxTermMonths = 120;
    private const decimal FixedAnnualRatePercent = 5.5m;

    private static readonly ConcurrentDictionary<Guid, SemaphoreSlim> LoanLocks = new();

    private readonly BankDbContext _db;
    private readonly ILedger _ledger;
    private readonly IAccountService _accounts;
    private readonly ICurrentUser _user;
    private readonly IClock _clock;
    private readonly IEventBus _bus;
    private readonly INotifier _notifier;

    public LoanService(
        BankDbContext db,
        ILedger ledger,
        IAccountService accounts,
        ICurrentUser user,
        IClock clock,
        IEventBus bus,
        INotifier notifier)
    {
        _db = db;
        _ledger = ledger;
        _accounts = accounts;
        _user = user;
        _clock = clock;
        _bus = bus;
        _notifier = notifier;
    }

    public async Task<Loan> ApplyAsync(LoanApplication application, CancellationToken ct = default)
    {
        ArgumentNullException.ThrowIfNull(application);

        if (application.Principal < MinPrincipal || application.Principal > MaxPrincipal)
            throw new ArgumentException($"Principal must be between {MinPrincipal} and {MaxPrincipal}.", nameof(application));
        if (MoneyMath.ToCents(application.Principal) != application.Principal)
            throw new ArgumentException("Principal must be whole cents.", nameof(application));
        if (application.TermMonths < MinTermMonths || application.TermMonths > MaxTermMonths)
            throw new ArgumentException($"Term must be between {MinTermMonths} and {MaxTermMonths} months.", nameof(application));

        var customerId = _user.UserId;
        if (!await _accounts.IsOwnerAsync(application.DisbursementAccountId, customerId, ct))
            throw new UnauthorizedAccessException("Disbursement account is not owned by the caller.");

        var monthlyPayment = CalculateMonthlyAnnuity(application.Principal, application.TermMonths);
        var now = _clock.UtcNow;

        var loan = new Loan
        {
            CustomerId = customerId,
            DisbursementAccountId = application.DisbursementAccountId,
            Principal = application.Principal,
            TermMonths = application.TermMonths,
            AnnualRatePercent = FixedAnnualRatePercent,
            MonthlyPayment = monthlyPayment,
            AppliedAt = now,
        };

        _db.Loans.Add(loan);
        await _db.SaveChangesAsync(ct);
        await _bus.PublishAsync(new LoanSubmitted(loan.Id, customerId, loan.Principal, now), ct);

        return loan;
    }

    public async Task<Loan> GetAsync(Guid loanId, CancellationToken ct = default)
    {
        var loan = await _db.Loans.FirstOrDefaultAsync(l => l.Id == loanId, ct)
            ?? throw new KeyNotFoundException($"Loan {loanId} not found.");

        if (loan.CustomerId != _user.UserId && !_user.IsInRole(Roles.LoanOfficer))
            throw new UnauthorizedAccessException("Caller is not authorized to view this loan.");

        return loan;
    }

    public async Task<Loan> ApproveAsync(Guid loanId, string? note, CancellationToken ct = default)
    {
        if (!_user.IsInRole(Roles.LoanOfficer))
            throw new UnauthorizedAccessException("Only a loan officer may approve a loan.");

        var officerId = _user.UserId;
        var loanLock = LoanLocks.GetOrAdd(loanId, _ => new SemaphoreSlim(1, 1));
        Loan loan;

        await loanLock.WaitAsync(ct);
        try
        {
            IDbContextTransaction? transaction = null;
            if (_db.Database.IsRelational() && _db.Database.CurrentTransaction is null)
                transaction = await _db.Database.BeginTransactionAsync(ct);

            try
            {
                loan = await _db.Loans.FirstOrDefaultAsync(l => l.Id == loanId, ct)
                    ?? throw new KeyNotFoundException($"Loan {loanId} not found.");

                if (loan.Status != LoanStatus.Submitted)
                    throw new InvalidOperationException($"Cannot approve loan in status {loan.Status}.");

                var account = await _accounts.GetAsync(loan.DisbursementAccountId, ct)
                    ?? throw new KeyNotFoundException($"Account {loan.DisbursementAccountId} not found.");

                var fundingAccountId = BankAccounts.For(BankAccountKind.LoanFunding, account.Currency);
                await _ledger.PostTransferAsync(
                    fundingAccountId,
                    loan.DisbursementAccountId,
                    loan.Principal,
                    $"Loan {loan.Id} disbursement",
                    ct);

                loan.Approve(officerId, note);
                await _db.SaveChangesAsync(ct);

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
            loanLock.Release();
        }

        var now = _clock.UtcNow;
        await _bus.PublishAsync(new LoanApproved(loan.Id, loan.CustomerId, loan.Principal, now), ct);
        await _notifier.NotifyAsync(loan.CustomerId, $"Your loan application {loan.Id} has been approved and disbursed.", ct);
        return loan;
    }

    public async Task<Loan> RejectAsync(Guid loanId, string reason, CancellationToken ct = default)
    {
        if (!_user.IsInRole(Roles.LoanOfficer))
            throw new UnauthorizedAccessException("Only a loan officer may reject a loan.");

        var officerId = _user.UserId;

        if (string.IsNullOrWhiteSpace(reason))
            throw new ArgumentException("Rejection reason is required.", nameof(reason));

        var loanLock = LoanLocks.GetOrAdd(loanId, _ => new SemaphoreSlim(1, 1));
        Loan loan;

        await loanLock.WaitAsync(ct);
        try
        {
            loan = await _db.Loans.FirstOrDefaultAsync(l => l.Id == loanId, ct)
                ?? throw new KeyNotFoundException($"Loan {loanId} not found.");

            if (loan.CustomerId == officerId)
                throw new UnauthorizedAccessException("Loan officers cannot reject their own loan.");

            loan.Reject(officerId, reason);
            await _db.SaveChangesAsync(ct);
        }
        finally
        {
            loanLock.Release();
        }

        var now = _clock.UtcNow;
        await _bus.PublishAsync(new LoanRejected(loan.Id, loan.CustomerId, now), ct);
        await _notifier.NotifyAsync(loan.CustomerId, $"Your loan application {loan.Id} has been rejected.", ct);
        return loan;
    }

    private static decimal CalculateMonthlyAnnuity(decimal principal, int termMonths)
    {
        var monthlyRate = (FixedAnnualRatePercent / 100m) / 12m;
        var onePlusRate = 1m + monthlyRate;
        var compoundFactor = 1m;
        for (var i = 0; i < termMonths; i++)
            compoundFactor *= onePlusRate;

        var payment = principal * monthlyRate / (1m - 1m / compoundFactor);
        return MoneyMath.ToCents(payment);
    }
}
