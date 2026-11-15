using Bank.Modules.Accounts.Application;
using Bank.Modules.Auth;
using Bank.Modules.Auth.Application;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Bank.Modules.Accounts.Api;

public sealed record AccountDto(Guid Id, string Iban, string Currency, decimal Balance);
public sealed record OpenAccountRequest(string? Currency);

[ApiController]
[Route("api/accounts")]
[Authorize(Policy = Policies.Customer)]
public sealed class AccountsController : ControllerBase
{
    private readonly IAccountService _accounts;
    private readonly ICurrentUser _user;

    public AccountsController(IAccountService accounts, ICurrentUser user)
    {
        _accounts = accounts;
        _user = user;
    }

    [HttpGet]
    public async Task<IEnumerable<AccountDto>> Mine(CancellationToken ct) =>
        (await _accounts.ForOwnerAsync(_user.UserId, ct)).Select(a => new AccountDto(a.Id, a.Iban, a.Currency, a.Balance));

    [HttpGet("{id:guid}")]
    public async Task<ActionResult<AccountDto>> Get(Guid id, CancellationToken ct)
    {
        var a = await _accounts.GetAsync(id, ct);
        if (a is null || a.OwnerId != _user.UserId)
            return NotFound();
        return new AccountDto(a.Id, a.Iban, a.Currency, a.Balance);
    }

    [HttpPost]
    public async Task<ActionResult<AccountDto>> Open(OpenAccountRequest request, CancellationToken ct)
    {
        var a = await _accounts.OpenAsync(request.Currency, ct);
        return new AccountDto(a.Id, a.Iban, a.Currency, a.Balance);
    }
}
