using System.Text.Json;
using Bank.Modules.Auth;
using Bank.Modules.Auth.Application;
using Bank.Modules.Payments.Application;
using Bank.Modules.Payments.Domain;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Bank.Modules.Payments.Api;

public sealed record RejectPaymentRequest(string? Reason);

public sealed record PaymentDto(
    Guid Id,
    string IdempotencyKey,
    string CustomerId,
    Guid FromAccountId,
    Guid ToAccountId,
    decimal Amount,
    string Currency,
    PaymentStatus Status,
    Guid? TransferId,
    string? Reference,
    DateTimeOffset CreatedAt)
{
    public decimal Fee { get; init; }
}

[ApiController]
[Route("api/payments")]
[Authorize(Policy = Policies.Customer)]
public sealed class PaymentsController : ControllerBase
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);

    private readonly IPaymentService _payments;
    private readonly IPaymentReviewService _review;
    private readonly ICurrentUser _user;

    public PaymentsController(IPaymentService payments, IPaymentReviewService review, ICurrentUser user)
    {
        _payments = payments;
        _review = review;
        _user = user;
    }

    [HttpGet("quote")]
    [Authorize(Policy = Policies.Customer)]
    public async Task<ActionResult<PaymentQuote>> Quote(
        [FromQuery] Guid from,
        [FromQuery] Guid to,
        [FromQuery] decimal amount,
        CancellationToken ct)
    {
        try
        {
            var quote = await _payments.QuoteAsync(from, to, amount, ct);
            return Ok(quote);
        }
        catch (UnauthorizedAccessException)
        {
            return Forbid();
        }
        catch (ArgumentException ex)
        {
            return BadRequest(ex.Message);
        }
        catch (KeyNotFoundException ex)
        {
            return NotFound(ex.Message);
        }
    }

    [HttpPost]
    public async Task<ActionResult<PaymentDto>> Pay(PaymentRequest request, CancellationToken ct)
    {
        try
        {
            var payment = await _payments.PayAsync(request, ct);
            return ToDto(payment);
        }
        catch (UnauthorizedAccessException)
        {
            return Forbid();
        }
        catch (ArgumentException ex)
        {
            return BadRequest(ex.Message);
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

    [HttpGet]
    public async Task<IEnumerable<PaymentDto>> Mine(CancellationToken ct) =>
        (await _payments.ForCustomerAsync(_user.UserId, ct)).Select(ToDto);

    [HttpGet("held")]
    [Authorize(Policy = Policies.Compliance)]
    public async Task<ActionResult<IEnumerable<PaymentDto>>> Held(CancellationToken ct)
    {
        try
        {
            var payments = await _review.HeldAsync(ct);
            return Ok(payments.Select(ToDto));
        }
        catch (UnauthorizedAccessException)
        {
            return Forbid();
        }
    }

    [HttpPost("{id:guid}/release")]
    [Authorize(Policy = Policies.Compliance)]
    public async Task<ActionResult<PaymentDto>> Release(Guid id, CancellationToken ct)
    {
        try
        {
            var payment = await _review.ReleaseAsync(id, ct);
            return ToDto(payment);
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

    [HttpPost("{id:guid}/reject")]
    [Authorize(Policy = Policies.Compliance)]
    public async Task<ActionResult<PaymentDto>> Reject(Guid id, CancellationToken ct)
    {
        try
        {
            var request = await ReadOptionalJsonBodyAsync<RejectPaymentRequest>(ct);
            var payment = await _review.RejectAsync(id, request?.Reason ?? "", ct);
            return ToDto(payment);
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

    private static PaymentDto ToDto(Payment p) =>
        new(
            p.Id,
            p.IdempotencyKey,
            p.CustomerId,
            p.FromAccountId,
            p.ToAccountId,
            p.Amount,
            p.Currency,
            p.Status,
            p.TransferId,
            p.Reference,
            p.CreatedAt)
        {
            Fee = p.Fee
        };
}
