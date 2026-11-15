using System.Collections.Concurrent;
using System.Data.Common;
using System.Runtime.CompilerServices;
using Bank.Data;
using Bank.Modules.Accounts.Application;
using Bank.Modules.Accounts.Domain;
using Bank.Modules.Auth.Application;
using Bank.Modules.Fees.Application;
using Bank.Modules.Fx.Application;
using Bank.Modules.Ledger.Application;
using Bank.Modules.Ledger.Domain;
using Bank.Modules.Notifications.Application;
using Bank.Modules.Payments.Domain;
using Bank.Shared.Events;
using Bank.Shared.Settings;
using Bank.Shared.Time;
using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Storage;
using Microsoft.Extensions.DependencyInjection;

namespace Bank.Modules.Payments.Application;

public sealed record PaymentRequest(string IdempotencyKey, Guid FromAccountId, Guid ToAccountId, decimal Amount, string? Reference);

public sealed record PaymentQuote(decimal Amount, string Currency, decimal Fee, decimal CreditedAmount, string CreditedCurrency, decimal Rate);

public sealed class DailyLimitExceededException : InvalidOperationException
{
    public DailyLimitExceededException() : base("Daily transfer limit exceeded.")
    {
    }

    public DailyLimitExceededException(string message) : base(message)
    {
    }
}

public interface IPaymentService
{
    Task<PaymentQuote> QuoteAsync(Guid fromAccountId, Guid toAccountId, decimal amount, CancellationToken ct = default);
    Task<Payment> PayAsync(PaymentRequest request, CancellationToken ct = default);
    Task<IReadOnlyList<Payment>> ForCustomerAsync(string customerId, CancellationToken ct = default);
}

public sealed class PaymentService : IPaymentService
{
    private const decimal HoldThresholdEur = 5_000.00m;

    private static readonly ConcurrentDictionary<string, SemaphoreSlim> IdempotencyLocks = new();
    private static readonly ConcurrentDictionary<string, SemaphoreSlim> SqliteFileWriteLocks = new();
    private static readonly ConditionalWeakTable<DbConnection, SemaphoreSlim> SqliteConnectionWriteLocks = new();

    private readonly BankDbContext _db;
    private readonly ILedger _ledger;
    private readonly IAccountService _accounts;
    private readonly ICurrentUser _user;
    private readonly IClock _clock;
    private readonly BankSettings _settings;
    private readonly IFxService _fx;
    private readonly IFeeCalculator _fees;
    private readonly INotifier _notifier;
    private readonly IEventBus _bus;

    [ActivatorUtilitiesConstructor]
    public PaymentService(
        BankDbContext db,
        ILedger ledger,
        IAccountService accounts,
        ICurrentUser user,
        IClock clock,
        BankSettings settings,
        IFxService fx,
        IFeeCalculator fees,
        INotifier notifier,
        IEventBus bus)
    {
        _db = db;
        _ledger = ledger;
        _accounts = accounts;
        _user = user;
        _clock = clock;
        _settings = settings;
        _fx = fx;
        _fees = fees;
        _notifier = notifier;
        _bus = bus;
    }

    public PaymentService(
        BankDbContext db,
        ILedger ledger,
        IAccountService accounts,
        ICurrentUser user,
        IClock clock,
        BankSettings settings,
        IFxService fx,
        IFeeCalculator fees,
        IEventBus bus)
        : this(db, ledger, accounts, user, clock, settings, fx, fees, new NullNotifier(), bus)
    {
    }

    public PaymentService(
        BankDbContext db,
        ILedger ledger,
        IAccountService accounts,
        ICurrentUser user,
        IClock clock,
        BankSettings settings,
        IFxService fx,
        IEventBus bus)
        : this(db, ledger, accounts, user, clock, settings, fx, new FeeCalculator(fx), new NullNotifier(), bus)
    {
    }

    public PaymentService(
        BankDbContext db,
        ILedger ledger,
        IAccountService accounts,
        ICurrentUser user,
        IClock clock,
        BankSettings settings,
        IEventBus bus)
        : this(db, ledger, accounts, user, clock, settings, new FxService(), bus)
    {
    }

