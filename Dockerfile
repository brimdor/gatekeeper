# Gatekeeper - Multi-stage build for amd64 + arm64
FROM python:3.11-slim AS builder

# Install uv
RUN pip install uv

WORKDIR /app

# Copy project files
COPY pyproject.toml README.md ./
COPY gatekeeper/ gatekeeper/

# Install dependencies
RUN uv pip install --system --no-cache -e ".[dev]"

FROM python:3.11-slim AS runtime

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages/ /usr/local/lib/python3.11/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/
COPY --from=builder /app/gatekeeper/ /app/gatekeeper/

WORKDIR /app

# Create data directory
RUN mkdir -p /data

# Set environment defaults
ENV GATEKEEPER_HOST=0.0.0.0
ENV GATEKEEPER_PORT=8080
ENV GATEKEEPER_DATABASE_URL=sqlite+aiosqlite:////data/gatekeeper.db
ENV GATEKEEPER_GOOGLE_TOKEN_FILE=/data/google_token.json

# Expose ports
EXPOSE 8080 8081

# Volume for persistent data
VOLUME ["/data"]

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run
CMD ["gatekeeper", "serve"]