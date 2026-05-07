#!/bin/bash
# HOOK / Shadowbox setup script — automated installation for macOS.
#
# Usage:
#   cd ~/projects/hook && ./install/setup.sh
#
# Idempotent: re-running upgrades dependencies and refreshes the build
# without clobbering .env, the SQLite DB, or pulled Ollama models.
#
set -euo pipefail

HOOK_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$HOOK_DIR/.venv"
ENV_FILE="$HOOK_DIR/.env"
ENV_TEMPLATE="$HOOK_DIR/.env.example"
WEB_DIR="$HOOK_DIR/web"
LOG_DIR="$HOME/.openclaw/logs/hook"
LAUNCH_AGENT="$HOME/Library/LaunchAgents/com.punchcyber.hook.web.plist"
PORT="${HOOK_WEB_PORT:-7799}"

echo ""
echo "Shadowbox setup -- PUNCH Cyber"
echo ""
echo "  Repo:    $HOOK_DIR"
echo "  Venv:    $VENV_DIR"
echo "  .env:    $ENV_FILE"
echo "  Port:    $PORT"
echo ""

# --- Prerequisites --------------------------------------------------------

echo "Checking prerequisites..."

MISSING=0

if ! command -v brew >/dev/null 2>&1; then
    echo "  [FAIL] Homebrew not installed -- see https://brew.sh"
    MISSING=1
else
    echo "  [OK]   Homebrew $(brew --version | head -1 | awk '{print $2}')"
fi

if ! command -v git >/dev/null 2>&1; then
    echo "  [FAIL] git not installed -- run: brew install git"
    MISSING=1
else
    echo "  [OK]   git $(git --version | awk '{print $3}')"
fi

PY=""
for candidate in python3.14 python3.13 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
        PY_VER=$("$candidate" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')
        case "$PY_VER" in
            3.13|3.14|3.15|3.16) PY="$candidate"; break ;;
        esac
    fi
done
if [ -z "$PY" ]; then
    echo "  [FAIL] Python 3.13+ not found -- run: brew install python@3.13"
    MISSING=1
else
    echo "  [OK]   $PY ($($PY --version | awk '{print $2}'))"
fi

if ! command -v node >/dev/null 2>&1; then
    echo "  [FAIL] node not installed -- run: brew install node@22"
    MISSING=1
else
    NODE_MAJOR=$(node --version | sed -E 's/^v([0-9]+).*/\1/')
    if [ "$NODE_MAJOR" -lt 20 ]; then
        echo "  [FAIL] node $NODE_MAJOR is too old -- need 20+, run: brew install node@22"
        MISSING=1
    else
        echo "  [OK]   node $(node --version)"
    fi
fi

if ! command -v ollama >/dev/null 2>&1; then
    echo "  [WARN] ollama not installed -- run: brew install ollama"
    echo "         (Shadowbox will still start; embeddings will be unavailable)"
else
    echo "  [OK]   ollama installed"
fi

if [ "$MISSING" -gt 0 ]; then
    echo ""
    echo "[FAIL] Missing prerequisites. Install them and re-run."
    exit 1
fi

echo ""

# --- Security CLI tools ---------------------------------------------------

echo "Checking enrichment CLI tools..."

TO_INSTALL=""
for cmd_pkg in "jq:jq" "dig:bind" "whois:whois" "nmap:nmap"; do
    cmd="${cmd_pkg%:*}"
    pkg="${cmd_pkg#*:}"
    if command -v "$cmd" >/dev/null 2>&1; then
        echo "  [OK]   $cmd"
    else
        echo "  [ ]    $cmd not installed (brew package: $pkg)"
        TO_INSTALL="$TO_INSTALL $pkg"
    fi
done

if [ -n "$TO_INSTALL" ]; then
    echo ""
    read -rp "Install missing tools via brew?$TO_INSTALL [Y/n]: " ANSWER
    if [ "${ANSWER:-Y}" != "n" ] && [ "${ANSWER:-Y}" != "N" ]; then
        # shellcheck disable=SC2086
        brew install $TO_INSTALL
    else
        echo "  [WARN] skipped -- enrichment scripts may fail without these"
    fi
