#!/usr/bin/env bash
# Gatekeeper install script
# Supports: Ubuntu/Debian, Fedora/RHEL, Arch Linux, macOS
# Installs: uv (if needed), then gatekeeper via uv tool install
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/brimdor/gatekeeper/main/install.sh | bash
#   or:
#   bash install.sh

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info()  { echo -e "${BLUE}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }
success() { echo -e "${GREEN}[OK]${NC} $*"; }

REPO="https://github.com/brimdor/gatekeeper"

# ===================== Check Python =====================
check_python() {
    if command -v python3 &>/dev/null; then
        PYTHON=python3
    elif command -v python &>/dev/null; then
        PYTHON=python
    else
        error "Python 3.11+ is required but not found. Install it first: https://www.python.org/downloads/"
    fi

    PY_VERSION=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    if (( $(echo "$PY_VERSION < 3.11" | bc -l) )); then
        error "Python 3.11+ required, found $PY_VERSION"
    fi
    info "Python $PY_VERSION found ✓"
}

# ===================== Install uv =====================
install_uv() {
    if command -v uv &>/dev/null; then
        UV_VERSION=$(uv --version 2>/dev/null || echo "unknown")
        info "uv $UV_VERSION already installed ✓"
        return
    fi

    info "Installing uv (Python package manager)..."
    if [[ "$(uname)" == "Darwin" ]]; then
        # macOS - prefer brew
        if command -v brew &>/dev/null; then
            brew install uv
        else
            curl -LsSf https://astral.sh/uv/install.sh | sh
            export PATH="$HOME/.local/bin:$PATH"
        fi
    else
        # Linux
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.local/bin:$PATH"
    fi

    if ! command -v uv &>/dev/null; then
        error "uv installation failed"
    fi
    success "uv installed ✓"
}

# ===================== Install Gatekeeper =====================
install_gatekeeper() {
    info "Installing Gatekeeper..."
    uv tool install "gatekeeper @ git+$REPO"

    if ! command -v gatekeeper &>/dev/null; then
        error "Gatekeeper installation failed. Try: uv tool install git+$REPO"
    fi
    success "Gatekeeper installed ✓"
}

# ===================== Initial Setup =====================
initial_setup() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}  🎉 Gatekeeper is installed!${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo "  Next steps:"
    echo ""
    echo "  1. Create a .env file from the template:"
    echo "     ${YELLOW}cp .env.example .env && nano .env${NC}"
    echo ""
    echo "  2. Set up Google OAuth credentials:"
    echo "     • Go to https://console.cloud.google.com/apis/credentials"
    echo "     • Create an OAuth 2.0 Client ID (Desktop app type)"
    echo "     • Add the client ID and secret to your .env"
    echo ""
    echo "  3. Initialize the database:"
    echo "     ${YELLOW}gatekeeper init${NC}"
    echo ""
    echo "  4. Authorize with Google (opens browser):"
    echo "     ${YELLOW}gatekeeper auth${NC}"
    echo ""
    echo "  5. Create an API key for your agent:"
    echo "     ${YELLOW}gatekeeper key create --name my-agent${NC}"
    echo ""
    echo "  6. Start the server:"
    echo "     ${YELLOW}gatekeeper serve${NC}"
    echo ""
    echo "  7. Open the admin UI:"
    echo "     ${YELLOW}http://localhost:8080/admin/${NC}"
    echo ""
    echo "  MCP endpoint (for AI agents):"
    echo "     ${YELLOW}http://localhost:8080/mcp/sse${NC}"
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# ===================== Main =====================
main() {
    echo -e "${BLUE}"
    echo "  ╔══════════════════════════════════════╗"
    echo "  ║     Gatekeeper Installer            ║"
    echo "  ║     Policy Gateway for Google APIs  ║"
    echo "  ╚══════════════════════════════════════╝"
    echo -e "${NC}"

    check_python
    install_uv
    install_gatekeeper
    initial_setup
}

main "$@"