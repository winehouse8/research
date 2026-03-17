# GitHub Branch Protection Configuration Guide

**Purpose:** Establish branch protection controls for safety-critical software repositories as part of CI/CD certification evidence automation.

**Scope:** `main` and `release/*` branches in all repositories containing safety-critical software.

---

## Implementation Path A: GitHub Enterprise (Cloud or Server)

GitHub Enterprise enables organization-level Rulesets, which are enforced across all repositories and cannot be overridden by repository administrators. This is the preferred path for certification compliance.

### 1. Organization-Level Rulesets via GitHub UI

Navigate to: **Organization Settings → Code security and analysis → Rulesets → New ruleset → New branch ruleset**

Configure the following:

| Field | Value |
|---|---|
| Ruleset name | `safety-critical-branch-protection` |
| Enforcement status | `Active` |
| Target branches | `main`, `release/*` |
| Bypass actors | See break-glass policy below |

### 2. Required Review Configuration

Under **Require a pull request before merging**:

- Enable: **Require approving reviews**
- Minimum number of approvals: **2** (for safety-critical modules)
- Enable: **Dismiss stale pull request approvals when new commits are pushed**
- Enable: **Require review from Code Owners**
- Enable: **Require approval of the most recent reviewable push**
- Disable: **Allow specified actors to bypass required pull requests** (use break-glass exception list only)

### 3. Required Status Checks

Under **Require status checks to pass**:

Enable **Require branches to be up to date before merging**, then add the following required checks:

| Check Name | Description |
|---|---|
| `build` | Compilation and artifact generation |
| `test` | Full unit and integration test suite |
| `lint` | Static code style and quality checks |
| `sast` | Static Application Security Testing (e.g., CodeQL, Semgrep) |
| `jira-ticket-validator` | Confirms PR title contains valid JIRA ticket ID and ticket is in correct workflow state |

All checks must be marked **Required** (not optional). Checks must be sourced from a trusted GitHub Actions workflow — do not allow forks to supply status checks.

### 4. Additional Rule Configuration

Under **Additional settings**, enable:

- **Require linear history** — prevents merge commits; all merges via squash or rebase only
- **Require signed commits** — all commits must be GPG or SSH signed
- **Block force pushes** — prevents rewriting history on protected branches
- **Restrict deletions** — prevents branch deletion

### 5. No-Bypass Policy and Break-Glass Exception List

For certification purposes, the default state is **zero bypass actors**. Any emergency exception (break-glass) requires:

1. A named individual (not a team) listed in the bypass actor list with role `Repository Admin` or `Organization Admin`
2. A mandatory JIRA ticket opened before or within 1 hour of the bypass action (SOP-BYPASS-001)
3. The bypass event captured in the audit log stream (see section 7)
4. Post-incident review completed within 24 hours

Break-glass actors must be reviewed and recertified quarterly. List is maintained in `docs/certification-automation/access-control/break-glass-actors.md`.

### 6. CODEOWNERS Enforcement

Enable **Require review from Code Owners** in the ruleset. The `CODEOWNERS` file must be present in the repository root or `.github/` directory. See `CODEOWNERS.example` for the required structure.

CODEOWNERS reviews are in addition to the minimum 2-approver requirement — a CODEOWNERS reviewer counts as one of the required approvals only if they are not the PR author.

### 7. Audit Log Streaming Configuration

GitHub Enterprise supports streaming audit logs to an external SIEM. Configure via:

**Organization Settings → Audit log → Log streaming → New stream**

Supported targets: Amazon S3, Azure Blob Storage, Google Cloud Storage, Datadog, Splunk.

Minimum events to capture for certification evidence:

```
repo.branch_protection_rule.create
repo.branch_protection_rule.update
repo.branch_protection_rule.destroy
protected_branch.authorized_users_teams
pull_request.review_required_dismissed
pull_request_review.submitted
pull_request.merged
org.member_privilege_change
repo.ruleset.create
repo.ruleset.update
repo.ruleset.destroy
```

