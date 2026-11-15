# AI review · pr-1 → main

**Decision: BLOCKED** · Tier **HIGH** · 2 sign-off(s) required · Requirement **PR-1** · Owner: **Md Abdullah Al Noman**

> Merge locked: Security: Safety Blocker(s) found; Correctness: 1 Blocker(s) Not checked: Requirement. WARNING: review-policy.yaml is not approved by a named human yet.

The AI review is advice with evidence. It is not an approval. A named human owns the decision.

## What the change does (orientation)

PR-1 implements customer onboarding and KYC compliance verification. It introduces domain models, event definitions, an application service for customer registration and verification/rejection, account opening enforcement rules, and controller endpoints. The goal is to allow customers to submit personal identity details while preventing underage applicants or unverified customers from opening bank accounts.

Requirement alignment: **partial**

## Requirement radar

Radar call failed: radar: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported methods.', 'status': 'NOT_FOUND'}}

| Hunk | File:lines | Classification | Items | Why |
| --- | --- | --- | --- | --- |
| H01 | src/Bank.Api/Data/BankDbContext.cs:3-3 | unclear | - | radar failed |
| H02 | src/Bank.Api/Data/BankDbContext.cs:19-19 | unclear | - | radar failed |
| H03 | src/Bank.Api/Modules/Customers/Api/CustomersController.cs:1-103 | unclear | - | radar failed |
| H04 | src/Bank.Api/Modules/Customers/Application/CustomerService.cs:1-107 | unclear | - | radar failed |
| H05 | src/Bank.Api/Modules/Customers/Application/KycAccountOpeningRule.cs:1-20 | unclear | - | radar failed |
| H06 | src/Bank.Api/Modules/Customers/CustomersModule.cs:1-14 | unclear | - | radar failed |
| H07 | src/Bank.Api/Modules/Customers/Domain/Customer.cs:1-49 | unclear | - | radar failed |
| H08 | src/Bank.Api/Program.cs:5-5 | unclear | - | radar failed |
| H09 | src/Bank.Api/Program.cs:23-23 | unclear | - | radar failed |
| H10 | tests/Bank.Tests/Customers/CustomerTests.cs:1-498 | unclear | - | radar failed |

## Second opinion on Critical findings (validator panel)

- C01: 1 of 1 reviewers say real → not enough votes
- S01: 1 of 1 reviewers say real → not enough votes

## Investigator

- C01: unsure after 0 step(s). investigator call failed: investigator: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateConten
- S01: unsure after 0 step(s). investigator call failed: investigator: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateConten

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

Noise funnel: 5 proposed by specialists → 5 with verified evidence (0 hallucinated dropped) → 1 removed by validator → 4 shown (incl. 0 deterministic sensor findings); 0 ready-to-apply patch(es).

## Every area

| Area | Status | Reason |
| --- | --- | --- |
| What | HUMAN CHECK | Requirement match is partial: The domain logic, service workflows, PII annotations, and account opening validation rules align with the specification. However, CustomersController adds [Authorize(Policy = Policies.Customer)] at the class level, causing verify and reject endpoints to combine Customer and Compliance policies and preventing compliance officers without the Customer role from accessing those actions. |
| Where | HUMAN CHECK | Tier HIGH → full human read and 2 sign-off(s) required<br>src/Bank.Api/Data/BankDbContext.cs: area 'Platform' is high (Database schema, wiring and bank-wide settings touch every module)<br>src/Bank.Api/Modules/Customers/Api/CustomersController.cs: area 'Customers' is high (Identity checks (KYC) and personal data)<br>src/Bank.Api/Modules/Customers/Api/CustomersController.cs: content rule 'authorization attribute changed' matched → high<br>src/Bank.Api/Modules/Customers/Application/CustomerService.cs: area 'Customers' is high (Identity checks (KYC) and personal data) |
| Why | VERIFIED | Linked to a requirement |
| Security | BLOCKED | Safety Blocker(s) found<br>S01 src/Bank.Api/Modules/Customers/Api/CustomersController.cs:14 |
| Build | VERIFIED | Build succeeded |
| Tests | HUMAN CHECK | Test weakening or gaps to check<br>T01 src/Bank.Api/Modules/Customers/Api/CustomersController.cs:15 |
| Correctness | BLOCKED | 1 Blocker(s)<br>C01 src/Bank.Api/Modules/Customers/Api/CustomersController.cs:14 |
| Architecture | VERIFIED | No blocking issue |
| Maintainability | VERIFIED | No blocking issue; 1 ShouldFix noted (does not hold the merge)<br>M01 src/Bank.Api/Modules/Customers/Api/CustomersController.cs:14 |
| Performance | VERIFIED | No blocking issue |
| Impact | VERIFIED | 48 changed member(s); callers covered by tests or none |
| Requirement | NOT CHECKED | Not checked: requirement check failed: requirement:analyst: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported metho |

