# Operations and Configuration Runbook

**System:** JIRA + GitHub CI/CD Software Certification Evidence Automation
**Document Version:** 1.0
**Date:** 2026-03-11
**Audience:** DevOps Engineers, Platform Engineers, System Administrators

---

## System Overview

### Architecture Diagram

```
                        +-----------------------+
                        |   Developer Workstation|
                        |  (git push / PR open)  |
                        +----------+------------+
                                   |
                                   v
+------------------+     +-------------------+     +--------------------+
|                  |     |                   |     |                    |
|   JIRA Cloud /   +<--->+  n8n CE Workflow  +<--->+   GitHub (Repos,   |
|   JIRA Server    |     |  Engine (webhook  |     |   Actions, PRs,    |
|                  |     |  receiver +       |     |   Branch Protect.) |
|  - Projects      |     |  automation)      |     |                    |
|  - Tickets       |     |                   |     |  - jira-ticket-    |
|  - Workflows     |     |  Receives:        |     |    validator       |
|  - Transitions   |     |  - JIRA webhooks  |     |  - evidence-       |
|                  |     |  - GitHub webhooks|     |    collector       |
+------------------+     |                   |     |  - CI test runs    |
         ^               |  Syncs ticket     |     |                    |
         |               |  status to GitHub |     +----------+---------+
         |               |  PR checks        |                |
         |               +-------------------+                |
         |                                                     |
         |               +------------------------------------+|
         |               |          Evidence Store             |
         +-------------->+                                     |
  (workflow history)     |  MinIO (self-hosted) or             |
                        |  AWS S3-compatible bucket            |
                        |                                      |
                        |  certification-evidence/             |
                        |    {project}/{release}/              |
                        |      evidence-records/               |
                        |      traceability-matrix.*           |
                        |      approval-ledger.json            |
                        |      cicd-summary.json               |
                        |      jira-workflow-history.json      |
                        |      github-pr-records.json          |
                        |      integrity-manifest.sha256       |
                        +------------------------------------+
```

### Component Inventory

| Component | Role | Hosted / Managed |
|---|---|---|
| **JIRA** | Requirement and ticket lifecycle management; workflow stage enforcement | Cloud or self-hosted |
| **GitHub** | Source code hosting, Pull Request management, branch protection, CI/CD | GitHub.com or GitHub Enterprise |
| **n8n CE** | Webhook receiver and automation engine; syncs JIRA ticket status to GitHub PR checks | Self-hosted (Docker/Kubernetes) |
| **Evidence Store** | Tamper-evident object storage for all collected evidence artifacts | MinIO (self-hosted) or AWS S3 |
| **GitHub Actions: `jira-ticket-validator`** | Required PR check; blocks merge if JIRA ticket has not completed required workflow stages | GitHub-hosted runners |
| **GitHub Actions: `evidence-collector`** | Collects and writes evidence record at merge time | GitHub-hosted runners |
| **GitHub Actions: `traceability-builder`** | Builds traceability matrix and package-level artifacts at release tag | GitHub-hosted runners |

### Integration Flow

```
1. Developer opens PR on GitHub
        |
        v
2. GitHub webhook -> n8n
   n8n reads JIRA ticket status
   n8n posts result as GitHub Commit Status ("jira-sync" check)
        |
        v
3. GitHub Actions: jira-ticket-validator runs
   - Reads JIRA ticket via JIRA API
   - Verifies all required stages completed
   - Posts pass/fail as required PR check
        |
        v
4. CI test suite runs (GitHub Actions)
   Posts pass/fail as required PR check
        |
        v
5. Qualified reviewer(s) approve PR on GitHub
        |
        v
6. All required checks pass -> merge unblocked
        |
        v
7. GitHub Actions: evidence-collector runs on merge
   - Collects PR metadata, approvals, CI results, JIRA data
   - Writes PR-{number}-evidence.json to evidence store
   - Updates integrity manifest
        |
        v
8. (At release tag) GitHub Actions: traceability-builder runs
   - Builds traceability-matrix, approval-ledger, cicd-summary,
     jira-workflow-history, github-pr-records
   - Writes complete evidence package to evidence store
   - Computes and writes integrity-manifest.sha256
```

