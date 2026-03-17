# Work Plan: JIRA + GitHub CI/CD Workflow Enforcement for Software Certification Evidence Automation

## Context

### Original Request
JIRA + GitHub CI/CD 워크플로우 강제화로 소프트웨어 인증 절차 증거 자동화 (Automating software certification evidence through JIRA + GitHub CI/CD workflow enforcement)

### Research Summary
Comprehensive research was conducted across the following areas:
- n8n workflow automation capabilities (webhooks, audit logs, self-hosting)
- JIRA native workflow enforcement (conditions, validators, status history)
- GitHub branch protection, rulesets, and Actions for compliance
- Certification standards: IEC 62304, ISO 26262, DO-178C
- Certification-specific ALM tools: Ketryx, Jama, Polarion, codebeamer, SpiraTest
- Orchestration tools: Temporal.io, Apache Airflow
- Low-code automation: Zapier, Make (Integromat)
- Direct API approach: JIRA REST API + GitHub API + GitHub Actions

### Standards Context
The plan targets evidence generation for safety-critical software standards:
- **IEC 62304**: Medical device software lifecycle
- **ISO 26262**: Automotive functional safety (ASIL levels)
- **DO-178C**: Airborne software assurance (DAL levels)
- Common thread: All require **bidirectional traceability**, **audit trails**, and **process enforcement evidence**

---

## Phase 0: Prerequisites and Environment Discovery (MANDATORY)

**This phase MUST be completed before any implementation begins.** The answers to this questionnaire determine which implementation path is used in every subsequent phase.

### 0.1 JIRA Deployment Model

Answer ONE of the following:

- [ ] **JIRA Cloud (Company-Managed Projects)**: Atlassian-hosted, company-managed projects with full workflow customization including conditions, validators, and post-functions via the workflow editor.
- [ ] **JIRA Cloud (Team-Managed Projects)**: Atlassian-hosted, team-managed projects with simplified workflow rules. **Limitation**: No native workflow validators or conditions. Enforcement must use JIRA Automation Rules or upgrade to company-managed.
- [ ] **JIRA Data Center**: Self-hosted JIRA with full workflow customization including classic workflow validators (status history checks are natively available). Supports ScriptRunner and other plugins without Marketplace approval delays.
- [ ] **JIRA Server (End of Life)**: If still running, migrate to Data Center or Cloud before proceeding.

**Impact on plan**:
| JIRA Model | Workflow Enforcement Method | Plugin Availability |
|---|---|---|
| Cloud (Company-Managed) | JIRA Automation Rules + webhook validation; native validators exist but "Status History" validator is NOT available natively -- requires ScriptRunner for JIRA Cloud or JMWE plugin | Requires Atlassian Marketplace approval process (can take days to weeks) |
| Cloud (Team-Managed) | JIRA Automation Rules only; no validators/conditions | Same as above; more limited even with plugins |
| Data Center | Native workflow validators including status history checks; ScriptRunner available without Marketplace approval | Install directly; no external approval |

### 0.2 GitHub Tier

Answer ONE of the following:

- [ ] **GitHub Free / Team**: Branch protection rules available. **Limitation**: Rulesets with full audit trail and bypass policies are NOT available. Fallback: use branch protection rules + required status checks (functional enforcement but weaker audit trail).
- [ ] **GitHub Enterprise Cloud**: Full Rulesets with audit trail, bypass policies, organization-level enforcement. Recommended for certification.
- [ ] **GitHub Enterprise Server**: Self-hosted, full Rulesets. Best for data sovereignty requirements.

**Impact on plan**:
| GitHub Tier | Enforcement Method | Audit Trail |
|---|---|---|
| Free / Team | Branch protection rules + required status checks | PR review logs only; no ruleset audit events |
| Enterprise Cloud | Organization-level Rulesets with no-bypass policies | Full audit trail via Rulesets API and audit log streaming |
| Enterprise Server | Same as Enterprise Cloud, self-hosted | Same, stored on-premise |

