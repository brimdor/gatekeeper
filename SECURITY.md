# Security Policy

## Supported Versions

| Version | Supported |
| ------- | --------- |
| 0.1.x   | ✅        |

Gatekeeper is pre-1.0 software. Breaking changes may occur between minor versions.

## Reporting a Vulnerability

**Do not report security vulnerabilities through public GitHub issues.**

Instead, please report them via one of these methods:

1. **Email:** Send details to the maintainer (see GitHub profile for contact info)
2. **GitHub Security Advisory:** Use the [private vulnerability reporting](https://github.com/brimdor/gatekeeper/security/advisories/new) feature

Please include:

- Description of the vulnerability
- Steps to reproduce or proof of concept
- Affected versions
- Any potential mitigations you've identified

You can expect:

- Acknowledgment within 48 hours
- An initial assessment within 5 business days
- A fix or mitigation plan within 30 days for confirmed vulnerabilities

## Security Considerations

Gatekeeper handles sensitive data:

- **Google OAuth tokens** — stored encrypted at rest using Fernet (symmetric encryption)
- **API keys** — hashed with bcrypt, never stored in plaintext
- **Admin credentials** — auto-generated with high entropy, stored in `gatekeeper_secrets.json` (chmod 600)
- **CORS** — configurable; defaults to localhost only

### Deployment Checklist

- [ ] Change the default admin password or let Gatekeeper auto-generate one
- [ ] Set `GATEKEEPER_HOST=127.0.0.1` unless you have a reverse proxy
- [ ] Restrict `GATEKEEPER_CORS_ORIGINS` to trusted domains only
- [ ] Enable HTTPS via a reverse proxy (nginx, Caddy, Traefik)
- [ ] Don't expose `gatekeeper_secrets.json` or `google_token.json` publicly
- [ ] Add `.env` and `*_secrets.json` to `.gitignore` (already in the default `.gitignore`)