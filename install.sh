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

    # Create ~/.local/bin if needed and symlink gatekeeper
    mkdir -p "$HOME/.local/bin"
    local gk_bin
    gk_bin="$(pwd)/.venv/bin/gatekeeper"
    if [[ -x "$gk_bin" ]]; then
        ln -sf "$gk_bin" "$HOME/.local/bin/gatekeeper"
        info "Linked gatekeeper → ~/.local/bin/gatekeeper"
    else
        error "gatekeeper binary not found in venv — installation may have failed"
    fi

    # Ensure ~/.local/bin is in PATH for this session
    export PATH="$HOME/.local/bin:$PATH"

    # Persist PATH for future sessions
    local shell_rc="$HOME/.bashrc"
    if [[ -f "$HOME/.zshrc" ]]; then
        shell_rc="$HOME/.zshrc"
    fi
    if ! grep -q '.local/bin' "$shell_rc" 2>/dev/null; then
        echo '' >> "$shell_rc"
        echo '# Added by Gatekeeper installer' >> "$shell_rc"
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$shell_rc"
        info "Added ~/.local/bin to PATH in $shell_rc"
    fi

    if ! command -v gatekeeper &>/dev/null; then
        error "Gatekeeper installation failed — gatekeeper not found in PATH"
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
    printf "    1. Open: ${CYAN}https://console.cloud.google.com/apis/library${NC}\n"
    printf "    2. Create or select a project\n"
    printf "    3. Enable these APIs (search each one and click Enable):\n"
    printf "       • Google Drive API\n"
    printf "       • Gmail API\n"
    printf "       • Google Calendar API\n"
    printf "    4. Go to: ${CYAN}https://console.cloud.google.com/auth/clients${NC}\n"
    printf "       • Click ${BOLD}Create Client${NC}\n"
    printf "       • Application type: ${BOLD}Desktop app${NC}\n"
    printf "       • Copy the Client ID and Client Secret\n"
    printf "    5. Go to: ${CYAN}https://console.cloud.google.com/auth/branding${NC}\n"
    printf "       • If not configured yet, click ${BOLD}Get Started${NC}\n"
    printf "         - App name: Gatekeeper\n"
    printf "         - Audience: ${BOLD}External${NC}\n"
    printf "    6. Add OAuth scopes — go to: ${CYAN}https://console.cloud.google.com/auth/data-access${NC}\n"
    printf "       Click ${BOLD}Add or Remove Scopes${NC} and add ALL of these:\n"
    printf "       • ${CYAN}https://www.googleapis.com/auth/drive${NC} (Drive)\n"
    printf "       • ${CYAN}https://www.googleapis.com/auth/gmail.modify${NC} (Gmail)\n"
    printf "       • ${CYAN}https://www.googleapis.com/auth/gmail.send${NC} (Gmail)\n"
    printf "       • ${CYAN}https://www.googleapis.com/auth/gmail.compose${NC} (Gmail)\n"
    printf "       • ${CYAN}https://www.googleapis.com/auth/gmail.settings.basic${NC} (Gmail)\n"
    printf "       • ${CYAN}https://www.googleapis.com/auth/calendar${NC} (Calendar)\n"
    printf "       • ${CYAN}https://www.googleapis.com/auth/calendar.events${NC} (Calendar)\n"
    printf "       Search by keyword in the scope picker (type \"drive\", \"gmail\", or \"calendar\").\n"
    printf "    7. Add yourself as a Test User — go to: ${CYAN}https://console.cloud.google.com/auth/audience${NC}\n"
    printf "       • Scroll to ${BOLD}Test users${NC} → ${BOLD}Add users${NC}\n"
    printf "       • Enter your Google account email\n"
    printf "\n"
    printf "  ${YELLOW}⚠ Missing scopes cause 403 ACCESS_TOKEN_SCOPE_INSUFFICIENT errors.${NC}\n"
    printf "  ${YELLOW}⚠ Your email must be a Test User or auth will fail.${NC}\n"
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
GATEKEEPER_MCP_ALLOWED_HOSTS=[]
ENVFILE

    success ".env written"
}

