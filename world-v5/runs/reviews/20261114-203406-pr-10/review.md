# AI review · pr-10 → main

**Decision: BLOCKED** · Tier **HIGH** · 2 sign-off(s) required · Requirement **PR-10** · Owner: **Md Abdullah Al Noman**

> Merge locked: Tests: Tests failed Not checked: Requirement. WARNING: review-policy.yaml is not approved by a named human yet.

The AI review is advice with evidence. It is not an approval. A named human owns the decision.

## What the change does (orientation)

This pull request centralizes cent rounding into a shared static helper `MoneyMath.ToCents` in the `Bank.Shared.Money` namespace using `MidpointRounding.AwayFromZero`. It refactors inline rounding calls across Deposits, Fees, Fx, and Loans to use this helper without changing calculation order or financial amounts, and adds unit tests covering midpoint and edge cases.

Requirement alignment: **met**

## Requirement radar

Radar call failed: radar: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported methods.', 'status': 'NOT_FOUND'}}

| Hunk | File:lines | Classification | Items | Why |
| --- | --- | --- | --- | --- |
| H01 | src/Bank.Api/Modules/Deposits/Application/DepositService.cs:9-9 | unclear | - | radar failed |
| H02 | src/Bank.Api/Modules/Deposits/Application/DepositService.cs:31-31 | unclear | - | radar failed |
| H03 | src/Bank.Api/Modules/Deposits/Application/DepositService.cs:128-129 | unclear | - | radar failed |
| H04 | src/Bank.Api/Modules/Fees/Application/FeeCalculator.cs:2-2 | unclear | - | radar failed |
| H05 | src/Bank.Api/Modules/Fees/Application/FeeCalculator.cs:27-29 | unclear | - | radar failed |
| H06 | src/Bank.Api/Modules/Fx/Application/FxService.cs:1-2 | unclear | - | radar failed |
| H07 | src/Bank.Api/Modules/Fx/Application/FxService.cs:46-46 | unclear | - | radar failed |
| H08 | src/Bank.Api/Modules/Loans/Application/LoanService.cs:11-11 | unclear | - | radar failed |
| H09 | src/Bank.Api/Modules/Loans/Application/LoanService.cs:70-70 | unclear | - | radar failed |
| H10 | src/Bank.Api/Modules/Loans/Application/LoanService.cs:220-220 | unclear | - | radar failed |
| H11 | src/Bank.Api/Shared/Money/MoneyMath.cs:1-7 | unclear | - | radar failed |
| H12 | tests/Bank.Tests/Shared/MoneyMathTests.cs:1-98 | unclear | - | radar failed |

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

Noise funnel: 0 proposed by specialists → 0 with verified evidence (0 hallucinated dropped) → 0 removed by validator → 0 shown (incl. 0 deterministic sensor findings); 0 ready-to-apply patch(es).

## Every area

| Area | Status | Reason |
| --- | --- | --- |
| What | VERIFIED | Change meets the requirement: The PR implements `MoneyMath.ToCents` exactly to specification, updates all cent-rounding points across the four specified modules without altering calculation flow, preserves error and validation semantics, and adds thorough unit tests. |
| Where | HUMAN CHECK | Tier HIGH → full human read and 2 sign-off(s) required<br>src/Bank.Api/Modules/Deposits/Application/DepositService.cs: area 'Deposits' is medium (Savings and interest)<br>src/Bank.Api/Modules/Fees/Application/FeeCalculator.cs: area 'Fees' is high (What the bank charges customers)<br>src/Bank.Api/Modules/Fx/Application/FxService.cs: area 'Fx' is high (Exchange rates decide how much money customers get)<br>src/Bank.Api/Modules/Loans/Application/LoanService.cs: area 'Loans' is high (Credit decisions and payouts) |
| Why | VERIFIED | Linked to a requirement |
| Security | VERIFIED | No secrets, no unverified packages, no safety findings |
| Build | VERIFIED | Build succeeded |
| Tests | BLOCKED | Tests failed<br>Failed!  - Failed:     4, Passed:   249, Skipped:     0, Total:   253, Duration: 3 s - Bank.Tests.dll (net10.0) |
| Correctness | VERIFIED | No blocking issue |
| Architecture | VERIFIED | No blocking issue |
| Maintainability | VERIFIED | No blocking issue |
| Performance | VERIFIED | No blocking issue |
| Impact | VERIFIED | 16 changed member(s); callers covered by tests or none |
| Requirement | NOT CHECKED | Not checked: requirement check failed: requirement:analyst: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported metho |

