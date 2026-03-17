# Contributing Guide

**Repository:** Safety-Critical Software Project
**Applies to:** All contributors — engineers, QA, DevSecOps, and external collaborators

This guide defines the mandatory contribution workflow for this repository. Because this software is subject to certification requirements, the procedures here are not suggestions — they are enforced by automated tooling. Deviations will cause your pull request to be blocked or automatically rolled back.

If you are new to the project, complete the safety onboarding checklist (`docs/safety/onboarding-checklist.md`) before opening your first pull request.

---

## 1. Commit Message Convention

Every commit must reference a JIRA ticket. This is enforced by a commit-msg hook and by the `jira-ticket-validator` CI check.

### Format

```
[PROJ-XXX] Short imperative description (max 72 characters)

Optional longer body explaining the why, not the what. Wrap at 72 characters.
Reference related tickets, ADRs, or test results here.

Refs: PROJ-YYY, PROJ-ZZZ
```

### Rules

- The ticket ID `[PROJ-XXX]` must appear at the very start of the subject line, including the square brackets.
- The ticket must exist in JIRA and must be assigned to you at the time of the commit.
- The subject line must use the imperative mood: "Add", "Fix", "Remove", not "Added", "Fixed", "Removing".
- Maximum subject line length: 72 characters including the ticket prefix.
- No period at the end of the subject line.
- Separate subject from body with a blank line.

### Valid Examples

```
[PROJ-142] Add fault isolation boundary in actuator controller

[PROJ-98] Fix watchdog reset timing on cold boot sequence

The previous implementation used wall-clock time which drifted on
embedded targets without RTC. Switched to monotonic counter.
Refs: PROJ-95 (original bug report)

[PROJ-205] Remove deprecated CAN bus fallback path

[PROJ-310] Update FMEA coverage for brake-by-wire subsystem
```

### Invalid Examples

```
# WRONG — no ticket ID
Fix the bug

# WRONG — ticket not in brackets
PROJ-142 Add fault isolation boundary

# WRONG — past tense
[PROJ-142] Added fault isolation boundary

# WRONG — subject too long (over 72 characters)
[PROJ-142] Add fault isolation boundary in the actuator controller subsystem which handles

# WRONG — ticket ID not at start
Fixes [PROJ-142] — fault isolation boundary
```

### Installing the Commit-Msg Hook

Run this once after cloning:

```bash
cp .github/hooks/commit-msg .git/hooks/commit-msg
chmod +x .git/hooks/commit-msg
```

The hook rejects commits that do not match the required format before they are created locally, saving you a round-trip through CI.

---

## 2. Branch Naming Convention

Branches must be named according to their type and must include the JIRA ticket ID. The `jira-ticket-validator` check reads the branch name as a fallback when the PR title is being validated.

### Format

```
<type>/PROJ-XXX-short-description
```

### Types

| Type | When to use |
|---|---|
| `feature/` | New functionality or capability |
| `fix/` | Bug fix, defect correction |
| `hotfix/` | Urgent fix targeting a release branch directly |
| `refactor/` | Code restructuring with no behavior change |
| `test/` | Adding or improving tests only |
| `docs/` | Documentation changes only |
| `chore/` | Build system, CI, dependency updates |

### Valid Examples

```
feature/PROJ-142-actuator-fault-isolation
fix/PROJ-98-watchdog-reset-timing
hotfix/PROJ-301-brake-signal-overflow
refactor/PROJ-215-simplify-can-arbitration
test/PROJ-188-add-hil-brake-scenarios
docs/PROJ-220-update-fmea-coverage
chore/PROJ-199-upgrade-cmake-3.28
```

### Invalid Examples

```
# WRONG — no ticket ID
feature/actuator-fault-isolation

# WRONG — no type prefix
PROJ-142-actuator-fault-isolation

# WRONG — spaces not allowed
feature/PROJ 142 actuator fault

# WRONG — uppercase in description
feature/PROJ-142-Actuator-Fault-Isolation
```

### Creating a Branch

```bash
git checkout main
git pull --rebase origin main
git checkout -b feature/PROJ-142-actuator-fault-isolation
```

Never branch off another feature branch. Always branch from `main` (or the target release branch for hotfixes).

---

## 3. Pull Request Requirements

### PR Title Format

```
[PROJ-XXX] Short imperative description
```

The title must match the same format as the commit message subject. The `jira-ticket-validator` CI check will fail if:

- No JIRA ticket ID is present in the title.
- The ticket does not exist in JIRA.
- The ticket is not in the `In Review` workflow state at the time the PR is opened or updated.
- The ticket is not assigned to the PR author.

### PR Size Guidelines

