# AI review · pr-8 → main

**Decision: BLOCKED** · Tier **HIGH** · 2 sign-off(s) required · Requirement **PR-8** · Owner: **Md Abdullah Al Noman**

> Merge locked: Tests: Tests failed; Correctness: 1 Blocker(s) Not checked: Requirement. WARNING: review-policy.yaml is not approved by a named human yet.

The AI review is advice with evidence. It is not an approval. A named human owns the decision.

## What the change does (orientation)

PR-8 introduces the Bank.Modules.Statements module, providing monthly statement calculation (StatementService) and a GET API endpoint (StatementsController). It retrieves ledger entries to compute the opening balance, chronologically ordered statement lines with running balances, and closing balance for an account over a calendar month in UTC. The controller is secured for customer/staff access and maps domain exceptions to HTTP status codes.

Requirement alignment: **partial**

Optimization context detected: research shows AI optimizations most often introduce memory-safety flaws, so safety and performance were reviewed with extra care.

## Requirement radar

Radar call failed: radar: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported methods.', 'status': 'NOT_FOUND'}}

| Hunk | File:lines | Classification | Items | Why |
| --- | --- | --- | --- | --- |
| H01 | src/Bank.Api/Modules/Statements/Api/StatementsController.cs:1-38 | unclear | - | radar failed |
| H02 | src/Bank.Api/Modules/Statements/Application/StatementService.cs:1-77 | unclear | - | radar failed |
| H03 | src/Bank.Api/Modules/Statements/StatementsModule.cs:1-12 | unclear | - | radar failed |
| H04 | src/Bank.Api/Program.cs:14-14 | unclear | - | radar failed |
| H05 | src/Bank.Api/Program.cs:37-37 | unclear | - | radar failed |
| H06 | tests/Bank.Tests/Statements/StatementTests.cs:1-371 | unclear | - | radar failed |

## Second opinion on Critical findings (validator panel)

- C01: 0 of 1 reviewers say real → not enough votes

## Investigator

- C01: unsure after 0 step(s). investigator call failed: investigator: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateConten

## Not checked (never counted as passed)

- specialist.tests · Tests · not part of Essential coverage
- specialist.architecture · Tests · not part of Essential coverage
- specialist.maintainability · Tests · not part of Essential coverage
- specialist.performance · Tests · not part of Essential coverage
- validator_panel · Tests · not part of Essential coverage
- investigator · Tests · not part of Essential coverage
- requirement_check · Tests · not part of Essential coverage
- radar · Tests · not part of Essential coverage
- fixer · Tests · not part of Essential coverage
- requirement_check · (all touched) · requirement check failed: requirement:analyst: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported metho

Noise funnel: 3 proposed by specialists → 3 with verified evidence (0 hallucinated dropped) → 0 removed by validator → 3 shown (incl. 0 deterministic sensor findings); 0 ready-to-apply patch(es).

## Every area

| Area | Status | Reason |
| --- | --- | --- |
| What | HUMAN CHECK | Requirement match is partial: The module structure, routing, models, and authorization checks meet the requirement. However, month boundary handling in StatementService fails to enforce exclusive upper bounds on ledger queries, causing entries at midnight UTC on month boundaries to be included in both opening balance and statement lines. |
| Where | HUMAN CHECK | Tier HIGH → full human read and 2 sign-off(s) required<br>src/Bank.Api/Modules/Statements/Api/StatementsController.cs: area 'Statements' is medium (What customers see about their money)<br>src/Bank.Api/Modules/Statements/Api/StatementsController.cs: content rule 'authorization attribute changed' matched → high<br>src/Bank.Api/Modules/Statements/Application/StatementService.cs: area 'Statements' is medium (What customers see about their money)<br>src/Bank.Api/Modules/Statements/StatementsModule.cs: area 'Statements' is medium (What customers see about their money) |
| Why | VERIFIED | Linked to a requirement |
| Security | VERIFIED | No secrets, no unverified packages, no safety findings |
| Build | VERIFIED | Build succeeded |
| Tests | BLOCKED | Tests failed<br>Failed!  - Failed:     4, Passed:   213, Skipped:     0, Total:   217, Duration: 1 s - Bank.Tests.dll (net10.0) |
| Correctness | BLOCKED | 1 Blocker(s)<br>C01 src/Bank.Api/Modules/Statements/Application/StatementService.cs:45 |
| Architecture | VERIFIED | No blocking issue |
| Maintainability | VERIFIED | No blocking issue |
| Performance | VERIFIED | No blocking issue |
| Impact | VERIFIED | 19 changed member(s); callers covered by tests or none |
| Requirement | NOT CHECKED | Not checked: requirement check failed: requirement:analyst: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported metho |

## What the AI found (3 shown, 0 filtered as noise)

