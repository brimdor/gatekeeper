#!/usr/bin/env bash
# Gatekeeper install script
# Supports: Ubuntu/Debian, Fedora/RHEL, Arch Linux, macOS
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/brimdor/gatekeeper/main/install.sh | bash
#   bash install.sh [--non-interactive]
#
# --non-interactive: Install only, skip setup wizard (use gatekeeper setup later)

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC} $*"; }
prompt()  { echo -e "${CYAN}[?]${NC} $*"; }

REPO="https://github.com/brimdor/gatekeeper"
NON_INTERACTIVE=false
INSTALL_DIR=""

for arg in "$@"; do
    case "$arg" in
        --non-interactive) NON_INTERACTIVE=true ;;
        --dir=*) INSTALL_DIR="${arg#--dir=}" ;;
        -h|--help)
            echo "Usage: bash install.sh [--non-interactive] [--dir=PATH]"
            echo ""
            echo "  --non-interactive   Install only, skip interactive setup"
            echo "  --dir=PATH          Installation directory (default: ./gatekeeper)"
            exit 0
            ;;
    esac
done

# ===================== Dependency Checks =====================

check_bc() {
    if ! command -v bc &>/dev/null; then
        return 1
    fi
    return 0
}

check_python() {
    if command -v python3 &>/dev/null; then
        PYTHON=python3
    elif command -v python &>/dev/null; then
        PYTHON=python
    else
        error "Python 3.11+ is required but not found."
        echo "  Install it first: https://www.python.org/downloads/"
        exit 1
    fi

    if check_bc; then
        PY_VERSION=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        if (( $(echo "$PY_VERSION < 3.11" | bc -l) )); then
            error "Python 3.11+ required, found $PY_VERSION"
            echo "  Upgrade: https://www.python.org/downloads/"
            exit 1
        fi
        success "Python $PY_VERSION"
    else
        warn "bc not found — skipping Python version validation"
        success "Python found ($PYTHON)"
    fi
}

install_uv() {
    if command -v uv &>/dev/null; then
        UV_VERSION=$(uv --version 2>/dev/null || echo "unknown")
        success "uv $UV_VERSION"
        return
    fi

    info "Installing uv (Python package manager)..."
    if [[ "$(uname)" == "Darwin" ]]; then
        if command -v brew &>/dev/null; then
            brew install uv
        else
            curl -LsSf https://astral.sh/uv/install.sh | sh
            export PATH="$HOME/.local/bin:$PATH"
        fi
    else
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.local/bin:$PATH"
    fi

    if ! command -v uv &>/dev/null; then
        error "uv installation failed"
    fi
    success "uv installed"
}

check_git() {
    if ! command -v git &>/dev/null; then
        error "git is required but not found."
        echo "  Install git: https://git-scm.com/book/en/v2/Getting-Starteded-Installing-Git"
        exit 1
    fi
    success "git found"
}

# ===================== Install Gatekeeper =====================

install_gatekeeper() {
    INSTALL_DIR="${INSTALL_DIR:-./gatekeeper}"

    # Clone repo
    if [[ -d "$INSTALL_DIR" ]]; then
        info "Directory '$INSTALL_DIR' already exists — pulling latest..."
        cd "$INSTALL_DIR"
        git pull || true
    else
        info "Cloning Gatekeeper into '$INSTALL_DIR'..."
        git clone "$REPO" "$INSTALL_DIR"
        cd "$INSTALL_DIR"
    fi

    # Create venv and install
    info "Installing dependencies..."
    uv venv --python 3.12 2>/dev/null || uv venv --python 3.11
    source .venv/bin/activate
    uv pip install -e .

    if ! command -v gatekeeper &>/dev/null; then
        # Add .venv/bin to PATH for this session
        export PATH="$(pwd)/.venv/bin:$PATH"
        if ! command -v gatekeeper &>/dev/null; then
            error "Gatekeeper installation failed"
        fi
    fi
    success "Gatekeeper installed"
}

# ===================== Interactive Setup =====================

