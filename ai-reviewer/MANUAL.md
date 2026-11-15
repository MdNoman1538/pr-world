# AI Reviewer v2.2: Instruction Manual

An evidence-first AI reviewer for pull requests written by AI coding agents, with a 4-zone visual dashboard. It produces a review a named human can check and sign. It never approves or merges anything.

Built for Junction 2026, Tieto challenge "Earned Trust in AI Code". v2 follows the research specification *Architecting a Trustworthy AI Code Review Agent* (Nov 2026).

---

## Project layout (v2.2)

The backend and the frontend are separate apps. They share no code and talk only through a JSON data contract.

```
ai-reviewer/
  backend/                review engine + JSON API (Python)
    review.py             CLI: review, api, bundle, ping, check, stats, feedback, escape, draft-policy
    reviewer/             pipeline (agents, sensors, context, radar, fixer, gate, memory, api.py)
    review-policy.yaml    the rulebook
    runs/<run>/           outputs, including bundle.json (the data contract)
  frontend/               dashboard UI (static HTML/JS, no Python packages)
    index.html app.js style.css d3.min.js config.js
    serve_ui.py           static server (port 8780)
    export.py             bundle.json → one self-contained dashboard.html
  simulate_challenge.sh   runs everything (reviews in parallel, then API + UI)
  .env                    your key and model names (never share)
```

- **Data contract:** `bundle.json` (schema `ai-reviewer-bundle/1`) holds `review`, `graph` (world map + `api` impact), `evidence`, `feedback` and `signoff`.
- **Backend API (port 8765):**
  - `GET /api/health`, `/api/runs`, `/api/runs/<id>`
  - `POST /api/feedback`, `/api/signoff`
  - CORS is limited to localhost origins.
- **Frontend:** reads the API set in `config.js`, which can be overridden with `?api=http://host:port`. It can also read a bundle embedded by `export.py`.
- **What runs in parallel:**
  - the four branch reviews (`PARALLEL=4` by default)
  - inside each review: the deterministic sensors alongside context building and API impact
  - the six specialists alongside the requirement radar
  - the API and the UI servers.

  The validator and then the fix agent run after the specialists, because they need the specialists' findings.

## Contents

1. What's new in v2
2. What it does
3. How it works (the four tiers and the research behind them)
4. Install on your Mac
5. Rehearse the demo offline (no API key)
6. Review a real challenge branch with Gemini
7. The dashboard: four zones and the sign-off
8. Close the loop: feedback, escapes and the track record
9. The rulebook: draft, approve, use
10. Optional: approved plan, build and test sensors
11. Command reference
12. Output files
13. Troubleshooting
14. Limits

---

## 1. What's new in v2

| Change | Research basis |
| --- | --- |
| **Validator uses the research's Q1–Q3:** Q1 nitpick check, Q2 hallucination check, Q3 severity scoring | Q1–Q3 validator pipeline (Lu et al.) |
| **Requirement radar:** every hunk is classified as aligned, supporting, tangled or unclear, and every requirement item as covered, partial or missing | PR–issue requirement radar, tangled changes |
| **Fix agent:** a ready-to-apply patch for each Blocker and ShouldFix; patches are built by code, so they apply cleanly to the PR head | Line-anchored stream with runnable patches |
| **Sixth specialist, Performance**, plus the **optimization trap:** performance or optimization PRs go one tier up and get extra memory-safety scrutiny | Security degradation in iterative AI refinement |
| **OWASP checklist** in the safety specialist | Most AI code that passes its tests still contains OWASP weaknesses |
| **Familiarity context:** recent history of each changed file, plus past findings on it, are fed to the specialists | The familiarity bottleneck in human review |
| **Iteration delta:** a second review of the same branch shows what was fixed, what is still open and what is new | Quality degrades across unvalidated AI iterations |
| **Evidence bundle:** each sensor writes a log, and `dotnet build/test` logs are kept per run | Verifiable execution traces |
| **4-zone dashboard:** world map, requirement radar, evidence, and the findings stream with sign-off | Dual-coding theory and the scan-then-detail pattern |

## 2. What it does

You give it a local git repo, a base branch, a PR branch and the requirement (issue text). It produces:

