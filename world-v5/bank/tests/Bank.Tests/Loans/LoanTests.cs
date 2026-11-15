using Bank.Data;
using Bank.Modules.Accounts.Application;
using Bank.Modules.Auth;
using Bank.Modules.Auth.Application;
using Bank.Modules.Ledger.Domain;
using Bank.Modules.Loans.Application;
using Bank.Modules.Loans.Domain;
using Bank.Tests;
using Xunit;

namespace Bank.Tests.Loans;

public sealed class LoanTests
{
    private static LoanService CreateService(
        BankDbContext db,
        ICurrentUser user,
        FakeClock? clock = null,
        RecordingBus? bus = null,
        RecordingNotifier? notifier = null)
    {
        clock ??= new FakeClock();
        bus ??= new RecordingBus();
        notifier ??= new RecordingNotifier();
        var ledger = TestKit.Ledger(db, bus, clock);
        var accounts = new AccountService(db, user, TestKit.Settings(), clock, bus, Array.Empty<IAccountOpeningRule>());
        return new LoanService(db, ledger, accounts, user, clock, bus, notifier);
    }

    [Fact]
    public async Task Apply_persists_submitted_loan_and_publishes_event()
    {
        using var db = TestKit.Db();
        var clock = new FakeClock();
        var bus = new RecordingBus();
        var accountId = TestKit.Account(db, "alice");
        var service = CreateService(db, new FakeUser("alice", Roles.Customer), clock, bus);

        var created = await service.ApplyAsync(new LoanApplication(accountId, 10_000m, 12));

        var saved = db.Loans.Single(l => l.Id == created.Id);
        Assert.Equal("alice", saved.CustomerId);
        Assert.Equal(accountId, saved.DisbursementAccountId);
        Assert.Equal(10_000m, saved.Principal);
        Assert.Equal(12, saved.TermMonths);
        Assert.Equal(5.5m, saved.AnnualRatePercent);
        Assert.Equal(858.37m, saved.MonthlyPayment);
        Assert.Equal(LoanStatus.Submitted, saved.Status);
        Assert.Null(saved.DecidedBy);
        Assert.Null(saved.DecisionNote);
        Assert.Equal(clock.UtcNow, saved.AppliedAt);

        var submitted = Assert.IsType<LoanSubmitted>(Assert.Single(bus.Events));
        Assert.Equal(created.Id, submitted.LoanId);
        Assert.Equal("alice", submitted.CustomerId);
        Assert.Equal(10_000m, submitted.Principal);
        Assert.Equal(clock.UtcNow, submitted.OccurredAt);
    }

    [Theory]
    [InlineData(1000, 6, 169.35)]
    [InlineData(10000, 12, 858.37)]
    [InlineData(50000, 120, 542.63)]
    public async Task Apply_accepts_inclusive_boundaries_and_rounds_annuity_away_from_zero(
        decimal principal, int termMonths, decimal expectedMonthlyPayment)
    {
        using var db = TestKit.Db();
        var accountId = TestKit.Account(db, "alice");
        var service = CreateService(db, new FakeUser("alice", Roles.Customer));

        var loan = await service.ApplyAsync(new LoanApplication(accountId, principal, termMonths));

        Assert.Equal(5.5m, loan.AnnualRatePercent);
        Assert.Equal(expectedMonthlyPayment, loan.MonthlyPayment);
        Assert.Equal(LoanStatus.Submitted, loan.Status);
    }

    [Theory]
    [InlineData(999.99, 12)]
    [InlineData(50000.01, 12)]
    [InlineData(0, 12)]
    [InlineData(-1000, 12)]
    [InlineData(10000, 5)]
    [InlineData(10000, 121)]
    [InlineData(10000, 0)]
    [InlineData(10000, -6)]
    public async Task Apply_rejects_out_of_range_principal_or_term(decimal principal, int termMonths)
    {
        using var db = TestKit.Db();
        var bus = new RecordingBus();
        var accountId = TestKit.Account(db, "alice");
        var service = CreateService(db, new FakeUser("alice", Roles.Customer), bus: bus);

        await Assert.ThrowsAsync<ArgumentException>(() =>
            service.ApplyAsync(new LoanApplication(accountId, principal, termMonths)));

        Assert.Empty(db.Loans);
        Assert.Empty(bus.Events);
    }