run_init() {
    printf "\n"
    info "Initializing database and seeding default policies..."
    INIT_OUTPUT=$(gatekeeper init 2>&1) || true
    printf "%s\n" "$INIT_OUTPUT"

    # Extract the default API key from init output (it's only shown once)
    DEFAULT_API_KEY=$(echo "$INIT_OUTPUT" | grep -oP 'gkp_[A-Za-z0-9_-]+' | head -1) || true
}

run_auth() {
    printf "\n"
    printf "${BOLD}  Step 4: Google Authorization${NC}\n"
    printf "\n"
    printf "  Gatekeeper needs to authenticate with Google to access your data.\n"
    printf "  The default flow opens your browser for authorization.\n"
    printf "  If you're on SSH, it will print a URL for you to open manually.\n"
    printf "\n"

    if [[ -z "${GOOGLE_CLIENT_ID:-}" ]] || [[ -z "${GOOGLE_CLIENT_SECRET:-}" ]]; then
        warn "Google OAuth credentials not configured — skipping auth."
        printf "  Run ${CYAN}gatekeeper auth${NC} when you've added credentials to .env\n"
        return
    fi

    if tty_ask_yn "Authorize with Google now?" "y"; then
        gatekeeper auth
    else
        printf "  Run ${CYAN}gatekeeper auth${NC} when you're ready.\n"
    fi
}

