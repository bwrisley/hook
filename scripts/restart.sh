#!/bin/bash
# scripts/restart.sh -- Restart Shadowbox services
#
# Usage:
#   ./scripts/restart.sh          # Restart web + gateway
#   ./scripts/restart.sh web      # Restart web only
#   ./scripts/restart.sh gateway  # Restart gateway only
#   ./scripts/restart.sh status   # Show service status
#   ./scripts/restart.sh stop     # Stop web + gateway
#
set -euo pipefail

WEB_LABEL="com.punchcyber.hook.web"
GW_LABEL="ai.openclaw.gateway"
DAILY_LABEL="ai.openclaw.hook-daily"
USERID=$(id -u)

status() {
    echo "=== Shadowbox Services ==="
    for label in "$WEB_LABEL" "$GW_LABEL" "$DAILY_LABEL"; do
        pid=$(launchctl list | grep "$label" | awk '{print $1}')
        exit_code=$(launchctl list | grep "$label" | awk '{print $2}')
        if [ "$pid" != "-" ] && [ -n "$pid" ]; then
            echo "  $label: running (PID $pid)"
        elif [ -n "$exit_code" ]; then
            echo "  $label: stopped (exit $exit_code)"
        else
            echo "  $label: not loaded"
        fi
    done
    echo ""
    echo "=== Ports ==="
    echo "  Web (7799): $(lsof -ti:7799 2>/dev/null || echo 'not listening')"
    echo "  Gateway (18789): $(lsof -ti:18789 2>/dev/null || echo 'not listening')"
}

restart_web() {
    echo "Restarting Shadowbox web..."
    launchctl kickstart -k "gui/$USERID/$WEB_LABEL" 2>/dev/null || {
        # Not loaded — try bootstrap
        lsof -ti:7799 | xargs kill -9 2>/dev/null || true
        launchctl bootstrap "gui/$UID" ~/Library/LaunchAgents/$WEB_LABEL.plist 2>/dev/null || true
    }
    sleep 2
    if curl -s http://localhost:7799/api/status > /dev/null 2>&1; then
        echo "  Web: running on port 7799"
    else
        echo "  Web: starting (may take a moment)..."
    fi
}

restart_gateway() {
    echo "Restarting OpenClaw gateway..."
    openclaw gateway restart 2>&1 | grep -v "^$"
    sleep 2
    echo "  Gateway: port 18789"
}

stop_all() {
    echo "Stopping services..."
    launchctl bootout "gui/$USERID/$WEB_LABEL" 2>/dev/null && echo "  Web stopped" || echo "  Web: not running"
    openclaw gateway stop 2>/dev/null && echo "  Gateway stopped" || echo "  Gateway: not running"
}

case "${1:-all}" in
    web)
        restart_web
        ;;
    gateway)
        restart_gateway
        ;;
    status)
        status
        ;;
    stop)
        stop_all
        ;;
    all|restart)
        restart_gateway
        restart_web
        echo ""
        status
        ;;
    *)
        echo "Usage: $0 {web|gateway|status|stop|all}"
        exit 1
        ;;
esac