    public async Task<PaymentQuote> QuoteAsync(Guid fromAccountId, Guid toAccountId, decimal amount, CancellationToken ct = default)
    {
        if (amount <= 0m)
            throw new ArgumentException("Amount must be positive.", nameof(amount));
        if (amount != Math.Round(amount, 2, MidpointRounding.AwayFromZero))
            throw new ArgumentException("Amount must be whole cents.", nameof(amount));

        var fromAccount = await _accounts.GetAsync(fromAccountId, ct)
            ?? throw new KeyNotFoundException($"Account {fromAccountId} not found.");
        if (!await _accounts.IsOwnerAsync(fromAccountId, _user.UserId, ct))
            throw new UnauthorizedAccessException("Source account is not owned by the caller.");
        var toAccount = await _accounts.GetAsync(toAccountId, ct)
            ?? throw new KeyNotFoundException($"Account {toAccountId} not found.");

        var sameCurrency = string.Equals(fromAccount.Currency, toAccount.Currency, StringComparison.OrdinalIgnoreCase);
        var rate = sameCurrency ? 1m : _fx.Rate(fromAccount.Currency, toAccount.Currency);
        var creditedAmount = sameCurrency
            ? amount
            : _fx.Convert(amount, fromAccount.Currency, toAccount.Currency);
        var fee = _fees.Quote(amount, fromAccount.Currency, toAccount.Currency);

        return new PaymentQuote(
            amount,
            fromAccount.Currency,
            fee.Amount,
            creditedAmount,
            toAccount.Currency,
            rate);
    }

    public async Task<Payment> PayAsync(PaymentRequest request, CancellationToken ct = default)
    {
        ArgumentNullException.ThrowIfNull(request);
        if (string.IsNullOrWhiteSpace(request.IdempotencyKey))
            throw new ArgumentException("Idempotency key is required.", nameof(request));
        if (request.Amount <= 0m)
            throw new ArgumentException("Amount must be positive.", nameof(request));

        var amount = Math.Round(request.Amount, 2, MidpointRounding.AwayFromZero);
        if (request.Amount != amount)
            throw new ArgumentException("Amount must be whole cents.", nameof(request));

        var customerId = _user.UserId;

        var fromAccount = await _accounts.GetAsync(request.FromAccountId, ct)
            ?? throw new KeyNotFoundException($"Account {request.FromAccountId} not found.");
        if (!await _accounts.IsOwnerAsync(request.FromAccountId, customerId, ct))
            throw new UnauthorizedAccessException("Source account is not owned by the caller.");
        var toAccount = await _accounts.GetAsync(request.ToAccountId, ct)
            ?? throw new KeyNotFoundException($"Account {request.ToAccountId} not found.");

        var existing = await _db.Payments.AsNoTracking().FirstOrDefaultAsync(
            p => p.CustomerId == customerId && p.IdempotencyKey == request.IdempotencyKey,
            ct);
        if (existing is not null)
            return existing;

        var lockKey = $"{customerId}\0{request.IdempotencyKey}";
        var keyLock = IdempotencyLocks.GetOrAdd(lockKey, _ => new SemaphoreSlim(1, 1));

        Payment result;
        bool created;

        await keyLock.WaitAsync(ct);
        try
        {
            existing = await _db.Payments.AsNoTracking().FirstOrDefaultAsync(
                p => p.CustomerId == customerId && p.IdempotencyKey == request.IdempotencyKey,
                ct);
            if (existing is not null)
                return existing;

            var dbWriteLock = GetSqliteWriteLock();
            if (dbWriteLock is not null)
            {
                await dbWriteLock.WaitAsync(ct);
                try
                {
                    (result, created) = await ExecuteIdempotentPaymentAsync(request, customerId, fromAccount, toAccount, amount, ct);
                }
                finally
                {
                    dbWriteLock.Release();
                }
            }
            else
            {
                (result, created) = await ExecuteIdempotentPaymentAsync(request, customerId, fromAccount, toAccount, amount, ct);
            }
        }
        finally
        {
            keyLock.Release();
        }

        if (created)
        {
            if (result.Status == PaymentStatus.Held)
            {
                await _bus.PublishAsync(
                    new PaymentHeld(result.Id, customerId, result.Amount, result.Currency, _clock.UtcNow),
                    ct);
                await _notifier.NotifyAsync(
                    customerId,
                    $"Payment {result.Id} is being checked for compliance review.",
                    ct);
            }
            else
            {
                await _bus.PublishAsync(
                    new PaymentCompleted(result.Id, customerId, result.Amount, result.Currency, result.CreatedAt),
                    ct);
            }
        }

        return result;
    }

    public async Task<IReadOnlyList<Payment>> ForCustomerAsync(string customerId, CancellationToken ct = default) =>
        await _db.Payments
            .Where(p => p.CustomerId == customerId)
            .OrderByDescending(p => p.CreatedAt)
            .ToListAsync(ct);

