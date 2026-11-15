#!/usr/bin/env bash
# Run the whole AI review on the four Junction challenge PR branches, in parallel, then start the
# backend API and the frontend dashboard as two independent processes.
#
#   ./simulate_challenge.sh            real run with Gemini (key in .env)
#   ./simulate_challenge.sh --mock     rehearsal: no model calls
#   PARALLEL=2 ./simulate_challenge.sh limit how many branches are reviewed at the same time (default 4)
#
# Layout:  backend/  = review engine + JSON API (port 8765)
#          frontend/ = dashboard UI, static, talks to the API over HTTP (port 8780)
set -euo pipefail
cd "$(dirname "$0")"
HERE="$(pwd)"
BACKEND="$HERE/backend"
FRONTEND="$HERE/frontend"
REPO_URL="https://github.com/te-industry-tech-office/junction26-messagepack-csharp.git"
REPO_DIR="$HERE/../junction26-messagepack-csharp"
UPSTREAM="MessagePack-CSharp/MessagePack-CSharp"
OWNER="${REVIEW_OWNER:-Md Abdullah Al Noman}"
BRANCHES="2283 2234 2129 2297"
PARALLEL="${PARALLEL:-4}"
MODE="real"
[[ "${1:-}" == "--mock" ]] && MODE="mock"

echo "== 1/5 challenge repo"
if [[ ! -d "$REPO_DIR/.git" ]]; then git clone "$REPO_URL" "$REPO_DIR"; fi
git -C "$REPO_DIR" fetch --all --quiet
BASE="$(git -C "$REPO_DIR" remote show origin | sed -n 's/.*HEAD branch: //p')"
echo "   base branch (repo default): $BASE"
git -C "$REPO_DIR" branch --quiet --track "$BASE" "origin/$BASE" 2>/dev/null || true
for n in $BRANCHES; do git -C "$REPO_DIR" branch --quiet --track "ju26-issue-$n" "origin/ju26-issue-$n" 2>/dev/null || true; done

echo "== 2/5 python environment (backend only; the frontend needs no packages)"
if [[ ! -d .venv ]]; then python3 -m venv .venv; fi
# shellcheck disable=SC1091
source .venv/bin/activate
if [[ -z "${SKIP_PIP:-}" ]]; then
  pip install --quiet --upgrade pip
  pip install --quiet -r "$BACKEND/requirements.txt"
fi

echo "== 3/5 api key and models"
if [[ -f .env ]]; then set -a; source .env; set +a; fi
EXTRA=()
if [[ "$MODE" == "mock" ]]; then
  EXTRA+=(--mock --offline); echo "   rehearsal mode: no Gemini calls"
elif [[ -z "${GEMINI_API_KEY:-}" ]]; then
  echo "   GEMINI_API_KEY is not set. Put it in $HERE/.env (see .env.example), or run with --mock."; exit 1
else
  echo "   key found (not printed). fast: ${GEMINI_FAST_MODEL:-default}  strong: ${GEMINI_STRONG_MODEL:-default}"
  python "$BACKEND/review.py" ping || { echo "   Model check failed; fix .env as suggested above."; exit 1; }
fi

echo "== 4/5 reviews: ${PARALLEL} branch(es) at a time"
LOGS="$BACKEND/runs/_logs"; mkdir -p "$LOGS"
run_one() {
  local n="$1"
  local code=0
  python "$BACKEND/review.py" review --repo "$REPO_DIR" --base "$BASE" --head "ju26-issue-$n" \
    --req-id "ISSUE-$n" --issue "$UPSTREAM#$n" --owner "$OWNER" --workers 2 ${EXTRA[@]+"${EXTRA[@]}"} \
    > "$LOGS/ju26-issue-$n.log" 2>&1 || code=$?
  echo "$code" > "$LOGS/ju26-issue-$n.exit"
}
running=0
for n in $BRANCHES; do
  rm -f "$LOGS/ju26-issue-$n.exit"
  echo "   started ju26-issue-$n  (log: backend/runs/_logs/ju26-issue-$n.log)"
  run_one "$n" &
  running=$((running + 1))
  if [[ $running -ge $PARALLEL ]]; then wait; running=0; fi   # macOS bash 3.2 has no `wait -n`
done
wait
FAILED=0
for n in $BRANCHES; do
  code="$(cat "$LOGS/ju26-issue-$n.exit" 2>/dev/null || echo 9)"
  line="$(grep -E 'DECISION|AI REVIEW FAILED' "$LOGS/ju26-issue-$n.log" | tail -1 || true)"
  if [[ "$code" == "3" ]]; then FAILED=1; echo "   ju26-issue-$n: AI REVIEW FAILED (see its log)";
  elif [[ "$code" != "0" ]]; then FAILED=1; echo "   ju26-issue-$n: error (exit $code, see its log)";
  else echo "   ju26-issue-$n: ${line#*] }"; fi
done
for d in "$BACKEND"/runs/*/; do
  [[ -f "$d/bundle.json" && ! -f "$d/dashboard.html" ]] && python "$FRONTEND/export.py" "$d" >/dev/null || true
done
[[ $FAILED -eq 1 ]] && echo "   Some reviews did not complete; the dashboard shows the ones that did."

echo "== 5/5 backend API + frontend dashboard (two independent processes)"
python "$BACKEND/review.py" api --runs "$BACKEND/runs" &
API_PID=$!
python "$FRONTEND/serve_ui.py" &
UI_PID=$!
trap 'kill $API_PID $UI_PID 2>/dev/null; exit 0' INT TERM
sleep 1.5
echo "   dashboard: http://127.0.0.1:8780   (API: http://127.0.0.1:8765/api/runs)   Ctrl+C stops both"
open "http://127.0.0.1:8780" >/dev/null 2>&1 || true
wait
