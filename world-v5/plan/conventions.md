# Coding conventions for Nordbank (the Builder must follow these)

Stack: C# / ASP.NET Core Web API (.NET 8+), EF Core (SQLite), xUnit. No new NuGet packages.

## Layout — one folder per module, one folder per layer
src/Bank.Api/Modules/<Module>/
  Api/          controllers + DTOs            (HTTP layer)
  Application/  services + interfaces         (use cases)
  Domain/       entities, enums, events       (business rules)
  Data/         repositories (optional)       (database access)
  <Module>Module.cs   static class with AddXModule(this IServiceCollection): services.AddScoped<IThing, Thing>()
Register a new module in Program.cs above the "// MODULES:" line.
Add a new table as a DbSet in src/Bank.Api/Data/BankDbContext.cs above the "// TABLES:" line.
Each module already has a CONSTITUTION.md written by the humans who own it: follow its rules.

## Rules
- Namespaces follow folders: Bank.Modules.<Module>.<Layer>.
- Controllers: [ApiController], [Route("api/...")], and ALWAYS an [Authorize(Policy = Policies.X)] (Bank.Modules.Auth.Policies:
  Customer, Staff, LoanOfficer, Compliance, Admin). Roles are in Bank.Modules.Auth.Roles.
- Current user: inject Bank.Modules.Auth.Application.ICurrentUser (UserId, IsInRole). Never trust user ids from request bodies.
- Time: inject Bank.Shared.Time.IClock and use clock.UtcNow. Never call DateTime.Now / DateTimeOffset.UtcNow directly.
- Settings: inject Bank.Shared.Settings.BankSettings (DefaultCurrency, SupportedCurrencies, DailyTransferLimit).
- Money: decimal only. Round to cents with Math.Round(x, 2, MidpointRounding.AwayFromZero).
- Money moves ONLY through Bank.Modules.Ledger.Application.ILedger.PostTransferAsync(from, to, amount, reference),
  which returns the transfer id and works in ONE currency. The bank's own accounts:
  Bank.Modules.Ledger.Domain.BankAccounts.For(BankAccountKind.X, currency) with kinds
  LoanFunding, FeeIncome, FxClearing, DepositHolding, InterestExpense, Suspense (EUR, SEK, USD).
- Accounts: Bank.Modules.Accounts.Application.IAccountService (GetAsync, IsOwnerAsync, ForOwnerAsync). Never edit Account.Balance.
- State machines: an entity owns its status (private setter) and changes it only through methods that check the current state.
- Entities: public parameterless constructor and public settable properties (except a status with a private setter),
  so the database and tests can create them.
- Events: sealed records implementing Bank.Shared.Events.IDomainEvent (with DateTimeOffset OccurredAt), published with
  IEventBus.PublishAsync(...). Handlers implement IEventHandler<TEvent> and are registered in their module.
- Personal data properties get [Pii] (Bank.Shared). Never put personal data in events, logs or messages.
- Do not name a type "Ledger" outside the Ledger module (namespace clash).
- Keep files small; one public type per file unless they are tiny records.
