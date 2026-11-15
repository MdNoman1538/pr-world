#!/usr/bin/env bash
# PR World v5 — agents build Nordbank (12 PRs over 8 new modules), then people review each PR by travelling it.
#
#   ./run_world.sh --fresh       real run from the seed: Gemini agents + dotnet build/test + Roslyn cartographer + reviewer + PR notes
#                                (about 1.5-2 hours; it can be stopped and restarted: finished PRs are kept)
#   ./run_world.sh               continue a run (only the PRs not done yet)
#   ./run_world.sh --notes       only (re)write the PR notes + trust evidence for the last run, then open the viewer
#   ./run_world.sh --view        only open the app on the last run. No sign-in: pick who you are in Menu -> View as
#                                (each person sees only the modules their role allows; see server/access.yaml)
#   ./run_world.sh --calibrate   confidence against known outcomes (no AI calls)
#   ./run_world.sh --experiment  review the finished PRs again with/without the requirement check and one vs mixed models
#   extra flags go to agents/simulate.py:  --only PR-1,PR-2  --no-review  --export-only  --config path/to/prworld.yaml
set -euo pipefail
cd "$(dirname "$0")"
PY=../ai-reviewer/.venv/bin/python
if [ ! -x "$PY" ]; then
  echo "Missing ../ai-reviewer/.venv. Run ../ai-reviewer/simulate_challenge.sh once (it creates the Python environment)."
  exit 1
fi
VIEW_ONLY=0; NOTES_ONLY=0; CAL_ONLY=0; EXP=0; ARGS=()
clean() {   # pasted text often carries look-alike dashes or hidden spaces: turn them into plain ones
  printf '%s' "$1" | LC_ALL=C sed -e 's/\xe2\x80[\x90-\x95]/-/g' -e 's/\xe2\x88\x92/-/g' -e 's/\xc2\xa0//g' -e 's/\xe2\x80\x8b//g' | LC_ALL=C tr -d '[:space:]' | sed -e 's/^-\{1,\}\([a-z]\)/--\1/'
}
for raw in "$@"; do
  a=$(clean "$raw")
  [ -n "$a" ] || continue
  case "$a" in
    \#*) break ;;   # zsh passes pasted "# comments" as arguments: ignore everything after them
    view|server) VIEW_ONLY=1 ;;
    notes) NOTES_ONLY=1 ;;
    --no-dotnet|--no-review|--fresh|--redo|--export-only) ARGS+=("$a") ;;
    --only|--owner|--config) ARGS+=("$a") ;;
    --view) VIEW_ONLY=1 ;;
    --notes) NOTES_ONLY=1 ;;
    --server) VIEW_ONLY=1 ;;   # same as --view (one app now)
    --calibrate) CAL_ONLY=1 ;;
    --experiment) EXP=1 ;;
    --mock) echo "Nordbank has no rehearsal mode: every PR is written by the agents. Use ./run_world.sh --fresh"; exit 1 ;;
    -*) echo "Unknown option: $raw"; echo "Options: --view  --notes  --fresh  --calibrate  --experiment   (and for a run: --only PR-1,PR-2  --no-review  --export-only  --config file)"; exit 2 ;;
    *) ARGS+=("$a") ;;
  esac
done
if [ -f ../ai-reviewer/.env ]; then set -a; . ../ai-reviewer/.env; set +a; fi   # keys are never printed
# v5 needs a few more packages (settings schema, outside providers, the server); installed once
"$PY" -c "import jsonschema, requests" 2>/dev/null || "$PY" -m pip install -q -r ../ai-reviewer/backend/requirements.txt
mkdir -p runs
if [ "$CAL_ONLY" = 1 ]; then "$PY" agents/calibration.py; exit 0; fi
if [ "$EXP" = 1 ]; then
  echo "== Experiment: the finished PRs reviewed again under each set-up (log: runs/experiment.log)"
  "$PY" agents/experiment.py ${ARGS[@]+"${ARGS[@]}"} 2>&1 | tee runs/experiment.log
  exit 0
fi
if [ "$NOTES_ONLY" = 1 ]; then
  [ -f viewer/data/index.json ] || { echo "No run yet. Run ./run_world.sh --fresh first."; exit 1; }
  echo "== Checking Gemini"
  (cd ../ai-reviewer && "$PY" backend/review.py ping) || { echo "Gemini check failed: writing facts-only notes."; "$PY" agents/pr_notes.py --no-ai; VIEW_ONLY=1; }
  [ "$VIEW_ONLY" = 1 ] || "$PY" agents/pr_notes.py 2>&1 | tee runs/notes.log
  "$PY" agents/calibration.py || true
  VIEW_ONLY=1
fi
if [ "$VIEW_ONLY" = 0 ]; then
  echo "== Checking Gemini (one tiny call per model)"
  (cd ../ai-reviewer && "$PY" backend/review.py ping) || { echo "Gemini check failed. Fix ../ai-reviewer/.env and run again."; exit 1; }
  echo "== Agents at work (log: runs/last.log)"
  "$PY" agents/simulate.py ${ARGS[@]+"${ARGS[@]}"} 2>&1 | tee runs/last.log
  echo "== PR notes + trust evidence"
  "$PY" agents/pr_notes.py 2>&1 | tee runs/notes.log
  "$PY" agents/calibration.py || true
fi
[ -f viewer/data/index.json ] || { echo "No world data yet. Run ./run_world.sh --fresh first."; exit 1; }
# one app: the PR World server, in "switch" mode (no sign-in; Menu -> View as changes the person)
"$PY" -c "import starlette, uvicorn, jwt, itsdangerous" 2>/dev/null || "$PY" -m pip install -q -r server/requirements.txt
[ -f server/access.yaml ] || { cp server/access.example.yaml server/access.yaml; echo "Created server/access.yaml (people, roles, module owners)."; }
(cd server && "../$PY" -m prw_server --config access.yaml run --port 8795) & SRV=$!
URL="http://127.0.0.1:8795"
trap 'kill $SRV 2>/dev/null || true' EXIT INT TERM
for _ in $(seq 1 60); do curl -sf "$URL/healthz" >/dev/null 2>&1 && break; kill -0 $SRV 2>/dev/null || { echo "Server stopped; see the message above."; exit 1; }; sleep 0.5; done
open "$URL" 2>/dev/null || echo "Open $URL"
echo "Viewer running at $URL. Ctrl+C to stop."
wait $SRV