    private async Task<(Payment Payment, bool Created)> ExecuteIdempotentPaymentAsync(
        PaymentRequest request,
        string customerId,
        Account fromAccount,
        Account toAccount,
        decimal amount,
        CancellationToken ct)
    {
        var existing = await _db.Payments.AsNoTracking().FirstOrDefaultAsync(
            p => p.CustomerId == customerId && p.IdempotencyKey == request.IdempotencyKey,
            ct);
        if (existing is not null)
            return (existing, false);

        if (_db.Entry(fromAccount).State != EntityState.Detached)
            await _db.Entry(fromAccount).ReloadAsync(ct);

        var latestAccount = await _db.Accounts.AsNoTracking()
            .Where(a => a.Id == request.FromAccountId)
            .Select(a => new { a.Balance, a.AllowOverdraft })
            .FirstOrDefaultAsync(ct);
        var availableBalance = latestAccount?.Balance ?? fromAccount.Balance;
        var allowOverdraft = latestAccount?.AllowOverdraft ?? fromAccount.AllowOverdraft;

        var sameCurrency = string.Equals(fromAccount.Currency, toAccount.Currency, StringComparison.OrdinalIgnoreCase);
        var rate = sameCurrency ? 1m : _fx.Rate(fromAccount.Currency, toAccount.Currency);
        var creditedAmount = sameCurrency
            ? amount
            : _fx.Convert(amount, fromAccount.Currency, toAccount.Currency);
        var creditedCurrency = toAccount.Currency;

        if (creditedAmount <= 0m)
            throw new ArgumentException("Converted amount must be positive.", nameof(request));

        var fee = _fees.Quote(amount, fromAccount.Currency, toAccount.Currency);

        var now = _clock.UtcNow;
        var dayStart = new DateTimeOffset(now.UtcDateTime.Date, TimeSpan.Zero);
        var dayEnd = dayStart.AddDays(1);

        Payment? payment = null;
        IDbContextTransaction? transaction = null;
        if (_db.Database.IsRelational() && _db.Database.CurrentTransaction is null)
            transaction = await _db.Database.BeginTransactionAsync(ct);

        try
        {
            var todayPayments = await _db.Payments
                .AsNoTracking()
                .Where(p => p.CustomerId == customerId
                    && p.Status == PaymentStatus.Completed
                    && p.CreatedAt >= dayStart
                    && p.CreatedAt < dayEnd)
                .Select(p => new { p.Amount, p.Currency })
                .ToListAsync(ct);

            var todayTotalEur = todayPayments.Sum(p => _fx.Convert(p.Amount, p.Currency, "EUR"));
            var requestAmountEur = Math.Round(_fx.Convert(amount, fromAccount.Currency, "EUR"), 2, MidpointRounding.AwayFromZero);

            if (todayTotalEur + requestAmountEur > _settings.DailyTransferLimit)
                throw new DailyLimitExceededException();

            if (!allowOverdraft && availableBalance < amount + fee.Amount)
                throw new InsufficientFundsException(request.FromAccountId);

            var hasPriorCompletedPayment = await _db.Payments
                .AsNoTracking()
                .AnyAsync(p => p.CustomerId == customerId
                    && p.ToAccountId == request.ToAccountId
                    && p.Status == PaymentStatus.Completed, ct);

            var shouldHold = requestAmountEur >= HoldThresholdEur && !hasPriorCompletedPayment;

            payment = new Payment
            {
                IdempotencyKey = request.IdempotencyKey,
                CustomerId = customerId,
                FromAccountId = request.FromAccountId,
                ToAccountId = request.ToAccountId,
                Amount = amount,
                Currency = fromAccount.Currency,
                Fee = fee.Amount,
                CreditedAmount = creditedAmount,
                CreditedCurrency = creditedCurrency,
                Rate = rate,
                Reference = request.Reference,
                CreatedAt = now,
            };
            payment.Hold();

            _db.Payments.Add(payment);
            await _db.SaveChangesAsync(ct);

            if (!shouldHold)
            {
                var reference = request.Reference ?? "";
                Guid transferId;
                if (sameCurrency)
                {
                    transferId = await _ledger.PostTransferAsync(
                        request.FromAccountId,
                        request.ToAccountId,
                        Math.Round(amount, 2, MidpointRounding.AwayFromZero),
                        reference,
                        ct);
                }
                else
                {
                    var fxClearingFrom = BankAccounts.For(BankAccountKind.FxClearing, fromAccount.Currency);
                    var fxClearingTo = BankAccounts.For(BankAccountKind.FxClearing, toAccount.Currency);

                    await _ledger.PostTransferAsync(
                        request.FromAccountId,
                        fxClearingFrom,
                        Math.Round(amount, 2, MidpointRounding.AwayFromZero),
                        reference,
                        ct);

                    transferId = await _ledger.PostTransferAsync(
                        fxClearingTo,
                        request.ToAccountId,
                        Math.Round(creditedAmount, 2, MidpointRounding.AwayFromZero),
                        reference,
                        ct);
                }

                if (fee.Amount > 0m)
                {
                    var feeIncome = BankAccounts.For(BankAccountKind.FeeIncome, fromAccount.Currency);
                    await _ledger.PostTransferAsync(
                        request.FromAccountId,
                        feeIncome,
                        Math.Round(fee.Amount, 2, MidpointRounding.AwayFromZero),
                        reference,
                        ct);
                }

                payment.Complete(transferId);
                await _db.SaveChangesAsync(ct);
            }

            if (transaction is not null)
            {
                await transaction.CommitAsync(ct);
                await transaction.DisposeAsync();
                transaction = null;
            }

            return (payment, true);
        }
        catch (DbUpdateException ex) when (IsIdempotencyUniqueConstraintViolation(ex))
        {
            if (transaction is not null)
            {
                await transaction.RollbackAsync(CancellationToken.None);
                await transaction.DisposeAsync();
                transaction = null;
            }

            DetachDirtyEntries();

            var concurrent = await _db.Payments.AsNoTracking().FirstOrDefaultAsync(
                p => p.CustomerId == customerId && p.IdempotencyKey == request.IdempotencyKey,
                ct);
            if (concurrent is not null)
                return (concurrent, false);

            throw;
        }
        catch
        {
            if (transaction is not null)
            {
                await transaction.RollbackAsync(CancellationToken.None);
                await transaction.DisposeAsync();
                transaction = null;
            }
            else if (payment is not null && _db.Entry(payment).State != EntityState.Detached)
            {
                _db.Payments.Remove(payment);
                await _db.SaveChangesAsync(CancellationToken.None);
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

    private SemaphoreSlim? GetSqliteWriteLock()
    {
        if (!_db.Database.IsRelational() || !_db.Database.IsSqlite() || _db.Database.CurrentTransaction is not null)
            return null;

        var connection = _db.Database.GetDbConnection();
        var dataSource = connection.DataSource;
        if (string.IsNullOrEmpty(dataSource) || string.Equals(dataSource, ":memory:", StringComparison.OrdinalIgnoreCase))
            return SqliteConnectionWriteLocks.GetValue(connection, _ => new SemaphoreSlim(1, 1));

        return SqliteFileWriteLocks.GetOrAdd(dataSource, _ => new SemaphoreSlim(1, 1));
    }

    private void DetachDirtyEntries()
    {
        foreach (var entry in _db.ChangeTracker.Entries()
                     .Where(e => e.State is EntityState.Added or EntityState.Modified or EntityState.Deleted)
                     .ToList())
        {
            entry.State = EntityState.Detached;
        }
    }

    private static bool IsIdempotencyUniqueConstraintViolation(DbUpdateException ex)
    {
        if (ex.InnerException is SqliteException sqliteEx)
        {
            if (sqliteEx.SqliteErrorCode != 19)
                return false;

            if (sqliteEx.SqliteExtendedErrorCode != 0
                && sqliteEx.SqliteExtendedErrorCode != 19
                && sqliteEx.SqliteExtendedErrorCode != 2067)
            {
                return false;
            }

            var msg = sqliteEx.Message;
            if (msg.Contains("UNIQUE constraint failed", StringComparison.OrdinalIgnoreCase))
            {
                return msg.Contains("CustomerId", StringComparison.OrdinalIgnoreCase)
                    && msg.Contains("IdempotencyKey", StringComparison.OrdinalIgnoreCase);
            }

            return sqliteEx.SqliteExtendedErrorCode == 2067;
        }

        var message = ex.InnerException?.Message ?? ex.Message;
        return message.Contains("UNIQUE constraint failed", StringComparison.OrdinalIgnoreCase)
            && message.Contains("CustomerId", StringComparison.OrdinalIgnoreCase)
            && message.Contains("IdempotencyKey", StringComparison.OrdinalIgnoreCase);
    }

    private sealed class NullNotifier : INotifier
    {
        public Task NotifyAsync(string customerId, string message, CancellationToken ct = default) => Task.CompletedTask;
    }
}
