#!/bin/bash
# scripts/backup-agents.sh -- Back up all agent SOUL.md and TOOLS.md files
# Usage: ./scripts/backup-agents.sh [tag]
# Creates: workspaces/backups/YYYYMMDD-HHMMSS[-tag]/
set -euo pipefail

HOOK_DIR="${HOOK_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
TAG="${1:-}"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR="$HOOK_DIR/workspaces/backups/${TIMESTAMP}${TAG:+-$TAG}"

mkdir -p "$BACKUP_DIR"

for agent_dir in "$HOOK_DIR"/workspaces/*/; do
  agent=$(basename "$agent_dir")
  [ "$agent" = "backups" ] && continue
  mkdir -p "$BACKUP_DIR/$agent"
  for file in SOUL.md TOOLS.md; do
    [ -f "$agent_dir/$file" ] && cp "$agent_dir/$file" "$BACKUP_DIR/$agent/$file"
  done
done

echo "Backed up to: $BACKUP_DIR"
ls -R "$BACKUP_DIR"