    [Fact]
    public async Task Apply_throws_when_disbursement_account_not_owned_by_caller()
    {
        using var db = TestKit.Db();
        var bus = new RecordingBus();
        var bobsAccountId = TestKit.Account(db, "bob");
        var service = CreateService(db, new FakeUser("alice", Roles.Customer), bus: bus);

        await Assert.ThrowsAsync<UnauthorizedAccessException>(() =>
            service.ApplyAsync(new LoanApplication(bobsAccountId, 5_000m, 12)));
        await Assert.ThrowsAsync<UnauthorizedAccessException>(() =>
            service.ApplyAsync(new LoanApplication(Guid.NewGuid(), 5_000m, 12)));

        Assert.Empty(db.Loans);
        Assert.Empty(bus.Events);
    }

    [Fact]
    public async Task Get_allows_owner_and_loan_officer_and_rejects_others_or_unknown()
    {
        using var db = TestKit.Db();
        var accountId = TestKit.Account(db, "alice");
        var aliceService = CreateService(db, new FakeUser("alice", Roles.Customer));
        var loan = await aliceService.ApplyAsync(new LoanApplication(accountId, 2_000m, 12));

        var ownerView = await aliceService.GetAsync(loan.Id);
        Assert.Equal(loan.Id, ownerView.Id);

        var officerService = CreateService(db, new FakeUser("officer-1", Roles.LoanOfficer));
        var officerView = await officerService.GetAsync(loan.Id);
        Assert.Equal(loan.Id, officerView.Id);

        var otherCustomerService = CreateService(db, new FakeUser("bob", Roles.Customer));
        await Assert.ThrowsAsync<UnauthorizedAccessException>(() => otherCustomerService.GetAsync(loan.Id));

        var tellerService = CreateService(db, new FakeUser("teller-1", Roles.Teller));
        await Assert.ThrowsAsync<UnauthorizedAccessException>(() => tellerService.GetAsync(loan.Id));

        await Assert.ThrowsAsync<KeyNotFoundException>(() => officerService.GetAsync(Guid.NewGuid()));
    }

