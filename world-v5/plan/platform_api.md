# Public platform API the Test agent may use (signatures only, no implementations)

namespace Bank.Data
  sealed class BankDbContext : DbContext   // DbSet<Account> Accounts, DbSet<LedgerEntry> LedgerEntries, DbSet<AuditEntry> AuditEntries
                                           // (+ the tables that modules add, as named in their contracts)

namespace Bank.Shared            [Pii] attribute for personal data
namespace Bank.Shared.Time       interface IClock { DateTimeOffset UtcNow { get; } }
namespace Bank.Shared.Settings   sealed class BankSettings { string DefaultCurrency = "EUR"; IReadOnlyList<string> SupportedCurrencies; decimal DailyTransferLimit = 10_000m }  (init properties)
namespace Bank.Shared.Events
  interface IDomainEvent { DateTimeOffset OccurredAt { get; } }
  interface IEventBus { Task PublishAsync<TEvent>(TEvent e, CancellationToken ct = default) where TEvent : IDomainEvent; }

namespace Bank.Modules.Accounts.Domain
  enum AccountKind { Customer, Internal }
  sealed class Account { Guid Id; string OwnerId; [Pii] string Iban; string Currency; decimal Balance; AccountKind Kind; bool AllowOverdraft; DateTimeOffset OpenedAt }
namespace Bank.Modules.Accounts.Application
  interface IAccountService { Task<Account?> GetAsync(Guid id, ...); Task<bool> IsOwnerAsync(Guid accountId, string userId, ...);
                              Task<IReadOnlyList<Account>> ForOwnerAsync(string ownerId, ...); Task<Account> OpenAsync(string? currency, ...); }
  sealed class AccountService(BankDbContext db, ICurrentUser user, BankSettings settings, IClock clock, IEventBus bus, IEnumerable<IAccountOpeningRule> rules)
  interface IAccountOpeningRule { Task EnsureMayOpenAsync(string ownerId, CancellationToken ct = default); }

namespace Bank.Modules.Ledger.Application
  interface ILedger { Task<Guid> PostTransferAsync(Guid fromAccountId, Guid toAccountId, decimal amount, string reference, ...);
                      Task<IReadOnlyList<LedgerEntry>> EntriesAsync(Guid accountId, DateTimeOffset fromInclusive, DateTimeOffset toExclusive, ...); }
  sealed class InsufficientFundsException : InvalidOperationException;   sealed class CurrencyMismatchException : InvalidOperationException
namespace Bank.Modules.Ledger.Domain
  sealed class LedgerEntry { Guid Id; Guid TransferId; Guid AccountId; decimal Amount; string Currency; decimal BalanceAfter; string Reference; DateTimeOffset CreatedAt }
  enum BankAccountKind { LoanFunding, FeeIncome, FxClearing, DepositHolding, InterestExpense, Suspense }
  static class BankAccounts { static Guid For(BankAccountKind kind, string currency); }   // the bank's own accounts (may go below zero)

namespace Bank.Modules.Auth
  static class Roles { Customer = "customer", Teller = "teller", LoanOfficer = "loan-officer", ComplianceOfficer = "compliance-officer", Admin = "admin" }
namespace Bank.Modules.Auth.Application
  interface ICurrentUser { string UserId { get; } bool IsInRole(string role); }
namespace Bank.Modules.Notifications.Application
  interface INotifier { Task NotifyAsync(string customerId, string message, CancellationToken ct = default); }
namespace Bank.Modules.Audit.Application
  sealed class AuditLog { static string Redact(IDomainEvent e); }   // the JSON the audit trail stores for an event

namespace Bank.Tests (test helpers — see TestKit.cs; build ALL test state through these and public constructors/services)
  TestKit.Db() -> fresh in-memory BankDbContext (with the bank's own accounts)
  TestKit.Account(db, ownerId, balance = 0m, currency = "EUR") -> Guid   // funded through the Ledger
  TestKit.Balance(db, accountId) -> decimal (fresh from the database)
  TestKit.Ledger(db, bus?, clock?) -> ILedger
  TestKit.Settings(defaultCurrency = "EUR", dailyTransferLimit = 10_000m) -> BankSettings
  new FakeUser(userId, params string[] roles) : ICurrentUser      (UserId is settable: switch user mid-test)
  new FakeClock() : IClock   (.UtcNow settable, starts 2026-03-15 10:00 UTC; .Advance(TimeSpan))
  new RecordingBus() : IEventBus          // .Events lists everything published
  new RecordingNotifier() : INotifier     // .Sent lists (customerId, message)