Keep PRs small and focused on a single concern. Large PRs slow down review and make certification traceability harder.

| Lines changed | Guidance |
|---|---|
| < 200 | Preferred size |
| 200–500 | Acceptable with good description |
| 500–1000 | Requires justification in PR body |
| > 1000 | Split into multiple PRs unless structurally impossible |

---

## 4. PR Description Template

When you open a pull request, the following template will be pre-filled. All sections are mandatory. Do not delete sections; write "N/A" with a brief explanation if a section genuinely does not apply.

```markdown
## JIRA Ticket

<!-- Replace with the full URL to your JIRA ticket -->
[PROJ-XXX](https://your-org.atlassian.net/browse/PROJ-XXX)

**Ticket status at time of PR creation:** In Review

## Summary

<!-- One or two sentences. What does this PR do and why? -->

## Changes

<!-- Bullet list of concrete changes made. Be specific. -->
-
-

## Test Evidence

<!-- Describe how the change was tested. Link to test results, CI run, or HIL report. -->

### Unit tests
- [ ] New unit tests added for changed logic
- [ ] All existing unit tests pass (CI: link to run)

### Integration tests
- [ ] Integration tests updated or confirmed unaffected
- [ ] CI integration test job passed (link to run)

### Hardware-in-the-loop (if applicable)
- [ ] HIL test executed — attach report or link here
- [ ] N/A — changes do not affect hardware interfaces

## Safety Impact Assessment

<!-- Required for any change in src/safety/, src/actuators/, src/watchdog/, src/fault-monitor/ -->
- [ ] No safety-critical code affected
- [ ] Safety-critical code affected — FMEA impact reviewed with @your-org/safety-engineers
- [ ] Hazard analysis updated (link to updated doc)

## Checklist

- [ ] Commit messages follow `[PROJ-XXX] Description` format
- [ ] Branch name follows `type/PROJ-XXX-description` format
- [ ] JIRA ticket is in `In Review` state
- [ ] CODEOWNERS have been notified (GitHub does this automatically)
- [ ] No new warnings introduced in build or lint output
- [ ] SAST scan passed with no new high or critical findings
- [ ] Documentation updated if behavior changed
- [ ] No secrets, credentials, or PII committed

## Related PRs / Dependencies

<!-- List any PRs that must be merged before or after this one -->
- None
```

---

## 5. JIRA Workflow Stages

Every code change must be tracked through the full JIRA workflow. The `jira-ticket-validator` CI check enforces that tickets are in the correct state at each stage of the GitHub workflow. Attempting to skip stages will cause automated enforcement actions described below.

### Required Workflow Sequence

```
Open  -->  In Progress  -->  In Review  -->  Approved  -->  Merged
```

| Stage | Who transitions | When |
|---|---|---|
| **Open** | Ticket creator or project manager | Ticket created and acceptance criteria defined |
| **In Progress** | Assignee (you) | You begin coding — transition before your first commit |
| **In Review** | Assignee (you) | You open the pull request — transition before or at PR creation |
| **Approved** | Reviewer(s) | All required approvals received and all CI checks pass |
| **Merged** | Automation | PR is merged; JIRA ticket automatically transitions to Merged via webhook |

### Stage Descriptions

**Open:** The ticket exists and has been triaged. Acceptance criteria are written. No code work has started.

**In Progress:** You are actively working on the ticket. The branch exists. At least one commit has been pushed. Only one ticket per engineer should be In Progress at a time.

**In Review:** The pull request is open and awaiting reviewer action. You must not continue making substantive changes to the implementation while In Review — only changes requested by reviewers are permitted. New commits that are not reviewer-requested changes will dismiss existing approvals.

**Approved:** All required reviewers have approved. All CI checks are green. The ticket is ready to merge. Do not merge immediately — allow 15 minutes for any last-minute objections before merging.

**Merged:** The PR has been merged into the target branch. The JIRA webhook transitions the ticket automatically. You do not manually transition to this state.

### What the `jira-ticket-validator` Check Enforces

| GitHub event | Required JIRA state | Failure action |
|---|---|---|
| PR opened | `In Review` | CI check fails; PR cannot be merged |
| PR updated (new commits) | `In Review` | CI check fails; PR cannot be merged |
| PR approved (all approvals received) | `In Review` or `Approved` | CI check fails; merge blocked |
| PR merge attempted | `Approved` | Merge blocked by required status check |

---

## 6. What Happens If You Skip Stages

The enforcement system is automated and will take the following actions without manual intervention.

### Skipping "Open" to "In Progress" (committing without a valid ticket)