Retention: Minimum 2 years for safety-critical repositories.

### 8. Sample GitHub API Calls — Create Ruleset Programmatically

All API calls require a GitHub Personal Access Token or GitHub App token with `admin:org` scope.

**Create a branch ruleset via REST API:**

```bash
# Set variables
ORG="your-organization"
TOKEN="ghp_your_token_here"

curl -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  "https://api.github.com/orgs/${ORG}/rulesets" \
  -d '{
    "name": "safety-critical-branch-protection",
    "target": "branch",
    "enforcement": "active",
    "conditions": {
      "ref_name": {
        "include": ["refs/heads/main", "refs/heads/release/*"],
        "exclude": []
      }
    },
    "rules": [
      {
        "type": "pull_request",
        "parameters": {
          "required_approving_review_count": 2,
          "dismiss_stale_reviews_on_push": true,
          "require_code_owner_review": true,
          "require_last_push_approval": true,
          "required_review_thread_resolution": true
        }
      },
      {
        "type": "required_status_checks",
        "parameters": {
          "strict_required_status_checks_policy": true,
          "required_status_checks": [
            { "context": "build", "integration_id": null },
            { "context": "test", "integration_id": null },
            { "context": "lint", "integration_id": null },
            { "context": "sast", "integration_id": null },
            { "context": "jira-ticket-validator", "integration_id": null }
          ]
        }
      },
      { "type": "non_fast_forward" },
      { "type": "required_linear_history" },
      { "type": "required_signatures" },
      { "type": "deletion" }
    ],
    "bypass_actors": []
  }'
```

**Retrieve current ruleset to verify configuration:**

```bash
curl -X GET \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  "https://api.github.com/orgs/${ORG}/rulesets" | jq '.[] | select(.name == "safety-critical-branch-protection")'
```

**Export ruleset as certification evidence artifact:**

```bash
RULESET_ID=$(curl -s \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/orgs/${ORG}/rulesets" \
  | jq -r '.[] | select(.name == "safety-critical-branch-protection") | .id')

curl -s \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/orgs/${ORG}/rulesets/${RULESET_ID}" \
  > evidence/branch-protection-ruleset-$(date +%Y%m%d).json
```

---

## Implementation Path B: GitHub Free / Team

GitHub Free and Team plans do not support organization-level Rulesets. Branch protection must be configured at the repository level. This path has inherent limitations that must be documented and mitigated.

### 1. Repository-Level Branch Protection Rules

Navigate to: **Repository Settings → Branches → Add branch protection rule**

Set **Branch name pattern** to `main` and repeat for `release/*`.

### 2. Required Review Configuration

| Setting | Value |
|---|---|
| Require a pull request before merging | Enabled |
| Required number of approvals | 2 (safety-critical), 1 (standard) |
| Dismiss stale pull request approvals | Enabled |
| Require review from Code Owners | Enabled |
| Restrict who can dismiss pull request reviews | Enabled — limit to security leads only |

### 3. Required Status Checks

Enable **Require status checks to pass before merging** and **Require branches to be up to date before merging**.

Add required contexts:

- `build`
- `test`
- `lint`
- `sast`
- `jira-ticket-validator`

### 4. CODEOWNERS Enforcement

Same as Path A. Place `CODEOWNERS` in the repository root or `.github/` directory. Enable **Require review from Code Owners** in the branch protection rule.

### 5. Linear History

Enable **Require linear history**. Configure the repository to only allow **Squash merging** or **Rebase merging** under **Repository Settings → General → Pull Requests**.

### 6. Configuring via GitHub API (Repository Level)

