#!/usr/bin/env bash
# Gatekeeper install script
# Supports: Ubuntu/Debian, Fedora/RHEL, Arch Linux, macOS
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/brimdor/gatekeeper/main/install.sh | bash
#   bash install.sh [--non-interactive] [--dir=PATH]
#
# --non-interactive: Install only, skip setup wizard
# --dir=PATH:        Installation directory (default: ./gatekeeper)

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()    { printf "${BLUE}[INFO]${NC} %s\n" "$*"; }
warn()    { printf "${YELLOW}[WARN]${NC} %s\n" "$*"; }
error()   { printf "${RED}[ERROR]${NC} %s\n" "$*" >&2; exit 1; }
success() { printf "${GREEN}[OK]${NC} %s\n" "$*"; }
prompt()  { printf "${CYAN}[?]${NC} %s " "$*"; }

# Read from terminal even when piped (curl ... | bash)
# IFS= preserves leading/trailing whitespace, -r preserves backslashes
tty_read()    { local IFS=''; read -r "$1" < /dev/tty; }
tty_read_s()  {
    # Read sensitive input with echo disabled.
    # We use stty instead of read -s because read -s can mangle
    # special characters like !, $, backticks, and backslashes.
    local saved_tty
    saved_tty=$(stty -g < /dev/tty)
    trap 'stty "$saved_tty" < /dev/tty 2>/dev/null' EXIT
    stty -echo -icanon < /dev/tty
    local IFS=''
    read -r "$1" < /dev/tty
    stty "$saved_tty" < /dev/tty
    trap - EXIT
    printf "\n"
}
tty_ask_yn()  {
    local default="${2:-n}"
    local answer
    while true; do
        printf "${CYAN}[?]${NC} %s [%s] " "$1" "$(if [[ "$default" == "y" ]]; then echo "Y/n"; else echo "y/N"; fi)"
        local IFS=''
        read -r answer < /dev/tty || answer=""
        answer="${answer,,}"
        [[ -z "$answer" ]] && answer="$default"
        case "$answer" in
            y|yes) return 0 ;;
            n|no)  return 1 ;;
            *)     echo "  Please answer y or n." ;;
        esac
    done
}

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

