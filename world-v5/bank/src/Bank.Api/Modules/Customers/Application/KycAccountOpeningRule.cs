using Bank.Data;
using Bank.Modules.Accounts.Application;
using Bank.Modules.Customers.Domain;
using Microsoft.EntityFrameworkCore;

namespace Bank.Modules.Customers.Application;

public sealed class KycAccountOpeningRule : IAccountOpeningRule
{
    private readonly BankDbContext _db;

    public KycAccountOpeningRule(BankDbContext db) => _db = db;

    public async Task EnsureMayOpenAsync(string ownerId, CancellationToken ct = default)
    {
        var customer = await _db.Customers.FirstOrDefaultAsync(c => c.Id == ownerId, ct);
        if (customer is null || customer.Status != KycStatus.Verified)
            throw new UnauthorizedAccessException("Customer must be KYC verified before opening an account.");
    }
}
