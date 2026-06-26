#!/usr/bin/env bash
# Rebuild both snapshots. Called by the 3am cron and once at boot.
# Logs to data/refresh.log so a failed morning sync is debuggable.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="python3"

mkdir -p "$ROOT/data"
echo "=== refresh $(date -Is) ===" >> "$ROOT/data/refresh.log"
"$PY" -m server.sync "$@" >> "$ROOT/data/refresh.log" 2>&1
echo "exit $?" >> "$ROOT/data/refresh.log"