## What the AI found (0 shown, 0 filtered as noise)

No findings survived evidence checking and validation.
## What the AI refused to decide, and why

- **Reason for dotnet_test failure** (specialist:correctness): The deterministic sensor indicates test suite failure (exit 1), but execution outputs, failure logs, and stack traces are not included in the review context. It cannot be determined from the code diff whether the failure stems from pre-existing issues in other modules or a specific regression test.
- **Unchanged methods outside AST slices** (specialist:correctness): Methods outside the shown context in DepositService, FeeCalculator, FxService, and LoanService cannot be checked to verify whether any other cent-rounding operations exist that were left unmodified.
- **Root cause of deterministic sensor test failure** (specialist:architecture): Deterministic sensors report dotnet_test failed (exit 1), but standard output and test failure traces are not provided in the review context.
- **Root cause of deterministic dotnet_test failure** (specialist:safety): Test runner logs and stack traces are not included in the review context, making it impossible to determine whether the test failure is pre-existing or caused by a specific regression.
- **Root cause of dotnet_test failure** (specialist:tests): Test runner logs and stack traces are not provided in the review context, making it impossible to determine whether the failure stems from a newly introduced test or pre-existing failures in the test suite.
- **Existing regression test coverage in Fx, Fees, Deposits, and Loans modules** (specialist:tests): Existing test files for Fx, Fees, Deposits, and Loans are outside the provided context, so their specific assertions and coverage for the refactored endpoints cannot be directly inspected.
- **Reason for dotnet_test failure** (specialist:maintainability): The deterministic sensors report that dotnet_test failed (exit 1), but test execution logs and stack traces are outside the provided context.
- **Deterministic test runner failure diagnosis** (specialist:performance): The deterministic sensor reported test failures (`dotnet_test: ran; Tests failed (exit 1)`), but compiler and test runner output/stack traces are not included in the review context.

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

- src/Bank.Api/Modules/Deposits/Application/DepositService.cs: area 'Deposits' is medium (Savings and interest)
- src/Bank.Api/Modules/Fees/Application/FeeCalculator.cs: area 'Fees' is high (What the bank charges customers)
- src/Bank.Api/Modules/Fx/Application/FxService.cs: area 'Fx' is high (Exchange rates decide how much money customers get)
- src/Bank.Api/Modules/Loans/Application/LoanService.cs: area 'Loans' is high (Credit decisions and payouts)
- src/Bank.Api/Shared/Money/MoneyMath.cs: area 'Platform' is high (Database schema, wiring and bank-wide settings touch every module)

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

- Checked by AI and tools: What, Why, Security, Build, Correctness, Architecture, Maintainability, Performance, Impact
- Must be checked by a human: Where
- Not checked: Scope vs approved plan (no --plan given); Requirement radar (Radar call failed: radar: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported methods.', 'status': 'NOT_FOUND'}})
- Residual risk I accept: ______________________________
- Signed: ______________________ (owner)   ______________________ (second signer)

---
Run `20261114-203406-pr-10` · 2026-11-14T18:36:28+00:00 · policy 0.2-nordbank (approved by: NOT APPROVED) · models: {'specialist': 'gemini/gemini-3.8-flash', 'validator': 'gemini/gemini-3.1-pro-preview', 'radar': 'gemini/gemini-3.1-pro-preview', 'fixer': 'gemini/gemini-3.1-pro-preview', 'investigator': 'gemini/gemini-3.1-pro-preview', 'requirement_analyst': 'gemini/gemini-3.1-pro-preview', 'change_interpreter': 'gemini/gemini-3.8-flash', 'requirement_judge': 'gemini/gemini-3.1-pro-preview', 'panel': ['gemini/gemini-3.1-pro-preview', 'gemini/gemini-3.8-flash'], 'parser': 'tree-sitter', 'specialists': 'gemini/gemini-3.8-flash'} · changed files: 6

Settings: balanced preset · default essential · Full on high-risk · 13 plugins ran · #b5e52429b2df
Model calls: 9 · cost 0.0 EUR (budget {'max_calls': 40, 'max_cost_eur': 5.0})