### 0.3 Existing Infrastructure Inventory

Check all that apply:

- [ ] **Kubernetes cluster** available for deploying n8n / webhook receivers
- [ ] **Docker host** available (if no Kubernetes)
- [ ] **Object storage** available (S3, MinIO, GCS, or equivalent) for evidence artifacts
- [ ] **CI runner capacity**: GitHub-hosted runners sufficient / Self-hosted runners available
- [ ] **DNS and TLS**: Can provision a public or internal HTTPS endpoint for webhook receivers

**Impact on plan**:
| Infrastructure | Deployment Path |
|---|---|
| Kubernetes available | Deploy n8n via Helm chart with HA; evidence storage via PVC or external S3 |
| Docker only | Deploy n8n via docker-compose; evidence storage via mounted volume or external S3 |
| No container infrastructure | Use GitHub Actions as sole integration platform; no n8n deployment |
| No object storage | Use GitHub Actions Artifacts for evidence (90-day default retention -- must configure longer retention or mirror to git-based evidence repo) |

### 0.4 Certification Scope for This Iteration

Select ONE primary target:

- [ ] **IEC 62304 only** (medical device software)
- [ ] **ISO 26262 only** (automotive functional safety)
- [ ] **DO-178C only** (airborne systems software)
- [ ] **Multiple standards** (specify which combination)

**Impact on plan**: Determines which clause-mapping tables are required in Phase 3 (Task 3.1) and the evidence schema fields. Selecting multiple standards increases Task 3.1 effort from 1 day to 2-3 days.

### 0.5 Integration Platform Decision

Based on infrastructure answers above, select ONE:

- [ ] **n8n Community Edition** (recommended if container infrastructure available): Visual orchestration, self-hosted, free. **Trade-off**: No built-in audit logs in CE -- evidence audit trail must come from GitHub Actions logs and JIRA audit logs instead.
- [ ] **n8n Enterprise Edition**: Adds audit logs, SSO, LDAP. **Trade-off**: Licensing cost (~$300/month).
- [ ] **Direct API (GitHub Actions + JIRA Automation Rules)**: Zero additional infrastructure. **Trade-off**: Higher development effort, distributed logic across multiple systems, harder to visualize full workflow.

See Section "Tool Comparison and Decision" below for detailed rationale.

---

## Work Objectives

### Core Objective
Build an automated system that:
1. **Enforces** JIRA workflow stages so they cannot be skipped (Review -> Approved -> Merged)
2. **Links** JIRA tickets to GitHub PRs/CI/CD pipelines bidirectionally
3. **Generates** certification-grade evidence artifacts (logs, approvals, traceability matrices)

### Deliverables
1. Research report with tool comparison and architecture recommendation
2. JIRA workflow configuration with enforced transitions
3. GitHub repository configuration (branch protection, rulesets, CODEOWNERS)
4. Integration layer connecting JIRA <-> GitHub (chosen approach)
5. Evidence generation pipeline (GitHub Actions + storage)
6. Traceability matrix auto-generation mechanism
7. Audit log aggregation and export system

### Definition of Done
- No JIRA ticket can reach "Merged" without passing through "Review" and "Approved"
- Every GitHub PR is linked to a JIRA ticket; PRs without tickets are blocked
- Every merge generates a timestamped evidence package (approvals, test results, review records)
- Traceability matrix can be exported on demand for any release
- Audit trail covers: who approved, when, what changed, test results, deployment status

---

## Tool Comparison and Decision

### Comparison Matrix

