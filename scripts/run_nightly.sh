#!/usr/bin/env bash
# Nightly entry point invoked by launchd. Wraps the Python scan with retries
# because macOS occasionally fails Python startup with transient filesystem
# errors (errno 11 / pyarrow mmap timeouts). One retry minute apart almost
# always succeeds.
set -uo pipefail
# Resolve project dir from this script's location -- never hardcode the path.
PROJ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$PROJ/venv/bin/python"
LOG="$PROJ/.state/scan.log"

cd "$PROJ"
mkdir -p "$(dirname "$LOG")"

for attempt in 1 2 3; do
    echo "=== Attempt $attempt at $(date) ===" >> "$LOG"
    if "$PY" scan.py --live >> "$LOG" 2>&1; then
        echo "=== Success on attempt $attempt at $(date) ===" >> "$LOG"
        exit 0
    fi
    code=$?
    echo "=== Attempt $attempt failed (exit $code); retrying in 90s ===" >> "$LOG"
    sleep 90
done

echo "=== All 3 attempts failed at $(date) ===" >> "$LOG"
exit 1
