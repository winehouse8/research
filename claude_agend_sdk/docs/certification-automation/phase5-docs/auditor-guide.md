# Auditor-Facing Evidence Guide

**System:** JIRA + GitHub CI/CD Software Certification Evidence Automation
**Document Version:** 1.0
**Date:** 2026-03-11
**Audience:** Auditors, Assessors, Regulatory Reviewers (non-technical)

---

## Introduction

### What This System Does

This system automatically collects and preserves evidence of software development activities to support certification audits. Every time a developer's code change is merged into the main codebase, the system captures a complete record of:

- Who made the change and when
- What the change was and why (linked to a requirement ticket)
- Who reviewed and approved the change
- Whether all automated tests passed before approval
- Whether the team followed every required development stage in order

The evidence is stored in a tamper-evident repository and is available for auditor inspection at any time, without requiring access to the engineering team's day-to-day tooling.

### Target Certification Standards

This evidence collection system is designed to support audits against the following standards:

| Standard | Domain | What It Governs |
|---|---|---|
| **IEC 62304** | Medical Device Software | Software development lifecycle for medical devices |
| **ISO 26262** | Automotive Functional Safety | Software development for safety-related automotive systems |
| **DO-178C** | Airborne Systems | Software considerations in airborne systems and equipment certification |

All three standards require documented evidence that software was developed using a controlled, traceable process. This system automates that documentation so that evidence is comprehensive, consistent, and available on demand.

### How Evidence Is Collected

Evidence collection is triggered automatically at each **code merge event** — the moment a developer's proposed change is accepted into the official codebase. No manual steps are required from the engineering team to generate evidence records. The process is:

1. A developer opens a Pull Request (PR) on GitHub to propose a code change.
2. The system checks that the PR is linked to an approved JIRA ticket (a requirement or task item).
3. The system checks that the JIRA ticket passed through every required workflow stage (e.g., "In Development" → "In Review" → "Approved") in the correct order, with no stages skipped.
4. Automated tests run and must pass.
5. One or more qualified reviewers approve the PR.
6. At the moment of merge, the system collects all of the above information and writes it into a structured, timestamped evidence record stored in the evidence repository.

---

## Evidence Repository Access

### Accessing the Evidence Repository

Evidence is stored in a secure object store (MinIO or AWS S3-compatible). Auditors can access the evidence repository through one of two methods:

**Method A: Web Browser (MinIO Console)**

1. Navigate to the evidence repository URL provided by your point of contact (e.g., `https://evidence.example.com`).
2. Log in with the auditor credentials provided in the audit engagement letter.
3. Select the bucket named `certification-evidence`.
4. Use the folder browser to navigate to the release package you wish to inspect.

**Method B: Direct File Download (AWS CLI or MinIO Client)**

If your technical contact has provided CLI credentials, you can list and download files using:

```
# List all releases
mc ls evidence-store/certification-evidence/

# Download a specific release package
mc cp --recursive evidence-store/certification-evidence/v2.4.1/ ./local-evidence-review/
```

**Method C: GitHub Releases (if configured)**

For projects that publish evidence alongside software releases, evidence packages are attached as assets to GitHub Releases. Navigate to the project's GitHub repository, click "Releases," and download the evidence package ZIP file from the relevant release.

### Directory Structure

Evidence is organized by project and release version. The top-level structure is:

```
certification-evidence/
  {project-key}/                    <- JIRA project key (e.g., MED, AUTO)
    {release-version}/              <- Software release version (e.g., v2.4.1)
      evidence-records/             <- One record per merged PR
        PR-{number}-evidence.json
        PR-{number}-evidence.json
        ...
      traceability-matrix.json      <- Links requirements to PRs and test results
      traceability-matrix.csv       <- Same content, spreadsheet-friendly format
      approval-ledger.json          <- All approval events with timestamps
      cicd-summary.json             <- CI/CD test run results for this release
      jira-workflow-history.json    <- JIRA ticket stage transitions for this release
      github-pr-records.json        <- GitHub PR metadata for this release
      integrity-manifest.sha256     <- SHA-256 hashes of all files in this package
      package-metadata.json         <- Release summary and collection timestamp
```