| Criterion | n8n (Self-hosted) | Direct API (JIRA + GitHub native) | Ketryx (JIRA Plugin) | Zapier/Make | Temporal.io |
|---|---|---|---|---|---|
| **JIRA Webhook Support** | Yes (native node) | Yes (JIRA Automation rules) | Yes (embedded in JIRA) | Yes | Custom code needed |
| **GitHub Webhook Support** | Yes (native node) | Yes (GitHub Actions) | Yes (CI/CD integration) | Yes | Custom code needed |
| **Workflow Gate Enforcement** | Orchestration only (cannot enforce JIRA gates directly) | JIRA validators + conditions enforce natively | Built-in compliance gates | No enforcement capability | Durable workflow states |
| **Audit Log Generation** | Enterprise edition; custom logging possible | GitHub Actions artifacts + JIRA audit log | Automatic Part 11 compliant trails | Limited | Complete event history |
| **Self-Hostable** | Yes (Community Edition free) | N/A (SaaS + self-managed options) | No (SaaS) | No | Yes |
| **Certification Awareness** | None | None | IEC 62304, ISO 14971, FDA 21 CFR Part 11 | None | None |
| **Traceability Matrix** | Must build custom | Must build custom | Auto-generated | Must build custom | Must build custom |
| **Setup Complexity** | Medium | Medium-High | Low | Low | High |
| **Ongoing Maintenance** | Medium | Medium | Low (vendor managed) | Low | High |
| **Cost** | Free (CE) / Enterprise paid | Free (built-in tools) | Per-user SaaS license | Per-operation pricing | Free (self-hosted) |
| **Vendor Lock-in Risk** | Low | None | Medium (Ketryx specific) | High | Low |
| **Flexibility** | High | Highest | Low (opinionated) | Medium | Highest |

### Recommended Architecture: Hybrid Approach

**Primary recommendation: n8n Community Edition for orchestration + JIRA Native enforcement + GitHub Native enforcement + GitHub Actions for evidence collection**

This is a committed recommendation (not an either/or). The roles are clearly separated:

| Component | Role | Why This Component |
|---|---|---|
| **JIRA (native)** | Workflow gate enforcement | Only JIRA can reliably block its own transitions |
| **GitHub (native)** | Branch/merge enforcement | Only GitHub can reliably block merges |
| **n8n CE** | Bidirectional sync orchestration | Visual workflows, self-hosted, webhook handling, event routing |
| **GitHub Actions** | Evidence collection and packaging | Runs at merge time, has full access to PR/CI data, produces immutable artifacts |

**Audit log strategy for n8n CE**: Since Community Edition does not include built-in audit logs, the evidence audit trail is constructed from:
1. GitHub Actions workflow run logs (immutable, timestamped)
2. JIRA audit log (native, available on all tiers)
3. n8n execution history (available in CE but not tamper-proof -- used for debugging, not as primary evidence)

**Alternative for medical device teams: JIRA Native + GitHub Native + Ketryx**
- If the target standard is IEC 62304 specifically, Ketryx provides out-of-the-box compliance
- Trade-off: Less flexibility, vendor dependency, but dramatically faster time-to-compliance

**Alternative if no container infrastructure: Direct API approach**
- Use JIRA Automation Rules for JIRA-side event handling
- Use GitHub Actions for GitHub-side event handling and evidence collection
- Use a lightweight Python/Node.js webhook receiver (deployed as a GitHub Actions self-hosted runner or serverless function) for cross-system sync
- Trade-off: More distributed logic, harder to visualize, but zero additional infrastructure

---

## Must Have / Must NOT Have (Guardrails)

### Must Have
- JIRA workflow enforcement that blocks skipping stages (method depends on JIRA deployment model -- see Phase 0 and Task 1.1)
- GitHub branch protection rules requiring: PR approval, status checks, linked JIRA ticket
- Bidirectional linking: JIRA ticket <-> GitHub PR (via commit message conventions or API)
- Evidence artifacts stored as immutable records (GitHub Actions artifacts or S3/MinIO)
- Timestamped approval records with user identity
- Traceability: Requirement -> Design -> Code -> Test -> Approval chain
- Automated evidence packaging per release/milestone