- **[Blocker] C01 · Inclusive upper bounds in ledger queries violate UTC month boundary exclusion** (correctness, specialist:correctness · confidence 0.95) `src/Bank.Api/Modules/Statements/Application/StatementService.cs:45`

  ledger.EntriesAsync evaluates ranges with inclusive upper bounds. Passing monthStart when retrieving prior entries causes entries at exactly YYYY-MM-01T00:00:00Z to be included in opening balance, while passing monthEnd causes entries at 00:00:00Z on the 1st of the next month to be included in the current month's lines. This violates strict month boundary criteria and causes boundary tests to fail.

  ```
  var priorEntries = await ledger.EntriesAsync(accountId, DateTimeOffset.MinValue, monthStart, ct);
  var openingBalance = Math.Round(priorEntries.Sum(e => e.Amount), 2, MidpointRounding.AwayFromZero);
  
  var monthEntries = await ledger.EntriesAsync(accountId, monthStart, monthEnd, ct);
  var orderedEntries = monthEntries.OrderBy(e => e.CreatedAt).ToList();
  ```

  Requirement: Month boundaries are strictly UTC: include entries with timestamp >= YYYY-MM-01T00:00:00Z and < (YYYY-MM-01 + 1 month)T00:00:00Z; entries at exactly 00:00:00Z on the 1st of the next month belong to the next month and are excluded.

  Suggested fix: Filter priorEntries with .Where(e => e.CreatedAt < monthStart) and monthEntries with .Where(e => e.CreatedAt >= monthStart && e.CreatedAt < monthEnd) so that midnight UTC boundary entries are strictly excluded as required.

- **[ShouldFix] T01 · StatementsController endpoint and HTTP status mappings have no test coverage** (tests, specialist:tests · confidence 0.95) `src/Bank.Api/Modules/Statements/Api/StatementsController.cs:17`

  StatementsController is completely uncovered by tests. The requirement acceptance criteria explicitly specify endpoint routing, [Authorize(Policy = Policies.Customer)], 401 for unauthenticated calls, and exception-to-HTTP-status mappings (400, 404, 403), none of which are validated by any unit or integration tests.

  ```
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
  ```

  Requirement: Expose GET api/accounts/{id}/statements/{year}/{month} on a controller decorated with [ApiController] and [Authorize(Policy = Policies.Customer)], returning HTTP 200 OK with the Statement payload.

  Suggested fix: Add controller unit or integration tests verifying that GET api/accounts/{id}/statements/{year}/{month} returns 200 OK for valid requests, 401 for unauthenticated calls, 403 when forbidden, 404 on missing account, and 400 on invalid calendar inputs.

- **[ShouldFix] T02 · Tautological assertion recalculates running balance over returned lines without checking expected line order** (tests, specialist:tests · confidence 0.85) `tests/Bank.Tests/Statements/StatementTests.cs:238`

  The test re-computes running balances by looping over the returned statement.Lines array in whatever sequence the service returned them. Because two transactions share the identical timestamp (10:00:00), an arbitrary or reversed ordering would still pass the assertion loop without verifying expected transaction sequence or reference order.

  ```
  var running = statement.OpeningBalance;
  DateTimeOffset? previousAt = null;
  foreach (var line in statement.Lines)
  {
  if (previousAt is not null)
  Assert.True(line.At >= previousAt.Value);
  running = Math.Round(running + line.Amount, 2, MidpointRounding.AwayFromZero);
  Assert.Equal(running, line.BalanceAfter);
  previousAt = line.At;
  }
  ```

  Requirement: Lines are ordered chronologically by At ascending, and each line's BalanceAfter equals the prior balance plus that line's signed Amount, rounded to 2 decimal places with MidpointRounding.AwayFromZero.

  Suggested fix: Assert expected line references, individual amounts, and explicit BalanceAfter values for statement.Lines[0], statement.Lines[1], and statement.Lines[2] directly rather than looping and recalculating.

## What the AI refused to decide, and why

- **ILedger.EntriesAsync implementation details** (specialist:correctness): The source implementation of LedgerService is not within the provided pull request context; inclusive boundary behavior is inferred from requirement notes and failing test execution.
- **Secondary sort key for identical timestamps** (specialist:correctness): The declaration of LedgerEntry is outside the context, so whether an Id or SequenceNumber field exists to ensure deterministic ordering on equal timestamps cannot be verified without guessing.
- **Test failure root cause** (specialist:architecture): Deterministic sensors indicate dotnet_test failed (exit 1), but specific test execution output and error stack traces were not provided in the review context.
- **dotnet_test failure diagnosis** (specialist:safety): Test runner output and stack traces were not provided in the review context, preventing verification of which specific test assertion failed.
- **ILedger.EntriesAsync interval semantics** (specialist:safety): The implementation of ILedger.EntriesAsync is outside the shown context; whether its upper timestamp boundary is inclusive or exclusive cannot be verified from the interface call alone.
- **Root cause of dotnet_test failure** (specialist:tests): The deterministic sensor reports that dotnet_test failed with exit 1, but the test runner error output, stack traces, and the remainder of tests/Bank.Tests/Statements/StatementTests.cs (lines 275+) are not included in the review context.
- **Reason for dotnet_test runner failure** (specialist:maintainability): The deterministic test runner reported exit code 1, but test failure output and the latter portion of tests/Bank.Tests/Statements/StatementTests.cs are not included in the provided context, preventing diagnosis of the failing test.
- **Scalability and memory consumption of historical ledger query for opening balance** (specialist:performance): StatementService.ForMonthAsync retrieves all ledger entries from DateTimeOffset.MinValue up to the start of the month into memory via ILedger.EntriesAsync to calculate openingBalance. Assessing whether this poses a latency or memory risk in production requires knowing the ILedger contract capabilities (such as whether server-side aggregation is supported) and profiling under high transaction volumes, neither of which is available in the diff.
- **Noise filtering** (validator): Validator call failed; findings are shown unvalidated.

