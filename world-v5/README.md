# PR World v5 — Nordbank

Agents build a realistic bank, PR by PR, and you review each PR by travelling a map of the code.
No reference code and no rehearsal mode: every line is written by the agents, and failures are shown as failures.

## Run (on your Mac)
```
cd ~/Projects/junction-ai-review/world-v5
./run_world.sh --fresh      # the whole run, about 1.5–2 hours (stop with Ctrl+C any time; run ./run_world.sh to continue)
./run_world.sh --view       # open the app (no sign-in; Menu -> View as switches the person, see server/README.md)
./run_world.sh --notes      # rewrite the PR notes and reviewer feedback (one short AI call per PR)
./run_world.sh --calibrate  # confidence against known outcomes (no AI calls)
./run_world.sh --experiment # review the finished PRs again: with/without the requirement check, one vs mixed models
```
Team settings (coverage, models per role, budget, integrations): `../ai-reviewer/backend/prworld.yaml`, see
`../ai-reviewer/CUSTOMIZE.md`. Without that file the reviewer runs everything (Full) with the Gemini models, as in v4.
Needs: .NET SDK 8+ and `../ai-reviewer` with its `.venv` and `.env` (Gemini key). The key is never printed.

## The bank
Seed (written by the platform team): **Auth, Accounts, Ledger, Audit, Notifications**, plus bank-wide settings, a clock,
and one rulebook (CONSTITUTION.md) per module — also for the 8 modules the agents will build:
**Customers (KYC), Payments, Fx, Fees, Cards, Deposits, Loans, Statements.**
Money moves only through the multi-currency Ledger (EUR, SEK, USD); personal data is marked `[Pii]` and stripped from the audit trail.

## The 12 PRs (plan/prs.yaml)
| PR | Type | What |
|---|---|---|
| PR-1 | feature | Customer onboarding and identity checks (KYC) |
| PR-2 | feature, 2 commits | Payments between accounts (idempotency key, daily limit) |
| PR-3 | feature | Currency exchange and cross-currency payments |
| PR-4 | feature | Fees for cross-currency payments (with a quote) |
| PR-5 | feature, 2 commits | Debit cards: issue, freeze, cancel, authorise |
| PR-6 | feature | Term deposits with interest |
| PR-7 | feature, 2 commits | Loans with four-eyes approval and payout |
| PR-8 | feature | Monthly account statements |
| PR-9 | config | Swedish launch: default currency SEK, daily limit 5,000 (small change, big impact) |
| PR-10 | refactor | One shared rounding rule for money (no behaviour change) |
| PR-11 | bug fix | "Customer charged twice when the app retried" (support ticket) |
| PR-12 | feature | Hold large payments to new payees for review (fraud) |

Hidden defects (plan/answer_key.yaml, never shown to the Builder, Test agent or Reviewer) are planted in 8 PRs:
privacy, idempotency, fee cap, frozen card, four-eyes, month boundary, rounding mode, fraud threshold.
**PR-3, PR-6, PR-9 and PR-11 are clean on purpose** — to measure false alarms.

## Agents
Requirement agent → Builder (one commit per step) → Bug planter (hidden) → Test agent (blind to the code) →
dotnet build + tests → Roslyn Cartographer (world map) → Reviewer → PR notes (verdict, confidence, reviewer feedback).
If the Builder cannot make a PR compile, the PR is recorded as not merged and PRs that depend on it are skipped.

## What is new in v5
- **Trust level** Low / Medium / High by default (percentage in Settings), in two parts: changed code verified by tests,
  and requirement met (three blind agents: analyst, interpreter, judge, each "met" with code proof).
- **Plug and play**: Full / Essential / Custom coverage per risk tier or area; switched-off checks show as **Not checked**,
  never as passed. Plugins page with cost per PR and what you lose; set-up wizard (regulated / business / small).
- **Validator panel** (2–5 models vote on each Critical finding; a "not real" majority moves it to Major, never deletes it)
  and an **investigator** that may search the code and run one test before a Critical finding is shown.
- **Models per role** (Gemini, OpenAI, Anthropic, local), budget cap, local-only areas, company plugins (signed).
- **One app with people**: no sign-in in this version; Menu → View as switches the person (example Nordbank people in
  `server/access.yaml`). Module access per person, locked modules shown as closed blocks, access requests,
  emergency access, sign-off per module, signed merge rules, hash-chained audit log.
- **Personal view**: findings shown, lenses, layout, density, theme, start page.
- **Proof tools** (test tool, admins): calibration (reliability diagram, Brier score) and the reviewer experiment.

## What was new in the v4 viewer
- Clean right panel: PR name, then **Reviewer feedback** written for the person who signs; click an item for the facts.
- **Trust details**, **What this PR does** and **Requirement** are buttons.
- Settings and default values are part of the map: changing one shows every part of the bank that uses it,
  and the feedback asks for a business decision ("DefaultCurrency goes from "EUR" to "SEK"").

## Honest limits
- All agents use the same Gemini model unless you change `agents/common.py`; the reviewer's roles follow
  `prworld.yaml` (a warning shows when roles share one model): disclose it.
- Calibration on 12 PRs shows the method, not a result. "Correct" means only "no planted defect".
- Locked modules: a name that appears inside code you can read (e.g. a test calling `LoanService`) stays visible there.
- The confidence number is test evidence for the changed code (Jeffreys estimate), labelled uncalibrated.
- "Caught by reviewer" in the scorecard is matched by location: open each one before the demo.
