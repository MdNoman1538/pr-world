using Bank.Modules.Auth;
using Bank.Modules.Auth.Application;
using Bank.Modules.Customers.Application;
using Bank.Modules.Customers.Domain;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Bank.Modules.Customers.Api;

public sealed record CustomerDto(string Id, string FullName, string Email, KycStatus Status, string? DecidedBy, DateTimeOffset RegisteredAt);

[ApiController]
[Route("api/customers")]
[Authorize(Policy = Policies.Customer)]
public sealed class CustomersController : ControllerBase
{
    private readonly ICustomerService _customers;
    private readonly ICurrentUser _user;

    public CustomersController(ICustomerService customers, ICurrentUser user)
    {
        _customers = customers;
        _user = user;
    }

    [HttpPost]
    [Authorize(Policy = Policies.Customer)]
    public async Task<ActionResult<CustomerDto>> Register(RegisterCustomerRequest request, CancellationToken ct)
    {
        try
        {
            var customer = await _customers.RegisterAsync(request, ct);
            return ToDto(customer);
        }
        catch (ArgumentException ex)
        {
            return BadRequest(ex.Message);
        }
        catch (InvalidOperationException ex)
        {
            return Conflict(ex.Message);
        }
    }

    [HttpGet("me")]
    [Authorize(Policy = Policies.Customer)]
    public async Task<ActionResult<CustomerDto>> Me(CancellationToken ct)
    {
        var customer = await _customers.GetAsync(_user.UserId, ct);
        if (customer is null)
            return NotFound();
        return ToDto(customer);
    }

    [HttpPost("{id}/verify")]
    [Authorize(Policy = Policies.Compliance)]
    public async Task<ActionResult<CustomerDto>> Verify(string id, CancellationToken ct)
    {
        try
        {
            var customer = await _customers.VerifyAsync(id, ct);
            return ToDto(customer);
        }
        catch (UnauthorizedAccessException)
        {
            return Forbid();
        }
        catch (KeyNotFoundException)
        {
            return NotFound();
        }
        catch (InvalidOperationException ex)
        {
            return Conflict(ex.Message);
        }
    }

    [HttpPost("{id}/reject")]
    [Authorize(Policy = Policies.Compliance)]
    public async Task<ActionResult<CustomerDto>> Reject(string id, CancellationToken ct)
    {
        try
        {
            var customer = await _customers.RejectAsync(id, ct);
            return ToDto(customer);
        }
        catch (UnauthorizedAccessException)
        {
            return Forbid();
        }
        catch (KeyNotFoundException)
        {
            return NotFound();
        }
        catch (InvalidOperationException ex)
        {
            return Conflict(ex.Message);
        }
    }

    private static CustomerDto ToDto(Customer c) =>
        new(c.Id, c.FullName, c.Email, c.Status, c.DecidedBy, c.RegisteredAt);
}