## What was NOT checked

- Scope vs approved plan (no --plan given)
- Requirement radar (Radar call failed: radar: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported methods.', 'status': 'NOT_FOUND'}})
- Part of tests/Bank.Tests/Statements/StatementTests.cs (context truncated)

## Deterministic sensors

| Sensor | Ran | Result |
| --- | --- | --- |
| secret_scan | yes | pass: No secret patterns in added lines (log: `evidence/secret_scan.txt`) |
| package_check | yes | pass: No package references added (log: `evidence/package_check.txt`) |
| test_integrity | yes | pass: No test files edited (log: `evidence/test_integrity.txt`) |
| removed_guards | yes | pass: No validation/guard lines removed (log: `evidence/removed_guards.txt`) |
| risky_code | yes | pass: 0 pattern hit(s) in added code (log: `evidence/risky_code.txt`) |
| dotnet_build | yes | pass: Build succeeded (log: `evidence/dotnet_build.log`) |
| dotnet_test | yes | FAIL: Tests failed (exit 1) (log: `evidence/dotnet_test.log`) |

## Risk tier reasons (rulebook)

- src/Bank.Api/Modules/Statements/Api/StatementsController.cs: area 'Statements' is medium (What customers see about their money)
- src/Bank.Api/Modules/Statements/Api/StatementsController.cs: content rule 'authorization attribute changed' matched → high
- src/Bank.Api/Modules/Statements/Application/StatementService.cs: area 'Statements' is medium (What customers see about their money)
- src/Bank.Api/Modules/Statements/StatementsModule.cs: area 'Statements' is medium (What customers see about their money)
- src/Bank.Api/Program.cs: area 'Platform' is high (Database schema, wiring and bank-wide settings touch every module)
- Large change (500 lines > 400) → one tier up
- Optimization context detected (research: optimization trap)

## Reviewer track record (from human feedback)

| Dimension | Accepted | Rejected | Escapes | Precision | Trust |
| --- | --- | --- | --- | --- | --- |
| architecture | 0 | 0 | 0 | None | not enough feedback yet (need 10+ judged findings) |
| correctness | 0 | 0 | 0 | None | not enough feedback yet (need 10+ judged findings) |
| maintainability | 0 | 0 | 0 | None | not enough feedback yet (need 10+ judged findings) |
| performance | 0 | 0 | 0 | None | not enough feedback yet (need 10+ judged findings) |
| safety | 0 | 0 | 0 | None | not enough feedback yet (need 10+ judged findings) |
| tests | 0 | 0 | 0 | None | not enough feedback yet (need 10+ judged findings) |

## Sign-off (to be completed by the named owner)

- Checked by AI and tools: Why, Security, Build, Architecture, Maintainability, Performance, Impact
- Must be checked by a human: What, Where
- Not checked: Scope vs approved plan (no --plan given); Requirement radar (Radar call failed: radar: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported methods.', 'status': 'NOT_FOUND'}}); Part of tests/Bank.Tests/Statements/StatementTests.cs (context truncated)
- Residual risk I accept: ______________________________
- Signed: ______________________ (owner)   ______________________ (second signer)

---
Run `20261114-202656-pr-8` · 2026-11-14T18:30:22+00:00 · policy 0.2-nordbank (approved by: NOT APPROVED) · models: {'specialist': 'gemini/gemini-3.8-flash', 'validator': 'gemini/gemini-3.1-pro-preview', 'radar': 'gemini/gemini-3.1-pro-preview', 'fixer': 'gemini/gemini-3.1-pro-preview', 'investigator': 'gemini/gemini-3.1-pro-preview', 'requirement_analyst': 'gemini/gemini-3.1-pro-preview', 'change_interpreter': 'gemini/gemini-3.8-flash', 'requirement_judge': 'gemini/gemini-3.1-pro-preview', 'panel': ['gemini/gemini-3.1-pro-preview', 'gemini/gemini-3.8-flash'], 'parser': 'tree-sitter', 'specialists': 'gemini/gemini-3.8-flash'} · changed files: 5

Settings: balanced preset · default essential · Full on high-risk · 15 plugins ran · #b5e52429b2df
Model calls: 14 · cost 0.0 EUR (budget {'max_calls': 40, 'max_cost_eur': 5.0})
