# Phase 3 Evidence Scripts

Python CLI tools for generating software certification evidence by correlating
JIRA issues with GitHub pull requests, CI results, and approvals.

---

## Scripts

| Script | Purpose |
|--------|---------|
| `traceability_matrix.py` | Build a full Requirement → JIRA → PR → CI → Approval traceability chain |
| `approval_collector.py` | Collect and reconcile all approval evidence; produce a tamper-evident ledger |

---

## Setup

**Python 3.9+ required.**

```bash
pip install -r requirements.txt
```

---

## Environment Variables

Both scripts require the following variables to be set before running:

| Variable | Description | Example |
|----------|-------------|---------|
| `JIRA_BASE_URL` | Root URL of your Atlassian instance | `https://yourorg.atlassian.net` |
| `JIRA_EMAIL` | Email address for JIRA authentication | `you@example.com` |
| `JIRA_API_TOKEN` | Atlassian API token (not your password) | `ATATT3xFf...` |
| `GITHUB_TOKEN` | GitHub personal access token or GitHub App token | `ghp_abc123...` |

Export them in your shell before running:

```bash
export JIRA_BASE_URL="https://yourorg.atlassian.net"
export JIRA_EMAIL="you@example.com"
export JIRA_API_TOKEN="your-atlassian-api-token"
export GITHUB_TOKEN="your-github-token"
```

Minimum token scopes:
- **JIRA API token**: read access to issues, changelogs, and remote links.
- **GitHub token**: `repo` scope (read PRs, reviews, check runs, releases).

---

## Usage

### traceability_matrix.py

```
python traceability_matrix.py \
    --jira-project PROJ \
    --github-repo owner/repo \
    --release-tag v1.0.0 \
    [--output-format csv|json|md] \
    [--output-file matrix.csv] \
    [--summary-file gaps.json]
```

**Arguments:**

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--jira-project` | yes | — | JIRA project key (e.g. `MYPROJ`) |
| `--github-repo` | yes | — | GitHub repo as `owner/repo` |
| `--release-tag` | yes | — | Git tag for the release (e.g. `v1.0.0`) |
| `--output-format` | no | `csv` | `csv`, `json`, or `md` |
| `--output-file` | no | stdout | File path for matrix output |
| `--summary-file` | no | stderr | File path for JSON gap-analysis summary |

**Examples:**

```bash
# CSV to file, gap analysis to gaps.json
python traceability_matrix.py \
    --jira-project MYPROJ \
    --github-repo acme/my-service \
    --release-tag v2.3.0 \
    --output-format csv \
    --output-file matrix.csv \
    --summary-file gaps.json

# Markdown table printed to stdout
python traceability_matrix.py \
    --jira-project MYPROJ \
    --github-repo acme/my-service \
    --release-tag v2.3.0 \
    --output-format md

# Full nested JSON
python traceability_matrix.py \
    --jira-project MYPROJ \
    --github-repo acme/my-service \
    --release-tag v2.3.0 \
    --output-format json \
    --output-file matrix.json
```

---

### approval_collector.py

```
python approval_collector.py \
    --jira-project PROJ \
    --github-repo owner/repo \
    --release-tag v1.0.0 \
    [--start-date 2024-01-01] \
    [--output-file approvals.json]
```

**Arguments:**

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--jira-project` | yes | — | JIRA project key |
| `--github-repo` | yes | — | GitHub repo as `owner/repo` |
| `--release-tag` | yes | — | Git tag for the release |
| `--start-date` | no | — | Earliest approval date to include (`YYYY-MM-DD`) |
| `--output-file` | no | stdout | Path for JSON ledger; also writes `<name>_summary.md` |

**Examples:**

```bash
# JSON ledger + markdown summary, scoped to a sprint window
python approval_collector.py \
    --jira-project MYPROJ \
    --github-repo acme/my-service \
    --release-tag v2.3.0 \
    --start-date 2024-03-01 \
    --output-file approvals.json
# produces: approvals.json + approvals_summary.md

# Print JSON to stdout (pipe into jq, etc.)
python approval_collector.py \
    --jira-project MYPROJ \
    --github-repo acme/my-service \
    --release-tag v2.3.0
```

