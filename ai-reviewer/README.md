# AI Reviewer v2.2

Evidence-first AI review for agent-written pull requests (Junction 2026, Tieto "Earned Trust in AI Code").
AI reviews, a named human decides.

- `backend/` — review engine (6 Gemini specialists, Q1–Q3 validator, requirement radar, fix agent, API impact,
  deterministic sensors, rule engine, memory) and a JSON API.
- `frontend/` — 4-zone dashboard (API call flow + world map, requirement radar, evidence, findings + sign-off);
  a separate static app that talks to the API, or reads an exported bundle.

```bash
cp .env.example .env                 # add GEMINI_API_KEY
./simulate_challenge.sh --mock       # rehearsal
./simulate_challenge.sh              # real: 4 PRs reviewed in parallel, then API (:8765) + dashboard (:8780)
```

Full guide: MANUAL.md