### Must NOT Have
- Manual evidence collection steps (defeats the purpose)
- Workflow bypasses for any role (admin override must also be logged if allowed)
- Evidence stored only in volatile locations (must be durable)
- Hard dependency on a single SaaS vendor for the core enforcement logic
- Hard dependency on a paid JIRA Marketplace plugin for core workflow enforcement (plugins may be used as enhancements, but primary enforcement must work without them)
- Over-engineering: Do not build a full ALM if existing tools suffice

---

## Task Flow and Dependencies

```
Phase 0: Prerequisites & Environment Discovery (MUST COMPLETE FIRST)
  |
  +-- Questionnaire: JIRA model, GitHub tier, infrastructure, certification scope, integration platform
  |
Phase 1: Foundation (JIRA + GitHub Native Configuration)
  |
  +-- Task 1.1: Design JIRA Workflow with Enforced Transitions
  |     (implementation path branches based on Phase 0 answers)
  +-- Task 1.2: Configure GitHub Branch Protection & Rulesets
  |     (implementation path branches based on GitHub tier)
  +-- Task 1.3: Establish Commit Message Convention (JIRA ticket linking)
  |
Phase 2: Integration Layer
  |
  +-- Task 2.0: [DECISION GATE] Confirm integration platform choice
  +-- Task 2.1: Deploy n8n CE Instance (if n8n chosen)
  |   OR Task 2.1-alt: Set up GitHub Actions webhook receiver (if direct API chosen)
  +-- Task 2.2: Build JIRA -> GitHub Sync Workflow
  +-- Task 2.3: Build GitHub -> JIRA Sync Workflow
  +-- Task 2.4: Implement PR-JIRA Ticket Validation Gate
  |
Phase 3: Evidence Generation Pipeline
  |
  +-- Task 3.1: Design Evidence Artifact Schema (with standard clause mappings)
  +-- Task 3.2: Build GitHub Actions for Evidence Collection
  +-- Task 3.3: Build Traceability Matrix Generator
  +-- Task 3.4: Build Approval Record Collector
  |
Phase 4: Storage and Export
  |
  +-- Task 4.1: Set Up Evidence Storage (artifact repository)
  +-- Task 4.2: Build Evidence Package Export (per release)
  +-- Task 4.3: Build Audit Log Aggregation Dashboard
  |
Phase 5: Validation and Documentation
  |
  +-- Task 5.1: End-to-End Testing with Sample Workflow
  +-- Task 5.2: Write Configuration Documentation
  +-- Task 5.3: Create Auditor-Facing Evidence Guide
```

---

## Detailed TODOs

### Phase 1: Foundation

#### Task 1.1: Design JIRA Workflow with Enforced Transitions

**Statuses**: `Open` -> `In Progress` -> `In Review` -> `Approved` -> `Merged` -> `Closed`

**Implementation Path A: JIRA Cloud (Company-Managed Projects)**

The "Status History" validator does NOT exist as a native JIRA Cloud feature. Use the following approach instead:

1. **Primary enforcement (no plugin required)**: Use JIRA Automation Rules to enforce transition ordering:
   - Rule: When issue transitions to `Approved`, check that the issue's status was previously `In Review`. If not, automatically transition the issue back and add a comment explaining the violation.
   - Rule: When issue transitions to `Merged`, check that the issue's status was previously `Approved`. If not, block by transitioning back.
   - Use workflow **conditions** (native in company-managed projects) to restrict which transitions are visible. For example, the transition to `Approved` only appears when current status is `In Review`.
   - Use workflow **validators** (native) to check for required fields: linked GitHub PR, approver group membership.

2. **Enhanced enforcement (plugin required)**: For true pre-transition validation (blocking the transition before it executes rather than rolling it back after):
   - **ScriptRunner for JIRA Cloud**: Provides custom validators that can check status history. Available on Atlassian Marketplace.
   - **JMWE (JIRA Misc Workflow Extensions)**: Provides additional validators and conditions. Available on Atlassian Marketplace.
   - **WARNING**: Marketplace plugin installation may require organizational approval. See Risk Assessment for timeline risk.

