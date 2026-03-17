# Phase 1 – JIRA Automation Rules Reference

> This document specifies all Automation Rules used in the certification evidence workflow.
> Rules are numbered and referenced by `workflow-config.md`.
> Each rule entry follows the same structure: Trigger, Condition, Action, Audit Log Output.

---

## Background: Automation Rules vs ScriptRunner Validators

Understanding this distinction is critical for audit defensibility.

| Property | Automation Rules (Cloud + DC) | ScriptRunner Validators (DC only) |
|---|---|---|
| Execution timing | **Post-transition** (issue has already moved) | **Pre-transition** (issue has not moved yet) |
| Enforcement style | Rollback: transition executes, then reversed | Blocking: transition never executes |
| Visible to user | Transition succeeds briefly, then comment appears | Immediate error message before status changes |
| Audit window | Small window where invalid status is visible | No window; invalid status never written |
| Suitable for Cloud | Yes (only option for sequence enforcement) | No (not available on Cloud) |
| Suitable for Data Center | Yes (supplemental) | Yes (primary enforcement) |
| Certification risk | Low if rollback is fast and logged | Minimal — preferred for Class C / ASIL D |
| Can be disabled by project admin | Yes — must be access-controlled | No — embedded in workflow definition |

**Recommendation for Data Center:** Use ScriptRunner validators as the primary gate (as specified in `workflow-config.md` Path B). Use Automation Rules as a secondary audit layer and for GitHub webhook integration (Rules 3 and 4 in this document).

**Requirement for Cloud:** Automation Rules are the *only* available sequence enforcement mechanism. Implement all four rules. Document the post-transition rollback window in your Software Development Plan as a known limitation and obtain quality lead sign-off.

---

## Rule Naming Convention

All rules must be named with the prefix `[CERT]` to distinguish them from operational automation. Example: `[CERT] Enforce In Review Before Approved`. This allows filtering in the Automation Rule audit log.

---

## Rule 1: Enforce In Review → Approved Sequence

**Purpose:** Prevent any issue from reaching "Approved" status without having first passed through "In Review". Implements the segregation of duties and review gate required by IEC 62304 §5.5 and ISO 26262-8 §9.

---

**Trigger**

```
Type:        Issue transitioned
From status: (any — leave blank to catch all paths)
To status:   Approved
```

---

**Condition**

```
Type:   JQL condition
JQL:    issue = {{issue.key}} AND NOT status WAS "In Review"

Logic:  If this JQL returns any results (i.e., the issue exists AND
        has never been in "In Review"), the condition is TRUE and
        the rollback action fires.

Note:   The JIRA "status WAS" predicate queries the full status
        history of the issue, not just the immediately preceding
        status. An issue that was In Review, went back to In Progress,
        and then jumped to Approved would NOT trigger this rule,
        which is the correct behavior.
```

---

**Action (executes only when condition is TRUE)**

```
Step 1 — Transition issue
  To status:  In Progress
  Comment:    [AUTOMATED ENFORCEMENT — DO NOT REMOVE]
              Rule: [CERT] Enforce In Review Before Approved
              Result: Transition to "Approved" has been REVERSED.

              Reason: This issue has no "In Review" history.
              Certification requirement: IEC 62304 §5.5 / ISO 26262-8 §9 require
              that all software changes pass a documented review stage before approval.

              Attempted by:  {{initiator.displayName}} ({{initiator.accountId}})
              Attempted at:  {{now.format("yyyy-MM-dd HH:mm:ss z")}}
              Issue:         {{issue.key}} — {{issue.summary}}

              Required next steps:
              1. Ensure a GitHub Pull Request is open and linked in the
                 "GitHub PR URL" field.
              2. Transition the issue to "In Review" via "Submit for Review".
              3. Have a member of jira-approvers review and approve the PR.
              4. Only then transition to "Approved".

Step 2 — Add audit comment (separate comment for machine parsing)
  Comment:    CERT_AUDIT | rule=ENFORCE_IN_REVIEW_BEFORE_APPROVED
              | result=ROLLBACK | issue={{issue.key}}
              | actor_id={{initiator.accountId}}
              | actor_name={{initiator.displayName}}
              | attempted_transition=*->Approved
              | rolled_back_to=In Progress
              | timestamp={{now.format("yyyy-MM-dd'T'HH:mm:ssXXX")}}
              | jira_project={{issue.project.key}}
```

