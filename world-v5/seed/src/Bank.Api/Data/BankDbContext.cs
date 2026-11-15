using Bank.Modules.Accounts.Domain;
using Bank.Modules.Audit.Domain;
using Bank.Modules.Ledger.Domain;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Storage.ValueConversion;

namespace Bank.Data;

public sealed class BankDbContext : DbContext
{
    public BankDbContext(DbContextOptions<BankDbContext> options) : base(options)
    {
    }

    public DbSet<Account> Accounts => Set<Account>();
    public DbSet<LedgerEntry> LedgerEntries => Set<LedgerEntry>();
    public DbSet<AuditEntry> AuditEntries => Set<AuditEntry>();
    // TABLES: modules add their DbSet above this line

    protected override void ConfigureConventions(ModelConfigurationBuilder configurationBuilder)
    {
        // SQLite cannot compare or sort DateTimeOffset values: store them as sortable numbers.
        configurationBuilder.Properties<DateTimeOffset>().HaveConversion<DateTimeOffsetToBinaryConverter>();
    }

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        // The bank's own accounts: one per purpose and currency (see BankAccounts).
        var seed = new List<Account>();
        foreach (var kind in Enum.GetValues<BankAccountKind>())
        foreach (var currency in BankAccounts.Currencies)
            seed.Add(new Account
            {
                Id = BankAccounts.For(kind, currency),
                OwnerId = "bank",
                Iban = $"FI00BANK{(int)kind:D2}{currency}",
                Currency = currency,
                Kind = AccountKind.Internal,
                AllowOverdraft = true,
                Balance = 0m,
                OpenedAt = new DateTimeOffset(2026, 1, 1, 0, 0, 0, TimeSpan.Zero),
            });
        modelBuilder.Entity<Account>().HasData(seed);
    }
}