3. **Fallback if no plugin approved**: The Automation Rule approach (rollback-based enforcement) is functionally equivalent for certification purposes -- the JIRA audit log proves the rollback occurred and no stage was ultimately skipped. Document this in the auditor-facing evidence guide.

**Implementation Path B: JIRA Data Center**

Classic workflow validators are natively available:
1. Add **Status History Validator** on the transition to `Approved`: requires ticket to have been in `In Review` status.
2. Add **Status History Validator** on the transition to `Merged`: requires ticket to have been in `Approved` status.
3. Add **Permission Validator**: only members of the `jira-approvers` group can execute the `Approve` transition.
4. Add **Custom Validator** (via ScriptRunner, natively installable): check for linked GitHub PR before allowing transition to `In Review`.
5. No global transition arrows that skip stages.

**Implementation Path C: JIRA Cloud (Team-Managed Projects)**

Team-managed projects have severely limited workflow customization:
1. Workflow rules support only: "Restrict who can move an issue" and "Restrict transition" (limit which statuses can transition to which).
2. **Recommended**: Convert to company-managed project for this use case, OR use JIRA Automation Rules as the sole enforcement mechanism (same as Path A, primary enforcement).

**Acceptance Criteria (all paths)**:
- Workflow statuses defined: `Open` -> `In Progress` -> `In Review` -> `Approved` -> `Merged` -> `Closed`
- Stage skipping is prevented (via validators on DC, via automation rules + conditions on Cloud)
- `In Review` requires: linked GitHub PR exists
- `Approved` requires: at least one approver from designated approval group
- `Merged` requires: GitHub PR status is "merged" (webhook-triggered transition)
- No global transition arrows that skip stages
- Document the workflow diagram, all conditions/validators, and enforcement mechanism used
- Document which enforcement path was chosen and why

#### Task 1.2: Configure GitHub Branch Protection & Rulesets

**Implementation Path A: GitHub Enterprise (Cloud or Server)**
- Configure organization-level Rulesets for `main` and `release/*` branches
- Rulesets include: required reviews (2 for safety-critical), required status checks, no bypass list (or bypass with audit)
- Enable audit log streaming for ruleset events
- Configure CODEOWNERS for critical paths

**Implementation Path B: GitHub Free / Team**
- Configure repository-level branch protection rules for `main` and `release/*`
- Required: At least 1 approving review (consider 2 for safety-critical)
- Required: All CI status checks pass (build, test, lint, SAST)
- Required: CODEOWNERS review for critical paths (CODEOWNERS file works on all tiers)
- Required: Linear history (no merge commits that obscure audit trail)
- **Limitation**: No organization-level enforcement; repo admins can modify rules. Mitigate by restricting repo admin access and monitoring via GitHub audit log API.
- PR title/body must contain JIRA ticket ID (enforced via GitHub Action)

**Acceptance Criteria (all paths)**:
- Protected branches: `main`, `release/*`
- Required: At least 1 approving review (2 recommended for safety-critical)
- Required: All CI status checks pass
- Required: CODEOWNERS review for critical paths
- Required: Linear history
- PR title/body must contain JIRA ticket ID (enforced via GitHub Action)
- Document all protection rules and which tier-specific features are in use

#### Task 1.3: Establish Commit Message Convention
**Acceptance Criteria:**
- Convention defined: e.g., `[PROJ-123] Description of change`
- Pre-commit hook or GitHub Action validates commit message format
- JIRA ticket ID extracted and used for bidirectional linking
- Convention documented in CONTRIBUTING.md

### Phase 2: Integration Layer

#### Task 2.0: [DECISION GATE] Confirm Integration Platform
**Purpose**: Formally confirm the integration platform choice from Phase 0 before investing in deployment.

**Inputs**:
- Phase 0 answers (infrastructure availability, team capability)
- n8n CE audit log limitation awareness (evidence comes from GH Actions + JIRA logs, not n8n)