### Navigating to a Specific Release

To locate the evidence package for a specific software release:

1. Open the evidence repository (see access instructions above).
2. Enter the folder for the JIRA project key (your point of contact can confirm the key; for example, `MED` for a medical device project).
3. Enter the folder for the release version (for example, `v2.4.1`).
4. All evidence files for that release are contained within this folder.

If you are unsure which release version corresponds to the software version under audit, refer to the `package-metadata.json` file in each release folder. It contains the release version, the date evidence was collected, and a summary of how many PRs and requirements are covered.

### Verifying Evidence Integrity

Each evidence package includes a file named `integrity-manifest.sha256`. This file contains the SHA-256 cryptographic hash of every other file in the package. You can use this to verify that no file has been modified since it was collected.

**To verify integrity:**

**On Windows (PowerShell):**
```powershell
# Download the release folder to a local directory, then:
Get-FileHash .\PR-42-evidence.json -Algorithm SHA256
# Compare the output hash to the corresponding line in integrity-manifest.sha256
```

**On macOS or Linux:**
```bash
# From inside the downloaded release folder:
sha256sum -c integrity-manifest.sha256
# Output will show "OK" for each unmodified file, or "FAILED" for any modified file
```

**What to do if a hash fails:** A hash mismatch indicates a file was altered after evidence collection. This is a significant finding. Record it immediately and contact the system owner using the contact information in the FAQ section below. Do not proceed with that file until the discrepancy is explained.

---

## Evidence Package Contents

The following sections explain each evidence artifact in plain language, including what it proves and how to interpret it.

### 1. Evidence Records

**Files:** `evidence-records/PR-{number}-evidence.json` (one per merged code change)

**What they are:** Each evidence record is a structured document that captures the complete history of a single code change (Pull Request) from the moment it was proposed to the moment it was merged.

**What they prove:**

- **Who changed what code:** The record identifies the developer who authored the change, the files that were modified, and a summary of what changed.
- **When it happened:** Timestamps are recorded for every event: when the PR was opened, when each reviewer approved it, when tests ran, and when the merge occurred.
- **Who approved it:** Every approver is named with their GitHub username and the timestamp of their approval. For safety-critical changes, at least two approvers are required.
- **What requirement it fulfills:** The PR is linked to a JIRA ticket number. The evidence record captures the JIRA ticket ID, title, and status at the time of merge.

**How to read it:** The file is in JSON format. Key fields to review:

| Field | Meaning |
|---|---|
| `pr_number` | The GitHub PR number |
| `pr_title` | Brief description of the change |
| `author` | Developer who made the change |
| `merged_at` | Timestamp of merge (UTC) |
| `jira_ticket` | Linked JIRA requirement ticket |
| `reviewers` | List of approvers with timestamps |
| `ci_status` | Whether all automated tests passed (`passed` or `failed`) |
| `workflow_stages_verified` | Whether JIRA ticket passed all required stages (`true`/`false`) |

### 2. Traceability Matrix

**Files:** `traceability-matrix.json` and `traceability-matrix.csv`

**What it is:** A comprehensive table linking every software requirement to the code changes that implemented it and the tests that verified it.

**What it proves:** Every requirement in the project was:
- Implemented in code (there is at least one PR linked to it)
- Tested (there is at least one passing test run associated with it)
- Merged with proper authorization

The traceability matrix is the primary artifact for demonstrating requirements traceability, which is mandated by all three target standards (IEC 62304 Section 5.7, ISO 26262-6 Table 2, DO-178C Section 6.3).

**What to look for:** Open `traceability-matrix.csv` in a spreadsheet application for the easiest review. Each row is a requirement (JIRA ticket). Check:
- The `implementation_status` column: all rows should show `implemented`
- The `test_status` column: all rows should show `passed`
- The `pr_count` column: any requirement with `0` PRs was not implemented — this requires investigation
- The `coverage_gaps` column: any requirement listed here was identified by the system as potentially incomplete

