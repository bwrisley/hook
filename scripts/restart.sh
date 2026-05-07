#!/bin/bash
# scripts/restart.sh -- Restart Shadowbox services
#
# Usage:
#   ./scripts/restart.sh          # Restart web
#   ./scripts/restart.sh web      # Restart web
#   ./scripts/restart.sh status   # Show service status
#   ./scripts/restart.sh stop     # Stop web
#
set -euo pipefail

WEB_LABEL="com.punchcyber.hook.web"
DAILY_LABEL="ai.openclaw.hook-daily"
WATCH_LABEL="com.punchcyber.hook.watch-check"
USERID=$(id -u)

status() {
    echo "=== Shadowbox Services ==="
    for label in "$WEB_LABEL" "$DAILY_LABEL" "$WATCH_LABEL"; do
        line=$(launchctl list | awk -v l="$label" '$3 == l { print $1, $2 }')
        if [ -z "$line" ]; then
            echo "  $label: not loaded"
            continue
        fi
        pid=$(echo "$line" | awk '{print $1}')
        exit_code=$(echo "$line" | awk '{print $2}')
        if [ "$pid" != "-" ] && [ -n "$pid" ]; then
            echo "  $label: running (PID $pid)"
        else
            echo "  $label: stopped (exit $exit_code)"
        fi
    done
    echo ""
    echo "=== Ports ==="
    echo "  Web (7799): $(lsof -ti:7799 2>/dev/null || echo 'not listening')"
    echo "  Ollama (11434): $(lsof -ti:11434 2>/dev/null || echo 'not listening')"
}

restart_web() {
    echo "Restarting Shadowbox web..."
    launchctl bootout "gui/$USERID/$WEB_LABEL" 2>/dev/null || true
    lsof -ti:7799 2>/dev/null | xargs kill -9 2>/dev/null || true
    find "${HOOK_DIR:-.}" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
    sleep 1
    launchctl bootstrap "gui/$USERID" ~/Library/LaunchAgents/$WEB_LABEL.plist 2>/dev/null || true
    sleep 2
    if curl -s http://localhost:7799/api/status > /dev/null 2>&1; then
        echo "  Web: running on port 7799"
    else
        echo "  Web: starting (may take a moment)..."
    fi
}

stop_all() {
    echo "Stopping services..."
    if launchctl bootout "gui/$USERID/$WEB_LABEL" 2>/dev/null; then
        echo "  Web stopped"
    else
        echo "  Web: not running"
    fi
}

case "${1:-all}" in
    web)
        restart_web
        ;;
    status)
        status
        ;;
    stop)
        stop_all
        ;;
    all|restart)
        restart_web
        echo ""
        status
        ;;
    *)
        echo "Usage: $0 {web|status|stop|all}"
        exit 1
        ;;
esac