---

**Audit Log Output**

When this rule fires, the JIRA Automation audit log records:

```
Rule name:    [CERT] Enforce In Review Before Approved
Triggered by: Issue transitioned to Approved
Issue:        <PROJECT-KEY>
Actor:        <displayName> (<accountId>)
Result:       Rule executed successfully (both actions completed)
Timestamp:    <ISO-8601>
```

The machine-readable `CERT_AUDIT` comment on the issue is additionally parseable by the evidence collection pipeline (Phase 2) for report generation.

---

## Rule 2: Enforce Approved → Merged Sequence

**Purpose:** Prevent any issue from reaching "Merged" status without having first been "Approved". Ensures that no unapproved code is recorded as merged in the certification evidence trail.

---

**Trigger**

```
Type:        Issue transitioned
From status: (any)
To status:   Merged
```

---

**Condition**

```
Type:   JQL condition
JQL:    issue = {{issue.key}} AND NOT status WAS "Approved"

Logic:  If the issue has never been in "Approved" status, the
        condition is TRUE and rollback fires.

        If the issue was Approved, then un-Approved (e.g., sent
        back to In Review), and then someone tries to merge —
        this rule correctly allows it IF Approved is in history.
        If your process requires the *most recent* pre-Merged
        status to be Approved (stricter), supplement with
        Rule 2b below.
```

---

**Action (executes only when condition is TRUE)**

```
Step 1 — Transition issue
  To status:  In Review
  Comment:    [AUTOMATED ENFORCEMENT — DO NOT REMOVE]
              Rule: [CERT] Enforce Approved Before Merged
              Result: Transition to "Merged" has been REVERSED.

              Reason: This issue has no "Approved" history.
              A merge without prior approval violates the controlled
              change process required by the certification scope.

              Attempted by:  {{initiator.displayName}} ({{initiator.accountId}})
              Attempted at:  {{now.format("yyyy-MM-dd HH:mm:ss z")}}
              Issue:         {{issue.key}} — {{issue.summary}}

              Required next steps:
              1. Have a member of jira-approvers transition this issue to "Approved".
              2. Only after approval may the PR be merged and this issue
                 transitioned to "Merged" (automated via CI webhook).

Step 2 — Add audit comment
  Comment:    CERT_AUDIT | rule=ENFORCE_APPROVED_BEFORE_MERGED
              | result=ROLLBACK | issue={{issue.key}}
              | actor_id={{initiator.accountId}}
              | actor_name={{initiator.displayName}}
              | attempted_transition=*->Merged
              | rolled_back_to=In Review
              | timestamp={{now.format("yyyy-MM-dd'T'HH:mm:ssXXX")}}
              | jira_project={{issue.project.key}}
```

---

**Optional Rule 2b — Strict: Last Status Before Merged Must Be Approved**

If your process requires the *immediately preceding* status (not just any historical status) to be Approved, add this additional condition to Rule 2:

```
Additional condition (AND):
  Type:   Advanced compare
  Field:  {{issue.previousStatus.name}}
  Op:     not equals
  Value:  Approved

Combined logic: fires if (never was Approved) OR (last status was not Approved)
```

Consult your quality lead on whether strict or history-based checking is required by your specific standard interpretation.

---

**Audit Log Output**

```
Rule name:    [CERT] Enforce Approved Before Merged
Triggered by: Issue transitioned to Merged
Issue:        <PROJECT-KEY>
Actor:        <displayName> (<accountId>)
Result:       Rule executed successfully
Timestamp:    <ISO-8601>
```

