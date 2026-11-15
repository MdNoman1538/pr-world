#!/bin/bash
# Publish this folder as a public GitHub repo. Needs git and the GitHub CLI (brew install gh; gh auth login).
set -e
cd "$(dirname "$0")"
git init -b main
git add .
git commit -m "PR World v5 and AI reviewer: Junction 2026, Earned Trust in AI Code"
gh repo create pr-world --public --source=. --remote=origin --push \
  --description "PR World: Seeing Is Believing. Junction 2026, Tieto Earned Trust in AI Code"
