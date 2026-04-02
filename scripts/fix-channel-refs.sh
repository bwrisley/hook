#!/bin/bash
# fix-channel-refs.sh — Standardize channel references across the HOOK repo
#
# Problem: Some files reference #hook-test, others reference #hook.
#          Scripts use HOOK_SLACK_CHANNEL env var (default: #hook).
#          Config template now uses HOOK_CHANNEL_NAME placeholder.
#
# This script updates all hardcoded #hook-test references to #hook,
# aligning with the scripts' default and the live deployment.
#
# Usage: cd ~/PROJECTS/hook && ./scripts/fix-channel-refs.sh
#        ./scripts/fix-channel-refs.sh --dry-run    (preview changes)

set -uo pipefail

HOOK_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DRY_RUN="${1:-}"

echo ""
echo "HOOK Channel Reference Standardization"
echo "  $(date -u '+%Y-%m-%d %H:%M UTC')"
echo ""

if [ "$DRY_RUN" = "--dry-run" ]; then
    echo "  Mode: DRY RUN (no changes will be made)"
    echo ""
fi

# Files that need #hook-test -> #hook replacement
FILES_TO_FIX=(
    "workspaces/coordinator/SOUL.md"
    "README.md"
    "install/INSTALL.md"
    "docs/RESEARCH-INTER-AGENT-ROUTING.md"
)

CHANGED=0

for file in "${FILES_TO_FIX[@]}"; do
    FULL_PATH="$HOOK_DIR/$file"
    if [ ! -f "$FULL_PATH" ]; then
        echo "  [SKIP] $file (not found)"
        continue
    fi

    COUNT=$(grep -c "#hook-test" "$FULL_PATH" 2>/dev/null || true)
    if [ "$COUNT" -eq 0 ]; then
        echo "  [OK]   $file (no #hook-test references)"
        continue
    fi

    if [ "$DRY_RUN" = "--dry-run" ]; then
        echo "  [WOULD FIX] $file ($COUNT occurrences)"
        grep -n "#hook-test" "$FULL_PATH" | sed 's/^/             /'
    else
        sed -i '' 's/#hook-test/#hook/g' "$FULL_PATH"
        echo "  [FIXED] $file ($COUNT occurrences -> #hook)"
        CHANGED=$((CHANGED + COUNT))
    fi
done

echo ""

# Verify config template uses placeholder (not hardcoded channel)
TEMPLATE="$HOOK_DIR/config/openclaw.json.template"
if [ -f "$TEMPLATE" ]; then
    if grep -q "HOOK_CHANNEL_NAME" "$TEMPLATE"; then
        echo "  [OK]   Config template uses HOOK_CHANNEL_NAME placeholder"
    elif grep -q "#hook-test\|#hook" "$TEMPLATE"; then
        echo "  [WARN] Config template has hardcoded channel name"
        echo "         Should use HOOK_CHANNEL_NAME placeholder"
    fi
fi

echo ""
if [ "$DRY_RUN" = "--dry-run" ]; then
    echo "  Dry run complete. Run without --dry-run to apply changes."
else
    echo "  $CHANGED reference(s) updated."
    echo "  All channel references now standardized to #hook."
    echo ""
    echo "  To use a different channel, set HOOK_SLACK_CHANNEL env var"
    echo "  and re-run setup.sh to update the config."
fi