---

## Common Operations

### Adding a New JIRA Project

Follow these steps when onboarding a new software project that requires certification evidence collection.

#### Step 1: JIRA Workflow Configuration

1. In JIRA, navigate to **Settings > Issues > Workflows**.
2. Copy the existing certified workflow template (named `Certification-Standard-Workflow-vX`). Do not modify the template directly.
3. Rename the copy to `{PROJECT-KEY}-Certification-Workflow`.
4. Associate the new workflow with the new project's issue types via **Settings > Issues > Workflow Schemes**.
5. Verify the required stage sequence is intact:
   ```
   Open -> In Development -> In Review -> Approved -> Closed
   ```
   Additional project-specific stages may be inserted between these, but none of the required stages may be removed.
6. Configure transition conditions and validators on the workflow to prevent out-of-order transitions (e.g., prevent moving from `Open` directly to `Approved`).

#### Step 2: JIRA Automation Rules

Clone the following automation rules from an existing certified project and update the project scope to include the new project:

- **Rule: "Require linked PR before Approved transition"** — Prevents a ticket from being moved to `Approved` unless it has at least one linked GitHub PR.
- **Rule: "Notify on stage skip attempt"** — Sends a notification to the project lead if a workflow validator rejects a transition.
- **Rule: "Auto-close ticket on PR merge"** — Optionally transitions ticket to `Closed` when the linked PR is merged.

To clone: **Project Settings > Automation > [Rule] > Copy rule to another project**.

#### Step 3: GitHub Actions — Update JIRA_PROJECT Variable

In every GitHub repository associated with the new project:

1. Navigate to **Settings > Secrets and variables > Actions > Variables**.
2. Add or update the repository variable `JIRA_PROJECT` to the new project key (e.g., `MED2`).
3. If the repository serves multiple JIRA projects, set `JIRA_PROJECT` to a comma-separated list: `MED,MED2`.

#### Step 4: Configure n8n Workflow

1. Open the n8n dashboard.
2. Open the workflow named **"JIRA-GitHub PR Status Sync"**.
3. In the **JIRA Webhook Trigger** node, add the new project key to the project filter list.
4. In the **JIRA Status Mapper** node, verify the new project's workflow stage names map correctly to the required stage identifiers. Update the mapping table if the new project uses different stage names.
5. Save and activate the updated workflow.
6. In JIRA, navigate to **Project Settings > Webhooks** for the new project and confirm a webhook is configured pointing to the n8n webhook URL for JIRA events (`POST {N8N_BASE_URL}/webhook/jira-events`).

#### Step 5: Evidence Store — Create Project Bucket Prefix

```bash
# Create the project prefix in the evidence store
mc mb evidence-store/certification-evidence/{PROJECT-KEY}/
# Verify access
mc ls evidence-store/certification-evidence/
```

No schema changes are needed if the new project uses the same evidence schema version as existing projects.

#### Step 6: Smoke Test

1. Create a test JIRA ticket in the new project and move it through all required stages.
2. Open a test PR in the associated GitHub repository, link it to the test ticket.
3. Verify the `jira-ticket-validator` check passes.
4. Merge the PR and verify an evidence record appears in `evidence-store/certification-evidence/{PROJECT-KEY}/`.

---

### Adding a New GitHub Repository

#### Step 1: Branch Protection Rules

In the new repository, navigate to **Settings > Branches > Add branch protection rule** for the `main` branch (and any other release branches):

- [x] Require a pull request before merging
  - [x] Require approvals: **1** (or **2** for safety-critical repositories)
  - [x] Dismiss stale pull request approvals when new commits are pushed
  - [x] Require review from Code Owners
- [x] Require status checks to pass before merging
  - Required checks (add each by name):
    - `jira-ticket-validator`
    - `ci-tests` (or the name of your CI test job)
    - `jira-sync` (n8n-posted status, if configured)
- [x] Require branches to be up to date before merging
- [x] Require conversation resolution before merging
- [x] Restrict who can push to matching branches (limit to specific teams/roles)
- [x] Do not allow bypassing the above settings