---

## Output Formats

### traceability_matrix.py

**CSV** (`--output-format csv`)

One row per (requirement, PR, approver) combination.

```
req_id, jira_ticket, jira_summary, pr_url, pr_merged_at, test_result, approver, approved_at
REQ-001, MYPROJ-42, Add login flow, https://github.com/.../pull/7, 2024-04-10T..., PASS, alice, 2024-04-09T...
```

**JSON** (`--output-format json`)

Full nested structure preserving all linked objects:
```json
[
  {
    "jira_key": "MYPROJ-42",
    "jira_summary": "Add login flow",
    "jira_status": "Done",
    "requirements": [{"req_id": "REQ-001", ...}],
    "test_cases": [{"test_id": "TEST-10", ...}],
    "design_doc_links": ["https://docs.example.com/..."],
    "pull_requests": [{
      "pr_number": 7,
      "pr_url": "...",
      "merged_at": "2024-04-10T...",
      "commits": [...],
      "ci_results": [...],
      "approvals": [...]
    }]
  }
]
```

**Markdown** (`--output-format md`)

A formatted table with hyperlinks, suitable for pasting into Confluence or a PR description.

**Gap Analysis / Summary JSON** (`--summary-file`)

```json
{
  "total_tickets": 25,
  "tickets_with_requirements": 21,
  "orphan_tickets": ["MYPROJ-55"],
  "total_requirements": 18,
  "uncovered_requirements": ["REQ-007"],
  "tickets_without_pr": ["MYPROJ-60"],
  "tickets_with_ci_failure": []
}
```

---

### approval_collector.py

**JSON Ledger** (`--output-file approvals.json`)

```json
{
  "generated_at": "2024-04-15T12:00:00+00:00",
  "total_records": 22,
  "records": [
    {
      "ticket_id": "MYPROJ-42",
      "pr_url": "https://github.com/acme/my-service/pull/7",
      "pr_number": 7,
      "jira_approver": "Bob Smith",
      "jira_approved_at": "2024-04-09T10:30:00.000+0000",
      "github_approver": "alice",
      "github_approved_at": "2024-04-09T11:00:00Z",
      "code_merged_at": "2024-04-10T08:00:00Z",
      "merge_commit_sha": "abc123def456...",
      "discrepancies": [],
      "record_hash": "e3b0c44298fc..."
    }
  ]
}
```

**Markdown Summary** (auto-generated as `approvals_summary.md`)

Includes a statistics block, full ledger table, discrepancy section, and integrity verification instructions.

**Integrity / Tamper Detection**

Each record carries a `record_hash` (SHA-256) computed over the concatenation of its key fields. To verify a record independently:

```python
import hashlib
fields = "|".join([
    record["ticket_id"], record["pr_url"],
    record["jira_approver"], record["jira_approved_at"],
    record["github_approver"], record["github_approved_at"],
    record["code_merged_at"], record["merge_commit_sha"],
])
assert hashlib.sha256(fields.encode()).hexdigest() == record["record_hash"]
```

---

## JIRA PR Linking

The scripts detect GitHub PR links in JIRA via:
1. GitHub PR URLs embedded in the JIRA issue description (e.g. `https://github.com/owner/repo/pull/123`).
2. Custom fields (`customfield_*`) that contain PR URLs (populated by the official Atlassian GitHub integration).

To maximise coverage, ensure your team either:
- Uses the [GitHub for Jira](https://marketplace.atlassian.com/apps/1219592) app (auto-links), or
- Includes the GitHub PR URL in the JIRA description when opening a PR.

---

## Rate Limits

| API | Limit | Script behaviour |
|-----|-------|-----------------|
| JIRA Cloud REST v3 | ~1 req/sec per token | 1 s delay between requests |
| GitHub REST API | 5 000 req/hour (authenticated) | ~0.72 s delay; respects `Retry-After` on 429 |

Both scripts implement exponential backoff (up to 3 retries) on 5xx and 429 responses.
