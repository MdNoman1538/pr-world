using System.Text.Json;
using Bank.Modules.Auth;
using Bank.Modules.Loans.Application;
using Bank.Modules.Loans.Domain;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Bank.Modules.Loans.Api;

public sealed record ApplyLoanRequest(Guid DisbursementAccountId, decimal Principal, int TermMonths);

public sealed record ApproveLoanRequest(string? Note);

public sealed record RejectLoanRequest(string? Reason);

public sealed record LoanDto(
    Guid Id,
    string CustomerId,
    Guid DisbursementAccountId,
    decimal Principal,
    int TermMonths,
    decimal AnnualRatePercent,
    decimal MonthlyPayment,
    LoanStatus Status,
    string? DecidedBy,
    string? DecisionNote,
    DateTimeOffset AppliedAt);

[ApiController]
[Route("api/loans")]
[Authorize(Policy = Policies.Customer)]
public sealed class LoansController : ControllerBase
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);

    private readonly ILoanService _loans;

    public LoansController(ILoanService loans) => _loans = loans;

    [HttpPost]
    public async Task<ActionResult<LoanDto>> Apply(ApplyLoanRequest request, CancellationToken ct)
    {
        try
        {
            var loan = await _loans.ApplyAsync(new LoanApplication(request.DisbursementAccountId, request.Principal, request.TermMonths), ct);
            return ToDto(loan);
        }
        catch (UnauthorizedAccessException)
        {
            return Forbid();
        }
        catch (ArgumentException ex)
        {
            return BadRequest(ex.Message);
        }
    }

    [HttpGet("{id:guid}")]
    public async Task<ActionResult<LoanDto>> Get(Guid id, CancellationToken ct)
    {
        try
        {
            var loan = await _loans.GetAsync(id, ct);
            return ToDto(loan);
        }
        catch (KeyNotFoundException ex)
        {
            return NotFound(ex.Message);
        }
        catch (UnauthorizedAccessException)
        {
            return Forbid();
        }
    }

    [HttpPost("{id:guid}/approve")]
    [Authorize(Policy = Policies.LoanOfficer)]
    public async Task<ActionResult<LoanDto>> Approve(Guid id, CancellationToken ct)
    {
        try
        {
            var request = await ReadOptionalJsonBodyAsync<ApproveLoanRequest>(ct);
            var loan = await _loans.ApproveAsync(id, request?.Note, ct);
            return ToDto(loan);
        }
        catch (JsonException ex)
        {
            return BadRequest(ex.Message);
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
        catch (ArgumentException ex)
        {
            return BadRequest(ex.Message);
        }
    }

    [HttpPost("{id:guid}/reject")]
    [Authorize(Policy = Policies.LoanOfficer)]
    public async Task<ActionResult<LoanDto>> Reject(Guid id, CancellationToken ct)
    {
        try
        {
            var request = await ReadOptionalJsonBodyAsync<RejectLoanRequest>(ct);
            var loan = await _loans.RejectAsync(id, request?.Reason ?? "", ct);
            return ToDto(loan);
        }
        catch (JsonException ex)
        {
            return BadRequest(ex.Message);
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
        catch (ArgumentException ex)
        {
            return BadRequest(ex.Message);
        }
    }

    private async Task<T?> ReadOptionalJsonBodyAsync<T>(CancellationToken ct)
    {
        if (!Request.HasJsonContentType())
            return default;

        using var reader = new StreamReader(Request.Body);
        var body = await reader.ReadToEndAsync(ct);
        if (string.IsNullOrWhiteSpace(body))
            return default;

        return JsonSerializer.Deserialize<T>(body, JsonOptions);
    }

    private static LoanDto ToDto(Loan loan) =>
        new(
            loan.Id,
            loan.CustomerId,
            loan.DisbursementAccountId,
            loan.Principal,
            loan.TermMonths,
            loan.AnnualRatePercent,
            loan.MonthlyPayment,
            loan.Status,
            loan.DecidedBy,
            loan.DecisionNote,
            loan.AppliedAt);
}
