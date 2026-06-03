#!/usr/bin/env bash
# Install a launchd agent that runs the analyser bot every weeknight at 10:00 PM
# local time, with --live so it actually sends Telegram alerts.
#
# Idempotent: re-running unloads the old agent and replaces it cleanly.
# To remove: ./scripts/install_schedule.sh remove
set -euo pipefail

PROJ_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.analyser.nightly"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
PY="$PROJ_DIR/venv/bin/python"
LOG_DIR="$PROJ_DIR/.state"

if [[ "${1:-}" == "remove" ]]; then
    launchctl unload "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"
    echo "Removed nightly schedule ($LABEL)."
    exit 0
fi

mkdir -p "$LOG_DIR" "$(dirname "$PLIST")"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PY}</string>
        <string>${PROJ_DIR}/scan.py</string>
        <string>--live</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${PROJ_DIR}</string>
    <key>StartCalendarInterval</key>
    <array>
        <dict><key>Hour</key><integer>22</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>1</integer></dict>
        <dict><key>Hour</key><integer>22</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>2</integer></dict>
        <dict><key>Hour</key><integer>22</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>3</integer></dict>
        <dict><key>Hour</key><integer>22</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>4</integer></dict>
        <dict><key>Hour</key><integer>22</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>5</integer></dict>
    </array>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/scan.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/scan.log</string>
    <key>ProcessType</key>
    <string>Background</string>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
EOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load -w "$PLIST"

echo "Installed nightly schedule:"
echo "  Label:   ${LABEL}"
echo "  Runs:    22:00 local time, Mon-Fri"
echo "  Command: ${PY} ${PROJ_DIR}/scan.py --live"
echo "  Log:     ${LOG_DIR}/scan.log"
echo
launchctl list | grep analyser || echo "(launchctl list didn't show it -- might need a few seconds)"