#### Step 2: CODEOWNERS Setup

Create a `CODEOWNERS` file in the repository root (or `.github/CODEOWNERS`). At minimum:

```
# All files require review from the safety team
* @org/safety-reviewers

# Source code requires additional domain review
/src/ @org/safety-reviewers @org/domain-engineers

# GitHub Actions workflows require platform engineering review
/.github/workflows/ @org/platform-engineering
```

Adjust team names to match your GitHub organization's team structure.

#### Step 3: GitHub Actions Secrets

Navigate to **Settings > Secrets and variables > Actions > Secrets** and configure:

| Secret Name | Value | Purpose |
|---|---|---|
| `JIRA_BASE_URL` | `https://your-org.atlassian.net` | JIRA instance URL |
| `JIRA_USER_EMAIL` | Service account email | JIRA API authentication |
| `JIRA_API_TOKEN` | JIRA API token for service account | JIRA API authentication |
| `EVIDENCE_STORE_ENDPOINT` | MinIO/S3 endpoint URL | Evidence storage |
| `EVIDENCE_STORE_ACCESS_KEY` | Access key ID | Evidence storage authentication |
| `EVIDENCE_STORE_SECRET_KEY` | Secret access key | Evidence storage authentication |
| `EVIDENCE_STORE_BUCKET` | `certification-evidence` | Target bucket name |

#### Step 4: Copy GitHub Actions Workflows

Copy the following workflow files from the template repository into `.github/workflows/` of the new repository:

- `jira-ticket-validator.yml`
- `evidence-collector.yml`
- `traceability-builder.yml`

Update `JIRA_PROJECT` in each workflow file or rely on the repository variable set in the previous section.

#### Step 5: End-to-End Test

Run the standard end-to-end test scenario:

1. Create a JIRA ticket and move it through all required stages.
2. Open a PR linked to the ticket with a trivial code change.
3. Confirm all required PR checks appear and pass.
4. Merge the PR.
5. Confirm evidence record appears in the evidence store.
6. Confirm the traceability matrix (for the test release, if triggered) reflects the new entry.

---

### Changing Workflow Stages

Modifying the required JIRA workflow stages is a significant change that affects evidence integrity and auditor expectations. Follow this procedure carefully.

#### Impact Assessment Checklist

Before making any changes, assess and document:

- [ ] Which certification standard clauses reference the current workflow stages?
- [ ] Does the change add, remove, or rename a required stage?
- [ ] Does the change affect the evidence schema (i.e., are new fields needed in evidence records)?
- [ ] Does the change affect existing in-flight tickets or only new tickets?
- [ ] Have the relevant QA/Regulatory Affairs stakeholders approved the change?
- [ ] Is a deviation notice required for the current audit cycle?
- [ ] What is the rollback plan if the change causes issues?

Document answers before proceeding.

#### Step 1: Back Up JIRA Workflow

1. In JIRA, navigate to **Settings > Issues > Workflows**.
2. Locate the workflow to be modified.
3. Export the workflow as XML: **... > Export as XML**. Save with a timestamped filename: `{workflow-name}-backup-{YYYY-MM-DD}.xml`.
4. Store the backup in the designated configuration backup location.

#### Step 2: Update JIRA Workflow

1. Create a draft of the workflow (do not edit the active version directly): **Edit > Create Draft**.
2. Make the required stage changes in the draft.
3. If adding a new required stage, configure transition validators to enforce ordering.
4. Publish the draft after QA review sign-off.
5. Verify the updated workflow is assigned to the correct projects via Workflow Schemes.

#### Step 3: Update n8n Workflow Mapping

1. Open the **"JIRA-GitHub PR Status Sync"** workflow in n8n.
2. In the **JIRA Status Mapper** node, update the stage name mapping to include the new/renamed stages.
3. If a stage is removed, remove its mapping entry.
4. Save and test with a real ticket transition.

#### Step 4: Update Evidence Schema (if required)

If new stages add new data fields to evidence records:

1. Increment the schema version in `schemas/evidence-schema.json` (bump minor version for additive changes, major version for breaking changes).
2. Update the `evidence-collector` GitHub Actions workflow to populate new fields.
3. Update the `traceability-builder` to handle new fields in matrix and summary outputs.
4. Add schema migration notes to `schemas/CHANGELOG.md`.

#### Step 5: Re-validate End-to-End

Run the full end-to-end test scenario (see "Adding a New GitHub Repository > Step 5") and confirm:

- New stage appears in `jira-workflow-history.json`
- New stage is reflected correctly in evidence records
- `jira-ticket-validator` correctly enforces the new stage as required (if applicable)

#### Step 6: Update Auditor Guide

Update `phase5-docs/auditor-guide.md` to reflect:

- The new/changed stage name in the workflow description under "JIRA Workflow History"
- The verification checklist if the stage affects an auditable control
- The FAQ if the change is likely to prompt auditor questions

---

## Troubleshooting

### PR Blocked by JIRA Validator

**Symptom:** A PR is stuck with a failing `jira-ticket-validator` required check, blocking merge.

#### Step 1: Check GitHub Actions Logs

1. On the PR page, click **Details** next to the failing `jira-ticket-validator` check.
2. In the Actions run log, look for the failure reason. Common messages:
   - `No JIRA ticket reference found in PR title or body` — PR title/body does not include a JIRA ticket key (e.g., `MED-123`). Ask the developer to update the PR description.
   - `JIRA ticket MED-123 not found or not accessible` — The service account cannot read the ticket. See Step 2.
   - `Required stage "Approved" not completed` — The JIRA ticket has not reached the required stage. The ticket owner must advance it in JIRA.
   - `JIRA ticket is in invalid state: Closed` — The ticket was closed before the PR was merged. Reopen the ticket and advance it to `Approved`.

#### Step 2: Check JIRA Ticket Status and Accessibility

1. Confirm the JIRA ticket key in the PR matches an actual ticket (navigate to `{JIRA_BASE_URL}/browse/{TICKET-KEY}`).
2. Confirm the JIRA service account (`JIRA_USER_EMAIL`) has at least Read access to the project.
3. Confirm the JIRA API token secret (`JIRA_API_TOKEN`) has not expired. Test with:
   ```bash
   curl -u "service-account@example.com:YOUR_API_TOKEN" \
     "https://your-org.atlassian.net/rest/api/3/issue/MED-123"
   ```
   A 200 response with ticket JSON confirms connectivity. A 401 indicates an invalid token. Rotate the token in JIRA and update the GitHub Actions secret.

#### Step 3: Manual Override Procedure

Manual overrides bypass a required security control and must be used only in documented exceptional circumstances (e.g., production emergency fix).

**Requirements before override:**
- Written approval from QA lead and engineering manager (email or ticketing system record)
- A deviation ticket must be opened in JIRA documenting the reason
- The override event must be logged (see below)

**Procedure:**
1. Temporarily add the developer performing the merge to the repository's **Bypass list** in branch protection settings (**Settings > Branches > Edit rule > Allow specified actors to bypass required pull request**).
2. Merge the PR.
3. Immediately remove the developer from the bypass list.
4. Post a comment on the merged PR documenting: reason for override, approver names, deviation ticket number.
5. The `evidence-collector` will still run and will record `override: true` and `override_reason` in the evidence record if the comment follows the required format: `OVERRIDE: {reason} | APPROVED-BY: {names} | DEVIATION: {ticket}`.

**Important:** All override events are visible in the GitHub organization audit log. Auditors will see them. Ensure documentation is complete before the merge is performed.

---

### Evidence Record Not Generated

**Symptom:** A PR was merged but no evidence record appears in the evidence store.

#### Step 1: Check evidence-collector Workflow Run

1. In the GitHub repository, navigate to **Actions > evidence-collector**.
2. Filter runs by the merge date/time.
3. Find the run triggered by the merge (triggered event: `push` to `main`).
4. If the run failed, open the run log and identify the failure step.

Common failures and fixes:

| Failure Step | Likely Cause | Fix |
|---|---|---|
| `Configure AWS credentials` | Secret missing or expired | Verify `EVIDENCE_STORE_ACCESS_KEY` and `EVIDENCE_STORE_SECRET_KEY` are set and valid |
| `Upload evidence record` | Network connectivity to MinIO/S3 | Check MinIO service health; see Step 2 |
| `Fetch JIRA ticket data` | JIRA API token expired | Rotate JIRA API token; update `JIRA_API_TOKEN` secret |
| `Parse PR metadata` | Unexpected PR data format | Check for GitHub API changes; update workflow if needed |

#### Step 2: Check S3/MinIO Connectivity

From a host with network access to the MinIO instance:

```bash
# Test MinIO health endpoint
curl -I https://minio.example.com/minio/health/live

# Test bucket access with credentials
mc alias set evidence-store https://minio.example.com ACCESS_KEY SECRET_KEY
mc ls evidence-store/certification-evidence/
```

If MinIO is unreachable, check:
- MinIO pod/container status: `kubectl get pods -n evidence-store` or `docker ps | grep minio`
- MinIO service logs: `kubectl logs -n evidence-store -l app=minio` or `docker logs minio`
- Network policy / firewall rules between GitHub-hosted runners and the MinIO endpoint

#### Step 3: Manual Evidence Collection

If the automated collection failed but the PR data is intact in GitHub and JIRA, trigger manual collection:

```bash
# From a workstation with evidence-collector script installed and credentials configured
cd /path/to/cert-automation-tools

python collect_evidence.py \
  --repo "org/repository-name" \
  --pr-number 42 \
  --jira-ticket "MED-123" \
  --output-bucket "certification-evidence" \
  --manual-collection-reason "Automated collection failed: [brief reason]"
```

The script will write the evidence record and append a `manual_collection: true` flag and timestamp. Log the manual collection in the deviation register.

---

### n8n Sync Not Working

**Symptom:** The `jira-sync` GitHub commit status check is not appearing on PRs, or is stuck in a pending state.

#### Step 1: Check n8n Execution History

1. Open the n8n dashboard (`https://n8n.example.com`).
2. Navigate to **Executions**.
3. Filter by workflow: **"JIRA-GitHub PR Status Sync"**.
4. Look for recent executions. If none appear for recent JIRA events, the webhook is not being received.
5. If executions appear but show errors, open an execution and inspect the failed node for error details.

Common n8n errors:

| Error | Cause | Fix |
|---|---|---|
| `GitHub API 401` | GitHub token expired | Rotate `GITHUB_TOKEN` in n8n credentials |
| `JIRA API 403` | Service account permission issue | Check JIRA project permissions for service account |
| `Cannot read property 'key' of undefined` | Unexpected JIRA webhook payload format | Check JIRA webhook event type filter; ensure only `jira:issue_updated` events are sent |
| Execution timeout | n8n overloaded or slow JIRA/GitHub response | Check n8n resource usage; consider scaling |

#### Step 2: Check JIRA Webhook Delivery Logs

1. In JIRA, navigate to **Settings > System > WebHooks**.
2. Click on the webhook pointing to n8n.
3. Review the delivery log. Failed deliveries (non-2xx responses from n8n) will appear here.
4. If deliveries are failing with connection errors, verify n8n is reachable from JIRA's outbound network. If JIRA Cloud is used, n8n must be publicly accessible or reachable via a tunnel.

#### Step 3: Check GitHub Webhook Delivery Logs

1. In the GitHub organization or repository, navigate to **Settings > Webhooks**.
2. Click on the webhook pointing to n8n.
3. Click **Recent Deliveries** and inspect recent events.
4. If deliveries fail, click a failed delivery to see the response from n8n. A 5xx response indicates n8n received the request but encountered an error. A connection error indicates n8n is unreachable.

#### Step 4: n8n Restart Procedure

If n8n is unresponsive or in an error state:

**Docker Compose deployment:**
```bash
cd /opt/n8n
docker compose restart n8n
# Verify startup
docker compose logs -f n8n --tail=50
```

**Kubernetes deployment:**
```bash
kubectl rollout restart deployment/n8n -n n8n
kubectl rollout status deployment/n8n -n n8n
```

