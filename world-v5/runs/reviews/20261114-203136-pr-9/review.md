# AI review · pr-9 → main

**Decision: BLOCKED** · Tier **HIGH** · 2 sign-off(s) required · Requirement **PR-9** · Owner: **Md Abdullah Al Noman**

> Merge locked: Tests: Tests failed Not checked: Requirement. WARNING: review-policy.yaml is not approved by a named human yet.

The AI review is advice with evidence. It is not an approval. A named human owns the decision.

## What the change does (orientation)

This change updates the default bank settings in preparation for the Swedish launch. It sets the default currency to SEK and lowers the daily transfer limit to 5,000 EUR equivalent, accompanied by a suite of tests validating account creation and default currency handling.

Requirement alignment: **partial**

## Requirement radar

Radar call failed: radar: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported methods.', 'status': 'NOT_FOUND'}}

| Hunk | File:lines | Classification | Items | Why |
| --- | --- | --- | --- | --- |
| H01 | src/Bank.Api/Shared/Settings/BankSettings.cs:7-7 | unclear | - | radar failed |
| H02 | src/Bank.Api/Shared/Settings/BankSettings.cs:13-13 | unclear | - | radar failed |
| H03 | tests/Bank.Tests/Settings/LaunchSettingsTests.cs:1-174 | unclear | - | radar failed |

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

Noise funnel: 2 proposed by specialists → 2 with verified evidence (0 hallucinated dropped) → 0 removed by validator → 2 shown (incl. 0 deterministic sensor findings); 0 ready-to-apply patch(es).

## Every area

| Area | Status | Reason |
| --- | --- | --- |
| What | HUMAN CHECK | Requirement match is partial: The configuration properties on BankSettings were updated correctly, but the requirement that all existing modules and tests continue to pass after updating obsolete assertions was not met, as the test suite is failing. |
| Where | HUMAN CHECK | Tier HIGH → full human read and 2 sign-off(s) required<br>src/Bank.Api/Shared/Settings/BankSettings.cs: area 'Platform' is high (Database schema, wiring and bank-wide settings touch every module)<br>src/Bank.Api/Shared/Settings/BankSettings.cs: content rule 'bank-wide setting changed' matched → high |
| Why | VERIFIED | Linked to a requirement |
| Security | VERIFIED | No secrets, no unverified packages, no safety findings |
| Build | VERIFIED | Build succeeded |
| Tests | BLOCKED | Tests failed<br>Failed!  - Failed:     4, Passed:   225, Skipped:     0, Total:   229, Duration: 1 s - Bank.Tests.dll (net10.0) |
| Correctness | VERIFIED | No blocking issue |
| Architecture | VERIFIED | No blocking issue |
| Maintainability | VERIFIED | No blocking issue |
| Performance | VERIFIED | No blocking issue |
| Impact | VERIFIED | 12 changed member(s); callers covered by tests or none |
| Requirement | NOT CHECKED | Not checked: requirement check failed: requirement:analyst: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported metho |

## What the AI found (2 shown, 0 filtered as noise)

- **[ShouldFix] T01 · No behavioral tests verify the 5,000 EUR daily transfer limit enforcement** (tests, specialist:tests · confidence 0.95) `tests/Bank.Tests/Settings/LaunchSettingsTests.cs:20`

  The requirement specifies that the cumulative daily transfer limit check must enforce 5,000 EUR equivalent, allowing transfers at 5,000.00 and rejecting transfers at 5,000.01 or cumulative overruns. The test suite only asserts the property on BankSettings directly and does not test transfer limit enforcement behavior or boundary conditions.

  ```
  Assert.Equal(5_000m, settings.DailyTransferLimit);
  ```

  Requirement: For any Customer initiating transfers, the cumulative daily transfer limit check enforces 5_000m EUR equivalent (using decimal arithmetic and Math.Round(x, 2, MidpointRounding.AwayFromZero) where EUR equivalent conversion applies): a transfer causing the daily total to equal 5,000.00 EUR equivalent succeeds, while a transfer causing the daily total to exceed 5,000.00 EUR equivalent (e.g., 5,000.01 EUR equivalent or a second transfer pushing the UTC day total above 5,000.00) is rejected with the existing daily limit validation error and posts no ledger movement.

  Suggested fix: Add integration/behavioral tests using the transfer service with BankSettings to assert that transfers up to 5,000 EUR equivalent succeed and transfers exceeding 5,000 EUR equivalent (including cumulative daily transfers) fail with daily limit validation errors.