- The commit-msg hook rejects the commit locally.
- If the hook is bypassed (e.g., `--no-verify`), the `jira-ticket-validator` CI check will fail on push.
- CI failure blocks the PR from being merged.
- A flag is logged in the audit trail. Repeated use of `--no-verify` is treated as a compliance violation and escalated to the engineering lead.

### Skipping "In Progress" (ticket still in Open when PR is created)

- The `jira-ticket-validator` check fails with the message:
  `JIRA ticket PROJ-XXX is in state "Open" but must be in "In Review". Please transition the ticket before opening a PR.`
- The PR is blocked from merging until the ticket is transitioned.

### Skipping "In Review" (merging directly without a PR, or merging a draft PR)

- The branch protection rules prevent any direct push to `main` or `release/*`.
- Draft PRs cannot be merged — GitHub prevents this natively.
- If a PR is somehow merged while the ticket is not in `In Review` or `Approved` state, the post-merge webhook detects this and:
  1. Creates a JIRA incident ticket linked to the offending PR.
  2. Sends an alert to the engineering lead and DevSecOps channels.
  3. Logs the event in the compliance audit store.
  4. Flags the release as non-compliant pending investigation.

### Attempting to Rollback a Merged PR

If a non-compliant merge is detected, the rollback procedure is:

1. DevSecOps opens an incident JIRA ticket (automatically created by webhook).
2. Engineering lead reviews within 4 business hours.
3. If rollback is required, a revert PR is opened — it must also go through the full review workflow with the incident ticket ID referenced.
4. The original non-compliant merge is documented in the certification evidence as a deviation with corrective action.

Rollbacks are not automated. They require human review because a revert can itself introduce safety issues.

---

## 7. Requesting Approval and Approver Directory

### How to Request Approval

1. Ensure your JIRA ticket is in `In Review` state before opening the PR.
2. Open the PR using the description template above. GitHub automatically notifies CODEOWNERS.
3. Do not manually request reviews from engineers who are not CODEOWNERS for your changed files — CODEOWNERS assignment is automatic and adding additional reviewers can cause confusion about who has authority to approve.
4. Post a message in the `#code-review` Slack channel with the PR link and a one-line summary if your PR is time-sensitive.
5. Allow at least 1 business day for reviewers to respond before following up.

### Response Time SLAs

| PR size (lines changed) | Initial response SLA | Full review SLA |
|---|---|---|
| < 200 | 4 business hours | 1 business day |
| 200–500 | 1 business day | 2 business days |
| > 500 | 1 business day | 3 business days |

If a reviewer has not responded within the SLA, escalate to your engineering lead — do not re-request review from the same person.

### Approver Directory

| Path / Area | Required Approvers | GitHub Team |
|---|---|---|
| All files (catch-all) | Any 2 members | `@your-org/engineering-leads` |
| `src/safety/` | Safety engineer + QA rep | `@your-org/safety-engineers`, `@your-org/software-qa` |
| `src/actuators/` | Safety engineer + hardware lead | `@your-org/safety-engineers`, `@your-org/hardware-leads` |
| `src/fault-monitor/` | Safety engineer + QA rep | `@your-org/safety-engineers`, `@your-org/software-qa` |
| `src/watchdog/` | Safety engineer + QA rep | `@your-org/safety-engineers`, `@your-org/software-qa` |
| `tests/` | QA lead + engineering lead | `@your-org/software-qa`, `@your-org/engineering-leads` |
| `docs/certification-automation/` | QA lead + project manager | `@your-org/software-qa`, `@your-org/project-managers` |
| `.github/` | DevSecOps + engineering lead | `@your-org/devsecops`, `@your-org/engineering-leads` |
| Dependency manifests | DevSecOps | `@your-org/devsecops` |

Team membership is reviewed quarterly. To request a change to the approver directory, open a JIRA ticket of type `Process Change` and tag it with the label `codeowners-update`.

### Escalation Path

If you are blocked on review and cannot get a timely response:

1. Post in `#code-review` tagging your engineering lead.
2. Engineering lead may designate an alternate reviewer if the primary CODEOWNER is unavailable.
3. Alternate reviewer designation must be documented in the PR comments before the alternate submits their review.
4. For certification-sensitive paths (`src/safety/`, `src/actuators/`, etc.), only designated alternates from the safety engineering group may substitute — general engineering leads cannot substitute for safety reviewers.

---

## 8. Getting Help

| Question | Contact |
|---|---|
| JIRA workflow questions | Project manager or `#project-management` Slack |
| Branch protection / CI failures | `#devsecops` Slack |
| Review process questions | Engineering lead or `#engineering` Slack |
| Safety impact assessment | `@your-org/safety-engineers` or `#safety-engineering` Slack |
| Certification evidence questions | `@your-org/software-qa` or `#certification` Slack |