- **A decision:**
  - `BLOCKED`: a rule or a verified Blocker locks the merge.
  - `NEEDS_HUMAN`: named areas need a person.
  - `READY_FOR_SIGNOFF`: all areas are verified; the owner still signs.

  There is no "approved".
- **Areas,** each verified, human check or blocked: What, Where, Why, Scope, Plan, Security, Build, Tests, Correctness, Architecture, Maintainability, Performance and Impact.
- **Findings,** each with:
  - a severity tag (Blocker, Should Fix or Nit)
  - the exact file and line, with the code around it
  - the Q1–Q3 verdict and a confidence score
  - a requirement link
  - a ready-to-apply patch, where possible
- **A requirement radar** that traces hunks to requirement items.
- **What the AI refused to decide and why, and what was not checked.**
- **A noise funnel:** proposed → evidence verified → kept by the validator → shown.
- **The audit table** of filtered findings.
- **The iteration delta and the reviewer's track record.**
- **A sign-off record.**

## 3. How it works

```
Tier 1  Rule engine ........... review-policy.yaml → tier, guarded/no-go paths, sign-offs, optimization trap  (code)
        Deterministic sensors .. secrets, NuGet package exists, test weakening, removed guards, risky code,
                                 optional dotnet build/test; each writes a log                            (code)
Tier 2  Context engine ........ AST LeftFlow slices with line tags; impact (callers + test references);
                                 familiarity (file history + past findings from memory)                      (code)
Tier 3  Six specialists ....... correctness · architecture · safety (OWASP) · tests · maintainability ·
                                 performance — in parallel, structured JSON                          (Gemini, fast)
Tier 4  Evidence check ........ the quoted code must be at the cited lines, else dropped                      (code)
        Validator ............. Q1 nitpick? Q2 hallucination? Q3 true severity; duplicates merged      (Gemini, strong)
        Requirement radar ..... hunks ↔ requirement items; ids validated by code                        (Gemini, strong)
        Fix agent ............. old/new code → patch built and located by code                          (Gemini, strong)
Gate    Areas → decision ...... the AI can lock, never approve; iteration delta; memory; reports; graph.json
```

A typical run makes 9 model calls: 6 specialists, the validator, the radar and the fix agent.

**Two rules make the output trustworthy:**
- **Code decides, the AI explains.** Tiers, locks, evidence checks, hunk ids and patch placement are plain Python. The model cannot lower a tier, unlock a merge, invent a hunk, or place a patch where the code isn't.
- **No evidence, no finding.** A finding whose quote is not at the cited lines is dropped and listed in the audit table.

## 4. Install on your Mac

You need Python 3.10 or later and git. The dotnet SDK is optional.

```bash
cd ~/Downloads/ai-reviewer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export GEMINI_API_KEY="paste-your-key-here"   # keep it out of files and chats
python backend/review.py check
python backend/review.py models                       # models your key can use
python backend/review.py ping                         # one tiny call per model: proves key + model names work
```

The defaults are `gemini-3.8-flash` (fast) and `gemini-3.1-pro-preview` (strong). These are the names Gemini itself suggested when the 2.5 models were refused for new keys. If `ping` fails, it prints the model the API suggests; set the names your key has:

```bash
export GEMINI_FAST_MODEL="<fast model>"      # specialists
export GEMINI_STRONG_MODEL="<strong model>"  # validator, radar, fix agent
```

## 5. Rehearse the demo offline (no API key)

This builds a synthetic C# repo shaped like MessagePack. It has formatters, resolvers, LZ4, security, annotations, tests and a sandbox. The agent PR has planted problems. The run uses canned model answers, so it is reproducible, which makes it safe for a recorded demo.

```bash
python backend/examples/make_sample_repo.py /tmp/samplerepo
python backend/review.py review --repo /tmp/samplerepo --base master --head ju26-issue-9999 \
  --req-id ISSUE-9999 --req-file backend/examples/ISSUE-9999.md --owner "Your Name" \
  --mock backend/examples/mock_fixture.json --offline
```

Expected result: **BLOCKED**, HIGH tier, 2 sign-offs.
- **Radar:** "Existing length limits stay" is **missing**, and two hunks are **tangled** (the try/catch and an unused package).
- **Findings:** 3 Blockers with patches.
- **Audit table:**
  - one finding dropped by the evidence check
  - one dropped by Q2 as a hallucination
  - one duplicate
  - one Q1 nitpick