### 3. Approval Ledger

**File:** `approval-ledger.json`

**What it is:** A chronological log of every approval event recorded during the release period, including the approver's identity, the PR they approved, and the exact timestamp.

**What it proves:**
- All approvals came from named, identifiable individuals (GitHub authenticated accounts)
- Approvals occurred before the merge — not retroactively
- The number of approvals per PR meets the required minimum (1 for standard changes, 2 for safety-critical changes)
- No PR was self-approved (a developer cannot approve their own change)

**What to look for:** For each entry, verify that `approved_at` timestamp is earlier than the corresponding PR's `merged_at` timestamp. Also verify that `approver` is different from the PR `author`.

### 4. CI/CD Summary

**File:** `cicd-summary.json`

**What it is:** A consolidated record of all automated test runs (Continuous Integration / Continuous Delivery pipeline executions) associated with the release.

**What it proves:** Every code change that was merged had a passing automated test suite at the time of merge. No code was merged while tests were failing. This demonstrates that the software meets its automated verification criteria before being accepted.

**What to look for:** Every entry should show `status: "passed"`. Any entry showing `status: "failed"` indicates a test was failing at the time of merge, which is a process violation requiring investigation. The system is configured to block merges when tests fail, so a "failed" entry in this record would indicate the control was bypassed.

**Key fields:**

| Field | Meaning |
|---|---|
| `run_id` | GitHub Actions workflow run identifier |
| `pr_number` | PR this test run is associated with |
| `triggered_at` | When the test run started |
| `completed_at` | When the test run finished |
| `status` | `passed` or `failed` |
| `test_suites` | Breakdown of individual test suite results |
| `total_tests` | Number of individual tests executed |
| `pass_rate` | Percentage of tests that passed |

### 5. JIRA Workflow History

**File:** `jira-workflow-history.json`

**What it is:** A record of every JIRA ticket's stage transitions during the release period. For each ticket, it shows every workflow stage it passed through, who moved it, and when.

**What it proves:** No development stage was skipped. Each ticket progressed through stages in the required order (for example: `Open` → `In Development` → `In Review` → `Approved` → `Closed`). The required stage sequence is enforced by both JIRA configuration and the automated PR validator. This file provides the audit trail showing that enforcement worked as intended.

**What to look for:**
- The `stages_completed` field for each ticket should list all required stages.
- The `out_of_order_transitions` field should be empty (`[]`) for all tickets.
- The `bypassed_stages` field should be empty for all tickets. Any non-empty value here represents a process deviation and requires an explanation.

### 6. GitHub PR Records

**File:** `github-pr-records.json`

**What it is:** A full export of GitHub Pull Request metadata for all PRs merged during the release period.

**What it proves:** Code was reviewed by qualified reviewers before being merged into the protected main branch. The PR record shows the complete review conversation, the list of requested reviewers, and which reviewers gave formal approval.

**What to look for:**
- `base_branch` should be `main` (or the configured protected branch) for all production-bound changes.
- `review_count` should be at least 1 (or 2 for safety-critical PRs).
- `merged_by` should be a different person from `author` (no self-merge).
- `jira_ticket_linked` should be `true` for all PRs. A value of `false` means the PR was merged without a linked requirement, which is a process violation.

---

## Verification Checklist for Auditors

Use this checklist when reviewing a release evidence package. Each item maps to a specific control that the system enforces. For each item, verify against the evidence files identified.

**Release under review:** ______________________
**Auditor:** ______________________
**Date of review:** ______________________

---

### Requirements Traceability

- [ ] **All requirements have corresponding JIRA tickets.**
  *Verify:* `traceability-matrix.csv` — no requirement rows with `pr_count = 0` unless formally deferred with documented justification.

