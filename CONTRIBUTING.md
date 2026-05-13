# Contributing to Gatekeeper

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

1. **Clone and install:**
   ```bash
   git clone https://github.com/brimdor/gatekeeper.git
   cd gatekeeper
   uv venv && source .venv/bin/activate
   uv pip install -e ".[dev]"
   ```

2. **Configure:**
   ```bash
   cp .env.example .env
   # Edit .env with your Google OAuth credentials
   ```

3. **Run tests:**
   ```bash
   pytest tests/ -v
   ```

4. **Start the server:**
   ```bash
   gatekeeper serve
   ```

## Making Changes

- **Fork** the repository and create a feature branch from `main`
- **Write tests** for any new functionality — aim for regression coverage
- **Run the full test suite** before submitting: `pytest tests/ -v`
- **Keep PRs focused** — one feature or fix per PR
- **Document** new routes, config options, or CLI changes in the README

## Code Style

- Python 3.11+ (type hints encouraged)
- Follow the existing patterns in the codebase
- Async where it matters (database, HTTP calls) — sync is fine for CLI
- Module system: add new Google API modules under `gatekeeper/modules/`

## Reporting Issues

- Include Gatekeeper version, Python version, and OS
- Share sanitized error logs (remove API keys, tokens, and secrets)
- Steps to reproduce are always appreciated

## Security

**Do not report security vulnerabilities in public GitHub issues.** See [SECURITY.md](SECURITY.md) for responsible disclosure.