# Research Report: JIRA + GitHub CI/CD Workflow Enforcement for Software Certification Evidence Automation

**Date**: 2026-03-11
**Author**: Prometheus (Strategic Planning Consultant)
**Status**: Complete

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement](#2-problem-statement)
3. [Certification Standards Overview](#3-certification-standards-overview)
4. [What "Enforcement" and "Evidence" Mean Concretely](#4-what-enforcement-and-evidence-mean-concretely)
5. [Tool-by-Tool Analysis](#5-tool-by-tool-analysis)
6. [Tool Comparison Matrix](#6-tool-comparison-matrix)
7. [Recommended Architecture](#7-recommended-architecture)
8. [Implementation Roadmap](#8-implementation-roadmap)
9. [Evidence Artifacts Specification](#9-evidence-artifacts-specification)
10. [Risk Assessment](#10-risk-assessment)
11. [Cost Analysis](#11-cost-analysis)
12. [Conclusion and Recommendations](#12-conclusion-and-recommendations)
13. [References](#13-references)

---

## 1. Executive Summary

This report evaluates approaches to automating software certification evidence through enforced JIRA + GitHub CI/CD workflows. The goal is to ensure that every software change follows a mandatory lifecycle (Review -> Approved -> Merged) with no stage skipping, and that each transition produces audit-grade evidence suitable for safety-critical certifications (IEC 62304, ISO 26262, DO-178C).

**Key Finding**: No single tool solves the entire problem. The optimal approach is a **hybrid architecture** combining:
- **JIRA native workflow enforcement** (validators, conditions, status history checks) for process gates
- **GitHub native features** (branch protection, rulesets, required checks, CODEOWNERS) for code-level enforcement
- **n8n** (self-hosted) or **direct API scripting** for bidirectional synchronization and evidence orchestration
- **GitHub Actions** for evidence artifact generation and packaging

For teams targeting IEC 62304 specifically, **Ketryx** offers a compelling shortcut as a JIRA plugin with built-in compliance awareness, though at the cost of vendor dependency.

---

## 2. Problem Statement

### The Challenge

Software teams working on safety-critical products must demonstrate to certification bodies that:
1. **Process was followed**: Every change went through defined lifecycle stages
2. **Nothing was skipped**: Mandatory review and approval steps cannot be bypassed
3. **Evidence exists**: Timestamped, immutable records prove each step occurred
4. **Traceability is complete**: Every requirement links forward to code, tests, and approvals; every code change links backward to a requirement

### Current Pain Points

| Pain Point | Impact |
|---|---|
| Manual evidence collection before audits | Weeks of preparation time; error-prone |
| Developers skipping workflow stages in JIRA | Audit findings; non-conformance |
| Disconnected JIRA and GitHub records | Broken traceability chains |
| No automated proof that reviews occurred | Auditors must manually verify |
| Traceability matrices built by hand in Excel | Out of date immediately; massive effort |

### Desired End State

A system where the act of doing development work (writing code, reviewing PRs, merging) **automatically produces** all certification evidence with zero additional manual effort from developers.

---

## 3. Certification Standards Overview

### IEC 62304 - Medical Device Software Lifecycle

IEC 62304 is the international standard for medical device software lifecycle processes. It classifies software into three safety classes:

| Class | Risk Level | Documentation Requirements |
|---|---|---|
| **Class A** | No injury possible | Minimal (development plan, requirements) |
| **Class B** | Non-serious injury possible | Moderate (architecture, verification) |
| **Class C** | Death or serious injury possible | Comprehensive (detailed design, unit testing, full traceability) |

**Key Requirements for Evidence**:
- Software Development Plan (SDP)
- Requirements Specification with traceability
- Architecture and detailed design documentation
- Verification and validation records
- Risk management file (ISO 14971 integration)
- Configuration management records
- Problem resolution records
- Change control records with audit trail

**Source**: [IEC 62304 & Requirements Traceability Matrix in Jira (Ketryx)](https://www.ketryx.com/blog/iec-62304-requirements-traceability-matrix-rtm-in-jira-a-guide-for-medical-device-companies)

### ISO 26262 - Automotive Functional Safety

ISO 26262 uses ASIL (Automotive Safety Integrity Level) classification:

| ASIL | Risk Level | Verification Rigor |
|---|---|---|
| **QM** | No safety relevance | Basic quality management |
| **ASIL A** | Low risk | Requirements-based testing |
| **ASIL B** | Medium risk | + Interface testing |
| **ASIL C** | High risk | + Fault injection testing |
| **ASIL D** | Highest risk | + Back-to-back testing, formal verification |

**Key Requirements for Evidence**:
- Bidirectional traceability: safety goals <-> requirements <-> design <-> code <-> tests
- Verification reports at every level
- Configuration management with baseline identification
- Change impact analysis records
- Tool qualification records (if tools are used in safety-relevant activities)

**Source**: [Requirements Traceability: ISO 26262 Software Compliance (Parasoft)](https://www.parasoft.com/learning-center/iso-26262/requirements-traceability/)

### DO-178C - Airborne Systems Software

DO-178C defines Design Assurance Levels (DAL):

| DAL | Failure Condition | Typical Application |
|---|---|---|
| **Level E** | No effect | Non-critical |
| **Level D** | Minor | Convenience functions |
| **Level C** | Major | Navigation displays |
| **Level B** | Hazardous | Flight management |
| **Level A** | Catastrophic | Flight control |

**Key Requirements for Evidence**:
- Plans (software development, verification, configuration management, quality assurance)
- Requirements (high-level and low-level) with full traceability
- Source code to requirements traceability
- Test cases to requirements traceability
- Test results and coverage analysis
- Problem reports and change records

**Source**: [DO-178C Certification (LDRA)](https://ldra.com/do-178/)

### Common Thread Across Standards

All three standards share these evidence requirements:

1. **Process definition**: Documented plans for how development will proceed
2. **Bidirectional traceability**: Requirements <-> Design <-> Code <-> Tests
3. **Change control**: Every change recorded with reason, approval, and impact
4. **Verification records**: Test results linked to requirements
5. **Approval records**: Who approved what, when, and on what basis
6. **Configuration management**: Baselines, versions, reproducibility

---

## 4. What "Enforcement" and "Evidence" Mean Concretely

### Enforcement: What It Means in Practice

"Enforcement" means the system **physically prevents** non-compliant actions, not merely warns about them.

| Enforcement Level | Description | Example | Certification Suitability |
|---|---|---|---|
| **Advisory** | Warns but allows bypass | Slack notification "you skipped review" | NOT suitable |
| **Soft gate** | Requires justification to bypass | JIRA popup asking for reason | Marginal |
| **Hard gate** | Cannot be bypassed by normal users | JIRA validator blocks transition | Suitable |
| **Immutable gate** | Cannot be bypassed by anyone including admins | GitHub ruleset with no bypass list | Best |

For certification, **hard gates** are the minimum. The system must be able to demonstrate to an auditor that it was **impossible** for a developer to skip the Review and Approval stages.

#### Concrete Enforcement Mechanisms

**In JIRA:**
- **Workflow Conditions**: Prevent transitions from appearing unless criteria are met (e.g., "only show 'Move to Approved' if current status is 'In Review'")
- **Workflow Validators**: Check criteria before executing a transition (e.g., "ticket must have a linked GitHub PR")
- **Status History Validators**: Ensure ticket has been in specific statuses before allowing transition (e.g., "must have been in 'In Review' before moving to 'Approved'")
- **Required Fields**: Force users to fill in approval fields during transitions
- **Permission Schemes**: Restrict who can perform certain transitions (e.g., only QA leads can approve)

**In GitHub:**
- **Branch Protection Rules**: Require PR reviews, status checks, and signed commits
- **Required Status Checks**: CI must pass before merge is allowed
- **CODEOWNERS**: Specific people must review changes to specific files
- **GitHub Rulesets** (newer): More granular control with audit trail and bypass policies
- **Required Reviewers**: Minimum number of approvals before merge

**Source**: [Configure Advanced Workflows (Atlassian)](https://support.atlassian.com/jira-cloud-administration/docs/configure-advanced-issue-workflows/), [About Protected Branches (GitHub)](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)

### Evidence: What It Means in Practice

"Evidence" means **timestamped, attributable, immutable records** that prove a process step occurred.

| Evidence Type | What It Proves | Source | Format |
|---|---|---|---|
| **JIRA transition log** | Workflow stages were followed in order | JIRA audit log | JSON/CSV |
| **PR review record** | Code was reviewed by qualified person | GitHub PR API | JSON |
| **CI/CD test results** | Tests passed before merge | GitHub Actions | JUnit XML, JSON |
| **Approval timestamp** | Authorized person approved at specific time | GitHub + JIRA | ISO 8601 timestamp |
| **Code diff** | Exact changes made | GitHub compare API | Unified diff |
| **Traceability link** | Requirement -> code -> test chain exists | JIRA + GitHub cross-references | Matrix (CSV/JSON) |
| **Commit signature** | Author identity verified | Git GPG/SSH signatures | Signature blob |
| **Build artifact attestation** | Binary matches source code | GitHub Artifact Attestations | In-toto/Sigstore |

#### Evidence Quality Requirements

For certification, evidence must be:
- **Authentic**: Cannot be fabricated after the fact
- **Complete**: Covers every required lifecycle activity
- **Accurate**: Reflects what actually happened
- **Available**: Retrievable when needed (retention period: typically 10+ years)
- **Traceable**: Links to the specific requirement, change, or activity it documents

---

## 5. Tool-by-Tool Analysis

### 5.1 n8n (Self-hosted Workflow Automation)

**What it is**: Open-source workflow automation platform with visual workflow builder. Self-hostable. 400+ integrations including native JIRA and GitHub nodes.

**Capabilities**:
- Native JIRA node: Create/update/transition issues, read issue data, respond to JIRA webhooks via Jira Trigger node
- Native GitHub node: Create/update PRs, read PR data, respond to GitHub webhooks
- Webhook node: Receive arbitrary webhooks from any source
- HTTP Request node: Call any REST API
- Workflow execution logging with history
- Conditional logic, loops, error handling, sub-workflows
- Human-in-the-loop approval nodes

**Strengths for this use case**:
- Self-hostable: Data stays on-premise (important for some certification regimes)
- Visual workflow design: Easy to document and explain to auditors
- Execution history: Built-in log of every workflow run
- Flexible: Can orchestrate complex multi-step processes
- Cost-effective: Community Edition is free; Enterprise adds audit logs and SSO

**Limitations**:
- Cannot enforce JIRA workflow gates directly (JIRA must enforce its own gates)
- Cannot enforce GitHub branch protection (GitHub must enforce its own rules)
- Audit logs in full form require Enterprise edition
- Not certification-aware: Does not understand IEC 62304 or ISO 26262 natively
- Single point of failure if not deployed in HA mode
- Fine-grained per-workflow access control is immature compared to enterprise tools

**Verdict**: Excellent as an **orchestration and evidence collection bridge**, but must not be relied upon as the enforcement mechanism. JIRA and GitHub must enforce their own gates natively.

**Sources**: [n8n JIRA Integration](https://n8n.io/integrations/jira-software/), [n8n GitHub Integration](https://n8n.io/integrations/github/and/jira-software/), [n8n Security Audit](https://docs.n8n.io/hosting/securing/security-audit/), [n8n Enterprise Governance](https://dev.to/alifar/n8n-at-scale-enterprise-governance-and-secure-automation-1jih)

### 5.2 Direct API Approach (JIRA Automation + GitHub Actions + Custom Scripts)

**What it is**: Using the built-in automation capabilities of JIRA and GitHub without an intermediary platform.

**Components**:
- **JIRA Automation Rules**: Built-in rule engine that triggers on issue events, can call webhooks, transition issues, and validate conditions
- **GitHub Actions**: CI/CD workflows that can run arbitrary scripts, call APIs, generate artifacts
- **GitHub Branch Protection / Rulesets**: Native enforcement of merge requirements
- **JIRA Workflow Configuration**: Native validators, conditions, and post-functions
- **Custom Scripts**: Python/Node.js scripts for evidence collection and traceability matrix generation

**Strengths**:
- Zero additional infrastructure: Uses existing JIRA and GitHub capabilities
- No vendor lock-in: Standard APIs and configurations
- Maximum flexibility: Full programmatic control
- Well-documented: Both JIRA and GitHub have extensive API documentation
- Native enforcement: JIRA validators and GitHub branch protection are the most reliable enforcement mechanisms

**Limitations**:
- Higher development effort: Must write and maintain custom integration code
- Distributed logic: Business logic spread across JIRA Automation rules, GitHub Actions workflows, and custom scripts
- Harder to visualize: No single dashboard showing the complete workflow
- Monitoring requires custom setup: No built-in orchestration health monitoring
- JIRA Automation rules have limitations on complexity and external API calls

**Verdict**: The most flexible and vendor-independent approach, but requires more upfront development and ongoing maintenance. Best for teams with strong DevOps capabilities.

**Sources**: [JIRA Automation Triggers (Atlassian)](https://support.atlassian.com/cloud-automation/docs/jira-automation-triggers/), [GitHub Actions for Compliance (GitHub Blog)](https://github.blog/enterprise-software/github-actions-for-security-compliance/), [GitHub Artifact Attestations (GitHub Blog)](https://github.blog/changelog/2025-02-18-recent-improvements-to-artifact-attestations/)

### 5.3 Ketryx (JIRA Plugin for Medical Device Compliance)

**What it is**: A SaaS platform that integrates directly into JIRA to provide IEC 62304 / FDA 21 CFR Part 11 compliance capabilities. Available on Atlassian Marketplace.

**Capabilities**:
- Embeds directly in JIRA as a plugin
- Automatic traceability matrix generation (requirements -> design -> code -> tests)
- Part 11 compliant audit trail (every change logged with user, timestamp, reason)
- Auto-generated documents: Software Development Plan, Architecture Document, Traceability Matrix
- Risk management integration (ISO 14971)
- GitHub/GitLab CI/CD integration for pulling build and test results
- Release evidence packaging

**Strengths**:
- Purpose-built for medical device software certification
- Minimal setup: Plugin install + configuration
- Auditor-ready output: Documents formatted for regulatory submission
- Continuous compliance: Validates compliance state in real-time
- Understands IEC 62304 clauses natively

**Limitations**:
- SaaS only: Data leaves your infrastructure
- Medical-device focused: May not map well to ISO 26262 or DO-178C without customization
- Vendor dependency: Core compliance logic is in Ketryx's proprietary system
- Cost: Per-user SaaS pricing (not publicly listed; enterprise sales)
- Less flexible: Opinionated about workflow structure
- Only works with JIRA (not compatible with other issue trackers)

**Verdict**: The fastest path to IEC 62304 compliance if using JIRA + GitHub. Not suitable if the certification target is automotive (ISO 26262) or aerospace (DO-178C), or if data sovereignty requires on-premise solutions.

**Sources**: [Ketryx JIRA Connector](https://www.ketryx.com/use-case/jira-connector), [Ketryx on Atlassian Marketplace](https://marketplace.atlassian.com/apps/1228398/ketryx-connector-for-jira), [Ketryx for Developers](https://www.ketryx.com/function/developer)

### 5.4 Zapier / Make (Integromat)

**What it is**: Cloud-based low-code automation platforms with thousands of app integrations.

**Zapier**: 8,000+ integrations, simple linear workflow model ("Zaps"), per-task pricing.
**Make**: ~2,000 integrations, visual canvas with branching logic, per-operation pricing (cheaper at scale).

**Strengths**:
- Very fast to set up simple integrations
- Large integration library
- No infrastructure to manage

**Limitations**:
- **Cloud-only**: Data flows through third-party servers (compliance risk)
- **No enforcement capability**: Can react to events but cannot block JIRA transitions or GitHub merges
- **Limited audit trail**: Execution logs exist but are not designed for certification evidence
- **Per-operation pricing**: Can become expensive at scale
- **Rate limiting**: Both platforms have rate limits that may affect real-time sync
- **Not designed for compliance**: No understanding of certification standards

**Verdict**: **Not recommended** for this use case. Zapier and Make are excellent for simple notifications and data sync, but they cannot enforce workflow gates, their audit trails are insufficient for certification, and cloud-only operation may violate data sovereignty requirements.

**Sources**: [n8n vs Make vs Zapier Comparison (Digidop)](https://www.digidop.com/blog/n8n-vs-make-vs-zapier)

### 5.5 Temporal.io

**What it is**: Open-source durable workflow execution platform. Treats workflows as persistent, stateful functions with complete event history.

**Strengths**:
- **Complete event history**: Every workflow step is recorded and replayable
- Durable execution: Workflows survive process crashes and infrastructure failures
- Self-hostable: Full control over data
- Multi-language SDKs: Go, Java, Python, TypeScript, .NET
- Built-in retries, timeouts, and error handling

**Limitations**:
- **No native JIRA or GitHub integrations**: Must write all integration code manually
- **High complexity**: Requires significant development effort to build and maintain
- **Overkill for this use case**: Designed for distributed microservice orchestration, not dev tool integration
- **No certification awareness**: Must build all compliance logic from scratch
- **Operational overhead**: Requires running Temporal server cluster

**Verdict**: **Not recommended** unless the team is already using Temporal for other purposes. The development effort to build JIRA+GitHub integrations from scratch in Temporal far exceeds the benefit of its durable execution model for this use case.

**Sources**: [Temporal vs Airflow (ZenML)](https://www.zenml.io/blog/temporal-vs-airflow), [Top Open Source Workflow Orchestration Tools (Bytebase)](https://www.bytebase.com/blog/top-open-source-workflow-orchestration-tools/)

### 5.6 Certification-Specific ALM Tools (Jama, Polarion, codebeamer, SpiraTest)

**What they are**: Full Application Lifecycle Management platforms designed specifically for safety-critical industries.

| Tool | Vendor | Primary Industry | JIRA Integration | GitHub Integration |
|---|---|---|---|---|
| **Jama Connect** | Jama Software | Medical, Automotive, Aerospace | Yes (bidirectional sync) | Limited |
| **Polarion** | Siemens | Automotive, Industrial | Via connectors | Via connectors |
| **codebeamer** | PTC | Automotive, Medical, Aerospace | Yes (built-in) | Yes (built-in) |
| **SpiraTest** | Inflectra | General ALM | Via plugins | Via plugins |

**Strengths**:
- Purpose-built for certification with pre-configured templates
- Native traceability matrix generation
- Built-in risk management (ISO 14971, ISO 26262 Part 6)
- Audit trail designed for regulatory submission
- Support for multiple standards simultaneously

**Limitations**:
- **Expensive**: Enterprise licensing, often six-figure annual costs
- **Heavy**: Full ALM replacement, not a supplement to existing JIRA+GitHub workflow
- **Migration effort**: Requires moving from JIRA to the ALM tool (or maintaining both)
- **Learning curve**: Teams must learn a new platform
- **Overkill**: If JIRA+GitHub already works well, adding a full ALM creates friction

**Verdict**: Consider these tools only if:
- The organization is starting fresh without JIRA (greenfield)
- The certification level is high (ASIL D, DAL A, Class C) and requires tool qualification
- Budget allows six-figure annual ALM licensing
- The team is willing to migrate away from JIRA

For teams committed to JIRA + GitHub, these tools are **not recommended** as the primary platform, though they may be valuable as supplementary tools for traceability matrix visualization.

**Sources**: [Jama Connect JIRA Integration](https://www.jamasoftware.com/datasheet/jama-connect-integration-jira-datasheet/), [codebeamer vs Polarion (SPK)](https://www.spkaa.com/blog/choosing-the-right-alm-solution-codebeamer-vs-polarion)

### 5.7 LDRA + Parasoft (Verification Tool Chains with JIRA Integration)

**What they are**: Software verification and testing tool chains specifically designed for safety-critical standards.

- **LDRA**: Provides the TBmanager Integration Package for Jira, delivering bidirectional end-to-end traceability from JIRA issues to requirements, design, code, and testing
- **Parasoft**: Integrates with JIRA, Jama, Polarion, codebeamer for bidirectional traceability from work items to test cases and results

**Verdict**: These are complementary tools for the verification layer. They do not replace the workflow enforcement or evidence generation pipeline but can enhance the traceability chain, especially for code coverage and static analysis evidence. Consider them for Phase 3 enhancements.

**Sources**: [LDRA Jira Integration (BusinessWire)](https://www.businesswire.com/news/home/20200224005258/en/LDRA-Optimizes-Agile-Development-and-Verification-of-Critical-Embedded-Applications-with-New-Jira-Software-Integration), [Parasoft ISO 26262 Requirements Traceability](https://www.parasoft.com/learning-center/iso-26262/requirements-traceability/)

---

## 6. Tool Comparison Matrix

### Overall Suitability Scorecard

| Criterion (Weight) | n8n | Direct API | Ketryx | Zapier/Make | Temporal | Full ALM |
|---|---|---|---|---|---|---|
| **Workflow Enforcement** (25%) | 2/5 (orchestrates, cannot enforce) | 5/5 (native JIRA+GitHub gates) | 4/5 (plugin-level) | 1/5 (no enforcement) | 3/5 (durable states) | 5/5 (native) |
| **Evidence Generation** (25%) | 4/5 (custom workflows) | 4/5 (GitHub Actions) | 5/5 (auto-generated) | 2/5 (basic logs) | 4/5 (event history) | 5/5 (native) |
| **Traceability** (20%) | 3/5 (must build) | 3/5 (must build) | 5/5 (automatic) | 1/5 (not designed for this) | 2/5 (must build) | 5/5 (native) |
| **Setup Effort** (10%) | 3/5 (moderate) | 2/5 (high) | 5/5 (plugin install) | 4/5 (easy) | 1/5 (very high) | 2/5 (migration) |
| **Flexibility** (10%) | 5/5 (visual + code) | 5/5 (full control) | 2/5 (opinionated) | 3/5 (limited branching) | 5/5 (full code) | 3/5 (within ALM) |
| **Cost** (10%) | 5/5 (free CE) | 5/5 (free) | 2/5 (SaaS pricing) | 3/5 (per-operation) | 4/5 (free self-host) | 1/5 (expensive) |
| **Weighted Total** | **3.3** | **3.9** | **4.0** | **1.9** | **2.8** | **3.8** |

### Recommendation by Scenario

| Scenario | Recommended Approach |
|---|---|
| IEC 62304 (medical device), JIRA Cloud, budget available | **Ketryx** + GitHub branch protection |
| ISO 26262 / DO-178C, JIRA + GitHub, DevOps team available | **Direct API** (JIRA native + GitHub native + GitHub Actions) |
| Any standard, want visual orchestration and self-hosting | **n8n** + JIRA native enforcement + GitHub native enforcement |
| Any standard, maximum flexibility, strong engineering team | **Direct API** with n8n for monitoring/dashboarding |
| Greenfield, no existing JIRA, high ASIL/DAL | **Full ALM** (codebeamer or Jama Connect) |

---

## 7. Recommended Architecture

### Primary Recommendation: Hybrid (JIRA Native + GitHub Native + n8n)

```
+-------------------+     Webhooks      +-------------------+
|                   |  <--------------> |                   |
|   JIRA Cloud/DC   |                   |   n8n (Self-     |
|                   |  REST API calls   |   hosted)         |
|  - Workflow with  |  <--------------> |                   |
|    validators     |                   |  - Sync workflows |
|  - Status history |                   |  - Evidence       |
|    enforcement    |                   |    collection     |
|  - Transition     |                   |  - Traceability   |
|    conditions     |                   |    matrix gen     |
|  - Audit log      |                   |  - Monitoring     |
|                   |                   |                   |
+-------------------+                   +-------------------+
                                              |       |
                                              |       |
+-------------------+     Webhooks      +-----+       +------+
|                   |  <--------------> |                    |
|   GitHub          |                   |  Evidence Store    |
|                   |  REST API calls   |  (S3/MinIO/Git)    |
|  - Branch         |  <------------    |                    |
|    protection     |                   |  - Evidence JSON   |
|  - Required       |                   |  - Traceability    |
|    status checks  |                   |    matrices        |
|  - CODEOWNERS     |                   |  - Approval        |
|  - GitHub Actions |                   |    ledgers         |
|    (CI/CD +       |                   |  - Release         |
|     evidence)     |                   |    packages        |
|  - Rulesets       |                   |                    |
|                   |                   +--------------------+
+-------------------+
```

### Data Flow: Happy Path

```
1. Developer creates JIRA ticket (status: Open)
   -> JIRA enforces: required fields filled

2. Developer starts work (status: In Progress)
   -> JIRA enforces: must be from Open status
   -> Developer creates branch with JIRA ticket ID

3. Developer opens PR in GitHub
   -> GitHub Action: validates PR title contains JIRA ticket ID
   -> GitHub Action: sets status check "jira-linked" to pass/fail
   -> n8n webhook: receives GitHub PR event
   -> n8n: calls JIRA API to transition ticket to "In Review"
   -> n8n: logs sync event to evidence store

4. Reviewer reviews PR
   -> GitHub: requires minimum approvals per branch protection
   -> GitHub: requires CODEOWNERS review for critical files
   -> n8n webhook: receives GitHub review event
   -> n8n: updates JIRA ticket with reviewer info
   -> n8n: logs review event to evidence store

5. QA/Lead approves in JIRA (status: Approved)
   -> JIRA enforces: status must have been "In Review" (status history validator)
   -> JIRA enforces: only approval-group members can transition
   -> n8n webhook: receives JIRA transition event
   -> n8n: adds "jira-approved" status check to GitHub PR
   -> n8n: logs approval event to evidence store

6. PR is merged
   -> GitHub enforces: all status checks pass (CI + jira-linked + jira-approved)
   -> GitHub enforces: required reviewers approved
   -> GitHub Action: generates evidence package
     - PR metadata, review records, CI results, code diff
     - JIRA ticket snapshot (via API call)
     - Traceability record (requirement -> ticket -> PR -> tests)
   -> GitHub Action: uploads evidence to evidence store
   -> n8n webhook: receives merge event
   -> n8n: transitions JIRA ticket to "Merged"
   -> n8n: logs merge event to evidence store

7. Release created
   -> GitHub Action: aggregates all evidence for release
   -> GitHub Action: generates traceability matrix
   -> GitHub Action: generates approval ledger
   -> GitHub Action: packages everything into release evidence bundle
   -> Evidence bundle stored in evidence store with release tag
```

### Enforcement Points Summary

| Gate | Enforced By | Mechanism | Bypass Possible? |
|---|---|---|---|
| JIRA: Cannot skip to "Approved" without "In Review" | JIRA Workflow | Status History Validator | No (unless admin modifies workflow) |
| JIRA: Only QA leads can approve | JIRA Workflow | Transition Condition (group membership) | No (unless group is modified) |
| GitHub: PR must have JIRA ticket | GitHub Actions | Required status check "jira-linked" | No (branch protection) |
| GitHub: PR must have JIRA approval | n8n -> GitHub | Required status check "jira-approved" | No (branch protection) |
| GitHub: CI must pass | GitHub Actions | Required status check "ci-pass" | No (branch protection) |
| GitHub: Code review required | GitHub | Branch protection (required reviews) | No (unless rule is modified) |
| GitHub: CODEOWNERS must review | GitHub | CODEOWNERS + branch protection | No (unless CODEOWNERS is modified) |

---

## 8. Implementation Roadmap

### Phase 1: Foundation (Week 1-2)

| Task | Description | Effort |
|---|---|---|
| 1.1 Design JIRA Workflow | Define statuses, transitions, validators, conditions | 2 days |
| 1.2 Configure GitHub Branch Protection | Set up rules for main and release branches | 1 day |
| 1.3 Define Commit Convention | JIRA ticket ID format, pre-commit hooks | 0.5 days |
| 1.4 Test Enforcement | Verify stages cannot be skipped in both systems | 1 day |

### Phase 2: Integration (Week 2-3)

| Task | Description | Effort |
|---|---|---|
| 2.1 Deploy n8n | Docker/K8s deployment with persistence | 1 day |
| 2.2 JIRA -> GitHub Sync | Webhook handlers for JIRA transitions | 2 days |
| 2.3 GitHub -> JIRA Sync | Webhook handlers for PR events | 2 days |
| 2.4 PR-JIRA Validation Gate | GitHub Action for JIRA ticket validation | 1 day |
| 2.5 Integration Testing | End-to-end sync verification | 1 day |

### Phase 3: Evidence Pipeline (Week 3-5)

| Task | Description | Effort |
|---|---|---|
| 3.1 Evidence Schema Design | JSON schema for evidence records | 1 day |
| 3.2 Evidence Collection Actions | GitHub Actions for PR merge evidence | 3 days |
| 3.3 Traceability Matrix Generator | Script querying JIRA + GitHub APIs | 3 days |
| 3.4 Approval Record Collector | Consolidated approval ledger generator | 2 days |
| 3.5 Evidence Storage Setup | S3/MinIO bucket with access control | 1 day |

### Phase 4: Export and Dashboarding (Week 5-6)

| Task | Description | Effort |
|---|---|---|
| 4.1 Release Evidence Packaging | Automated evidence bundle on release tag | 2 days |
| 4.2 Audit Log Aggregation | Centralized log viewer/exporter | 2 days |
| 4.3 Dashboard | Compliance status overview (optional) | 2 days |

### Phase 5: Validation and Documentation (Week 6-7)

| Task | Description | Effort |
|---|---|---|
| 5.1 End-to-End Validation | Full scenario testing including negative cases | 2 days |
| 5.2 Configuration Documentation | All settings documented for reproducibility | 2 days |
| 5.3 Auditor Evidence Guide | Non-technical guide for auditors | 1 day |

**Total Estimated Effort**: 28-30 person-days (approximately 6-7 weeks with one engineer)

---

## 9. Evidence Artifacts Specification

### 9.1 Per-PR Evidence Record

```json
{
  "schema_version": "1.0",
  "evidence_type": "pr_merge",
  "timestamp": "2026-03-11T14:30:00Z",
  "pr": {
    "number": 42,
    "title": "[PROJ-123] Implement input validation",
    "author": "developer@company.com",
    "branch": "feature/PROJ-123-input-validation",
    "base_branch": "main",
    "created_at": "2026-03-08T09:00:00Z",
    "merged_at": "2026-03-11T14:30:00Z",
    "merge_commit_sha": "abc123def456",
    "files_changed": 5,
    "additions": 120,
    "deletions": 30
  },
  "jira_ticket": {
    "key": "PROJ-123",
    "summary": "Implement input validation for patient data entry",
    "type": "Story",
    "priority": "High",
    "requirement_links": ["REQ-045", "REQ-046"],
    "status_history": [
      {"status": "Open", "timestamp": "2026-03-07T10:00:00Z", "user": "pm@company.com"},
      {"status": "In Progress", "timestamp": "2026-03-08T08:00:00Z", "user": "developer@company.com"},
      {"status": "In Review", "timestamp": "2026-03-09T16:00:00Z", "user": "developer@company.com"},
      {"status": "Approved", "timestamp": "2026-03-11T11:00:00Z", "user": "qa-lead@company.com"},
      {"status": "Merged", "timestamp": "2026-03-11T14:30:00Z", "user": "automation"}
    ]
  },
  "reviews": [
    {
      "reviewer": "senior-dev@company.com",
      "decision": "APPROVED",
      "timestamp": "2026-03-10T15:00:00Z",
      "body": "Code looks good. Input validation covers all edge cases."
    },
    {
      "reviewer": "qa-lead@company.com",
      "decision": "APPROVED",
      "timestamp": "2026-03-11T10:00:00Z",
      "body": "Verified against REQ-045 and REQ-046. All acceptance criteria met."
    }
  ],
  "ci_results": {
    "build": {"status": "success", "duration_seconds": 120},
    "unit_tests": {"status": "success", "passed": 45, "failed": 0, "skipped": 0, "coverage": "87%"},
    "integration_tests": {"status": "success", "passed": 12, "failed": 0},
    "sast": {"status": "success", "findings": 0},
    "lint": {"status": "success", "warnings": 2}
  },
  "traceability": {
    "requirements": ["REQ-045", "REQ-046"],
    "design_elements": ["DESIGN-012"],
    "test_cases": ["TC-078", "TC-079", "TC-080"],
    "risk_items": ["RISK-015"]
  }
}
```

### 9.2 Traceability Matrix (per release)

| Requirement | JIRA Ticket | Design Element | PR(s) | Test Cases | Test Result | Approval | Status |
|---|---|---|---|---|---|---|---|
| REQ-045 | PROJ-123 | DESIGN-012 | PR #42 | TC-078, TC-079 | PASS | qa-lead (2026-03-11) | Complete |
| REQ-046 | PROJ-123 | DESIGN-012 | PR #42 | TC-080 | PASS | qa-lead (2026-03-11) | Complete |
| REQ-047 | PROJ-125 | DESIGN-013 | PR #44 | TC-081, TC-082 | PASS | qa-lead (2026-03-12) | Complete |

### 9.3 Approval Ledger (per release)

| Ticket | PR | Approver | Role | Decision | Timestamp | Evidence Link |
|---|---|---|---|---|---|---|
| PROJ-123 | PR #42 | senior-dev@company.com | Code Reviewer | APPROVED | 2026-03-10T15:00:00Z | /evidence/pr-42/reviews.json |
| PROJ-123 | PR #42 | qa-lead@company.com | QA Approver | APPROVED | 2026-03-11T10:00:00Z | /evidence/pr-42/reviews.json |
| PROJ-123 | JIRA | qa-lead@company.com | JIRA Approver | Approved -> Merged | 2026-03-11T11:00:00Z | /evidence/PROJ-123/transitions.json |

### 9.4 Release Evidence Package Structure

```
release-v1.2.0-evidence/
  index.json                         # Package manifest
  traceability-matrix.csv            # Full traceability matrix
  traceability-matrix.json           # Machine-readable version
  approval-ledger.csv                # All approvals for this release
  approval-ledger.json               # Machine-readable version
  ci-summary.json                    # Aggregated CI/CD results
  configuration-snapshot.json        # Tool versions, settings
  per-ticket/
    PROJ-123/
      evidence-record.json           # Full evidence record (see 9.1)
      jira-snapshot.json             # JIRA ticket state at merge time
      pr-42-metadata.json            # PR details
      pr-42-reviews.json             # Review records
      pr-42-ci-results.json          # CI/CD results
      pr-42-diff.patch               # Code changes
    PROJ-125/
      ...
  standard-mapping/
    iec-62304-clause-mapping.json    # Which evidence covers which IEC 62304 clause (see Section 9.5)
    iso-26262-part6-clause-mapping.json  # Which evidence covers which ISO 26262 Part 6 clause (see Section 9.6)
    do-178c-objective-mapping.json   # Which evidence covers which DO-178C objective (see Section 9.7)
```

### 9.5 Standard Clause Mapping (IEC 62304)

| IEC 62304 Clause | Required Evidence | Generated By | Location in Evidence Package |
|---|---|---|---|
| 5.1 Software Development Planning | Development plan, workflow definition | Manual + JIRA workflow export | /configuration-snapshot.json |
| 5.2 Software Requirements Analysis | Requirements with traceability | JIRA tickets (type=Requirement) | /traceability-matrix.csv |
| 5.3 Software Architectural Design | Architecture linked to requirements | JIRA tickets (type=Design) | /per-ticket/*/jira-snapshot.json |
| 5.5 Software Integration and Testing | Test results linked to requirements | GitHub Actions CI results | /per-ticket/*/pr-*-ci-results.json |
| 5.7 Software Release | Release evidence package | GitHub Actions on release tag | /index.json (this package) |
| 5.8 Software Maintenance | Change records with approval | JIRA transitions + PR reviews | /per-ticket/*/evidence-record.json |
| 8 Software Configuration Management | Version control records | Git history + JIRA audit log | /configuration-snapshot.json |
| 9 Software Problem Resolution | Problem reports and resolution | JIRA tickets (type=Bug) | /per-ticket/*/jira-snapshot.json |

### 9.6 Standard Clause Mapping (ISO 26262 Part 6 - Software Level)

ISO 26262 Part 6 governs the product development at the software level for automotive functional safety. The following table maps the key clauses (6.4.6 through 6.4.11) to the evidence produced by this automation system.

| ISO 26262 Part 6 Clause | Clause Title | Required Evidence | Generated By | Location in Evidence Package |
|---|---|---|---|---|
| 6.4.6 | Software Unit Design and Implementation | Design documentation linked to requirements; code changes traced to design items | JIRA tickets (type=Design, type=Story) + PR code diffs | /per-ticket/*/jira-snapshot.json, /per-ticket/*/pr-*-diff.patch |
| 6.4.7 | Software Unit Verification | Unit test results with pass/fail status; coverage analysis; static analysis results | GitHub Actions CI results (unit tests, coverage, SAST) | /per-ticket/*/pr-*-ci-results.json |
| 6.4.8 | Software Integration and Verification | Integration test results; interface test results linked to architecture elements | GitHub Actions CI results (integration tests) + JIRA design element traceability | /per-ticket/*/pr-*-ci-results.json, /traceability-matrix.csv |
| 6.4.9 | Verification of Software Safety Requirements | Test cases traced to safety requirements; test results demonstrating requirement satisfaction | Traceability matrix generator (requirement -> test case -> result) | /traceability-matrix.csv, /traceability-matrix.json |
| 6.4.10 | Software Integration Testing | Integration testing across software components; regression test results | GitHub Actions CI results (integration test suite) | /per-ticket/*/pr-*-ci-results.json, /ci-summary.json |
| 6.4.11 | Verification of Software Integration | Verification that integrated software meets architectural design; back-to-back test results (ASIL C/D) | GitHub Actions CI results + manual verification records in JIRA | /per-ticket/*/pr-*-ci-results.json, /per-ticket/*/jira-snapshot.json |
| 8.4.5 | Configuration Management | Version-controlled baselines; change history with approval records | Git history + JIRA audit log + approval ledger | /configuration-snapshot.json, /approval-ledger.csv |
| 8.4.3 | Change Management | Change requests with impact analysis; approval records; verification of changes | JIRA ticket lifecycle (status history, fields, comments) + PR reviews | /per-ticket/*/evidence-record.json |

**Note**: ISO 26262 Part 8 (Supporting Processes) clauses 8.4.3 and 8.4.5 are included because they directly relate to the configuration management and change control evidence this system produces. For ASIL C and D, additional evidence such as formal verification results and back-to-back testing may need to be collected through supplementary tools (e.g., LDRA, Parasoft) and added to the evidence package.

### 9.7 Standard Objective Mapping (DO-178C)

DO-178C defines objectives organized in tables within Annex A. The following maps the key objectives from Tables A-4, A-5, and A-7 to the evidence produced by this automation system.

**Table A-4: Verification of Outputs of Software Coding & Integration Processes**

| DO-178C Objective (Table A-4) | Description | Required Evidence | Generated By | Location in Evidence Package |
|---|---|---|---|---|
| A-4.1 | Source code complies with low-level requirements | Traceability from code (PRs) to low-level requirements (JIRA tickets) | Traceability matrix generator | /traceability-matrix.csv |
| A-4.2 | Source code complies with software architecture | Architecture traceability; code review records confirming architectural compliance | PR reviews + JIRA design element links | /per-ticket/*/pr-*-reviews.json, /traceability-matrix.csv |
| A-4.3 | Source code is verifiable | Code review records; static analysis results; coding standard compliance | GitHub Actions (SAST, lint) + PR reviews | /per-ticket/*/pr-*-ci-results.json, /per-ticket/*/pr-*-reviews.json |
| A-4.4 | Source code conforms to standards | Coding standard compliance results (linting, static analysis) | GitHub Actions CI (lint, SAST) | /per-ticket/*/pr-*-ci-results.json |
| A-4.5 | Source code is traceable to low-level requirements | Bidirectional traceability matrix | Traceability matrix generator | /traceability-matrix.csv, /traceability-matrix.json |
| A-4.6 | Source code is accurate and consistent | Code review approval records; test results | PR reviews + GitHub Actions CI | /per-ticket/*/pr-*-reviews.json, /per-ticket/*/pr-*-ci-results.json |
| A-4.13 | Source code is traceable to data and control coupling analysis | Architecture-level traceability | JIRA design tickets + traceability matrix | /traceability-matrix.csv |

**Table A-5: Verification of Outputs of Integration Process**

| DO-178C Objective (Table A-5) | Description | Required Evidence | Generated By | Location in Evidence Package |
|---|---|---|---|---|
| A-5.1 | Executable object code complies with high-level requirements | Integration test results traced to requirements | GitHub Actions CI (integration tests) + traceability matrix | /per-ticket/*/pr-*-ci-results.json, /traceability-matrix.csv |
| A-5.2 | Executable object code is robust with high-level requirements | Robustness test results (boundary conditions, error cases) | GitHub Actions CI (test suite including edge cases) | /per-ticket/*/pr-*-ci-results.json |
| A-5.3 | Executable object code complies with low-level requirements | Unit + integration test results traced to low-level requirements | GitHub Actions CI + traceability matrix | /per-ticket/*/pr-*-ci-results.json, /traceability-matrix.csv |
| A-5.5 | Executable object code is compatible with target computer | Build results on target platform; deployment verification | GitHub Actions CI (build pipeline) | /per-ticket/*/pr-*-ci-results.json |
| A-5.7 | Verification procedures are correct | Test case review records (test case linked to requirement, reviewed by peer) | JIRA test case tickets + PR reviews for test code | /traceability-matrix.csv, /per-ticket/*/pr-*-reviews.json |

**Table A-7: Verification of Verification Process Results**

| DO-178C Objective (Table A-7) | Description | Required Evidence | Generated By | Location in Evidence Package |
|---|---|---|---|---|
| A-7.1 | Test procedures are correct | Test code review records; test case traceability | PR reviews for test files + traceability matrix | /per-ticket/*/pr-*-reviews.json, /traceability-matrix.csv |
| A-7.2 | Test results are correct and discrepancies explained | Test execution results with pass/fail status; problem reports for failures | GitHub Actions CI results + JIRA bug tickets | /per-ticket/*/pr-*-ci-results.json, /ci-summary.json |
| A-7.3 | Test coverage of high-level requirements is achieved | Requirements coverage analysis from traceability matrix | Traceability matrix generator (gap detection) | /traceability-matrix.csv (with coverage % column) |
| A-7.4 | Test coverage of low-level requirements is achieved | Requirements coverage analysis from traceability matrix | Traceability matrix generator (gap detection) | /traceability-matrix.csv (with coverage % column) |
| A-7.5 | Test coverage of software structure (statement, decision, MC/DC) is achieved | Structural coverage reports from CI | GitHub Actions CI (coverage tools) | /per-ticket/*/pr-*-ci-results.json |
| A-7.7 | Verification activities were performed independently | Reviewer is different from author; approval records show independent review | PR review records (reviewer != author) + JIRA approval records | /per-ticket/*/pr-*-reviews.json, /approval-ledger.csv |
| A-7.9 | Previously verified items are not adversely affected | Regression test results; change impact analysis | GitHub Actions CI (full test suite on merge) + JIRA change impact field | /per-ticket/*/pr-*-ci-results.json, /per-ticket/*/jira-snapshot.json |

**Note**: DO-178C DAL levels A through D require progressively more objectives to be satisfied with independence. DAL A requires all objectives; DAL D requires fewer. The evidence package structure supports all levels; the auditor selects which objectives apply based on the declared DAL. For DAL A, structural coverage must include MC/DC (Modified Condition/Decision Coverage), which requires specialized coverage tooling configured in the CI pipeline.

---

## 10. Risk Assessment

### Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| JIRA API rate limiting during high activity | Medium | Medium | Request batching, caching, exponential backoff in n8n |
| GitHub webhook delivery failures (dropped events) | Low | High | GitHub webhook delivery logs + reconciliation cron job |
| n8n downtime causes sync gap | Medium | High | HA deployment; JIRA and GitHub still enforce natively (degraded but safe) |
| Evidence storage data loss | Low | Critical | Redundant storage (S3 cross-region or MinIO replication), checksums |
| JIRA workflow modification by unauthorized admin | Medium | High | JIRA audit log monitoring, permission scheme restrictions |
| GitHub branch protection disabled by repo admin | Medium | High | GitHub organization-level rulesets (cannot be overridden at repo level) |
| Stale JIRA ticket data in evidence (race condition) | Medium | Low | Capture JIRA snapshot at merge time (not before) |

### Process Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Developer resistance to enforced workflow | High | Medium | Gradual rollout, demonstrate time savings, training |
| Auditor unfamiliarity with automated evidence | Medium | Medium | Auditor-facing evidence guide with walkthrough |
| Standard requirements change | Low | Medium | Extensible evidence schema with clause mapping layer |
| Tool vendor discontinuation (Ketryx, n8n) | Low | High | Architecture with replaceable components; core enforcement is native |
| False positives blocking valid merges | Medium | High | Manual override mechanism with mandatory logging + SLA for resolution |

### Compliance Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Evidence deemed insufficient by auditor | Medium | High | Pre-audit review with certification body; iterative refinement |
| Traceability gaps (orphan requirements or code) | Medium | High | Automated gap detection in traceability matrix generator |
| Timestamp discrepancies across systems | Low | Medium | NTP synchronization; use UTC everywhere; log source system timestamps |
| Electronic signatures not meeting 21 CFR Part 11 | Medium (medical only) | High | Use authenticated API tokens as signature equivalent; consult regulatory counsel |

---

## 11. Cost Analysis

### Option A: n8n Hybrid (Recommended)

| Item | Cost | Notes |
|---|---|---|
| n8n Community Edition | Free | Self-hosted, unlimited workflows |
| n8n Enterprise (if audit logs needed) | ~$300/month | Adds audit logs, SSO, LDAP |
| JIRA Cloud Premium/Enterprise | Existing license | Workflow configuration is included |
| GitHub Enterprise | Existing license | Rulesets require Enterprise |
| Storage (S3/MinIO) | ~$5-50/month | Depends on volume |
| Development effort | 28-30 person-days | One-time setup |
| Maintenance | ~2 days/month | Ongoing |

**Annual cost (excluding labor)**: $60 - $3,600/year for tooling + existing JIRA/GitHub licenses

### Option B: Ketryx (Medical Device Shortcut)

| Item | Cost | Notes |
|---|---|---|
| Ketryx license | $200-500/user/month (estimated) | Enterprise pricing, contact sales |
| JIRA Cloud | Existing license | Required for Ketryx |
| GitHub | Existing license | For CI/CD integration |
| Setup effort | 5-10 person-days | Plugin configuration |
| Maintenance | ~1 day/month | Vendor managed |

**Annual cost (10-person team)**: $24,000 - $60,000/year for Ketryx + existing licenses

### Option C: Full ALM (codebeamer/Jama)

| Item | Cost | Notes |
|---|---|---|
| ALM license | $50,000 - $200,000/year | Enterprise licensing |
| Migration effort | 30-60 person-days | Moving from JIRA |
| Training | 10-20 person-days | Team onboarding |
| Maintenance | ~3 days/month | Ongoing |

**Annual cost**: $50,000 - $200,000/year + significant migration effort

---

## 12. Conclusion and Recommendations

### Primary Recommendation

For teams already using JIRA + GitHub, the **Hybrid approach (JIRA Native + GitHub Native + n8n)** provides the best balance of:
- **Reliability**: Core enforcement handled by native JIRA and GitHub mechanisms
- **Flexibility**: n8n can be customized for any evidence format or workflow variation
- **Cost**: Minimal additional tooling cost
- **Independence**: No single vendor lock-in for the critical path
- **Self-hosting**: Full data sovereignty if required

### Decision Framework

Use this decision tree:

```
Is your certification target IEC 62304 (medical device)?
  |
  +-- Yes -> Is data sovereignty a concern?
  |     |
  |     +-- No  -> Consider Ketryx (fastest path)
  |     +-- Yes -> Use Hybrid approach (n8n self-hosted)
  |
  +-- No (ISO 26262, DO-178C, or other) -> Use Hybrid approach
        |
        +-- Do you have a strong DevOps team?
              |
              +-- Yes -> Direct API approach (no n8n, use GitHub Actions for everything)
              +-- No  -> Hybrid with n8n (visual workflows, lower maintenance)
```

### Next Steps

1. **Decide on certification standard target** (IEC 62304, ISO 26262, DO-178C, or generic)
2. **Decide on approach** (Hybrid with n8n vs. Direct API vs. Ketryx)
3. **Begin Phase 1**: JIRA workflow design and GitHub branch protection
4. **Iterate**: Build integration and evidence pipeline incrementally
5. **Validate with auditor**: Share evidence format with certification body early

---

## 13. References

### JIRA Workflow and Automation
- [Configure Advanced Workflows (Atlassian)](https://support.atlassian.com/jira-cloud-administration/docs/configure-advanced-issue-workflows/)
- [Use Workflow Properties (Atlassian)](https://support.atlassian.com/jira-cloud-administration/docs/use-workflow-properties/)
- [Workflow Rules for Team-Managed Projects (Atlassian)](https://support.atlassian.com/jira-software-cloud/docs/available-workflow-rules-in-team-managed-projects/)
- [JIRA Automation Triggers (Atlassian)](https://support.atlassian.com/cloud-automation/docs/jira-automation-triggers/)
- [Integrate JIRA and GitHub using Automation (Atlassian)](https://confluence.atlassian.com/automation070/how-to-integrate-jira-and-github-using-automation-for-jira-1014664530.html)
- [JIRA Tutorial 2025: Workflows, Statuses and Transitions](https://www.testmanagement.com/blog/2025/02/jira-tutorial-2025-workflows-statuses-and-transitions/)

### GitHub Features
- [About Protected Branches (GitHub)](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
- [Managing Branch Protection Rules (GitHub)](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/managing-a-branch-protection-rule)
- [GitHub Actions for Security and Compliance (GitHub Blog)](https://github.blog/enterprise-software/github-actions-for-security-compliance/)
- [GitHub Artifact Attestations (GitHub Blog)](https://github.blog/changelog/2025-02-18-recent-improvements-to-artifact-attestations/)
- [GitHub Actions Branch Protection Rules (2026)](https://oneuptime.com/blog/post/2026-01-28-github-actions-branch-protection/view)
- [GitHub Compliance as Code (Pull Checklist)](https://www.pullchecklist.com/posts/github-compliance-as-code)
- [SOC 2 Compliance GitHub Configuration (Delve)](https://delve.co/blog/github-configuration-checklist-for-soc-2-compliance)

### n8n
- [n8n JIRA Software Integration](https://n8n.io/integrations/jira-software/)
- [n8n GitHub + JIRA Workflow](https://n8n.io/integrations/github/and/jira-software/)
- [n8n Webhook Integration](https://n8n.io/integrations/webhook/)
- [n8n Security Audit (Docs)](https://docs.n8n.io/hosting/securing/security-audit/)
- [n8n Enterprise Governance (DEV Community)](https://dev.to/alifar/n8n-at-scale-enterprise-governance-and-secure-automation-1jih)
- [n8n Logging (Docs)](https://docs.n8n.io/hosting/logging-monitoring/logging/)
- [Self-Hosting n8n for Compliance (Medium)](https://medium.com/@Nexumo_/keep-workflows-home-self-hosting-n8n-for-compliance-73baa5bfd4ea)
- [Secure n8n Workflows for Enterprise (Shakudo)](https://www.shakudo.io/blog/secure-n8n-workflows-enterprise-auditability)

### Certification Standards
- [IEC 62304 Guide (Jama Software)](https://www.jamasoftware.com/blog/an-in-depth-guide-to-iec-62304-software-lifecycle-processes-for-medical-devices/)
- [IEC 62304 & RTM in JIRA (Ketryx)](https://www.ketryx.com/blog/iec-62304-requirements-traceability-matrix-rtm-in-jira-a-guide-for-medical-device-companies)
- [IEC 62304 Overview (Perforce)](https://www.perforce.com/blog/qac/what-iec-62304)
- [ISO 26262 Requirements Traceability (Parasoft)](https://www.parasoft.com/learning-center/iso-26262/requirements-traceability/)
- [DO-178C Certification (LDRA)](https://ldra.com/do-178/)
- [Safety-Critical QA Standards (Mndwrk)](https://www.mndwrk.com/blog/the-role-of-standards-in-safety-critical-qa-navigating-iso-26262-do-178c-and-iec-62304)

### Certification-Specific Tools
- [Ketryx JIRA Connector](https://www.ketryx.com/use-case/jira-connector)
- [Ketryx on Atlassian Marketplace](https://marketplace.atlassian.com/apps/1228398/ketryx-connector-for-jira)
- [Jama Connect JIRA Integration](https://www.jamasoftware.com/datasheet/jama-connect-integration-jira-datasheet/)
- [codebeamer vs Polarion (SPK)](https://www.spkaa.com/blog/choosing-the-right-alm-solution-codebeamer-vs-polarion)
- [Best IEC 62304 Tools for 2026 (Visure)](https://visuresolutions.com/medtech-and-pharma-guide/best-iec-62304-tools)
- [LDRA JIRA Integration (BusinessWire)](https://www.businesswire.com/news/home/20200224005258/en/LDRA-Optimizes-Agile-Development-and-Verification-of-Critical-Embedded-Applications-with-New-Jira-Software-Integration)

### Automation Platform Comparisons
- [n8n vs Make vs Zapier (Digidop)](https://www.digidop.com/blog/n8n-vs-make-vs-zapier)
- [Temporal vs Airflow (ZenML)](https://www.zenml.io/blog/temporal-vs-airflow)
- [Top Open Source Workflow Orchestration Tools (Bytebase)](https://www.bytebase.com/blog/top-open-source-workflow-orchestration-tools/)
- [Git Workflows for FDA Compliance (IntuitionLabs)](https://intuitionlabs.ai/articles/git-workflows-fda-compliance)

---

*This report was produced through systematic research across tool documentation, vendor sites, standards references, and community discussions. All findings reflect publicly available information as of March 2026.*
