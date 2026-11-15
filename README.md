# PR World: Seeing Is Believing

**Junction 2026 · Tieto challenge "Earned Trust in AI Code".**
A reference implementation that illustrates the concept. It is not a product.

AI agents now write pull requests faster than people can read them. PR World shows a reviewer what to trust
before they read a single line: a map of the whole system, findings that must cite a real line,
trust computed by code from test evidence, and a named person who signs. The AI never approves.

## What is in this repository

| Folder | What it is |
|---|---|
| `world-v5/` | PR World v5: agents build a simulated bank (Nordbank) PR by PR, and the 2.5D viewer and server let you review each PR on a map of the code. See `world-v5/README.md`. |
| `ai-reviewer/` | The AI reviewer: risk rulebook, six blind specialist reviewers, evidence gate, validator and model panel, trust gate, persistent memory. See `ai-reviewer/MANUAL.md` and `CUSTOMIZE.md`. |

## Run it

```
cd ai-reviewer && python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
cp .env.example .env          # put your Gemini API key after GEMINI_API_KEY=
cd ../world-v5
./run_world.sh --view         # open the app with the finished 12-PR run
./run_world.sh --fresh        # rebuild everything from scratch (about 1.5–2 hours)
```

Needs Python 3.11+ and the .NET SDK 8+. Keys live only in `.env`, which is never committed.

## Core rules (locked in code)

1. No evidence, no finding.
2. The AI can only raise risk, never lower it.
3. Reviewer roles work blind.
4. Only new test failures count.
5. Labels and trust are computed by code.
6. "Not checked" is never a pass.
7. Nothing is deleted.
8. The server enforces access and logs it in a hash-chained audit log.

Author: Md Abdullah Al Noman · November 2026

## Deploy on Render (free)

1. Render dashboard → **New → Blueprint** → pick this repo. `render.yaml` sets everything up.
2. Wait for the build. The app opens on the finished 12-PR run; no API key is needed.
3. Free services sleep when idle (first visit takes about a minute). Demo mode has no sign-in: use Menu → View as.

Files: `render.yaml` (service), `requirements.txt` (packages), `start.sh` (starts the server on `$PORT`).