## What the AI found (4 shown, 1 filtered as noise)

- **[Blocker] C01 · Class-level Customer policy prevents compliance officers from verifying or rejecting registrations** (correctness, specialist:correctness · confidence 0.95) `src/Bank.Api/Modules/Customers/Api/CustomersController.cs:14`

  In ASP.NET Core, Authorize attributes combine cumulatively across controller and action levels. Because [Authorize(Policy = Policies.Customer)] is declared on the CustomersController class, Verify and Reject require callers to satisfy both Customer and Compliance policies simultaneously, blocking compliance officers who do not hold customer credentials.

  ```
  [Authorize(Policy = Policies.Customer)]
  ```

  Requirement: HTTP endpoints are exposed with [ApiController] and explicit [Authorize(Policy = ...)] attributes: POST api/customers (Customer policy, derives user id solely from ICurrentUser), GET api/customers/me (Customer policy, returns current user's customer), POST api/customers/{id}/verify (Compliance policy), and POST api/customers/{id}/reject (Compliance policy).

  Suggested fix: Remove [Authorize(Policy = Policies.Customer)] from the CustomersController class declaration so that each action's method-level [Authorize] attribute controls access independently.

- **[Blocker] S01 · Class-level Authorize attribute inadvertently requires Customer policy on Compliance endpoints** (safety, specialist:safety · confidence 0.95) `src/Bank.Api/Modules/Customers/Api/CustomersController.cs:14`

  In ASP.NET Core, class-level and action-level [Authorize] attributes are combined with logical AND. Specifying [Authorize(Policy = Policies.Customer)] on CustomersController forces callers of Verify and Reject to satisfy both Policies.Customer and Policies.Compliance, causing HTTP 403 Forbidden for compliance officers who do not possess the Customer role.

  ```
  [Authorize(Policy = Policies.Customer)]
  ```

  Requirement: HTTP endpoints are exposed with [ApiController] and explicit [Authorize(Policy = ...)] attributes: POST api/customers (Customer policy, derives user id solely from ICurrentUser), GET api/customers/me (Customer policy, returns current user's customer), POST api/customers/{id}/verify (Compliance policy), and POST api/customers/{id}/reject (Compliance policy).

  Suggested fix: Remove [Authorize(Policy = Policies.Customer)] from line 14 on CustomersController so that endpoints rely strictly on their individual method-level [Authorize] attributes.

- **[ShouldFix] M01 · Redundant and conflicting controller-level Authorize attribute** (maintainability, specialist:maintainability · confidence 0.95) `src/Bank.Api/Modules/Customers/Api/CustomersController.cs:14`

  Applying [Authorize(Policy = Policies.Customer)] at the class level causes ASP.NET Core to evaluate it conjunctively for every action in the controller. This makes lines 27 and 46 redundant and inadvertently forces Verify and Reject (lines 56 and 79) to require both Customer and Compliance policies, risking authorization failures for compliance officers.

  ```
  [Authorize(Policy = Policies.Customer)]
  ```

  Requirement: HTTP endpoints are exposed with [ApiController] and explicit [Authorize(Policy = ...)] attributes: POST api/customers (Customer policy, derives user id solely from ICurrentUser), GET api/customers/me (Customer policy, returns current user's customer), POST api/customers/{id}/verify (Compliance policy), and POST api/customers/{id}/reject (Compliance policy).

  Suggested fix: Remove [Authorize(Policy = Policies.Customer)] from the CustomersController class declaration so that each action exclusively enforces its own explicit Authorize policy.

- **[ShouldFix] T01 · CustomersController endpoints lack unit or integration tests** (tests, specialist:tests · confidence 0.95) `src/Bank.Api/Modules/Customers/Api/CustomersController.cs:15`

  The newly introduced CustomersController and its four endpoints (Register, Me, Verify, Reject) have no unit or integration tests. Routing, HTTP status code mapping (200, 400, 403, 404, 409), and policy authorization attributes ([Authorize(Policy = ...)]) are entirely unexercised by the test suite.

  ```
  public sealed class CustomersController : ControllerBase
  ```

  Requirement: HTTP endpoints are exposed with [ApiController] and explicit [Authorize(Policy = ...)] attributes: POST api/customers (Customer policy, derives user id solely from ICurrentUser), GET api/customers/me (Customer policy, returns current user's customer), POST api/customers/{id}/verify (Compliance policy), and POST api/customers/{id}/reject (Compliance policy).

  Suggested fix: Add controller tests verifying endpoint execution, status code translation for exceptions (BadRequest, Forbid, NotFound, Conflict), and authorization policy metadata.

## What the AI refused to decide, and why

- **Interaction of class-level [Authorize(Policy = Policies.Customer)] with action-level [Authorize(Policy = Policies.Compliance)]** (specialist:architecture): The definition of Policies and requirement evaluation logic in Bank.Modules.Auth are outside the shown context; cannot verify whether compliance officers satisfy both policies or whether ASP.NET Core's conjunctive authorization filter evaluation blocks verify/reject endpoints.
- **BankDbContext table marker placement** (specialist:safety): Lines 10-18 and lines after line 19 of BankDbContext.cs are truncated in the context, preventing verification of whether DbSet<Customer> Customers is declared directly above the // TABLES: marker.
- **Test coverage in CustomerTests.cs lines 306-498** (specialist:tests): The diff for CustomerTests.cs is truncated after line 305. Tests for KycAccountOpeningRule, GetAsync, self-verification/rejection prevention, and PII attribute validation may be present in lines 306-498 but cannot be inspected from the provided context.
- **BankDbContext // TABLES: marker placement** (specialist:maintainability): The code slice for BankDbContext.cs does not display the // TABLES: marker, so line placement relative to the marker cannot be verified from the shown context.
- **CustomersController endpoint authorization integration tests** (specialist:maintainability): The unit test file was truncated in the diff and does not reveal whether WebApplicationFactory integration tests exist for the HTTP authorization pipeline.
- **Database query execution plans and physical indexing** (specialist:performance): Execution plan performance and index utilization on the Customers table depend on EF Core relational migrations and the target database engine, which cannot be measured without runtime benchmarks or database profiling.
- **Noise filtering** (validator): Validator call failed; findings are shown unvalidated.

## What was NOT checked

- Scope vs approved plan (no --plan given)
- Requirement radar (Radar call failed: radar: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported methods.', 'status': 'NOT_FOUND'}})
- Part of tests/Bank.Tests/Customers/CustomerTests.cs (context truncated)

## Deterministic sensors

| Sensor | Ran | Result |
| --- | --- | --- |
| secret_scan | yes | pass: No secret patterns in added lines (log: `evidence/secret_scan.txt`) |
| package_check | yes | pass: No package references added (log: `evidence/package_check.txt`) |
| test_integrity | yes | pass: No test files edited (log: `evidence/test_integrity.txt`) |
| removed_guards | yes | pass: No validation/guard lines removed (log: `evidence/removed_guards.txt`) |
| risky_code | yes | pass: 0 pattern hit(s) in added code (log: `evidence/risky_code.txt`) |
| dotnet_build | yes | pass: Build succeeded (log: `evidence/dotnet_build.log`) |
| dotnet_test | yes | pass: Tests passed (log: `evidence/dotnet_test.log`) |

## Risk tier reasons (rulebook)

- src/Bank.Api/Data/BankDbContext.cs: area 'Platform' is high (Database schema, wiring and bank-wide settings touch every module)
- src/Bank.Api/Modules/Customers/Api/CustomersController.cs: area 'Customers' is high (Identity checks (KYC) and personal data)
- src/Bank.Api/Modules/Customers/Api/CustomersController.cs: content rule 'authorization attribute changed' matched → high
- src/Bank.Api/Modules/Customers/Application/CustomerService.cs: area 'Customers' is high (Identity checks (KYC) and personal data)
- src/Bank.Api/Modules/Customers/Application/KycAccountOpeningRule.cs: area 'Customers' is high (Identity checks (KYC) and personal data)
- src/Bank.Api/Modules/Customers/CustomersModule.cs: area 'Customers' is high (Identity checks (KYC) and personal data)
- src/Bank.Api/Modules/Customers/Domain/Customer.cs: area 'Customers' is high (Identity checks (KYC) and personal data)
- src/Bank.Api/Program.cs: area 'Platform' is high (Database schema, wiring and bank-wide settings touch every module)
- Large change (795 lines > 400) → one tier up

## Filtered out before you saw them (audit)

| ID | Source | Title | Why it was filtered |
| --- | --- | --- | --- |
| M02 | specialist:maintainability | Variable minDob is misleadingly named for maximum allowable birth date | Nit suppressed by policy (gates.show_nits=false) |

## Reviewer track record (from human feedback)

| Dimension | Accepted | Rejected | Escapes | Precision | Trust |
| --- | --- | --- | --- | --- | --- |
| correctness | 0 | 0 | 0 | None | not enough feedback yet (need 10+ judged findings) |
| maintainability | 0 | 0 | 0 | None | not enough feedback yet (need 10+ judged findings) |
| safety | 0 | 0 | 0 | None | not enough feedback yet (need 10+ judged findings) |
| tests | 0 | 0 | 0 | None | not enough feedback yet (need 10+ judged findings) |

## Sign-off (to be completed by the named owner)

- Checked by AI and tools: Why, Build, Architecture, Maintainability, Performance, Impact
- Must be checked by a human: What, Where, Tests
- Not checked: Scope vs approved plan (no --plan given); Requirement radar (Radar call failed: radar: Gemini call failed after retries: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'models/gemini-3.1-pro-preview is not found for API version v1, or is not supported for generateContent. Call ModelService.ListModels to see the list of available models and their supported methods.', 'status': 'NOT_FOUND'}}); Part of tests/Bank.Tests/Customers/CustomerTests.cs (context truncated)
- Residual risk I accept: ______________________________
- Signed: ______________________ (owner)   ______________________ (second signer)

---
Run `20261114-193751-pr-1` · 2026-11-14T17:40:34+00:00 · policy 0.2-nordbank (approved by: NOT APPROVED) · models: {'specialist': 'gemini/gemini-3.8-flash', 'validator': 'gemini/gemini-3.1-pro-preview', 'radar': 'gemini/gemini-3.1-pro-preview', 'fixer': 'gemini/gemini-3.1-pro-preview', 'investigator': 'gemini/gemini-3.1-pro-preview', 'requirement_analyst': 'gemini/gemini-3.1-pro-preview', 'change_interpreter': 'gemini/gemini-3.8-flash', 'requirement_judge': 'gemini/gemini-3.1-pro-preview', 'panel': ['gemini/gemini-3.1-pro-preview', 'gemini/gemini-3.8-flash'], 'parser': 'tree-sitter', 'specialists': 'gemini/gemini-3.8-flash'} · changed files: 8

Settings: balanced preset · default essential · Full on high-risk · 15 plugins ran · #b5e52429b2df
Model calls: 17 · cost 0.0 EUR (budget {'max_calls': 40, 'max_cost_eur': 5.0})