configure_mcp_hosts() {
    printf "\n"
    printf "${BOLD}  Step 5: MCP Allowed Hosts${NC}\n"
    printf "\n"
    printf "  Gatekeeper's MCP server validates the Host header on incoming\n"
    printf "  connections for security (DNS rebinding protection).\n"
    printf "  By default, only localhost connections are allowed.\n"
    printf "\n"
    printf "  If you access Gatekeeper from another machine (Tailscale,\n"
    printf "  LAN IP, reverse proxy), add that hostname here.\n"
    printf "\n"
    printf "  Examples:\n"
    printf "    ${CYAN}100.127.113.87${NC}          (Tailscale IP)\n"
    printf "    ${CYAN}myhost.tail-abc.ts.net${NC}  (Tailscale domain)\n"
    printf "    ${CYAN}10.0.30.10${NC}              (LAN IP)\n"
    printf "    ${CYAN}*${NC}                        (allow any host — less secure)\n"
    printf "\n"

    local env_file=".env"
    local hosts=""

    # Collect hosts interactively
    while true; do
        prompt "Add a host? (leave empty to finish):"
        tty_read host_input
        if [[ -z "$host_input" ]]; then
            break
        fi
        if [[ -n "$hosts" ]]; then
            hosts="${hosts}, ${host_input}"
        else
            hosts="${host_input}"
        fi
        printf "  ✅ Added ${CYAN}%s${NC}\n" "$host_input"
    done

    if [[ -n "$hosts" ]]; then
        # Build JSON array
        local json_array="["
        local first=true
        for h in ${hosts//,/ }; do
            h="${h#"${h%%[![:space:]]*}"}"  # trim leading whitespace
            h="${h%"${h##*[![:space:]]}"}"  # trim trailing whitespace
            if [[ "$first" == "true" ]]; then
                json_array="${json_array}\"${h}\""
                first=false
            else
                json_array="${json_array}, \"${h}\""
            fi
        done
        json_array="${json_array}]"

        # Update .env file
        if grep -q "^GATEKEEPER_MCP_ALLOWED_HOSTS=" "$env_file" 2>/dev/null; then
            sed -i "s|^GATEKEEPER_MCP_ALLOWED_HOSTS=.*|GATEKEEPER_MCP_ALLOWED_HOSTS=${json_array}|" "$env_file"
        else
            echo "GATEKEEPER_MCP_ALLOWED_HOSTS=${json_array}" >> "$env_file"
        fi
        success "MCP allowed hosts configured: $hosts"
    else
        info "No additional MCP hosts configured (localhost only)."
        info "Run ${CYAN}gatekeeper hosts add <host>${NC} later if needed."
    fi
}

run_service() {
    printf "\n"
    printf "${BOLD}  Step 6: Systemd Service${NC}\n"
    printf "\n"
    printf "  Gatekeeper can run as a systemd service so it starts\n"
    printf "  automatically and restarts on failure.\n"
    printf "\n"
    printf "  ${CYAN}User service${NC}   — tied to your login session (requires linger for always-on)\n"
    printf "  ${CYAN}System service${NC} — starts at boot, independent of sessions (${BOLD}recommended for servers${NC})\n"
    printf "\n"

    if ! command -v systemctl &>/dev/null; then
        warn "systemctl not found — skipping service setup."
        printf "  You can start Gatekeeper manually with: ${CYAN}gatekeeper serve${NC}\n"
        return
    fi

    # Default to system on Linux servers (where sudo is available)
    local default_scope="system"
    if [[ "$(uname)" == "Darwin" ]]; then
        default_scope="user"
    fi
    # Check if systemd user sessions are available
    if ! systemctl --user is-system-running &>/dev/null && ! systemctl --user status &>/dev/null; then
        if ! command -v sudo &>/dev/null; then
            warn "Neither systemd user sessions nor sudo are available — skipping service setup."
            printf "  You can start Gatekeeper manually with: ${CYAN}gatekeeper serve${NC}\n"
            return
        fi
        # Only system scope is viable
        default_scope="system"
        info "systemd user sessions unavailable — will install as system service."
    fi

    local scope_question="Install Gatekeeper as a systemd service?"
    if [[ "$default_scope" == "system" ]]; then
        scope_question="Install Gatekeeper as a systemd service? (system scope recommended)"
    fi

    if tty_ask_yn "$scope_question" "y"; then
        # Ask which scope
        local scope="$default_scope"
        if tty_ask_yn "Use system scope? (starts at boot, no user session needed) [Y/n]"; then
            scope="system"
        else
            scope="user"
            warn "User scope requires 'loginctl enable-linger' to survive disconnects."
            printf "  Run ${CYAN}loginctl enable-linger \$USER${NC} after installation.\n"
        fi
        gatekeeper service install "--scope=$scope"
    else
        printf "  Run ${CYAN}gatekeeper service install --scope system${NC} to set it up later.\n"
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
    printf "    ${CYAN}gatekeeper serve${NC}\n"
    printf "\n"
    printf "  Admin UI:\n"
    printf "    ${CYAN}http://localhost:${port}/admin/${NC}\n"
    if [[ -n "$admin_pass" ]]; then
        printf "    ${YELLOW}Username: admin    Password: ${admin_pass}${NC}\n"
    fi
    printf "\n"
    printf "  MCP endpoint (for AI agents):\n"
    printf "    ${CYAN}http://localhost:${port}/mcp/sse${NC}\n"
    if [[ -n "$DEFAULT_API_KEY" ]]; then
        printf "\n"
        printf "  ${YELLOW}Default API Key:${NC}\n"
        printf "    ${CYAN}${DEFAULT_API_KEY}${NC}\n"
        printf "    ${YELLOW}⚠ Save this — it won't be shown again!${NC}\n"
    fi
    printf "\n"
    printf "  Useful commands:\n"
    printf "    ${CYAN}gatekeeper status${NC}          — Show configuration\n"
    printf "    ${CYAN}gatekeeper key create --name my-agent${NC}  — Create API key\n"
    printf "    ${CYAN}gatekeeper key list${NC}        — List API keys\n"
    printf "    ${CYAN}gatekeeper auth${NC}            — (Re-)authorize with Google\n"
    printf "    ${CYAN}gatekeeper service status${NC}   — Check service status\n"
    printf "    ${CYAN}gatekeeper service restart${NC}  — Restart the service\n"
    printf "    ${CYAN}gatekeeper service logs -f${NC}  — Tail service logs\n"
    printf "    ${CYAN}gatekeeper service install --scope system${NC}  — Install as boot service\n
    printf "    ${CYAN}gatekeeper hosts list${NC}        — Show MCP allowed hosts\n"
    printf "    ${CYAN}gatekeeper hosts add <host>${NC}  — Add MCP allowed host\n"
    printf "\n"
    printf "  Config file: ${CYAN}.env${NC}\n"
    printf "  Secrets:     ${CYAN}gatekeeper_secrets.json${NC}  (auto-generated)\n"
    printf "  Database:    ${CYAN}gatekeeper.db${NC}  (auto-generated)\n"
    printf "\n"
    printf "  ${YELLOW}⚠ Save the admin password and API key — they're only shown once!${NC}\n"
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
        configure_mcp_hosts
        run_service
        print_success
    fi
}

main "$@"