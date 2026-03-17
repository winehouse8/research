# n8n Setup Guide — JIRA + GitHub CI/CD Certification Evidence Automation

This guide walks through deploying n8n Community Edition for bidirectional
JIRA ↔ GitHub synchronisation as part of the software certification evidence
automation system.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Step-by-Step Deployment](#2-step-by-step-deployment)
3. [Configuring JIRA Webhooks](#3-configuring-jira-webhooks)
4. [Configuring GitHub Webhooks](#4-configuring-github-webhooks)
5. [Importing Workflow JSONs](#5-importing-workflow-jsns)
6. [Testing with Sample Payloads](#6-testing-with-sample-payloads)
7. [Monitoring and Troubleshooting](#7-monitoring-and-troubleshooting)

---

## 1. Prerequisites

| Requirement | Minimum version | Notes |
|---|---|---|
| Docker Engine | 24.x | `docker --version` |
| Docker Compose plugin | 2.x | `docker compose version` |
| Domain name | — | Must resolve publicly for Let's Encrypt |
| JIRA Cloud / Server | — | Admin access to configure webhooks |
| GitHub repository | — | Admin access to configure webhooks |
| JIRA API token | — | Generate at id.atlassian.com → Security |
| GitHub fine-grained PAT | — | Scopes: `pull_requests:write`, `statuses:write`, `issues:write` |

### Firewall / networking requirements

- Port 80 open inbound (ACME HTTP-01 challenge + HTTP → HTTPS redirect)
- Port 443 open inbound (HTTPS traffic from JIRA and GitHub)
- Outbound HTTPS to `api.github.com` and your JIRA instance

---

## 2. Step-by-Step Deployment

### 2.1 Clone / copy the deployment files

```bash
# Copy the phase2-integration/n8n directory to your server
scp -r phase2-integration/n8n user@your-server:/opt/certification-n8n
ssh user@your-server
cd /opt/certification-n8n
```

### 2.2 Create the nginx server block

Create `nginx/conf.d/n8n.conf` before starting the stack:

```nginx
# nginx/conf.d/n8n.conf
server {
    listen 80;
    server_name n8n.your-domain.com;

    # Let's Encrypt ACME webroot challenge
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    # Redirect all other HTTP traffic to HTTPS
    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name n8n.your-domain.com;

    ssl_certificate     /etc/letsencrypt/live/n8n.your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/n8n.your-domain.com/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    # Security headers
    add_header Strict-Transport-Security "max-age=63072000" always;
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;

    location / {
        proxy_pass         http://n8n:5678;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
    }
}
```

### 2.3 Create the environment file

```bash
cp .env.example .env   # create from example if provided, otherwise:
cat > .env <<'EOF'
# PostgreSQL
POSTGRES_USER=n8n
POSTGRES_PASSWORD=CHANGE_ME_strong_password_1
POSTGRES_DB=n8n

# n8n core
N8N_HOST=n8n.your-domain.com
N8N_ENCRYPTION_KEY=CHANGE_ME_generate_with_openssl_rand_hex_32
GENERIC_TIMEZONE=UTC

# n8n Basic Auth (protects the UI)
N8N_BASIC_AUTH_USER=admin
N8N_BASIC_AUTH_PASSWORD=CHANGE_ME_strong_password_2

# JIRA
JIRA_API_URL=https://your-org.atlassian.net
JIRA_USER_EMAIL=automation@your-org.com
JIRA_API_TOKEN=CHANGE_ME_jira_api_token

# JIRA transition IDs (find via: GET /rest/api/3/issue/{KEY}/transitions)
JIRA_TRANSITION_IN_REVIEW=31
JIRA_TRANSITION_DONE=41

# GitHub
GITHUB_TOKEN=CHANGE_ME_github_pat
GITHUB_WEBHOOK_SECRET=CHANGE_ME_generate_with_openssl_rand_hex_20
GITHUB_OWNER=your-org
GITHUB_REPO=your-repo

# Let's Encrypt
CERTBOT_EMAIL=admin@your-domain.com
N8N_LOG_LEVEL=info
EOF
chmod 600 .env
```

Generate secure random values:

```bash
# Encryption key (32 bytes hex)
openssl rand -hex 32

# Webhook secret (20 bytes hex)
openssl rand -hex 20
```

### 2.4 Obtain TLS certificate (first run)

```bash
# Start only nginx first (without n8n) so certbot can complete the challenge
docker compose up -d nginx

# Obtain certificate
docker compose run --rm certbot

# Verify certificate was issued
docker compose exec nginx ls /etc/letsencrypt/live/
```

### 2.5 Start the full stack

```bash
docker compose up -d

# Watch logs during startup
docker compose logs -f --tail=50
```

Expected startup order: postgres (healthy) → n8n (healthy) → nginx.

### 2.6 Verify the deployment

```bash
# Check all containers are running
docker compose ps

# Test HTTPS endpoint (should return n8n login page)
curl -I https://n8n.your-domain.com

# Check n8n health endpoint
curl https://n8n.your-domain.com/healthz
```

### 2.7 Certificate auto-renewal (cron)

Add to the server's crontab (`crontab -e`):

```cron
0 3 * * * cd /opt/certification-n8n && docker compose run --rm certbot renew --quiet && docker compose exec nginx nginx -s reload
```

---

## 3. Configuring JIRA Webhooks

### 3.1 Navigate to webhook settings

- **JIRA Cloud**: Project Settings → System → WebHooks (admin required)
- **JIRA Server/Data Center**: Administration → System → WebHooks

### 3.2 Create the webhook

| Field | Value |
|---|---|
| Name | `n8n Certification Automation` |
| URL | `https://n8n.your-domain.com/webhook/jira-webhook` |
| Secret | *(optional — n8n does not natively verify JIRA HMAC; use IP allowlisting instead)* |

### 3.3 Select events to subscribe

Check the following events:

- **Issue**
  - `jira:issue_updated` — status changes, field edits
  - `jira:issue_created` — optional, for tracking new tickets
- **Comment**
  - `comment_created` — optional, for audit trail

Leave all other events unchecked to reduce noise.

### 3.4 JQL filter (recommended)

Restrict the webhook to only the projects relevant to certification:

```jql
project in (CERT, DEVOPS, RELEASE)
```

### 3.5 Find JIRA transition IDs

You need the numeric transition IDs for the workflow nodes:

```bash
# Replace CERT-123 with any issue in your project
curl -u automation@your-org.com:YOUR_API_TOKEN \
  "https://your-org.atlassian.net/rest/api/3/issue/CERT-123/transitions" \
  | jq '.transitions[] | {id, name}'
```

Update `JIRA_TRANSITION_IN_REVIEW` and `JIRA_TRANSITION_DONE` in `.env` with the real IDs, then restart n8n:

```bash
docker compose restart n8n
```

### 3.6 Convention: linking PRs in JIRA issues

The JIRA → GitHub workflow extracts the GitHub PR URL from the JIRA issue description. Use this format in the **Description** field of JIRA issues:

```
PR: https://github.com/your-org/your-repo/pull/123
```

---

## 4. Configuring GitHub Webhooks

### 4.1 Navigate to webhook settings

Repository → Settings → Webhooks → Add webhook

### 4.2 Webhook configuration

| Field | Value |
|---|---|
| Payload URL | `https://n8n.your-domain.com/webhook/github-webhook` |
| Content type | `application/json` |
| Secret | Value of `GITHUB_WEBHOOK_SECRET` from your `.env` |
| SSL verification | Enable |

### 4.3 Select individual events

Click **Let me select individual events** and check:

- `Pull requests` — opened, closed, reopened, synchronize
- `Pull request reviews` — submitted (approved, changes_requested, commented)
- `Check suites` — completed
- `Pushes` — optional, for branch-level audit trail

### 4.4 Convention: JIRA ticket ID in PR titles

The GitHub → JIRA workflow uses a regex `[A-Z]+-\d+` to extract the JIRA ticket from the PR title or body. Enforce this in your team workflow:

```
# Good PR title formats
feat(CERT-123): add retry logic for API calls
fix: resolve null pointer [CERT-456]
DEVOPS-789 — update deployment pipeline

# The regex matches the first occurrence, so leading placement is clearest
```

Consider enforcing this via a GitHub branch protection rule + status check, or a `.github/PULL_REQUEST_TEMPLATE.md`:

```markdown
## JIRA Ticket
<!-- Required: paste the JIRA ticket URL, e.g. CERT-123 -->
Fixes:

## Description
...
```

### 4.5 GitHub label setup

The JIRA → GitHub workflow adds labels to PRs. Create these labels in your repository before activating the workflow:

```bash
# Run once per repository
for label in "jira:in-review" "jira:approved" "jira:rejected" "jira:in-progress"; do
  gh label create "$label" --repo your-org/your-repo --color "0075ca" --force
done
```

---

## 5. Importing Workflow JSONs

### 5.1 Log in to n8n

Open `https://n8n.your-domain.com` in your browser and log in with the credentials from `N8N_BASIC_AUTH_USER` / `N8N_BASIC_AUTH_PASSWORD`.

### 5.2 Import the workflows

1. Click the **+** button (top-left, next to "Workflows")
2. Select **Import from file**
3. Import `workflows/jira-to-github-sync.json`
4. Repeat for `workflows/github-to-jira-sync.json`

Alternatively, use the n8n CLI inside the container:

```bash
docker compose exec n8n n8n import:workflow \
  --input=/home/node/.n8n/workflows/jira-to-github-sync.json

docker compose exec n8n n8n import:workflow \
  --input=/home/node/.n8n/workflows/github-to-jira-sync.json
```

### 5.3 Activate the workflows

After importing, open each workflow and click the **Active** toggle (top-right). The webhook URLs become live only when the workflow is active.

### 5.4 Note the webhook URLs

With the workflow active, click on the Webhook node and copy the **Production URL**. It will look like:

```
https://n8n.your-domain.com/webhook/jira-webhook
https://n8n.your-domain.com/webhook/github-webhook
```

Use these URLs in the JIRA and GitHub webhook configuration sections above.

---

## 6. Testing with Sample Payloads

### 6.1 Test JIRA → GitHub sync

Simulate a JIRA status change (issue moved to "In Review"):

```bash
curl -X POST https://n8n.your-domain.com/webhook/jira-webhook \
  -H "Content-Type: application/json" \
  -d '{
    "webhookEvent": "jira:issue_updated",
    "user": {
      "accountId": "5b10ac8d82e05b22cc7d4ef5",
      "displayName": "Alice Reviewer"
    },
    "issue": {
      "key": "CERT-123",
      "fields": {
        "summary": "Implement retry logic for certification API",
        "status": { "name": "In Review" },
        "description": "This issue tracks the implementation.\n\nPR: https://github.com/your-org/your-repo/pull/42"
      }
    },
    "changelog": {
      "items": [
        {
          "field": "status",
          "fromString": "In Progress",
          "toString": "In Review"
        }
      ]
    }
  }'
```

Expected result:
- GitHub PR #42 gets label `jira:in-review`
- n8n execution appears in the Executions list as successful
- Structured log entry printed in container stdout

Simulate approval:

```bash
curl -X POST https://n8n.your-domain.com/webhook/jira-webhook \
  -H "Content-Type: application/json" \
  -d '{
    "webhookEvent": "jira:issue_updated",
    "user": { "accountId": "abc123", "displayName": "Bob Approver" },
    "issue": {
      "key": "CERT-123",
      "fields": {
        "summary": "Implement retry logic for certification API",
        "status": { "name": "Approved" },
        "description": "PR: https://github.com/your-org/your-repo/pull/42"
      }
    },
    "changelog": {
      "items": [{ "field": "status", "fromString": "In Review", "toString": "Approved" }]
    }
  }'
```

### 6.2 Test GitHub → JIRA sync

Simulate a GitHub pull_request opened event:

```bash
curl -X POST https://n8n.your-domain.com/webhook/github-webhook \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: pull_request" \
  -d '{
    "action": "opened",
    "number": 42,
    "pull_request": {
      "number": 42,
      "title": "feat(CERT-123): add retry logic for certification API",
      "body": "This PR implements the retry mechanism.\n\nFixes CERT-123",
      "html_url": "https://github.com/your-org/your-repo/pull/42",
      "head": { "sha": "abc123def456", "ref": "feat/cert-123-retry" },
      "base": { "ref": "main" }
    },
    "sender": { "login": "developer-alice" },
    "repository": { "full_name": "your-org/your-repo" }
  }'
```

Expected result:
- JIRA issue CERT-123 transitions to "In Review"
- JIRA issue CERT-123 receives a comment with the PR link and author

Simulate a PR review (approved):

```bash
curl -X POST https://n8n.your-domain.com/webhook/github-webhook \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: pull_request_review" \
  -d '{
    "action": "submitted",
    "review": {
      "state": "approved",
      "body": "LGTM — all certification criteria met.",
      "user": { "login": "reviewer-bob" }
    },
    "pull_request": {
      "number": 42,
      "title": "feat(CERT-123): add retry logic",
      "body": "Fixes CERT-123",
      "html_url": "https://github.com/your-org/your-repo/pull/42",
      "head": { "sha": "abc123def456", "ref": "feat/cert-123-retry" },
      "base": { "ref": "main" }
    },
    "sender": { "login": "reviewer-bob" },
    "repository": { "full_name": "your-org/your-repo" }
  }'
```

Simulate a CI check suite completing:

```bash
curl -X POST https://n8n.your-domain.com/webhook/github-webhook \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: check_suite" \
  -d '{
    "action": "completed",
    "check_suite": {
      "status": "completed",
      "conclusion": "success",
      "app": { "name": "GitHub Actions" },
      "head_sha": "abc123def456"
    },
    "pull_requests": [
      {
        "number": 42,
        "title": "feat(CERT-123): add retry logic",
        "body": "Fixes CERT-123",
        "html_url": "https://github.com/your-org/your-repo/pull/42",
        "head": { "sha": "abc123def456", "ref": "feat/cert-123-retry" },
        "base": { "ref": "main" }
      }
    ],
    "sender": { "login": "github-actions[bot]" },
    "repository": { "full_name": "your-org/your-repo" }
  }'
```

### 6.3 Verify execution in n8n UI

1. Open n8n → Executions (left sidebar)
2. Each test call should appear as a green (success) execution
3. Click an execution to inspect each node's input/output data

---

## 7. Monitoring and Troubleshooting

### 7.1 View container logs

```bash
# All services
docker compose logs -f

# n8n only (most useful)
docker compose logs -f n8n

# Last 200 lines of postgres
docker compose logs --tail=200 postgres

# nginx access log
docker compose logs -f nginx
```

### 7.2 n8n execution history

- **UI**: n8n → Executions — filter by workflow, status (success/error), date range
- **Retention**: executions are pruned after `EXECUTIONS_DATA_MAX_AGE` hours (default: 720 = 30 days); adjust in `.env` if you need longer retention for audit purposes

### 7.3 Common issues

#### Webhook returns 404

- Confirm the workflow is **Active** (toggle in n8n UI)
- Confirm you are using the **Production** webhook URL, not the Test URL
- Check nginx proxy_pass is pointing to `http://n8n:5678`

#### JIRA API returns 401

- Verify `JIRA_USER_EMAIL` and `JIRA_API_TOKEN` in `.env`
- API token must be generated at `id.atlassian.com` (not your JIRA password)
- For JIRA Server: use `Authorization: Bearer <token>` instead of Basic Auth — update the HTTP Request nodes accordingly

#### JIRA transition fails with 400

- The transition ID in `JIRA_TRANSITION_IN_REVIEW` / `JIRA_TRANSITION_DONE` does not exist for the issue's current status
- Fetch available transitions dynamically: `GET /rest/api/3/issue/{KEY}/transitions`
- Ensure the automation user has permission to perform the transition

#### GitHub API returns 403

- The PAT is missing required scopes (`pull_requests:write`, `statuses:write`)
- The PAT has expired — generate a new one and update `GITHUB_TOKEN` in `.env`, then `docker compose restart n8n`

#### No JIRA ticket extracted from PR

- PR title or body does not match `[A-Z]+-\d+`
- Enforce PR title format via GitHub branch protection + a PR title linting action

#### n8n container keeps restarting

```bash
docker compose logs n8n | tail -50
```

Common causes:
- `N8N_ENCRYPTION_KEY` changed after credentials were saved (data is now unreadable)
- PostgreSQL not yet healthy when n8n starts — the `depends_on: condition: service_healthy` should prevent this, but check postgres logs

#### TLS certificate errors

```bash
# Check certificate validity
docker compose exec nginx openssl x509 \
  -in /etc/letsencrypt/live/n8n.your-domain.com/fullchain.pem \
  -noout -dates

# Force renewal
docker compose run --rm certbot renew --force-renewal
docker compose exec nginx nginx -s reload
```

### 7.4 Scaling and production hardening

| Topic | Recommendation |
|---|---|
| Execution storage | Switch to S3-backed binary data storage for large payloads (`N8N_BINARY_DATA_MODE=s3`) |
| High availability | Run n8n in queue mode with Redis + multiple worker containers |
| Secret management | Replace `.env` with HashiCorp Vault or AWS Secrets Manager via the n8n credentials store |
| IP allowlisting | Restrict `/webhook/*` paths in nginx to GitHub's IP ranges (`meta.github.com`) and your JIRA instance IP |
| Audit log export | Forward n8n stdout (structured JSON logs) to your SIEM (Splunk, Datadog, CloudWatch) |
| Backup | Schedule `pg_dump` of the `n8n` database nightly; also export workflows via n8n UI → Settings → Export |

### 7.5 Backup and restore workflows

```bash
# Export all workflows to JSON
docker compose exec n8n n8n export:workflow --all \
  --output=/home/node/.n8n/workflow-backup-$(date +%Y%m%d).json

# Copy backup off the container
docker compose cp \
  n8n_app:/home/node/.n8n/workflow-backup-$(date +%Y%m%d).json \
  ./backups/

# Restore
docker compose exec n8n n8n import:workflow \
  --input=/home/node/.n8n/workflow-backup-20240101.json
```

---

*Generated for the JIRA + GitHub CI/CD Certification Evidence Automation System — Phase 2 Integration.*