---

## Rule 3: Auto-Transition to Merged When GitHub PR Is Merged

**Purpose:** Remove the manual step of transitioning an issue to "Merged" after a GitHub PR is merged. Ensures the JIRA status update is atomic with the GitHub merge event and is attributable to the CI system rather than a human actor.

This rule is the primary integration point between GitHub and JIRA. It is triggered by an incoming webhook from GitHub Actions (or directly from the GitHub webhook settings).

---

**Trigger**

```
Type:     Incoming webhook
Webhook name: github-pr-merged
URL:      https://<your-jira-instance>.atlassian.net/rest/automation/
          webhook/github-pr-merged/<webhook-secret-token>

Payload shape expected (sent by GitHub Actions):
{
  "issue_key":   "PROJ-123",
  "pr_number":   42,
  "pr_url":      "https://github.com/org/repo/pull/42",
  "pr_title":    "feat: add safety monitor module",
  "merged_by":   "github-username",
  "merged_at":   "2026-03-11T14:22:00Z",
  "base_branch": "main",
  "sha":         "abc123def456..."
}
```

---

**Condition**

```
Step 1 — Validate webhook payload fields are present:
  Type:   Advanced compare
  Field:  {{webhookData.issue_key}}
  Op:     is not empty

  AND

  Field:  {{webhookData.pr_url}}
  Op:     is not empty

Step 2 — Confirm issue is in "Approved" status (correct state for merge):
  Type:   JQL condition
  JQL:    issue = {{webhookData.issue_key}} AND status = "Approved"

  Note:   If the issue is not in Approved when the webhook fires, the
          rule does NOT transition it. This prevents a race condition
          where a PR is merged before JIRA approval is recorded.
          In that case, Rule 3 logs an error comment and Rule 2 will
          catch the violation if someone manually tries to move to Merged.
```

---

**Action**

```
Step 1 — Update "GitHub PR URL" field (ensure it is set)
  Field:  GitHub PR URL
  Value:  {{webhookData.pr_url}}

Step 2 — Update "Merged SHA" field (custom field, type: Text)
  Field:  Merged Commit SHA
  Value:  {{webhookData.sha}}

Step 3 — Transition issue
  To status: Merged
  Comment:   [AUTOMATED — GitHub CI] Pull request merged.
             PR:         #{{webhookData.pr_number}} — {{webhookData.pr_title}}
             PR URL:     {{webhookData.pr_url}}
             Merged by:  {{webhookData.merged_by}}
             Merged at:  {{webhookData.merged_at}}
             Base:       {{webhookData.base_branch}}
             Commit SHA: {{webhookData.sha}}

Step 4 — Audit comment
  Comment:   CERT_AUDIT | rule=AUTO_TRANSITION_MERGED_ON_PR_MERGE
             | result=SUCCESS | issue={{webhookData.issue_key}}
             | pr_number={{webhookData.pr_number}}
             | pr_url={{webhookData.pr_url}}
             | merged_by={{webhookData.merged_by}}
             | merged_at={{webhookData.merged_at}}
             | sha={{webhookData.sha}}
             | timestamp={{now.format("yyyy-MM-dd'T'HH:mm:ssXXX")}}
```

---

**GitHub Actions Workflow Snippet (sends the webhook)**

Place this in `.github/workflows/jira-sync.yml` or as a step in your existing merge workflow:

