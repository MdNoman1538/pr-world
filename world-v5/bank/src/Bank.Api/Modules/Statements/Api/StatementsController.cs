using Bank.Modules.Auth;
using Bank.Modules.Statements.Application;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Bank.Modules.Statements.Api;

[ApiController]
[Route("api/accounts/{id:guid}/statements")]
[Authorize(Policy = Policies.Customer)]
public sealed class StatementsController : ControllerBase
{
    private readonly IStatementService _statements;

    public StatementsController(IStatementService statements) => _statements = statements;

    [HttpGet("{year:int}/{month:int}")]
    public async Task<ActionResult<Statement>> GetForMonth(Guid id, int year, int month, CancellationToken ct)
    {
        try
        {
            var statement = await _statements.ForMonthAsync(id, year, month, ct);
            return Ok(statement);
        }
        catch (ArgumentOutOfRangeException ex)
        {
            return BadRequest(ex.Message);
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
}
