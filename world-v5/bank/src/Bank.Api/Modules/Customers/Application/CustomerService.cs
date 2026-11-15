using Bank.Data;
using Bank.Modules.Auth;
using Bank.Modules.Auth.Application;
using Bank.Modules.Customers.Domain;
using Bank.Shared.Events;
using Bank.Shared.Time;
using Microsoft.EntityFrameworkCore;

namespace Bank.Modules.Customers.Application;

public sealed record RegisterCustomerRequest(string FullName, string Email, string NationalId, DateOnly DateOfBirth);

public interface ICustomerService
{
    Task<Customer> RegisterAsync(RegisterCustomerRequest request, CancellationToken ct = default);
    Task<Customer> VerifyAsync(string customerId, CancellationToken ct = default);
    Task<Customer> RejectAsync(string customerId, CancellationToken ct = default);
    Task<Customer?> GetAsync(string customerId, CancellationToken ct = default);
}

public sealed class CustomerService : ICustomerService
{
    private readonly BankDbContext _db;
    private readonly ICurrentUser _user;
    private readonly IClock _clock;
    private readonly IEventBus _bus;

    public CustomerService(BankDbContext db, ICurrentUser user, IClock clock, IEventBus bus)
    {
        _db = db;
        _user = user;
        _clock = clock;
        _bus = bus;
    }

    public async Task<Customer> RegisterAsync(RegisterCustomerRequest request, CancellationToken ct = default)
    {
        ArgumentNullException.ThrowIfNull(request);
        if (string.IsNullOrWhiteSpace(request.FullName))
            throw new ArgumentException("Full name is required.", nameof(request));
        if (string.IsNullOrWhiteSpace(request.Email))
            throw new ArgumentException("Email is required.", nameof(request));
        if (string.IsNullOrWhiteSpace(request.NationalId))
            throw new ArgumentException("National id is required.", nameof(request));

        var now = _clock.UtcNow;
        var today = DateOnly.FromDateTime(now.UtcDateTime);
        var minDob = today.Year > 18 ? today.AddYears(-18) : DateOnly.MinValue;
        if (request.DateOfBirth > minDob)
            throw new ArgumentException("Applicant must be at least 18 years old.", nameof(request));

        var userId = _user.UserId;
        if (await _db.Customers.AnyAsync(c => c.Id == userId, ct))
            throw new InvalidOperationException("Customer is already registered.");

        var customer = new Customer
        {
            Id = userId,
            FullName = request.FullName,
            Email = request.Email,
            NationalId = request.NationalId,
            DateOfBirth = request.DateOfBirth,
            RegisteredAt = now,
        };
        _db.Customers.Add(customer);
        await _db.SaveChangesAsync(ct);
        await _bus.PublishAsync(new CustomerRegistered(customer.Id, now), ct);
        return customer;
    }

    public async Task<Customer> VerifyAsync(string customerId, CancellationToken ct = default)
    {
        if (!_user.IsInRole(Roles.ComplianceOfficer))
            throw new UnauthorizedAccessException("Only a compliance officer may verify a customer.");
        var officerId = _user.UserId;
        if (officerId == customerId)
            throw new UnauthorizedAccessException("Compliance officers cannot verify themselves.");

        var customer = await _db.Customers.FirstOrDefaultAsync(c => c.Id == customerId, ct)
            ?? throw new KeyNotFoundException($"Customer {customerId} not found.");

        customer.Verify(officerId);
        await _db.SaveChangesAsync(ct);
        await _bus.PublishAsync(new CustomerVerified(customer.Id, officerId, _clock.UtcNow), ct);
        return customer;
    }

    public async Task<Customer> RejectAsync(string customerId, CancellationToken ct = default)
    {
        if (!_user.IsInRole(Roles.ComplianceOfficer))
            throw new UnauthorizedAccessException("Only a compliance officer may reject a customer.");
        var officerId = _user.UserId;
        if (officerId == customerId)
            throw new UnauthorizedAccessException("Compliance officers cannot reject themselves.");

        var customer = await _db.Customers.FirstOrDefaultAsync(c => c.Id == customerId, ct)
            ?? throw new KeyNotFoundException($"Customer {customerId} not found.");

        customer.Reject(officerId);
        await _db.SaveChangesAsync(ct);
        await _bus.PublishAsync(new CustomerRejected(customer.Id, officerId, _clock.UtcNow), ct);
        return customer;
    }

    public Task<Customer?> GetAsync(string customerId, CancellationToken ct = default) =>
        _db.Customers.FirstOrDefaultAsync(c => c.Id == customerId, ct);
}
