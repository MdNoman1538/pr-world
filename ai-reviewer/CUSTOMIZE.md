# Customising PR World and the AI reviewer (v5)

Three layers. The **locked core** never changes. The **team settings** file (`backend/prworld.yaml`) is checked by a
schema and approved by a named person. The **personal view** is each person's own (Settings in the app).

## 1. Locked core (refused if you try to set it)
- No evidence, no finding: a finding must quote real code at the cited line.
- The AI can raise risk, never lower it; the AI never approves.
- Blind roles: the test agent never sees the code; the requirement analyst and change interpreter never see each other's input.
- Only new test failures count; broken tests prove nothing either way.
- Labels and trust levels are computed by fixed rules; the confidence math (Jeffreys) is fixed.
- Nothing is deleted: dropped or hidden findings stay in the audit list.
- A check that did not run is shown as **Not checked**, never as passed, and keeps a PR below High trust.
- Access is enforced on the server; only people with Sign access sign; access, signatures and settings changes are logged.

Setting any of these (for example `allow_ai_approve: true`) is refused with the reason.

## 2. Team settings (`backend/prworld.yaml`)
Start from `backend/prworld.example.yaml`. Check it: `.venv/bin/python backend/review.py settings check backend/prworld.yaml`.
Use it: `review.py review ... --config backend/prworld.yaml` (Nordbank picks it up automatically).

| Key | What it does |
|---|---|
| `preset` | `strict-bank`, `balanced`, `fast-team`, `critical-only`. Your file only overrides it. |
| `approved_by`, `approved_on` | The named person who approved the settings. Until filled, every review says "settings NOT approved". |
| `coverage` | `full`, `essential` or `custom`, as a default, per risk tier and per area. Custom = a base level plus `enable` / `disable`. |
| `plugins` | Switch single plugins on or off for everyone; `company_dir` for your own plugins; `allow_unsigned: false` in regulated teams; `waivers` (a named person signs that a required plugin may be off for one area). |
| `models` | Provider and model per role: specialist, validator, panel (2–5), radar, fixer, investigator, requirement analyst / interpreter / judge, writer. Providers: Gemini, OpenAI, Anthropic, local (any OpenAI-compatible server). A warning shows when roles share one model. |
| `budget` | Max model calls and max cost per review. What did not run is listed as "budget reached". Fill the provider prices for the cost cap to work. |
| `thresholds` | Min confidence for a Critical finding (0.5–0.9), panel size, investigator steps, show Minor findings. |
| `local_only` | Areas whose code is only sent to the local model. With no local model, those checks are Not checked and nothing is sent. |
| `integrations` | Post the summary to GitHub, GitLab, Azure DevOps, Slack, Jira. `dry_run: true` writes the payload to a file instead. |
| `view_defaults` | The team's default personal view (trust as level or percent, findings shown, lenses, layout, theme, start page). |
| `access` | Hide the names of locked modules, max hours of emergency access. |
| `merge_policy` | Protected areas and signed merge rules (see the server README). |

**Coverage levels** (from the plugin list; the Plugins page shows the live numbers):
Essential = correctness and security reviewers, validator, sensors, build and tests (about 6 calls).
Full = Essential + test, architecture, maintainability and performance reviewers, validator panel, investigator,
requirement check, radar, fixer and writer (about 20 calls). Exact counts depend on the PR.

**Company plugins**: `plugins/company/<id>/manifest.yaml` (+ `prompt.md` for a checklist reviewer). Outside tools
(Semgrep, SonarQube, Stryker) run as sensors through their SARIF or Stryker JSON output. Sign a plugin with
`PRW_PLUGIN_SIGNING_KEY` (HMAC of the manifest, in `manifest.sig`); unsigned or changed plugins are refused when
`allow_unsigned: false`. Findings from company plugins go through the same evidence check as everything else.

## 3. Personal view (in the app: Menu → Settings)
Trust as Low / Medium / High (default) or percentage · findings shown (Critical only, Critical and Major, all;
the rest is folded with a count) · lenses in the bar · layout · density · theme · start page. English only for now.
With the server it is saved for your account; without it, in your browser. `PRW_TRUST_VIEW=percent` in `.env` sets the default.

## 4. Who may see what (the server)
See `world-v5/server/README.md`: roles, module access (Overview / Read / Review / Sign), grants with end dates,
access requests, emergency access, sign-off per module, signed merge rules, the audit log, company sign-in.