**Decision matrix**:
| Condition | Choose |
|---|---|
| Kubernetes or Docker available, want visual orchestration | **n8n CE** |
| Kubernetes or Docker available, need built-in audit logs | **n8n EE** (add ~$300/month to budget) |
| No container infrastructure, or strong GH Actions expertise | **Direct API** (GH Actions + JIRA Automation Rules + Python/Node.js webhook receiver) |

**Acceptance Criteria:**
- Integration platform formally chosen and documented
- If n8n CE: team acknowledges audit logs come from GH Actions + JIRA, not n8n
- If n8n EE: licensing cost approved
- If direct API: webhook receiver language (Python or Node.js) and hosting method (GH Actions self-hosted runner, serverless function, or dedicated VM) decided

#### Task 2.1: Deploy Integration Platform

**Path A: n8n CE (recommended)**
- Deploy n8n via Docker Compose or Helm chart (Kubernetes)
- Configure persistent storage for workflow data
- Configure authentication: JIRA API token, GitHub App (preferred over PAT for fine-grained permissions)
- Configure HTTPS endpoint for webhook reception
- Health monitoring: n8n health endpoint + external uptime check
- Backup: database backup schedule (PostgreSQL recommended for production)

**Path B: n8n EE**
- Same as Path A, plus:
- Configure SSO/LDAP integration
- Enable audit log feature
- Add n8n audit logs as an additional evidence source

**Path C: Direct API**
- Deploy webhook receiver application (Python FastAPI or Node.js Express)
- Hosting: GitHub Actions self-hosted runner, serverless function (AWS Lambda / GCP Cloud Functions), or dedicated VM
- Configure authentication: JIRA API token, GitHub App
- Configure HTTPS endpoint for webhook reception
- Implement structured logging (JSON format) to stdout/file for evidence trail
- Health monitoring: HTTP health endpoint + external uptime check

**Acceptance Criteria:**
- Integration platform deployed and accessible via HTTPS
- Authentication configured for both JIRA and GitHub APIs
- Health monitoring and alerting configured
- Backup and recovery plan documented

#### Task 2.2: Build JIRA -> GitHub Sync Workflow
**Acceptance Criteria:**
- When JIRA ticket moves to `In Review`: Verify linked PR exists, update PR label
- When JIRA ticket moves to `Approved`: Add approval status check to PR
- When JIRA ticket is rejected/returned: Add blocking label to PR
- All sync events logged with timestamps

#### Task 2.3: Build GitHub -> JIRA Sync Workflow
**Acceptance Criteria:**
- When PR is opened: Link to JIRA ticket, transition ticket to `In Review` (if allowed)
- When PR review is submitted: Update JIRA ticket with reviewer name and decision
- When PR is merged: Transition JIRA ticket to `Merged`
- When CI/CD passes/fails: Update JIRA ticket with build status
- All sync events logged with timestamps

#### Task 2.4: Implement PR-JIRA Ticket Validation Gate
**Acceptance Criteria:**
- GitHub Action or webhook validates every PR has a valid JIRA ticket ID
- Validates the JIRA ticket is in an appropriate state (not `Closed`, not `Open`)
- Reports validation status as a required check on the PR
- PRs without valid JIRA links cannot be merged

### Phase 3: Evidence Generation Pipeline

#### Task 3.1: Design Evidence Artifact Schema
**Effort estimate**: 1 day if targeting single standard (IEC 62304 only), 2-3 days if targeting multiple standards (IEC 62304 + ISO 26262 + DO-178C). See Phase 0 certification scope answer.

**Acceptance Criteria:**
- JSON/YAML schema defined for evidence records
- Schema covers: ticket ID, requirement links, code changes, test results, review approvals, timestamps, user identities
- Schema versioned and stored in repository
- Mapping document: schema fields -> certification standard clauses:
  - **IEC 62304**: Clause mapping table (see research report Section 9.5)
  - **ISO 26262 Part 6**: Clause mapping table for 6.4.6 through 6.4.11 (see research report Section 9.6)
  - **DO-178C**: Objective mapping table for Tables A-4, A-5, A-7 (see research report Section 9.7)
  - Only include mappings for standards selected in Phase 0