check_python() {
    local python_cmd=""
    if command -v python3 &>/dev/null; then
        python_cmd=python3
    elif command -v python &>/dev/null; then
        python_cmd=python
    else
        error "Python 3.11+ is required but not found."$'\n'"  Install it first: https://www.python.org/downloads/"
    fi

    # Try version check (needs bc)
    if command -v bc &>/dev/null; then
        local py_version
        py_version=$($python_cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        if (( $(echo "$py_version < 3.11" | bc -l) )); then
            error "Python 3.11+ required, found $py_version"$'\n'"  Upgrade: https://www.python.org/downloads/"
        fi
        success "Python $py_version"
    else
        success "Python found ($python_cmd)"
    fi

    PYTHON="$python_cmd"
}

install_uv() {
    if command -v uv &>/dev/null; then
        local uv_version
        uv_version=$(uv --version 2>/dev/null || echo "unknown")
        success "uv $uv_version"
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
        error "git is required but not found."$'\n'"  Install git: https://git-scm.com/book/en/v2/Getting-Started-Installing-Git"
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
    # shellcheck disable=SC1091
    source .venv/bin/activate
    uv pip install -e .

    # Ensure gatekeeper is findable
    if ! command -v gatekeeper &>/dev/null; then
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

    printf "\n"
    printf "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
    printf "${BOLD}  Gatekeeper Setup Wizard${NC}\n"
    printf "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
    printf "\n"
    printf "  This wizard will configure your .env file with the minimum\n"
    printf "  required settings. You can edit .env later for advanced options.\n"
    printf "\n"

    # ---- Google OAuth ----
    printf "${BOLD}  Step 1: Google OAuth Credentials${NC}\n"
    printf "\n"
    printf "  Gatekeeper needs Google OAuth credentials to access Google APIs.\n"
    printf "  If you don't have them yet, set them up now:\n"
    printf "\n"
    printf "    1. Open: %s\n" "${CYAN}https://console.cloud.google.com/apis/credentials${NC}"
    printf "    2. Create or select a project\n"
    printf "    3. Enable these APIs:\n"
    printf "       • Google Drive API\n"
    printf "       • Gmail API\n"
    printf "       • Google Calendar API\n"
    printf "    4. Click %s\n" "${BOLD}Create Credentials → OAuth 2.0 Client ID${NC}"
    printf "    5. Application type: %s\n" "${BOLD}Desktop app${NC}"
    printf "    6. Copy the Client ID and Client Secret\n"
    printf "    7. Go to %s\n" "${BOLD}OAuth consent screen${NC}"
    printf "       • Set publishing status to %s\n" "${BOLD}Testing${NC}"
    printf "       • Add your email as a %s\n" "${BOLD}Test User${NC}"
    printf "\n"
    printf "  %s\n" "${YELLOW}⚠ Your email must be a Test User or auth will fail.${NC}"
    printf "\n"

    local google_client_id=""
    local google_client_secret=""

    prompt "Enter your Google OAuth Client ID (or press Enter to skip):"
    tty_read google_client_id
    GOOGLE_CLIENT_ID="$google_client_id"

    prompt "Enter your Google OAuth Client Secret (input hidden):"
    tty_read_s google_client_secret
    GOOGLE_CLIENT_SECRET="$google_client_secret"

    # ---- Modules ----
    printf "\n"
    printf "${BOLD}  Step 2: Google API Modules${NC}\n"
    printf "\n"
    printf "  Choose which Google APIs to enable. You can change these later\n"
    printf "  in .env or via the Admin UI.\n"
    printf "\n"

    local drive_enabled=false
    local gmail_enabled=false
    local calendar_enabled=false

    if tty_ask_yn "Enable Google Drive?" "y"; then drive_enabled=true; fi
    if tty_ask_yn "Enable Gmail?" "y"; then gmail_enabled=true; fi
    if tty_ask_yn "Enable Google Calendar?" "y"; then calendar_enabled=true; fi

    if [[ "$drive_enabled" == "false" && "$gmail_enabled" == "false" && "$calendar_enabled" == "false" ]]; then
        printf "\n"
        warn "No modules enabled. Gatekeeper won't proxy any APIs."
        warn "You can enable them later in .env or the Admin UI."
    fi

    # ---- Server settings ----
    printf "\n"
    printf "${BOLD}  Step 3: Server Settings${NC}\n"
    printf "\n"

    local gatekeeper_host="127.0.0.1"
    local gatekeeper_port="8080"

    prompt "Bind address [127.0.0.1]:"
    tty_read host_input
    [[ -n "$host_input" ]] && gatekeeper_host="$host_input"

    prompt "Port [8080]:"
    tty_read port_input
    [[ -n "$port_input" ]] && gatekeeper_port="$port_input"

    # ---- Write .env ----
    cat > "$env_file" << ENVFILE
# Gatekeeper - Policy Gateway for Google Workspace APIs
# Generated by install.sh — edit as needed

# Server
GATEKEEPER_HOST=${gatekeeper_host}
GATEKEEPER_PORT=${gatekeeper_port}
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
GATEKEEPER_CORS_ORIGINS=["http://localhost:${gatekeeper_port}"]

# Rate limiting
GATEKEEPER_RATE_LIMIT_PER_MINUTE=120

# Modules
GATEKEEPER_DRIVE_ENABLED=${drive_enabled}
GATEKEEPER_GMAIL_ENABLED=${gmail_enabled}
GATEKEEPER_CALENDAR_ENABLED=${calendar_enabled}

# MCP Server
GATEKEEPER_MCP_ENABLED=true
ENVFILE

    success ".env written"
}

run_init() {
    printf "\n"
    info "Initializing database and seeding default policies..."
    gatekeeper init
}

run_auth() {
    printf "\n"
    printf "${BOLD}  Step 4: Google Authorization${NC}\n"
    printf "\n"
    printf "  Gatekeeper needs to authenticate with Google to access your data.\n"
    printf "  The device flow works on any machine — you'll get a URL and code to\n"
    printf "  enter on your phone or another device.\n"
    printf "\n"

    if [[ -z "${GOOGLE_CLIENT_ID:-}" ]] || [[ -z "${GOOGLE_CLIENT_SECRET:-}" ]]; then
        warn "Google OAuth credentials not configured — skipping auth."
        printf "  Run %s when you've added credentials to .env\n" "${CYAN}gatekeeper auth${NC}"
        return
    fi

    if tty_ask_yn "Authorize with Google now?" "y"; then
        gatekeeper auth
    else
        printf "  Run %s when you're ready.\n" "${CYAN}gatekeeper auth${NC}"
    fi
}

print_success() {
    # Try to read admin password from secrets file
    local admin_pass=""
    if [[ -f "gatekeeper_secrets.json" ]]; then
        admin_pass=$($PYTHON -c "import json; d=json.load(open('gatekeeper_secrets.json')); print(d.get('admin_password', ''))" 2>/dev/null || true)
    fi

    local port="${GATEKEEPER_PORT:-8080}"

    printf "\n"
    printf "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
    printf "${GREEN}  🎉 Gatekeeper is set up and ready!${NC}\n"
    printf "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
    printf "\n"
    printf "  Start the server:\n"
    printf "    %s\n" "${CYAN}gatekeeper serve${NC}"
    printf "\n"
    printf "  Admin UI:\n"
    printf "    %s\n" "${CYAN}http://localhost:${port}/admin/${NC}"
    if [[ -n "$admin_pass" ]]; then
        printf "    %s\n" "${YELLOW}Username: admin    Password: ${admin_pass}${NC}"
    fi
    printf "\n"
    printf "  MCP endpoint (for AI agents):\n"
    printf "    %s\n" "${CYAN}http://localhost:${port}/mcp/sse${NC}"
    printf "\n"
    printf "  Useful commands:\n"
    printf "    %-35s %s\n" "${CYAN}gatekeeper status${NC}" "— Show configuration"
    printf "    %-35s %s\n" "${CYAN}gatekeeper key create --name my-agent${NC}" "— Create API key"
    printf "    %-35s %s\n" "${CYAN}gatekeeper key list${NC}" "— List API keys"
    printf "    %-35s %s\n" "${CYAN}gatekeeper auth${NC}" "— (Re-)authorize with Google"
    printf "\n"
    printf "  Config file: %s\n" "${CYAN}.env${NC}"
    printf "  Secrets:     %s  (auto-generated)\n" "${CYAN}gatekeeper_secrets.json${NC}"
    printf "  Database:    %s  (auto-generated)\n" "${CYAN}gatekeeper.db${NC}"
    printf "\n"
    printf "  %s\n" "${YELLOW}⚠ Save the admin password — it's only shown once!${NC}"
    printf "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
}

# ===================== Main =====================

main() {
    printf "${BLUE}\n"
    printf "  ╔══════════════════════════════════════╗\n"
    printf "  ║     Gatekeeper Installer            ║\n"
    printf "  ║     Policy Gateway for Google APIs   ║\n"
    printf "  ╚══════════════════════════════════════╝\n"
    printf "${NC}\n"

    # 1. Check and install dependencies
    check_python
    install_uv
    check_git

    # 2. Install Gatekeeper
    install_gatekeeper

    # 3. Interactive setup (or skip if --non-interactive)
    if [[ "$NON_INTERACTIVE" == "true" ]]; then
        printf "\n"
        info "Non-interactive mode — skipping setup wizard."
        printf "  Run these commands to complete setup:\n"
        printf "\n"
        printf "    cp .env.example .env   # Then edit .env with your settings\n"
        printf "    gatekeeper init         # Initialize database\n"
        printf "    gatekeeper auth         # Authorize with Google\n"
        printf "\n"
    else
        setup_env
        run_init
        run_auth
        print_success
    fi
}

main "$@"