- [ ] **All JIRA tickets are linked to at least one merged PR.**
  *Verify:* `traceability-matrix.csv` — `implementation_status` column shows `implemented` for all in-scope tickets.

---

### Workflow Compliance

- [ ] **All JIRA tickets passed through required workflow stages in the correct order.**
  *Verify:* `jira-workflow-history.json` — `out_of_order_transitions` and `bypassed_stages` are empty for all tickets.

- [ ] **No workflow stage bypasses are detected in the audit log.**
  *Verify:* `jira-workflow-history.json` — search for any `bypassed_stages` entries. If found, require a written deviation justification.

---

### Code Review and Approval

- [ ] **All code changes have at least 1 reviewer approval (standard changes).**
  *Verify:* `approval-ledger.json` — every PR entry has at least one approval record.

- [ ] **Safety-critical code changes have at least 2 independent reviewer approvals.**
  *Verify:* `approval-ledger.json` — PRs tagged as safety-critical show `review_count >= 2`.

- [ ] **No developer approved their own code change.**
  *Verify:* `approval-ledger.json` — `approver` field is never the same as the PR `author` field.

- [ ] **Approval timestamps precede merge timestamps.**
  *Verify:* Compare `approved_at` in `approval-ledger.json` to `merged_at` in `evidence-records/` — approvals must be earlier.

---

### Automated Testing

- [ ] **All CI tests passed before code was merged.**
  *Verify:* `cicd-summary.json` — all entries show `status: "passed"`. Any `"failed"` entry requires investigation.

- [ ] **Test results are associated with the correct PR.**
  *Verify:* Spot-check several entries in `cicd-summary.json` and confirm `pr_number` matches corresponding `evidence-records/` files.

---

### Evidence Integrity

- [ ] **Evidence records match JIRA and GitHub source data (spot-check procedure).**
  *Procedure:* Select 3–5 PRs at random. For each, open the corresponding `PR-{number}-evidence.json` and compare:
  - PR title and author against the GitHub PR (if GitHub access is available)
  - JIRA ticket number and status against the JIRA ticket (if JIRA access is available)
  - Reviewer names and timestamps against the approval ledger

- [ ] **All files in the evidence package pass SHA-256 integrity verification.**
  *Verify:* Run `sha256sum -c integrity-manifest.sha256` from inside the downloaded package. All files should report `OK`.

---

### Completeness

- [ ] **All merges within the release period have corresponding evidence records.**
  *Verify:* The count of files in `evidence-records/` should match the `total_prs_merged` field in `package-metadata.json`.

- [ ] **The evidence package covers the full release period.**
  *Verify:* `package-metadata.json` — confirm `period_start` and `period_end` dates bracket the release period under audit.

---

## Standard Clause Mapping Quick Reference

The following table maps each evidence artifact to the specific clauses it satisfies across the three target standards. Use this as a quick reference when preparing audit responses.

| Evidence Artifact | IEC 62304 Clause | ISO 26262-6 Clause | DO-178C Section |
|---|---|---|---|
| **Evidence Records** (PR audit trail) | 5.1.1, 5.5.1, 8.2.1 | 7.4.5, 7.4.6 | 6.3, 11.14 |
| **Traceability Matrix** | 5.1.1 (b), 5.7.3, 5.7.5 | 6.4.3, 7.4.3, Table 2 | 6.3.a, 6.3.b, 6.3.c |
| **Approval Ledger** | 5.1.9, 5.5.1, 8.2.4 | 7.4.5, 8.4.7 | 6.2.b, 7.2 |
| **CI/CD Summary** (test results) | 5.6.1, 5.6.4, 5.7.1 | 9.4.2, Table 7 | 6.4.b, 6.4.c |
| **JIRA Workflow History** | 5.1.9, 5.4.1, 6.1 | 7.4.4, 8.4.2 | 4.1, 6.2.a |
| **GitHub PR Records** (code review) | 5.5.2, 5.5.3, 5.6.4 | 7.4.5, 7.4.7 | 6.3.d, 7.1 |
| **Integrity Manifest** (SHA-256) | 8.1.2, 8.2.2 | 7.4.9 | 11.15 |

