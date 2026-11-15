using Bank.Modules.Auth;
using Bank.Modules.Deposits.Application;
using Bank.Modules.Deposits.Domain;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Bank.Modules.Deposits.Api;

public sealed record OpenDepositRequest(Guid AccountId, decimal Principal, int TermMonths);

public sealed record TermDepositDto(
    Guid Id,
    string CustomerId,
    Guid AccountId,
    decimal Principal,
    string Currency,
    int TermMonths,
    decimal AnnualRatePercent,
    DateTimeOffset OpenedAt,
    DateTimeOffset MaturesAt,
    DepositStatus Status,
    decimal InterestPaid);

[ApiController]
[Route("api/deposits")]
[Authorize(Policy = Policies.Customer)]
public sealed class DepositsController : ControllerBase
{
    private readonly IDepositService _deposits;

    public DepositsController(IDepositService deposits) => _deposits = deposits;

    [HttpPost]
    [Authorize(Policy = Policies.Customer)]
    public async Task<ActionResult<TermDepositDto>> Open(OpenDepositRequest request, CancellationToken ct)
    {
        try
        {
            var deposit = await _deposits.OpenAsync(request.AccountId, request.Principal, request.TermMonths, ct);
            return ToDto(deposit);
        }
        catch (UnauthorizedAccessException)
        {
            return Forbid();
        }
        catch (KeyNotFoundException ex)
        {
            return NotFound(ex.Message);
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

    [HttpPost("{id:guid}/mature")]
    [Authorize(Policy = Policies.Staff)]
    public async Task<ActionResult<TermDepositDto>> Mature(Guid id, CancellationToken ct)
    {
        try
        {
            var deposit = await _deposits.MatureAsync(id, ct);
            return ToDto(deposit);
        }
        catch (KeyNotFoundException ex)
        {
            return NotFound(ex.Message);
        }
        catch (InvalidOperationException ex)
        {
            return Conflict(ex.Message);
        }
    }

    [HttpPost("{id:guid}/break")]
    [Authorize(Policy = Policies.Customer)]
    public async Task<ActionResult<TermDepositDto>> Break(Guid id, CancellationToken ct)
    {
        try
        {
            var deposit = await _deposits.BreakAsync(id, ct);
            return ToDto(deposit);
        }
        catch (UnauthorizedAccessException)
        {
            return Forbid();
        }
        catch (KeyNotFoundException ex)
        {
            return NotFound(ex.Message);
        }
        catch (InvalidOperationException ex)
        {
            return Conflict(ex.Message);
        }
    }

    private static TermDepositDto ToDto(TermDeposit d) =>
        new(
            d.Id,
            d.CustomerId,
            d.AccountId,
            d.Principal,
            d.Currency,
            d.TermMonths,
            d.AnnualRatePercent,
            d.OpenedAt,
            d.MaturesAt,
            d.Status,
            d.InterestPaid);
}