    [Fact]
    public async Task Approve_disburses_in_account_currency_publishes_event_and_notifies_without_pii()
    {
        using var db = TestKit.Db();
        var clock = new FakeClock();
        var bus = new RecordingBus();
        var notifier = new RecordingNotifier();
        var accountId = TestKit.Account(db, "alice-customer", 100m, "SEK");
        var iban = db.Accounts.Single(a => a.Id == accountId).Iban;

        var customerService = CreateService(db, new FakeUser("alice-customer", Roles.Customer), clock, bus, notifier);
        var loan = await customerService.ApplyAsync(new LoanApplication(accountId, 5_000m, 24));
        bus.Events.Clear();

        clock.Advance(TimeSpan.FromHours(2));
        var officerService = CreateService(db, new FakeUser("officer-1", Roles.LoanOfficer), clock, bus, notifier);
        var approved = await officerService.ApproveAsync(loan.Id, "Verified income");

        var saved = db.Loans.Single(l => l.Id == loan.Id);
        Assert.Equal(LoanStatus.Disbursed, approved.Status);
        Assert.Equal(LoanStatus.Disbursed, saved.Status);
        Assert.Equal("officer-1", saved.DecidedBy);
        Assert.Equal("Verified income", saved.DecisionNote);

        Assert.Equal(5_100m, TestKit.Balance(db, accountId));
        Assert.Equal(-5_000m, TestKit.Balance(db, BankAccounts.For(BankAccountKind.LoanFunding, "SEK")));
        Assert.Equal(0m, TestKit.Balance(db, BankAccounts.For(BankAccountKind.LoanFunding, "EUR")));

        var evt = Assert.IsType<LoanApproved>(Assert.Single(bus.Events));
        Assert.Equal(loan.Id, evt.LoanId);
        Assert.Equal("alice-customer", evt.CustomerId);
        Assert.Equal(5_000m, evt.Principal);
        Assert.Equal(clock.UtcNow, evt.OccurredAt);

        var notification = Assert.Single(notifier.Sent);
        Assert.Equal("alice-customer", notification.CustomerId);
        Assert.False(string.IsNullOrWhiteSpace(notification.Message));
        Assert.DoesNotContain("alice-customer", notification.Message, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain(iban, notification.Message, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain(accountId.ToString(), notification.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task Approve_allows_null_note()
    {
        using var db = TestKit.Db();
        var accountId = TestKit.Account(db, "alice");
        var customerService = CreateService(db, new FakeUser("alice", Roles.Customer));
        var loan = await customerService.ApplyAsync(new LoanApplication(accountId, 1_500m, 12));

        var officerService = CreateService(db, new FakeUser("officer-1", Roles.LoanOfficer));
        var approved = await officerService.ApproveAsync(loan.Id, null);

        Assert.Equal(LoanStatus.Disbursed, approved.Status);
        Assert.Null(approved.DecisionNote);
    }

    [Fact]
    public async Task Approve_enforces_role_four_eyes_and_submitted_status()
    {
        using var db = TestKit.Db();
        var bus = new RecordingBus();
        var notifier = new RecordingNotifier();
        var accountId = TestKit.Account(db, "alice-officer", 0m, "EUR");

        var dualRoleService = CreateService(db, new FakeUser("alice-officer", Roles.Customer, Roles.LoanOfficer), bus: bus, notifier: notifier);
        var loan = await dualRoleService.ApplyAsync(new LoanApplication(accountId, 3_000m, 12));
        bus.Events.Clear();

        await Assert.ThrowsAsync<UnauthorizedAccessException>(() =>
            dualRoleService.ApproveAsync(loan.Id, "Self-approved"));

        var tellerService = CreateService(db, new FakeUser("teller-1", Roles.Teller), bus: bus, notifier: notifier);
        await Assert.ThrowsAsync<UnauthorizedAccessException>(() =>
            tellerService.ApproveAsync(loan.Id, "Not an officer"));

        var customerService = CreateService(db, new FakeUser("bob", Roles.Customer), bus: bus, notifier: notifier);
        await Assert.ThrowsAsync<UnauthorizedAccessException>(() =>
            customerService.ApproveAsync(loan.Id, "Not an officer"));

        Assert.Equal(LoanStatus.Submitted, db.Loans.Single(l => l.Id == loan.Id).Status);
        Assert.Equal(0m, TestKit.Balance(db, accountId));
        Assert.Empty(bus.Events);
        Assert.Empty(notifier.Sent);

        var independentOfficer = CreateService(db, new FakeUser("officer-2", Roles.LoanOfficer), bus: bus, notifier: notifier);
        await Assert.ThrowsAsync<KeyNotFoundException>(() => independentOfficer.ApproveAsync(Guid.NewGuid(), "missing"));

        await independentOfficer.ApproveAsync(loan.Id, "Approved");
        await Assert.ThrowsAsync<InvalidOperationException>(() => independentOfficer.ApproveAsync(loan.Id, "Duplicate"));
        Assert.Equal(3_000m, TestKit.Balance(db, accountId));
    }

    [Fact]
    public async Task Reject_transitions_loan_publishes_event_and_notifies_without_pii()
    {
        using var db = TestKit.Db();
        var clock = new FakeClock();
        var bus = new RecordingBus();
        var notifier = new RecordingNotifier();
        var accountId = TestKit.Account(db, "alice-customer", 50m, "EUR");
        var iban = db.Accounts.Single(a => a.Id == accountId).Iban;

        var customerService = CreateService(db, new FakeUser("alice-customer", Roles.Customer), clock, bus, notifier);
        var loan = await customerService.ApplyAsync(new LoanApplication(accountId, 4_000m, 18));
        bus.Events.Clear();

        clock.Advance(TimeSpan.FromHours(1));
        var officerService = CreateService(db, new FakeUser("officer-2", Roles.LoanOfficer), clock, bus, notifier);
        var rejected = await officerService.RejectAsync(loan.Id, "Insufficient credit history");

        var saved = db.Loans.Single(l => l.Id == loan.Id);
        Assert.Equal(LoanStatus.Rejected, rejected.Status);
        Assert.Equal(LoanStatus.Rejected, saved.Status);
        Assert.Equal("officer-2", saved.DecidedBy);
        Assert.Equal("Insufficient credit history", saved.DecisionNote);
        Assert.Equal(50m, TestKit.Balance(db, accountId));
        Assert.Equal(0m, TestKit.Balance(db, BankAccounts.For(BankAccountKind.LoanFunding, "EUR")));

        var evt = Assert.IsType<LoanRejected>(Assert.Single(bus.Events));
        Assert.Equal(loan.Id, evt.LoanId);
        Assert.Equal("alice-customer", evt.CustomerId);
        Assert.Equal(clock.UtcNow, evt.OccurredAt);

        var notification = Assert.Single(notifier.Sent);
        Assert.Equal("alice-customer", notification.CustomerId);
        Assert.False(string.IsNullOrWhiteSpace(notification.Message));
        Assert.DoesNotContain("alice-customer", notification.Message, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain(iban, notification.Message, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain(accountId.ToString(), notification.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task Reject_enforces_role_four_eyes_reason_and_submitted_status()
    {
        using var db = TestKit.Db();
        var accountId = TestKit.Account(db, "alice-officer");
        var dualRoleService = CreateService(db, new FakeUser("alice-officer", Roles.Customer, Roles.LoanOfficer));
        var loan = await dualRoleService.ApplyAsync(new LoanApplication(accountId, 2_000m, 12));

        await Assert.ThrowsAsync<UnauthorizedAccessException>(() =>
            dualRoleService.RejectAsync(loan.Id, "Self-rejected"));

        var nonOfficerService = CreateService(db, new FakeUser("bob", Roles.Teller));
        await Assert.ThrowsAsync<UnauthorizedAccessException>(() =>
            nonOfficerService.RejectAsync(loan.Id, "Not allowed"));

        var independentOfficer = CreateService(db, new FakeUser("officer-2", Roles.LoanOfficer));
        await Assert.ThrowsAsync<KeyNotFoundException>(() => independentOfficer.RejectAsync(Guid.NewGuid(), "Missing"));
        await Assert.ThrowsAsync<ArgumentException>(() => independentOfficer.RejectAsync(loan.Id, ""));
        await Assert.ThrowsAsync<ArgumentException>(() => independentOfficer.RejectAsync(loan.Id, "   "));
        await Assert.ThrowsAsync<ArgumentException>(() => independentOfficer.RejectAsync(loan.Id, null!));
        Assert.Equal(LoanStatus.Submitted, db.Loans.Single(l => l.Id == loan.Id).Status);

        await independentOfficer.RejectAsync(loan.Id, "Declined");
        await Assert.ThrowsAsync<InvalidOperationException>(() => independentOfficer.RejectAsync(loan.Id, "Again"));
        await Assert.ThrowsAsync<InvalidOperationException>(() => independentOfficer.ApproveAsync(loan.Id, "Approve after reject"));
    }

    [Fact]
    public async Task Reject_after_disbursement_throws_invalid_operation()
    {
        using var db = TestKit.Db();
        var accountId = TestKit.Account(db, "alice");
        var customerService = CreateService(db, new FakeUser("alice", Roles.Customer));
        var loan = await customerService.ApplyAsync(new LoanApplication(accountId, 2_000m, 12));

        var officerService = CreateService(db, new FakeUser("officer-1", Roles.LoanOfficer));
        await officerService.ApproveAsync(loan.Id, "Approved");

        await Assert.ThrowsAsync<InvalidOperationException>(() => officerService.RejectAsync(loan.Id, "Too late"));
    }
}