After restart, verify the JIRA-GitHub sync workflow is active in the n8n dashboard (green "Active" toggle).

**Note:** A restart does not cause loss of pending work — n8n uses a persistent database (SQLite or PostgreSQL) for execution state. However, any webhook events received during the downtime window will not be replayed. If a PR status sync was missed, trigger it manually by commenting `/jira-sync` on the PR (if that command integration is configured) or by manually posting the commit status via the GitHub API.

---

## Monitoring and Alerting

### Key Metrics to Monitor

| Metric | Source | Warning Threshold | Critical Threshold |
|---|---|---|---|
| Evidence collector workflow success rate | GitHub Actions API | < 99% | < 95% |
| n8n workflow execution error rate | n8n metrics endpoint | > 1% | > 5% |
| Evidence store disk usage | MinIO metrics / CloudWatch | > 70% capacity | > 85% capacity |
| JIRA API response time | Synthetic monitor | > 2s average | > 5s average |
| GitHub API rate limit remaining | GitHub API headers | < 1000 remaining | < 200 remaining |
| n8n process memory usage | Host metrics | > 1.5 GB | > 2 GB |
| Evidence store write latency | MinIO metrics | > 500ms | > 2s |

### Recommended Alerts

Configure the following alerts in your monitoring system (Prometheus/Alertmanager, Datadog, PagerDuty, etc.):

**Critical (page on-call):**
- Evidence collector workflow failure rate > 5% in a 1-hour window
- Evidence store unreachable (health check failing for > 5 minutes)
- n8n process down (health check failing for > 2 minutes)

**Warning (ticket/Slack notification):**
- Evidence collector workflow failure rate > 1% in a 24-hour window
- GitHub API rate limit < 500 remaining
- Evidence store disk usage > 70%
- JIRA API latency > 3s sustained for > 10 minutes
- n8n execution queue depth > 50

**Informational (daily digest):**
- Count of evidence records written in the past 24 hours
- Count of PRs blocked by jira-ticket-validator
- Count of manual override events

### Dashboards (Grafana)

If using Grafana, import the provided dashboard templates from `monitoring/grafana-dashboards/`:

| Dashboard | File | Description |
|---|---|---|
| Evidence Collection Health | `evidence-collection-health.json` | Workflow success rates, latency, record counts |
| n8n Operations | `n8n-operations.json` | Execution history, error rates, queue depth |
| Evidence Store | `evidence-store.json` | Disk usage, write latency, request rates |
| Audit Control Status | `audit-control-status.json` | PR block rates, override events, compliance posture |

---

## Backup and Recovery

### n8n Database Backup

n8n stores workflow definitions, execution history, and credentials in its database (SQLite or PostgreSQL).

**SQLite (default single-node deployment):**
```bash
# Stop n8n to ensure consistent backup
docker compose stop n8n

# Copy the SQLite database file
cp /opt/n8n/data/database.sqlite \
   /backup/n8n/database-$(date +%Y%m%d-%H%M%S).sqlite

# Restart n8n
docker compose start n8n

# Verify backup integrity
sqlite3 /backup/n8n/database-{timestamp}.sqlite "PRAGMA integrity_check;"
```

Schedule this procedure daily via cron. Retain backups for at least 90 days.

**PostgreSQL (production deployment):**
```bash
pg_dump -h localhost -U n8n -d n8n \
  -f /backup/n8n/n8n-$(date +%Y%m%d-%H%M%S).sql
```

### Evidence Store Backup Verification

The evidence store is the primary audit artifact. Verify backup integrity weekly:

```bash
# List evidence store contents and sizes
mc du evidence-store/certification-evidence/

# Verify a sample of evidence records are readable and not corrupted
mc cat evidence-store/certification-evidence/{PROJECT}/{RELEASE}/package-metadata.json

# Run integrity verification on a release package
mc cp --recursive evidence-store/certification-evidence/{PROJECT}/{RELEASE}/ /tmp/verify/
cd /tmp/verify/{RELEASE}
sha256sum -c integrity-manifest.sha256
rm -rf /tmp/verify/
```