*Note: Clause numbers are provided as guidance and may require interpretation against the specific version of each standard applied to your audit. Consult your certification body for definitive clause applicability determinations.*

---

## Frequently Asked Questions

**Q: What if a developer bypassed the workflow?**

The system is designed with multiple independent controls to prevent workflow bypasses:

1. GitHub branch protection rules prevent any merge to the main branch without a passing CI run and at least one approval.
2. The JIRA ticket validator (a required GitHub Actions check) blocks the merge if the linked JIRA ticket has not completed all required workflow stages.
3. JIRA's own workflow configuration prevents tickets from being manually moved to a stage out of order.

If a bypass occurred despite these controls, it would require a deliberate circumvention of multiple independent mechanisms, which would itself be a significant audit finding. Any suspected bypass should appear in the `bypassed_stages` field of `jira-workflow-history.json` and must be explained by the system owner in writing.

If the system itself was reconfigured to disable controls, the configuration change would need to have been authorized, documented, and version-controlled. Request the GitHub Actions workflow configuration history and JIRA workflow configuration history for the period in question.

---

**Q: What if an evidence record is missing for a PR?**

Compare the count of evidence record files in `evidence-records/` to `total_prs_merged` in `package-metadata.json`. If these numbers differ, some PRs are missing evidence records. This is a process gap.

Possible causes include: a transient connectivity failure to the evidence store at the time of merge, or a failure in the evidence collection workflow. The system logs all evidence collection attempts; ask the system owner to provide the GitHub Actions workflow run logs for the release period to identify failed evidence collection attempts.

Missing evidence records for merged PRs is an audit finding unless the system owner can demonstrate that (a) the PR was captured in all other evidence files (approval ledger, CI/CD summary, traceability matrix) and (b) the evidence collection failure was detected and investigated at the time.

---

**Q: How do I verify that the electronic signatures and approvals are authentic?**

Approvals recorded in this system are GitHub Pull Request review approvals. GitHub authenticates each reviewer using their account credentials (password plus, typically, multi-factor authentication). The approval is recorded by GitHub's own infrastructure and is not modifiable after the fact.

To verify an approval is authentic:

1. Note the `approver` username and `approved_at` timestamp from `approval-ledger.json`.
2. If you have GitHub access, navigate to the PR and view the review history. The approval should appear there with a matching timestamp.
3. GitHub provides a tamper-evident audit log (GitHub Audit Log, available to organization administrators) that records all review events. Request the GitHub organization audit log export for the relevant period as additional corroboration.

For the highest assurance, the organization may also configure GitHub to require SAML SSO authentication, which ties GitHub identities to the organization's identity provider (e.g., Active Directory). Ask the system owner whether SAML SSO is enforced for this organization.

---

**Q: What is the retention period for this evidence?**

Evidence records are retained for a minimum of **10 years** from the date of collection, in accordance with typical regulatory requirements for safety-critical software. The specific retention policy applicable to your audit should be confirmed with the system owner, as it may be extended based on the product's expected service life or the requirements of the applicable regulatory body.

Evidence is stored in an object store with versioning enabled, meaning that no record can be silently overwritten or deleted without creating a version history. Deletion of records before the retention period expires requires explicit administrative action and is logged.

---

**Q: Who do I contact if I find a discrepancy?**

| Issue | Contact |
|---|---|
| Missing evidence records or integrity failures | Platform Engineering / DevOps team (primary point of contact from audit engagement letter) |
| Process deviation (bypassed stage, missing approval) | Quality Assurance / Regulatory Affairs team |
| Discrepancy between JIRA/GitHub data and evidence records | System owner (named in `package-metadata.json` under `system_owner`) |
| Access or credentials issues | IT Security / platform administrator |

All discrepancy reports should be made in writing and preserved as part of the audit record. The system owner is required to respond to discrepancy notices within the timeframe specified in the audit engagement terms.