fi

echo ""

# --- Python venv ----------------------------------------------------------

echo "Setting up Python environment..."
if [ ! -d "$VENV_DIR" ]; then
    "$PY" -m venv "$VENV_DIR"
    echo "  [OK]   created venv at $VENV_DIR"
else
    echo "  [OK]   venv exists"
fi

"$VENV_DIR/bin/pip" install --upgrade pip --quiet
"$VENV_DIR/bin/pip" install -r "$HOOK_DIR/requirements.txt" --quiet
echo "  [OK]   Python dependencies installed"

echo ""

# --- Frontend -------------------------------------------------------------

echo "Building the frontend..."
cd "$WEB_DIR"
if [ ! -d "node_modules" ]; then
    npm ci
else
    npm install --no-audit --no-fund --silent
fi
npm run build
cd "$HOOK_DIR"
echo "  [OK]   web/dist/ built"

echo ""

# --- .env -----------------------------------------------------------------

echo "Configuring .env..."

if [ ! -f "$ENV_FILE" ]; then
    cp "$ENV_TEMPLATE" "$ENV_FILE"
    echo "  [OK]   created .env from template"
else
    echo "  [OK]   .env already exists (keeping existing values)"
fi

# Helper: set a key in .env iff it's currently blank
set_env_if_blank() {
    local key="$1"
    local value="$2"
    [ -z "$value" ] && return 0
    # If the line exists and is blank, replace it. If it doesn't exist, append.
    if grep -qE "^${key}=" "$ENV_FILE"; then
        local current
        current=$(grep -E "^${key}=" "$ENV_FILE" | head -1 | cut -d= -f2-)
        if [ -z "$current" ]; then
            # macOS sed needs the empty backup arg
            sed -i '' "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
            echo "    [OK] $key set"
        else
            echo "    [SKIP] $key already set"
        fi
    else
        printf '\n%s=%s\n' "$key" "$value" >> "$ENV_FILE"
        echo "    [OK] $key appended"
    fi
}

prompt_key() {
    local label="$1"
    local var="$2"
    local input
    read -rp "    $label: " input
    set_env_if_blank "$var" "$input"
}

echo ""
echo "  --- API keys ---"
echo "  Press Enter to skip any key; you can edit .env manually later."
echo ""
prompt_key "OpenAI API key (required)" OPENAI_API_KEY
prompt_key "VirusTotal API key" VT_API_KEY
prompt_key "Censys API ID" CENSYS_API_ID
prompt_key "Censys API Secret" CENSYS_API_SECRET
prompt_key "AbuseIPDB API key" ABUSEIPDB_API_KEY
prompt_key "AlienVault OTX API key" OTX_API_KEY
prompt_key "Shodan API key" SHODAN_API_KEY

echo ""

# --- Ollama ---------------------------------------------------------------

if command -v ollama >/dev/null 2>&1; then
    echo "Setting up Ollama..."
    if ! curl -s --max-time 2 http://localhost:11434/api/tags >/dev/null 2>&1; then
        echo "  [INFO] starting ollama brew service..."
        brew services start ollama >/dev/null 2>&1 || true
        sleep 3
    fi
    if curl -s --max-time 2 http://localhost:11434/api/tags >/dev/null 2>&1; then
        echo "  [OK]   ollama reachable on :11434"

        EXISTING=$(curl -s http://localhost:11434/api/tags | "$VENV_DIR/bin/python" -c \
            "import json,sys; d=json.load(sys.stdin); print(' '.join(m['name'] for m in d.get('models',[])))" 2>/dev/null || echo "")

        if echo "$EXISTING" | grep -q "nomic-embed-text"; then
            echo "  [OK]   nomic-embed-text present"
        else
            read -rp "  Pull nomic-embed-text (embeddings, ~270MB)? [Y/n]: " PULL
            if [ "${PULL:-Y}" != "n" ] && [ "${PULL:-Y}" != "N" ]; then
                ollama pull nomic-embed-text
            fi
        fi

        if echo "$EXISTING" | grep -q "qwen2.5:14b"; then
            echo "  [OK]   qwen2.5:14b present"
        else
            read -rp "  Pull qwen2.5:14b (local chat model, ~9GB)? [y/N]: " PULL
            if [ "${PULL:-N}" = "y" ] || [ "${PULL:-N}" = "Y" ]; then
                ollama pull qwen2.5:14b
            else
                echo "  [SKIP] qwen2.5:14b -- you can pull later with: ollama pull qwen2.5:14b"
            fi
        fi
    else
        echo "  [WARN] ollama not reachable -- skipping model setup"
    fi
    echo ""