Now simulate the agent's second iteration and review again:

```bash
python backend/examples/make_sample_repo.py /tmp/samplerepo --iterate
python backend/review.py review --repo /tmp/samplerepo --base master --head ju26-issue-9999 \
  --req-id ISSUE-9999 --req-file backend/examples/ISSUE-9999.md --owner "Your Name" \
  --mock backend/examples/mock_fixture_iteration2.json --offline
```

The report now shows "**2 fixed, 4 still open, 0 new**".

Open the dashboard:

```bash
python backend/review.py api &        # backend API on :8765
python frontend/serve_ui.py           # dashboard on http://127.0.0.1:8780
```

Run the automated tests with `cd backend && python -m unittest discover -s tests`.

## 6. Review a real challenge branch with Gemini

**One command for all four branches:**

```bash
cp .env.example .env          # then put your key after GEMINI_API_KEY=
./simulate_challenge.sh --mock   # rehearsal first, no model calls
./simulate_challenge.sh          # the real run with Gemini
```

The script:
1. Clones the challenge repo next to this folder and creates the four PR branches.
2. Uses the repo's default branch as the base. The challenge branches were cut from it, so the file counts match the brief: 4, 4, 28 and 237.
3. Installs everything into `.venv`.
4. Reviews `ju26-issue-2283`, `2234`, `2129` and `2297`, using the original GitHub issue as the requirement.
5. Writes `runs/<run>/dashboard.html` for each review and opens the live dashboard.

Manual steps, if you prefer:

```bash
cd ~/code
git clone https://github.com/<you>/junction26-messagepack-csharp.git   # your own fork/copy
cd junction26-messagepack-csharp
git fetch --all
git remote show origin | grep HEAD           # base = the repo's default branch (the PR branches were cut from it)
for b in ju26-issue-2283 ju26-issue-2234 ju26-issue-2129 ju26-issue-2297; do git branch --track $b origin/$b 2>/dev/null; done
BASE=$(git remote show origin | sed -n 's/.*HEAD branch: //p'); git branch --track $BASE origin/$BASE 2>/dev/null

cd ~/Downloads/ai-reviewer
python backend/review.py review \
  --repo ~/code/junction26-messagepack-csharp --base $BASE --head ju26-issue-2283 \
  --req-id ISSUE-2283 --issue MessagePack-CSharp/MessagePack-CSharp#2283 \
  --owner "Md Abdullah Al Noman" --workers 2
python backend/review.py api  +  python frontend/serve_ui.py
```