setup_env() {
    local env_file=".env"

    if [[ -f "$env_file" ]]; then
        warn ".env already exists — backing up to .env.bak"
        cp "$env_file" "$env_file.bak"
    fi

    echo ""
    echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}  Gatekeeper Setup Wizard${NC}"
    echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo "  This wizard will configure your .env file with the minimum"
    echo "  required settings. You can edit .env later for advanced options."
    echo ""

    # ---- Google OAuth ----
    echo -e "${BOLD}  Step 1: Google OAuth Credentials${NC}"
    echo ""
    echo "  Gatekeeper needs Google OAuth credentials to access Google APIs."
    echo "  If you don't have them yet, set them up now:"
    echo ""
    echo "    1. Open: ${CYAN}https://console.cloud.google.com/apis/credentials${NC}"
    echo "    2. Create or select a project"
    echo "    3. Enable these APIs:"
    echo "       • Google Drive API"
    echo "       • Gmail API"
    echo "       • Google Calendar API"
    echo "    4. Click ${BOLD}Create Credentials → OAuth 2.0 Client ID${NC}"
    echo "    5. Application type: ${BOLD}Desktop app${NC}"
    echo "    6. Copy the Client ID and Client Secret"
    echo "    7. Go to ${BOLD}OAuth consent screen${NC}"
    echo "       • Set publishing status to ${BOLD}Testing${NC}"
    echo "       • Add your email as a ${BOLD}Test User${NC}"
    echo ""
    echo "  ${YELLOW}⚠ Your email must be a Test User or auth will fail.${NC}"
    echo ""

    prompt "Enter your Google OAuth Client ID (or press Enter to skip):"
    read -r GOOGLE_CLIENT_ID

    prompt "Enter your Google OAuth Client Secret (or press Enter to skip):"
    read -rs GOOGLE_CLIENT_SECRET
    echo ""

    # ---- Modules ----
    echo ""
    echo -e "${BOLD}  Step 2: Google API Modules${NC}"
    echo ""
    echo "  Choose which Google APIs to enable. You can change these later"
    echo "  in .env or via the Admin UI."
    echo ""

    DRIVE_ENABLED=false
    GMAIL_ENABLED=false
    CALENDAR_ENABLED=false

    prompt "Enable Google Drive? [y/N]"
    read -r DRIVE_ANSWER
    [[ "$DRIVE_ANSWER" =~ ^[Yy]$ ]] && DRIVE_ENABLED=true

    prompt "Enable Gmail? [y/N]"
    read -r GMAIL_ANSWER
    [[ "$GMAIL_ANSWER" =~ ^[Yy]$ ]] && GMAIL_ENABLED=true

    prompt "Enable Google Calendar? [y/N]"
    read -r CAL_ANSWER
    [[ "$CAL_ANSWER" =~ ^[Yy]$ ]] && CALENDAR_ENABLED=true

    # If none enabled, warn
    if [[ "$DRIVE_ENABLED" == "false" && "$GMAIL_ENABLED" == "false" && "$CALENDAR_ENABLED" == "false" ]]; then
        echo ""
        warn "No modules enabled. Gatekeeper won't proxy any APIs."
        warn "You can enable them later in .env or the Admin UI."
    fi

    # ---- Server settings ----
    echo ""
    echo -e "${BOLD}  Step 3: Server Settings${NC}"
    echo ""

    GATEKEEPER_HOST="127.0.0.1"
    GATEKEEPER_PORT="8080"

    prompt "Bind address [127.0.0.1]:"
    read -r HOST_INPUT
    [[ -n "$HOST_INPUT" ]] && GATEKEEPER_HOST="$HOST_INPUT"

    prompt "Port [8080]:"
    read -r PORT_INPUT
    [[ -n "$PORT_INPUT" ]] && GATEKEEPER_PORT="$PORT_INPUT"

    # ---- Write .env ----
    cat > "$env_file" <<ENVFILE
# Gatekeeper - Policy Gateway for Google Workspace APIs
# Generated by install.sh — edit as needed

# Server
GATEKEEPER_HOST=${GATEKEEPER_HOST}
GATEKEEPER_PORT=${GATEKEEPER_PORT}
GATEKEEPER_DEBUG=false

# Database
GATEKEEPER_DATABASE_URL=sqlite+aiosqlite:///./gatekeeper.db

# Google OAuth
GATEKEEPER_GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID}
GATEKEEPER_GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET}
GATEKEEPER_GOOGLE_TOKEN_FILE=./google_token.json

# Admin credentials (auto-generated on first run if empty)
GATEKEEPER_ADMIN_USERNAME=admin
GATEKEEPER_ADMIN_PASSWORD=

# Security (auto-generated on first run if empty)
GATEKEEPER_SECRET_KEY=
GATEKEEPER_ENCRYPTION_KEY=
GATEKEEPER_API_KEY_PREFIX=gkp_

# CORS origins
GATEKEEPER_CORS_ORIGINS=["http://localhost:${GATEKEEPER_PORT}"]

# Rate limiting
GATEKEEPER_RATE_LIMIT_PER_MINUTE=120