- **[ShouldFix] T02 · Unsupported currency test catches generic Exception instead of specific domain exception** (tests, specialist:tests · confidence 0.90) `tests/Bank.Tests/Settings/LaunchSettingsTests.cs:87`

  Customer_opening_account_with_unsupported_currency_is_rejected uses Assert.ThrowsAnyAsync<Exception>, which risks passing on unintended runtime faults such as NullReferenceException rather than validating business rule rejection.

  ```
  await Assert.ThrowsAnyAsync<Exception>(() => service.OpenAsync(unsupportedCurrency));
  ```

  Requirement: When an authenticated Customer (or authorized role) creates a new account explicitly specifying another supported currency (such as "EUR" or "USD"), the account is still created in that requested supported currency.

  Suggested fix: Replace Assert.ThrowsAnyAsync<Exception> with Assert.ThrowsAsync<TException> specifying the exact exception type thrown for unsupported currency validation.

## What the AI refused to decide, and why

- **Identification of existing test failures** (specialist:correctness): Deterministic test sensor reported test failures (`dotnet_test: Tests failed (exit 1)`), but failure stack traces and existing test files outside the PR diff are not provided in the shown context.
- **Transfer limit enforcement and currency conversion behavior** (specialist:correctness): Transfer service implementation and daily limit tracking logic are not present in the shown context, making it impossible to verify how the 5,000m limit is applied to EUR-equivalent cumulative transfers at runtime.
- **Daily transfer limit enforcement and rounding in transfer services** (specialist:architecture): The transfer service implementation that consumes BankSettings.DailyTransferLimit and performs AwayFromZero rounding is outside the shown context.
- **Identification of failing existing tests** (specialist:architecture): The test failure output and existing test files outside LaunchSettingsTests.cs are not included in the review context.
- **Daily transfer limit enforcement and rounding implementation across modules** (specialist:safety): The cumulative daily transfer limit check, UTC day boundary logic, and AwayFromZero EUR-equivalent conversion reside in the ledger/transfer modules outside the shown context.
- **Which existing tests failed during test run** (specialist:tests): Detailed dotnet test execution output and failure stack traces are outside the provided context.
- **Transfer service limit validation implementation** (specialist:tests): The transfer service implementation and its existing test suite are outside the shown code context.
- **Failure cause in existing test suite** (specialist:maintainability): The deterministic test runner reports failure, but existing test files asserting the previous default currency or daily transfer limit are outside the diff context provided.
- **Transfer limit aggregation and conversion performance at runtime** (specialist:performance): The transfer execution pipeline and EUR equivalent limit aggregation logic reside outside the files modified in this PR and cannot be inspected in the provided context.
- **Noise filtering** (validator): Validator call failed; findings are shown unvalidated.

## What was NOT checked

- Scope vs approved plan (no --plan given)
- Requirement radar (Radar call failed: radar: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported methods.', 'status': 'NOT_FOUND'}})

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

- src/Bank.Api/Shared/Settings/BankSettings.cs: area 'Platform' is high (Database schema, wiring and bank-wide settings touch every module)
- src/Bank.Api/Shared/Settings/BankSettings.cs: content rule 'bank-wide setting changed' matched → high

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

- Checked by AI and tools: Why, Security, Build, Correctness, Architecture, Maintainability, Performance, Impact
- Must be checked by a human: What, Where
- Not checked: Scope vs approved plan (no --plan given); Requirement radar (Radar call failed: radar: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported methods.', 'status': 'NOT_FOUND'}})
- Residual risk I accept: ______________________________
- Signed: ______________________ (owner)   ______________________ (second signer)

---
Run `20261114-203136-pr-9` · 2026-11-14T18:32:50+00:00 · policy 0.2-nordbank (approved by: NOT APPROVED) · models: {'specialist': 'gemini/gemini-3.8-flash', 'validator': 'gemini/gemini-3.1-pro-preview', 'radar': 'gemini/gemini-3.1-pro-preview', 'fixer': 'gemini/gemini-3.1-pro-preview', 'investigator': 'gemini/gemini-3.1-pro-preview', 'requirement_analyst': 'gemini/gemini-3.1-pro-preview', 'change_interpreter': 'gemini/gemini-3.8-flash', 'requirement_judge': 'gemini/gemini-3.1-pro-preview', 'panel': ['gemini/gemini-3.1-pro-preview', 'gemini/gemini-3.8-flash'], 'parser': 'tree-sitter', 'specialists': 'gemini/gemini-3.8-flash'} · changed files: 2

Settings: balanced preset · default essential · Full on high-risk · 13 plugins ran · #b5e52429b2df
Model calls: 11 · cost 0.0 EUR (budget {'max_calls': 40, 'max_cost_eur': 5.0})