fi

# --- LaunchAgent (optional) ----------------------------------------------

echo "macOS LaunchAgent..."
if [ -f "$LAUNCH_AGENT" ]; then
    echo "  [OK]   $LAUNCH_AGENT already installed"
else
    read -rp "  Install LaunchAgent so the web UI starts at login? [Y/n]: " INSTALL_LA
    if [ "${INSTALL_LA:-Y}" != "n" ] && [ "${INSTALL_LA:-Y}" != "N" ]; then
        mkdir -p "$LOG_DIR"
        sed -e "s|HOOK_REPO_PATH|$HOOK_DIR|g" \
            -e "s|HOOK_LOG_PATH|$LOG_DIR|g" \
            "$HOOK_DIR/config/com.punchcyber.hook.web.plist" > "$LAUNCH_AGENT"
        launchctl bootstrap "gui/$(id -u)" "$LAUNCH_AGENT" 2>/dev/null || true
        echo "  [OK]   LaunchAgent installed and loaded"
    else
        echo "  [SKIP] LaunchAgent not installed -- start manually with ./scripts/restart.sh web"
    fi
fi

echo ""

# --- Validation -----------------------------------------------------------

echo "Validating..."

# scripts executable
chmod +x "$HOOK_DIR/scripts/"*.sh 2>/dev/null || true
echo "  [OK]   scripts/*.sh executable"

# data dirs
mkdir -p "$HOOK_DIR/data/feeds" "$HOOK_DIR/data/cache" \
         "$HOOK_DIR/data/faiss" "$HOOK_DIR/data/investigations" \
         "$HOOK_DIR/data/reports"
echo "  [OK]   data/ directories present"

# OpenAI key sanity
if grep -qE "^OPENAI_API_KEY=.+" "$ENV_FILE"; then
    echo "  [OK]   OPENAI_API_KEY set"
else
    echo "  [WARN] OPENAI_API_KEY not set in .env -- agents will not work"
fi

# Try to start (or restart) the web service if the LaunchAgent is loaded
if launchctl list | grep -q "com.punchcyber.hook.web"; then
    "$HOOK_DIR/scripts/restart.sh" web >/dev/null 2>&1 || true
    sleep 2
fi

# Health check
if curl -s --max-time 5 "http://localhost:$PORT/api/status" >/dev/null 2>&1; then
    echo "  [OK]   web service responding on :$PORT"
    HEALTHY=1
else
    echo "  [INFO] web service not responding yet -- start it manually below"
    HEALTHY=0
fi

echo ""
echo "--- Done ---"
echo ""

if [ "$HEALTHY" = "1" ]; then
    echo "  Open: http://localhost:$PORT"
    echo "  Login: admin / shadowbox  (change immediately under Settings -> Users)"
else
    echo "  Start the web service:"
    echo "    ./scripts/restart.sh web"
    echo "  Then open: http://localhost:$PORT"
fi

echo ""
echo "  Status:  ./scripts/restart.sh status"
echo "  Logs:    tail -f $LOG_DIR/web-stderr.log"
echo "  Guide:   $HOOK_DIR/install/INSTALL.md"
echo ""