#### Task 3.2: Build GitHub Actions for Evidence Collection
**Acceptance Criteria:**
- On PR merge: Collect and package:
  - PR metadata (title, body, author, reviewers, approval timestamps)
  - Linked JIRA ticket snapshot (status, fields, comments)
  - CI/CD results (test reports, coverage, SAST findings)
  - Code diff summary
  - Commit history for the PR
- Store as GitHub Actions artifact (or upload to evidence store)
- Each evidence package is immutable and timestamped

#### Task 3.3: Build Traceability Matrix Generator
**Acceptance Criteria:**
- Script/action that queries JIRA and GitHub to build:
  - Requirement -> JIRA Ticket -> PR -> Commits -> Test Results -> Approval chain
- Output formats: CSV, JSON, and optionally PDF
- Can be run on-demand or triggered per release
- Covers bidirectional traceability (forward and backward)

#### Task 3.4: Build Approval Record Collector
**Acceptance Criteria:**
- Collects: Who approved (name, role), when (timestamp), what (PR/ticket), decision (approve/reject/request changes)
- Sources: GitHub PR reviews + JIRA ticket transitions
- Generates a consolidated approval ledger per release
- Includes electronic signature equivalent (authenticated user + timestamp)

### Phase 4: Storage and Export

#### Task 4.1: Set Up Evidence Storage
**Acceptance Criteria:**
- Durable storage configured (S3/MinIO bucket, or Git-based evidence repo)
- Retention policy defined (aligned with certification requirements, typically 10+ years)
- Access control configured (read-only for auditors)
- Integrity verification (checksums or signed artifacts)

#### Task 4.2: Build Evidence Package Export
**Acceptance Criteria:**
- Per-release evidence package containing:
  - All evidence records for included tickets/PRs
  - Traceability matrix
  - Approval ledger
  - CI/CD summary report
  - Configuration snapshot (tool versions, settings)
- Export format suitable for auditor consumption (ZIP with index)
- Automated generation triggered by release tag

#### Task 4.3: Build Audit Log Aggregation
**Acceptance Criteria:**
- Centralized view of all workflow events across JIRA and GitHub
- Searchable by: date range, user, ticket, PR, event type
- Dashboard or report format (can be simple log viewer or Grafana)
- Exportable for external audit

### Phase 5: Validation and Documentation

#### Task 5.1: End-to-End Testing
**Acceptance Criteria:**
- Test scenario: Create ticket -> develop -> PR -> review -> approve -> merge
- Verify: No stage can be skipped
- Verify: All evidence artifacts are generated correctly
- Verify: Traceability matrix is complete and accurate
- Verify: Approval records match actual approvals
- Test negative cases: attempt to skip stages, merge without approval, PR without ticket

#### Task 5.2: Configuration Documentation
**Acceptance Criteria:**
- All JIRA workflow configurations documented (screenshots + YAML/JSON export)
- All GitHub protection rules documented
- Integration layer architecture diagram
- Runbook for common operations (add new project, modify workflow, troubleshoot sync)

#### Task 5.3: Auditor-Facing Evidence Guide
**Acceptance Criteria:**
- Document explaining: what evidence is generated, where it is stored, how to access it
- Mapping: evidence artifacts -> certification standard clauses
- Sample evidence package walkthrough
- Written for non-technical auditor audience

---

## Commit Strategy

