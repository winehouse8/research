# Production Dockerfile for the JIRA + GitHub webhook receiver
# Base: Python 3.11-slim (Debian Bookworm)

FROM python:3.11-slim AS base

# ── System dependencies ───────────────────────────────────────────────────────
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

# ── Non-root user ─────────────────────────────────────────────────────────────
RUN groupadd --gid 1001 appgroup \
    && useradd --uid 1001 --gid appgroup --shell /bin/bash --create-home appuser

# ── Working directory ─────────────────────────────────────────────────────────
WORKDIR /app

# ── Python dependencies (separate layer for cache efficiency) ─────────────────
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ── Application source ────────────────────────────────────────────────────────
COPY main.py jira_client.py github_client.py ./

# ── Ownership ─────────────────────────────────────────────────────────────────
RUN chown -R appuser:appgroup /app

USER appuser

# ── Runtime configuration ─────────────────────────────────────────────────────
# All secrets are injected via environment variables at runtime; no .env file
# is baked into the image.
#
# Required env vars:
#   JIRA_BASE_URL          e.g. https://your-org.atlassian.net
#   JIRA_EMAIL             service-account email
#   JIRA_API_TOKEN         Atlassian API token
#   GITHUB_TOKEN           GitHub personal access / app token
#   GITHUB_WEBHOOK_SECRET  secret configured in GitHub webhook settings
#   JIRA_WEBHOOK_TOKEN     token configured in JIRA webhook settings
#   PORT                   (optional) listening port, default 8000

ENV PORT=8000 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

# ── Health check ──────────────────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# ── Entrypoint ────────────────────────────────────────────────────────────────
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT} --log-config /dev/null"]