Repeat for the other branches by changing `--head`, `--req-id` and `--issue`. If GitHub rate-limits the issue fetch, save the issue text to a file and use `--req-file`. The 237-file branch (#2297) will truncate context, and the report lists what was not seen. Use it for the "how would this scale" story.

## 7. The dashboard

Start it with `python backend/review.py api` and `python frontend/serve_ui.py` (live mode: feedback and sign-off are recorded). To share or record a run, use `python frontend/export.py backend/runs/<run-id>`, which writes one self-contained `dashboard.html`. It works offline and is read-only.

Read it the way the research describes: **scan first, then detail.**

- **Header:**
  - the decision, tier and sign-offs
  - the requirement alignment
  - an optimization-trap flag
  - the iteration delta
  - a warning while the rulebook is unapproved
- **Area chips:**
  - green means verified with evidence, purple needs a human, and red is blocked
  - click a chip to filter the findings to that area.
- **Zone A, API call flow (default tab).** For every API the PR changed:
  - **what changed:** NEW, BEHAVIOUR CHANGED (same signature), SIGNATURE CHANGED or REMOVED, plus **BREAKING** for public or protected contracts; signatures before and after are shown
  - **who is impacted:** the flow runs from callers of callers → direct callers → the changed API ← tests that call it, and boxes are coloured by area risk
  - **what is untested:** dashed boxes have no test reaching them; hover a box for its call sites and what to check; click a box to filter the findings to its file
  - test-only members are counted separately; they are evidence, not APIs.
- **Zone A, world map (second tab).** It speeds up orientation:
  - **countries** are rulebook areas, coloured by risk, with guarded areas outlined in red
  - **cities** are files, with 📍 marking the changed ones and the orange ring showing churn
  - **roads** are calls into the changed code (orange), tests (green dashed) and untested paths (grey ☁)
  - zoom shows three levels: areas → files → members, with callers, test references and finding counts
  - **📍 Change** flies to the change; clicking a country or city filters the findings.
- **Zone B, the requirement radar.** Every requirement item shows its status (covered, partial or missing). The matrix shows which hunk serves which item. Red cells are changes nobody asked for. Click a hunk to see its code.
- **Zone C, verifiable evidence.**
  - the noise funnel, and the sensors with their logs
  - the delta since the last review and the track record
  - what the AI refused to decide, and what was not checked.
- **Zone D, line-anchored findings.**
  - severity tags and the code around each cited line (cited lines highlighted)
  - the Q1–Q3 verdict and the ready-to-apply patch, with **Copy patch**
  - **✓ Real issue / ✕ Noise** buttons, which feed the track record
  - the audit table of filtered findings.
- **Sign-off.**
  - If the merge is locked, it says why and how to unlock it.
  - Otherwise, tick the areas that need you, write the residual risk you accept, and add a second signer for high tier.
  - **Sign** writes `signoff.json` into the run folder and shows a copyable record.

To apply a patch: copy it, save it as `fix.patch` in the repo on the PR branch, and run `git apply fix.patch`. Then re-run the tests and the review.

## 8. Close the loop: feedback, escapes and the track record

This is the Measurement criterion (25%).

- **Mark findings** in the dashboard (✓ / ✕), or from the CLI:
  `python backend/review.py feedback <run-id> C01 accepted --by "Your Name"`
- **Record misses (escapes):**
  `python backend/review.py escape <run-id> correctness --note "bug found in testing" --by "Your Name"`
- **See the record:** run `python backend/review.py stats`, or look in dashboard zone C.

The track record shows the following for each dimension:
- Precision: accepted ÷ judged.
- Escapes.
- A trust label: "not enough feedback yet" until 10 findings are judged, then "earned" at 80% or more with no escapes, "watch" below that, and "lowered after escape(s)" as soon as one is recorded.

Rejected findings are fed back into future prompts.

Numbers to show on stage:
- the noise funnel (proposed vs shown)
- precision per dimension and escapes
- the share of PRs routed to humans (NEEDS_HUMAN or BLOCKED)
- the iteration delta (issues fixed between agent iterations)

## 9. The rulebook: draft, approve, use

`review-policy.yaml` sets tiers, guarded areas, no-go zones, gates and the optimization-trap pattern. The shipped file is an **unapproved draft**, and every report says so.

```bash
python backend/review.py draft-policy --repo ~/code/junction26-messagepack-csharp --rev master         # heuristic
python backend/review.py draft-policy --repo ~/code/junction26-messagepack-csharp --rev master --llm   # Gemini
```

Compare `review-policy.draft.yaml` with `review-policy.yaml` and edit the areas. Then approve it:

```yaml
approved_by: "Md Abdullah Al Noman"
approved_on: "2026-11-14"
```

## 10. Optional: approved plan, build and test sensors

- **Plan:** list the files the change may touch, as in `examples/plan-example.yaml`, then pass `--plan`. Out-of-plan files are flagged; in guarded areas they lock the merge.
- **Build and tests:** pass `--build --test --test-target <project> --test-filter "<filter>"`. These need the .NET SDK. They run in a temporary git worktree, and the full logs land in `runs/<id>/evidence/`.

## 11. Command reference

| Command | Purpose |
| --- | --- |
| `check` | Environment check |
| `models` | Gemini models available to your key |
| `ping` | One tiny call per model; fails fast with the API's suggested model |
| `review` | Review one PR |
| `api [--port 8765]` | Backend JSON API for the dashboard |
| `bundle <run>` | Rewrite `bundle.json` (the data contract) |
| `frontend/serve_ui.py [--port 8780]` | Dashboard UI (separate app) |
| `frontend/export.py <run>` | Self-contained dashboard file |
| `draft-policy [--llm]` | AI drafts the rulebook |
| `feedback RUN FINDING accepted\|rejected --by NAME` | Record a verdict |
| `escape RUN DIMENSION --note TEXT --by NAME` | Record a miss |
| `stats` | Track record |

Global option: `--memory <file>` comes before the command.

Main `review` options:

| Option | Default | Meaning |
| --- | --- | --- |
| `--repo --base --head` | required | Clone, target branch, PR branch |
| `--req-id`, `--req-file` / `--issue owner/repo#N` | — | Requirement |
| `--owner` | UNASSIGNED | Accountable human |
| `--plan`, `--policy` | —, review-policy.yaml | Scope and rulebook |
| `--strategy` | leftflow | diff, parent, leftflow or fullflow |
| `--dimensions` | all six | e.g. `correctness,safety` |
| `--no-radar`, `--no-fixes` | off | Skip the radar or the fix agent |
| `--build --test --build-target --test-target --test-filter --timeout` | off | dotnet sensors |
| `--offline` | off | Skip the nuget.org check |
| `--mock [fixture]` | off | No model calls |
| `--fast-model --strong-model` | env or 2.5 flash/pro | Models |
| `--workers` | 6 | Parallel specialists; use 1–2 on a free-tier key |
| `--exit-code` | off | Exit 2/1/0 for CI |

## 12. Output files

`runs/<run-id>/` contains:

| File | Contents |
| --- | --- |
| `review.md` | Human report |
| `review.json` | Everything, machine-readable |
| `graph.json` | World map data: countries, cities, roads |
| `context.txt` | Exactly what the models saw |
| `llm_log.jsonl` | Every prompt and response (audit trail) |
| `requirement.md` | Requirement text used |
| `patches/<id>.patch` | Ready-to-apply fixes |
| `evidence/*` | Sensor and build/test logs |
| `signoff.json` | Written when someone signs in the dashboard |
| `dashboard.html` | Written by `frontend/export.py` |
| `bundle.json` | Data contract read by the frontend |

The memory lives in `.reviewer/memory.db`. Keep it: it holds the track record and the history behind the iteration delta.

## 13. Troubleshooting

| Problem | Fix |
| --- | --- |
| `No API key` | `export GEMINI_API_KEY=...` in the same terminal |
| 429 / RESOURCE_EXHAUSTED | Automatic retries; use `--workers 1` |
| Model not found (404) | `python backend/review.py ping` prints the model the API suggests; set `GEMINI_FAST_MODEL` / `GEMINI_STRONG_MODEL` in `.env` |
| Red banner "AI REVIEW DID NOT RUN" | Every model call failed (the error is in the banner and in `llm_log.jsonl`); the review is code-checks only. Fix the cause and run again; the review command exits with code 3 |
| `git merge-base` fails | Create the local branch: `git branch --track <b> origin/<b>` |
| Dashboard says "could not reach the backend" or "no reviews" | Start `python backend/review.py api` (it reads `backend/runs/`, or pass `--runs`), then reload |
| Port in use | `python backend/review.py api --port 9000` and open `http://127.0.0.1:8780/?api=http://127.0.0.1:9000` |
| Rough slices | `pip install tree-sitter tree-sitter-c-sharp` (`check` shows the parser in use) |

## 14. Limits

State these openly; judges will ask.

- **The model can still miss things.** Escapes lower trust, and high-tier PRs always get a full human read.
- **Evidence checks prove a finding is grounded, not that it is right.** Q2, Q3 and the human decide.
- **The radar and Q1–Q3 are model judgments,** constrained by code: hunk ids are checked, and findings without evidence are dropped.
- **Patches are guaranteed to apply, not to be correct.** Run the tests after applying one.
- **API impact and the world map are "code-graph lite":** name-based caller search, so overloads and common names (e.g. `Equals`) can over-count callers, and reflection or dynamic dispatch is invisible. Install `tree-sitter-c-sharp` for precise member detection.
- **Large PRs are truncated,** and the report says what was not seen.
- **The shipped rulebook is an unapproved draft.**
- **Code is sent to the Gemini API.** Use only synthetic or cleared data; a bank would need a data agreement or a self-hosted model.
- **Research figures should be checked before they are quoted.** v1 and v3 of the synthesis cite some studies with different details; verify against the original papers before putting numbers on slides.