If using MinIO in production, enable MinIO's built-in replication to a secondary site for disaster recovery. Verify replication lag daily.

### Recovery from n8n Failure

**Important:** n8n failure does not disable the core enforcement controls. GitHub branch protection rules and the `jira-ticket-validator` GitHub Actions workflow operate independently of n8n. During an n8n outage:

- PRs will still be blocked if JIRA tickets are not in the required state (via GitHub Actions validator)
- The `jira-sync` commit status check will not update (PRs may show a stale or missing n8n check)
- Evidence collection will still function (evidence-collector is a GitHub Actions workflow, not n8n)

**Acceptable temporary workaround during n8n outage:**

If `jira-sync` is configured as a required check and n8n is down, it will block all merges. To temporarily remove `jira-sync` from required checks:

1. Navigate to **Settings > Branches > Edit protection rule** for `main`.
2. Remove `jira-sync` from the required status checks list.
3. Document the time window and reason in the deviation register.
4. Restore `jira-sync` as a required check as soon as n8n is recovered.

**n8n Recovery Steps:**

1. Restore n8n database from most recent backup (see above).
2. Restart n8n service.
3. Verify all workflows are active in the n8n dashboard.
4. Test with a manual JIRA ticket status change and confirm the GitHub commit status is updated.
5. Restore `jira-sync` as a required PR check.

### Recovery of Evidence Records from Source Systems

If evidence records in the store are lost or corrupted and cannot be restored from backup, records can be reconstructed from GitHub and JIRA source data:

```bash
# Re-collect evidence for a specific PR from source systems
python collect_evidence.py \
  --repo "org/repository-name" \
  --pr-number 42 \
  --jira-ticket "MED-123" \
  --output-bucket "certification-evidence" \
  --manual-collection-reason "Recovery: original record lost, reconstructed from source" \
  --reconstructed true
```

Reconstructed records will include a `reconstructed: true` flag and the reconstruction timestamp. This flag must be disclosed to auditors reviewing the record. Reconstruction is only valid if the source data in GitHub and JIRA has not been modified since the original merge.

---

## Upgrade Procedures

### n8n Version Upgrade

1. Review the n8n release notes for breaking changes: `https://docs.n8n.io/release-notes/`
2. Back up the n8n database before upgrading (see Backup section).
3. Test the upgrade in a staging environment first.
4. In production:
   ```bash
   cd /opt/n8n
   # Update image tag in docker-compose.yml to new version
   docker compose pull n8n
   docker compose up -d n8n
   docker compose logs -f n8n --tail=50
   ```
5. After upgrade, verify:
   - All workflows are active
   - Test JIRA webhook delivery triggers a successful n8n execution
   - Test GitHub commit status is posted correctly

### Schema Version Migration

When the evidence schema is updated (new fields added or existing fields changed):

1. Review `schemas/CHANGELOG.md` for migration notes.
2. If the schema change is additive (new optional fields), no migration of existing records is required. New records will include new fields; old records will be valid under the previous schema version.
3. If the schema change is breaking (fields renamed or removed), a migration script must be run against existing records:
   ```bash
   python migrate_evidence.py \
     --bucket "certification-evidence" \
     --from-schema-version "1.2" \
     --to-schema-version "2.0" \
     --dry-run   # Remove --dry-run to apply
   ```
4. After migration, re-run integrity manifest generation for all affected release packages:
   ```bash
   python rebuild_integrity_manifest.py \
     --bucket "certification-evidence" \
     --project "MED" \
     --release "v2.4.1"
   ```
5. Document the migration event in the schema changelog and notify auditors of any in-progress audit that evidence records have been migrated.

### JIRA Plugin Updates

If using a JIRA plugin for enhanced workflow enforcement or GitHub integration:

1. Review the plugin release notes for changes to workflow configuration or API behavior.
2. Test the update in JIRA staging.
3. Perform a test end-to-end scenario after updating to confirm the `jira-ticket-validator` still reads ticket status correctly.
4. If the plugin changes how JIRA webhook payloads are structured, update the n8n JIRA Status Mapper node accordingly (see "Changing Workflow Stages > Step 3").
