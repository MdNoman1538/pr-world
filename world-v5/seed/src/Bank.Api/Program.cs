using Bank.Data;
using Bank.Modules.Accounts;
using Bank.Modules.Audit;
using Bank.Modules.Auth;
using Bank.Modules.Ledger;
using Bank.Modules.Notifications;
using Bank.Shared;
using Bank.Shared.Events;
using Microsoft.EntityFrameworkCore;

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddDbContext<BankDbContext>(o =>
    o.UseSqlite(builder.Configuration.GetConnectionString("Bank") ?? "Data Source=bank.db"));
builder.Services.AddControllers();
builder.Services.AddShared();
builder.Services.AddEventBus();
builder.Services.AddAuthModule();
builder.Services.AddAccountsModule();
builder.Services.AddLedgerModule();
builder.Services.AddAuditModule();
builder.Services.AddNotificationsModule();
// MODULES: register new modules above this line

var app = builder.Build();
using (var scope = app.Services.CreateScope())
{
    scope.ServiceProvider.GetRequiredService<BankDbContext>().Database.EnsureCreated();
}
app.UseAuthentication();
app.UseAuthorization();
app.MapControllers();
app.Run();

public partial class Program { }