```yaml
name: Notify JIRA on PR Merge

on:
  pull_request:
    types: [closed]
    branches: [main, release/**]

jobs:
  jira-notify:
    if: github.event.pull_request.merged == true
    runs-on: ubuntu-latest
    steps:
      - name: Extract JIRA issue key from PR title or branch
        id: extract
        run: |
          # Looks for pattern like PROJ-123 in PR title or branch name
          ISSUE_KEY=$(echo "${{ github.event.pull_request.title }} ${{ github.head_ref }}" \
            | grep -oP '[A-Z]+-[0-9]+' | head -1)
          echo "issue_key=$ISSUE_KEY" >> $GITHUB_OUTPUT

      - name: Send webhook to JIRA Automation
        if: steps.extract.outputs.issue_key != ''
        run: |
          curl -s -X POST \
            -H "Content-Type: application/json" \
            -d '{
              "issue_key":   "${{ steps.extract.outputs.issue_key }}",
              "pr_number":   ${{ github.event.pull_request.number }},
              "pr_url":      "${{ github.event.pull_request.html_url }}",
              "pr_title":    "${{ github.event.pull_request.title }}",
              "merged_by":   "${{ github.event.pull_request.merged_by.login }}",
              "merged_at":   "${{ github.event.pull_request.merged_at }}",
              "base_branch": "${{ github.event.pull_request.base.ref }}",
              "sha":         "${{ github.event.pull_request.merge_commit_sha }}"
            }' \
            "${{ secrets.JIRA_AUTOMATION_WEBHOOK_URL }}"
```

**Required GitHub secret:** `JIRA_AUTOMATION_WEBHOOK_URL` — the full webhook URL from the JIRA Automation rule trigger (including the secret token).

---

**Audit Log Output**

```
Rule name:    [CERT] Auto-Transition to Merged When GitHub PR Merged
Triggered by: Incoming webhook (github-pr-merged)
Issue:        <issue_key from payload>
PR:           #<pr_number> <pr_url>
Result:       Transitioned to Merged / Condition not met (issue not in Approved)
Timestamp:    <ISO-8601>
```

---

## Rule 4: Block Transition to In Review If No Linked GitHub PR

**Purpose:** Prevent an issue from entering the review stage without a valid GitHub PR URL recorded. This ensures the review artifact (the PR) exists in GitHub before the JIRA review state begins, creating a bidirectional traceability link at the time the review opens.

---

**Trigger**

```
Type:        Issue transitioned
From status: In Progress (or any)
To status:   In Review
```

---

**Condition**

```
Type:   Advanced compare condition
Field:  {{issue.GitHub PR URL}}     [smart value for the custom field]
Op:     is empty

Logic:  If the GitHub PR URL field is blank, condition is TRUE
        and the rollback action fires.
```

---

**Action (executes only when condition is TRUE)**

```
Step 1 — Transition issue
  To status:  In Progress
  Comment:    [AUTOMATED ENFORCEMENT — DO NOT REMOVE]
              Rule: [CERT] Block In Review if No GitHub PR
              Result: Transition to "In Review" has been REVERSED.

              Reason: The "GitHub PR URL" field is empty.
              A linked GitHub Pull Request is required before an issue
              can enter the review stage. This creates the traceability
              link between the JIRA change record and the code review
              artifact required by IEC 62304 §5.5.3 / ISO 26262-8 §9.

              Attempted by:  {{initiator.displayName}} ({{initiator.accountId}})
              Attempted at:  {{now.format("yyyy-MM-dd HH:mm:ss z")}}
              Issue:         {{issue.key}} — {{issue.summary}}

              Required next steps:
              1. Open a Pull Request in GitHub for the branch associated
                 with this issue.
              2. Copy the PR URL (format: https://github.com/org/repo/pull/N).
              3. Paste it into the "GitHub PR URL" field on this issue.
              4. Retry the "Submit for Review" transition.

Step 2 — Audit comment
  Comment:    CERT_AUDIT | rule=BLOCK_IN_REVIEW_NO_PR
              | result=ROLLBACK | issue={{issue.key}}
              | actor_id={{initiator.accountId}}
              | actor_name={{initiator.displayName}}
              | attempted_transition=In Progress->In Review
              | rolled_back_to=In Progress
              | missing_field=GitHub PR URL
              | timestamp={{now.format("yyyy-MM-dd'T'HH:mm:ssXXX")}}
              | jira_project={{issue.project.key}}
```

