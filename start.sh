#!/usr/bin/env bash
# Start PR World (view mode) on a host such as Render. Uses $PORT when the host sets it.
set -e
cd "$(dirname "$0")/world-v5/server"
[ -f access.yaml ] || cp access.example.yaml access.yaml
exec python -m prw_server --config access.yaml run --host 0.0.0.0 --port "${PORT:-8795}"