# Modules
GATEKEEPER_DRIVE_ENABLED=${DRIVE_ENABLED}
GATEKEEPER_GMAIL_ENABLED=${GMAIL_ENABLED}
GATEKEEPER_CALENDAR_ENABLED=${CALENDAR_ENABLED}

# MCP Server
GATEKEEPER_MCP_ENABLED=true
ENVFILE

    success ".env written to $env_file"
}

run_init() {
    echo ""
    info "Initializing database and seeding default policies..."
    gatekeeper init
}

run_auth() {
    echo ""
    echo -e "${BOLD}  Step 4: Google Authorization${NC}"
    echo ""
    echo "  Gatekeeper needs to authenticate with Google to access your data."
    echo "  The device flow works on any machine — you'll get a URL and code to"
    echo "  enter on your phone or another device."
    echo ""

    if [[ -z "${GOOGLE_CLIENT_ID:-}" ]] || [[ -z "${GOOGLE_CLIENT_SECRET:-}" ]]; then
        warn "Google OAuth credentials not configured — skipping auth."
        echo "  Run ${YELLOW}gatekeeper auth${NC} after adding credentials to .env"
        return
    fi

    prompt "Authorize with Google now? [Y/n]"
    read -r AUTH_ANSWER
    if [[ -z "$AUTH_ANSWER" ]] || [[ "$AUTH_ANSWER" =~ ^[Yy]$ ]]; then
        gatekeeper auth
    else
        echo "  Run ${YELLOW}gatekeeper auth${NC} when you're ready."
    fi
}

print_success() {
    # Try to read admin password from secrets file
    local ADMIN_PASS=""
    if [[ -f "gatekeeper_secrets.json" ]]; then
        ADMIN_PASS=$(python3 -c "import json; d=json.load(open('gatekeeper_secrets.json')); print(d.get('admin_password', ''))" 2>/dev/null || true)
    fi

    # Try to read API key from recent output (best effort)
    local API_KEY=""
    if [[ -f "gatekeeper.db" ]]; then
        API_KEY=$(gatekeeper key list 2>/dev/null | head -3 | grep -oP 'gkp_\S+' | head -1 || true)
    fi

    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}  🎉 Gatekeeper is set up and ready!${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo "  Start the server:"
    echo -e "    ${CYAN}gatekeeper serve${NC}"
    echo ""
    echo "  Admin UI:"
    echo -e "    ${CYAN}http://localhost:${GATEKEEPER_PORT:-8080}/admin/${NC}"
    if [[ -n "$ADMIN_PASS" ]]; then
        echo -e "    ${YELLOW}Username: admin    Password: ${ADMIN_PASS}${NC}"
    fi
    echo ""
    echo "  MCP endpoint (for AI agents):"
    echo -e "    ${CYAN}http://localhost:${GATEKEEPER_PORT:-8080}/mcp/sse${NC}"
    echo ""
    echo "  Useful commands:"
    echo -e "    ${CYAN}gatekeeper status${NC}          — Show configuration"
    echo -e "    ${CYAN}gatekeeper key create${NC}       — Create a new API key"
    echo -e "    ${CYAN}gatekeeper key list${NC}         — List API keys"
    echo -e "    ${CYAN}gatekeeper auth${NC}            — (Re-)authorize with Google"
    echo ""
    echo "  Config file: ${CYAN}.env${NC}"
    echo "  Secrets:     ${CYAN}gatekeeper_secrets.json${NC}  (auto-generated)"
    echo "  Database:    ${CYAN}gatekeeper.db${NC}  (auto-generated)"
    echo ""
    echo -e "${YELLOW}  ⚠ Save the admin password — it's only shown once!${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# ===================== Main =====================

main() {
    echo -e "${BLUE}"
    echo "  ╔══════════════════════════════════════╗"
    echo "  ║     Gatekeeper Installer            ║"
    echo "  ║     Policy Gateway for Google APIs   ║"
    echo "  ╚══════════════════════════════════════╝"
    echo -e "${NC}"

    # 1. Check and install dependencies
    check_python
    install_uv
    check_git

    # 2. Install Gatekeeper
    install_gatekeeper

    # 3. Interactive setup (or skip if --non-interactive)
    if [[ "$NON_INTERACTIVE" == "true" ]]; then
        echo ""
        info "Non-interactive mode — skipping setup wizard."
        echo "  Run these commands to complete setup:"
        echo ""
        echo "    cp .env.example .env   # Then edit .env with your settings"
        echo "    gatekeeper init         # Initialize database"
        echo "    gatekeeper auth         # Authorize with Google"
        echo ""
    else
        setup_env
        run_init
        run_auth
        print_success
    fi
}

main "$@"