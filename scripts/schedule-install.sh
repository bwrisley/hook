#!/bin/bash
# schedule-install.sh — Install HOOK scheduled tasks (macOS LaunchAgents)
# Usage: ./scripts/schedule-install.sh [--daily-hour 6] [--briefing-hour 8]
#
# Installs two LaunchAgents:
#   ai.openclaw.hook-daily    — Daily threat feed check (default: 6:00 AM)
#   ai.openclaw.hook-briefing — Morning Slack briefing (default: 8:00 AM)
#
# To uninstall: ./scripts/schedule-install.sh --uninstall

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LAUNCH_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="${HOOK_LOG_DIR:-$HOME/.openclaw/logs/hook}"

DAILY_HOUR=6
BRIEFING_HOUR=8
UNINSTALL=false
CHANNEL="${HOOK_SLACK_CHANNEL:-#hook}"

for arg in "$@"; do
    case "$arg" in
        --daily-hour) shift; DAILY_HOUR="${1:-6}" ;;
        --briefing-hour) shift; BRIEFING_HOUR="${1:-8}" ;;
        --uninstall) UNINSTALL=true ;;
    esac
done

DAILY_PLIST="$LAUNCH_DIR/ai.openclaw.hook-daily.plist"
BRIEFING_PLIST="$LAUNCH_DIR/ai.openclaw.hook-briefing.plist"

# ─── Uninstall ──────────────────────────────────────────────────────

if [ "$UNINSTALL" = true ]; then
    echo "Uninstalling HOOK scheduled tasks..."
    launchctl bootout "gui/$UID/ai.openclaw.hook-daily" 2>/dev/null && echo "  ✅ Daily check stopped" || echo "  ℹ️  Daily check was not running"
    launchctl bootout "gui/$UID/ai.openclaw.hook-briefing" 2>/dev/null && echo "  ✅ Morning briefing stopped" || echo "  ℹ️  Morning briefing was not running"
    rm -f "$DAILY_PLIST" "$BRIEFING_PLIST"
    echo "  ✅ LaunchAgents removed"
    exit 0
fi

# ─── Install ────────────────────────────────────────────────────────

echo "🪝 HOOK Schedule Installer"
echo ""
echo "   HOOK repo: $HOOK_DIR"
echo "   Daily check: ${DAILY_HOUR}:00 AM"
echo "   Morning briefing: ${BRIEFING_HOUR}:00 AM"
echo "   Slack channel: $CHANNEL"
echo ""

mkdir -p "$LAUNCH_DIR" "$LOG_DIR"

# Stop existing if running
launchctl bootout "gui/$UID/ai.openclaw.hook-daily" 2>/dev/null || true
launchctl bootout "gui/$UID/ai.openclaw.hook-briefing" 2>/dev/null || true

# Copy and configure daily check plist
cp "$HOOK_DIR/config/ai.openclaw.hook-daily.plist" "$DAILY_PLIST"
sed -i '' "s|HOOK_REPO_PATH|$HOOK_DIR|g" "$DAILY_PLIST"
sed -i '' "s|HOOK_USER_HOME|$HOME|g" "$DAILY_PLIST"
sed -i '' "s|<integer>6</integer>|<integer>$DAILY_HOUR</integer>|" "$DAILY_PLIST"
sed -i '' "s|#hook|$CHANNEL|g" "$DAILY_PLIST"

# Copy and configure briefing plist
cp "$HOOK_DIR/config/ai.openclaw.hook-briefing.plist" "$BRIEFING_PLIST"
sed -i '' "s|HOOK_REPO_PATH|$HOOK_DIR|g" "$BRIEFING_PLIST"
sed -i '' "s|HOOK_USER_HOME|$HOME|g" "$BRIEFING_PLIST"
sed -i '' "s|<integer>8</integer>|<integer>$BRIEFING_HOUR</integer>|" "$BRIEFING_PLIST"
sed -i '' "s|#hook|$CHANNEL|g" "$BRIEFING_PLIST"

# Load agents
launchctl bootstrap "gui/$UID" "$DAILY_PLIST" 2>/dev/null && echo "  ✅ Daily check installed (${DAILY_HOUR}:00 AM)" || echo "  ⚠️  Daily check may already be loaded"
launchctl bootstrap "gui/$UID" "$BRIEFING_PLIST" 2>/dev/null && echo "  ✅ Morning briefing installed (${BRIEFING_HOUR}:00 AM)" || echo "  ⚠️  Morning briefing may already be loaded"

echo ""
echo "Verify:"
echo "  launchctl list | grep hook"
echo ""
echo "Test manually:"
echo "  ./scripts/daily-check.sh --no-slack"
echo "  ./scripts/morning-briefing.sh --no-slack"
echo ""
echo "Uninstall:"
echo "  ./scripts/schedule-install.sh --uninstall"
echo ""
echo "Logs:"
echo "  tail -f $LOG_DIR/daily-launchd.log"
echo "  tail -f $LOG_DIR/briefing-launchd.log"