```bash
OWNER="your-org-or-user"
REPO="your-repository"
TOKEN="ghp_your_token_here"

curl -X PUT \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  "https://api.github.com/repos/${OWNER}/${REPO}/branches/main/protection" \
  -d '{
    "required_status_checks": {
      "strict": true,
      "contexts": ["build", "test", "lint", "sast", "jira-ticket-validator"]
    },
    "enforce_admins": true,
    "required_pull_request_reviews": {
      "dismissal_restrictions": {},
      "dismiss_stale_reviews": true,
      "require_code_owner_reviews": true,
      "required_approving_review_count": 2,
      "require_last_push_approval": true
    },
    "restrictions": null,
    "required_linear_history": true,
    "allow_force_pushes": false,
    "allow_deletions": false,
    "block_creations": false,
    "required_conversation_resolution": true,
    "lock_branch": false,
    "allow_fork_syncing": false
  }'
```

### 7. Limitations of GitHub Free / Team

| Limitation | Impact |
|---|---|
| No organization-level enforcement | Each repository must be configured individually; no central policy |
| Repository administrators can modify or disable branch protection | A repo admin could bypass controls without going through break-glass |
| No org-level Rulesets | Cannot cascade policy changes to all repos simultaneously |
| No native audit log streaming | Must poll audit log API; no real-time SIEM integration |
| `enforce_admins` can be disabled by repo admins | Admins could merge without review |

### 8. Mitigations for GitHub Free / Team

**Restrict repository administrator access:**

- Maintain minimum number of repository admins (target: 2, maximum: 4)
- All admins must be named individuals — no service accounts with admin role
- Admin list reviewed quarterly and documented in `docs/certification-automation/access-control/repo-admins.md`

**Monitor via GitHub Audit Log API:**

```bash
# Poll audit log for branch protection changes (run on a schedule)
curl -s \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/orgs/${ORG}/audit-log?phrase=action:protected_branch&per_page=100" \
  | jq '.[] | {action, actor, created_at, repo}'
```

Set up a daily cron job or GitHub Actions scheduled workflow to export audit log entries and write them to a compliance evidence store.

**Use GitHub Actions to detect configuration drift:**

Create a scheduled workflow (`.github/workflows/branch-protection-audit.yml`) that:
1. Reads current branch protection settings via API
2. Compares against expected baseline JSON stored in the repository
3. Opens a JIRA ticket and sends an alert if drift is detected

---

## Acceptance Criteria Checklist

Use this checklist to verify branch protection is correctly configured before declaring a repository compliant. Each item must be verified and the output documented as certification evidence.

### Evidence Collection

- [ ] Export branch protection / ruleset configuration as JSON artifact and store in evidence store
- [ ] Confirm audit log streaming is active (Enterprise) or polling job is scheduled (Free/Team)
- [ ] Record date of verification and verifier identity in evidence manifest

### Required Reviews

- [ ] Minimum 2 approving reviews required for `main` and `release/*`
- [ ] Stale review dismissal enabled (new commits invalidate prior approvals)
- [ ] Code Owner review required
- [ ] Most recent push approval required
- [ ] Review thread resolution required before merge

### Required Status Checks

- [ ] `build` check is required and must pass
- [ ] `test` check is required and must pass
- [ ] `lint` check is required and must pass
- [ ] `sast` check is required and must pass
- [ ] `jira-ticket-validator` check is required and must pass
- [ ] Branches must be up to date with target before merge

### History and Integrity

- [ ] Linear history enforced (no merge commits)
- [ ] Signed commits required (Enterprise) or commit signing policy documented (Free/Team)
- [ ] Force pushes blocked
- [ ] Branch deletion restricted

### Access Control

- [ ] Zero bypass actors configured in default state (Enterprise)
- [ ] Break-glass actor list documented and reviewed within last 90 days
- [ ] Repository admin list documented and reviewed within last 90 days
- [ ] `enforce_admins: true` confirmed via API response

### CODEOWNERS

- [ ] `CODEOWNERS` file present in repository root or `.github/`
- [ ] All safety-critical paths have designated owners
- [ ] Code Owner review requirement is enabled in branch protection
- [ ] CODEOWNERS reviewed and updated within last 90 days

### Audit and Monitoring

- [ ] Audit log retention meets minimum 2-year requirement
- [ ] Drift detection mechanism in place and last run within 24 hours
- [ ] Most recent audit log export available in evidence store