---

**Audit Log Output**

```
Rule name:    [CERT] Block In Review if No GitHub PR
Triggered by: Issue transitioned to In Review
Issue:        <PROJECT-KEY>
Actor:        <displayName> (<accountId>)
Result:       Rule executed (rollback applied) / Condition not met (PR URL present, no action)
Timestamp:    <ISO-8601>
```

---

## Rule Execution Order and Conflict Notes

JIRA Automation Rules with the same trigger fire in the order they are listed in the project's Automation settings. Ensure the following order to avoid conflicts:

| Order | Rule | Reason |
|---|---|---|
| 1 | [CERT] Block In Review if No GitHub PR | Must run before any review-stage rules |
| 2 | [CERT] Enforce In Review Before Approved | Must run on every transition to Approved |
| 3 | [CERT] Enforce Approved Before Merged | Must run on every transition to Merged |
| 4 | [CERT] Auto-Transition to Merged When GitHub PR Merged | Webhook-triggered; does not conflict |

To reorder rules: **Project Settings > Automation > (drag rules to correct order)**.

---

## Audit Comment Schema Reference

All `CERT_AUDIT` comments follow this schema for machine parsing by the evidence pipeline:

```
CERT_AUDIT
  | rule=<RULE_CONSTANT_NAME>
  | result=<ROLLBACK|SUCCESS|SKIPPED|ERROR>
  | issue=<JIRA-KEY>
  | actor_id=<accountId>          (Atlassian account UUID)
  | actor_name=<displayName>
  | attempted_transition=<from->to>
  | rolled_back_to=<status>       (present only when result=ROLLBACK)
  | missing_field=<field_name>    (present only for Rule 4)
  | pr_number=<N>                 (present only for Rule 3)
  | pr_url=<url>                  (present only for Rules 3 and 4)
  | merged_by=<github_username>   (present only for Rule 3)
  | merged_at=<ISO-8601>          (present only for Rule 3)
  | sha=<commit_sha>              (present only for Rule 3)
  | timestamp=<ISO-8601>
  | jira_project=<PROJECT-KEY>
```

The evidence collection pipeline (Phase 2) queries JIRA issue comments with `text ~ "CERT_AUDIT"` and parses the pipe-delimited fields to populate the certification evidence report.

---

## Testing All Four Rules

Run these test cases after implementation. Record pass/fail and date in the test log committed to the repository.

| # | Test Case | Expected Result | Rule Tested |
|---|---|---|---|
| T1 | Transition issue directly from Open to Approved | Rolls back to In Progress; CERT_AUDIT comment posted | Rule 1 |
| T2 | Move issue through In Review, then back to In Progress, then to Approved | Allowed (In Review is in history) | Rule 1 (negative case) |
| T3 | Transition issue from In Review directly to Merged (skip Approved) | Rolls back to In Review; CERT_AUDIT comment posted | Rule 2 |
| T4 | Move issue through full sequence (Open→IP→IR→Approved→Merged) | No rollback; all transitions succeed | Rules 1+2 (negative case) |
| T5 | Move issue to In Review with GitHub PR URL field empty | Rolls back to In Progress; CERT_AUDIT comment posted | Rule 4 |
| T6 | Move issue to In Review with valid PR URL present | Allowed | Rule 4 (negative case) |
| T7 | Send webhook payload with valid issue key in Approved status | Issue transitions to Merged; SHA and PR URL recorded | Rule 3 |
| T8 | Send webhook payload with valid issue key NOT in Approved status | No transition; error comment posted | Rule 3 (guard condition) |
| T9 | Send webhook payload with missing issue_key field | Rule condition fails; no action; logged in Automation history | Rule 3 (malformed payload) |

---

> After all rules are implemented and tested, proceed to Phase 2: GitHub branch protection rules, required status checks, and the CI evidence collection pipeline.