| Phase | Commits |
|-------|---------|
| Phase 1.1 | `feat: add JIRA workflow configuration with enforced transitions` |
| Phase 1.2 | `feat: configure GitHub branch protection and rulesets` |
| Phase 1.3 | `feat: establish commit message convention and validation` |
| Phase 2.0 | `docs: document integration platform decision` |
| Phase 2.1 | `feat: deploy integration platform (n8n CE / webhook receiver)` |
| Phase 2.2-2.3 | `feat: implement bidirectional JIRA-GitHub sync workflows` |
| Phase 2.4 | `feat: add PR-JIRA ticket validation gate` |
| Phase 3.1 | `feat: define evidence artifact schema with standard clause mappings` |
| Phase 3.2 | `feat: build GitHub Actions evidence collection pipeline` |
| Phase 3.3 | `feat: implement traceability matrix generator` |
| Phase 3.4 | `feat: build approval record collector` |
| Phase 4.1-4.2 | `feat: set up evidence storage and export system` |
| Phase 4.3 | `feat: build audit log aggregation` |
| Phase 5 | `docs: add configuration and auditor-facing documentation` |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **JIRA Marketplace plugin required for workflow enforcement on Cloud** | **High** (if on JIRA Cloud) | **High** (blocks Phase 1 workflow validator implementation) | Use JIRA Automation Rules as primary enforcement mechanism (rollback-based, no plugin needed). Automation rules + workflow conditions provide functional enforcement. ScriptRunner/JMWE plugin is an enhancement only, not a prerequisite. If plugin is desired, initiate Marketplace approval request in parallel with Phase 0 to reduce timeline impact. |
| **GitHub Enterprise tier required for Rulesets with full audit trail** | **Medium** | **Medium** (can still enforce merges, but weaker audit trail) | Document GitHub Free/Team fallback path: use repository-level branch protection rules + required status checks. Functional enforcement is equivalent. Audit trail gap mitigated by collecting PR review events via GitHub API in evidence collection pipeline (Task 3.2). For certification, the evidence package compensates for missing native ruleset audit events. |
| JIRA API rate limiting during high activity | Medium | Medium | Implement request batching and caching in n8n workflows |
| GitHub webhook delivery failures | Low | High | Implement retry logic; use GitHub webhook delivery logs for monitoring |
| Evidence storage corruption or loss | Low | Critical | Use checksums, redundant storage, and regular integrity verification |
| Workflow bypass via JIRA admin override | Medium | High | Log all admin actions; configure admin audit alerts; restrict admin access |
| n8n single point of failure | Medium | High | Deploy HA configuration; implement graceful degradation (JIRA/GitHub still enforce natively) |
| Sync delay causing inconsistent states | Medium | Medium | Implement eventual consistency with reconciliation jobs |
| Standard requirements change (IEC 62304 amendment) | Low | Medium | Design evidence schema to be extensible; map to standard clauses for easy adaptation |
| Team resistance to enforced workflow | High | Medium | Gradual rollout; training sessions; demonstrate audit time savings |
| False blocking (valid PRs blocked by sync issues) | Medium | High | Implement manual override with mandatory logging; SLA for integration issue resolution |
| **JIRA Marketplace plugin approval timeline** | **Medium** (if on Cloud and plugin desired) | **Medium** (delays enhanced enforcement but does not block primary enforcement) | Start approval process during Phase 0. Primary enforcement via Automation Rules does not require plugin. Plugin adds "nice-to-have" pre-transition blocking instead of post-transition rollback. |

---

## Success Criteria

1. **Enforcement**: 100% of merged PRs have passed through all JIRA workflow stages (verified by audit)
2. **Linkage**: 100% of merged PRs are linked to valid JIRA tickets
3. **Evidence**: Every merge produces a complete evidence package within 5 minutes
4. **Traceability**: On-demand traceability matrix generation completes within 10 minutes for up to 1000 tickets
5. **Audit readiness**: An auditor can independently navigate the evidence repository and verify any requirement's lifecycle
6. **Uptime**: Integration layer maintains 99.5% availability
7. **Recovery**: Evidence can be reconstructed from source systems (JIRA + GitHub) in case of integration layer failure

---

## Research Report

A detailed research report with full tool analysis, architecture diagrams, and implementation guidance has been saved to:
`/home/jovyan/deephunter-data-volumes/research/claude_agend_sdk/docs/260311_jira_github_cicd_certification_automation.md`
