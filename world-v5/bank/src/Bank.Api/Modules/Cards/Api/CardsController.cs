using Bank.Modules.Auth;
using Bank.Modules.Cards.Application;
using Bank.Modules.Cards.Domain;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Bank.Modules.Cards.Api;

public sealed record IssueCardRequest(Guid AccountId);

public sealed record AuthoriseCardRequest(decimal Amount, string Merchant);

public sealed record CardDto(Guid Id, Guid AccountId, string CustomerId, string Last4, CardStatus Status, decimal PerTransactionLimit);

[ApiController]
[Route("api/cards")]
[Authorize(Policy = Policies.Customer)]
public sealed class CardsController : ControllerBase
{
    private readonly ICardService _cards;

    public CardsController(ICardService cards) => _cards = cards;

    [HttpPost]
    public async Task<ActionResult<CardDto>> Issue(IssueCardRequest request, CancellationToken ct)
    {
        try
        {
            var card = await _cards.IssueAsync(request.AccountId, ct);
            return ToDto(card);
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

    [HttpPost("{id:guid}/freeze")]
    public async Task<ActionResult<CardDto>> Freeze(Guid id, CancellationToken ct)
    {
        try
        {
            var card = await _cards.FreezeAsync(id, ct);
            return ToDto(card);
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

    [HttpPost("{id:guid}/unfreeze")]
    public async Task<ActionResult<CardDto>> Unfreeze(Guid id, CancellationToken ct)
    {
        try
        {
            var card = await _cards.UnfreezeAsync(id, ct);
            return ToDto(card);
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

    [HttpPost("{id:guid}/cancel")]
    public async Task<ActionResult<CardDto>> Cancel(Guid id, CancellationToken ct)
    {
        try
        {
            var card = await _cards.CancelAsync(id, ct);
            return ToDto(card);
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

    [HttpPost("{id:guid}/authorise")]
    [Authorize(Policy = Policies.Staff)]
    public async Task<ActionResult<CardAuthorisation>> Authorise(Guid id, AuthoriseCardRequest request, CancellationToken ct)
    {
        try
        {
            var result = await _cards.AuthoriseAsync(id, request.Amount, request.Merchant, ct);
            return Ok(result);
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

    private static CardDto ToDto(Card card) =>
        new(card.Id, card.AccountId, card.CustomerId, card.Last4, card.Status, card.PerTransactionLimit);
}
