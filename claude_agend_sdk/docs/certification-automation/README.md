# Certification Evidence Automation System

**Version:** 1.0
**Date:** 2026-03-11
**Supported Standards:** IEC 62304 | ISO 26262 | DO-178C

---

## Project Overview

This system automates the collection, organization, and preservation of software development evidence required for certification audits in safety-critical domains. It integrates JIRA (requirement and ticket lifecycle management) with GitHub (source code, pull requests, and CI/CD) to capture a complete, tamper-evident audit trail at every code merge event — with no manual steps required from the engineering team.

**What it automates:**

- Enforcement of required JIRA workflow stages before any code change can be merged
- Verification that every merged PR is linked to an approved JIRA requirement ticket
- Collection of code review approvals, reviewer identities, and timestamps
- Collection of CI/CD test results for every merged change
- Generation of a traceability matrix linking requirements to implementations and test results
- Writing all collected evidence to a tamper-evident object store with SHA-256 integrity verification
- Packaging release-level evidence artifacts ready for auditor inspection

**What auditors get:** A structured, versioned evidence package per software release, accessible via a web browser or CLI, with a one-command integrity check and a pre-built traceability matrix.

---

## Supported Certification Standards

| Standard | Domain | Key Evidence Artifacts Covered |
|---|---|---|
| **IEC 62304** | Medical Device Software | Software development planning, requirements, architecture, detailed design, unit/integration/system testing, change control, configuration management |
| **ISO 26262** (Part 6) | Automotive Functional Safety | Software development lifecycle, verification, design and coding guidelines, software integration testing |
| **DO-178C** | Airborne Systems Software | Planning process, development process, verification process, configuration management, quality assurance, certification liaison |

See `phase5-docs/auditor-guide.md` for a clause-by-clause mapping of evidence artifacts to standard requirements.

---

## Quick Start Guide

### Prerequisites

Before deploying any component, confirm all prerequisites are met. Start with the prerequisites checklist:

**[phase0-prerequisites-checklist.md](phase0-prerequisites-checklist.md)**

At a high level, you will need:

- A JIRA instance (Cloud or Server/Data Center) with admin access
- A GitHub organization with admin access (GitHub.com or GitHub Enterprise)
- A self-hosted n8n CE instance (Docker or Kubernetes) with a publicly reachable webhook URL
- An S3-compatible object store (MinIO self-hosted or AWS S3) for evidence storage
- GitHub Actions enabled on all repositories that will participate in evidence collection

### Deployment Steps

Follow the phases in order. Each phase directory contains its own detailed instructions.

| Phase | Directory | What You Do |
|---|---|---|
| 0 | `phase0-prerequisites-checklist.md` | Verify all infrastructure prerequisites |
| 1 | `phase1-jira/`, `phase1-github/` | Configure JIRA workflows, automation rules, branch protection, and CODEOWNERS |
| 2 | `phase2-integration/` | Deploy and configure n8n or direct-api for JIRA-GitHub status synchronization |
| 3 | `phase3-evidence/` | Deploy GitHub Actions workflows for validation and evidence collection |
| 4 | `phase4-storage/` | Configure MinIO/S3 storage and evidence export |
| 5 | `phase5-docs/` | Review auditor guide and operations runbook |

To begin: **open `phase0-prerequisites-checklist.md` and work through it before proceeding to any other phase.**

---

## Directory Structure

```
certification-automation/
├── README.md
├── phase0-prerequisites-checklist.md
├── phase1-jira/
│   ├── workflow-config.md
│   └── automation-rules-reference.md
├── phase1-github/
│   ├── branch-protection-config.md
│   ├── CODEOWNERS.example
│   └── CONTRIBUTING.md
├── phase2-integration/
│   ├── n8n/
│   │   ├── docker-compose.yml
│   │   ├── n8n-setup-guide.md
│   │   └── workflows/
│   │       ├── jira-to-github-sync.json
│   │       └── github-to-jira-sync.json
│   └── direct-api/
│       └── webhook-receiver/
│           ├── main.py
│           ├── jira_client.py
│           ├── github_client.py
│           ├── requirements.txt
│           └── Dockerfile
├── phase3-evidence/
│   ├── schema/
│   │   ├── evidence-record.schema.json
│   │   └── standard-mappings.md
│   ├── github-actions/
│   │   ├── evidence-collector.yml
│   │   ├── pr-jira-validator.yml
│   │   └── commit-message-validator.yml
│   └── scripts/
│       ├── traceability_matrix.py
│       ├── approval_collector.py
│       ├── requirements.txt
│       └── README.md
├── phase4-storage/
│   ├── minio-setup.md
│   ├── evidence-export.py
│   ├── audit-aggregator.py
│   └── storage-architecture.md
└── phase5-docs/
    ├── auditor-guide.md
    └── configuration-runbook.md
```

---

## Prerequisites Summary

The following must be in place before deployment. Full details are in `phase0-prerequisites-checklist.md`.

**JIRA:**
- Admin access to create workflows, automation rules, and a service account
- A service account with project-level read access and an API token
- Webhook delivery capability to reach the n8n instance (network path must be open)

**GitHub:**
- Organization admin access to configure branch protection and webhooks
- GitHub Actions enabled
- Ability to configure repository secrets
- GitHub-hosted runners (or self-hosted runners with outbound internet access to JIRA and the evidence store)

**n8n CE:**
- Deployed and accessible at a stable URL (Docker Compose or Kubernetes)
- Reachable by inbound webhooks from both JIRA and GitHub
- Persistent storage configured for the n8n database

**Evidence Store (MinIO or S3):**
- Bucket named `certification-evidence` created with versioning enabled
- Access key and secret key available for GitHub Actions and manual tools
- Sufficient storage capacity (plan for ~50 KB per PR evidence record; grow from there)
- Network reachable from GitHub Actions runners

**General:**
- All team members who will be approving PRs have active GitHub accounts in the organization
- JIRA user accounts for all developers are active and have correct project permissions

---

## Key Documents

| Document | Audience | Purpose |
|---|---|---|
| [phase0-prerequisites-checklist.md](phase0-prerequisites-checklist.md) | Platform engineers | Starting point: verify all infrastructure is ready |
| [phase1-jira/workflow-config.md](phase1-jira/workflow-config.md) | JIRA admins | Configure JIRA workflows and service account |
| [phase1-github/branch-protection-config.md](phase1-github/branch-protection-config.md) | GitHub admins | Configure branch protection and secrets |
| [phase3-evidence/github-actions/evidence-collector.yml](phase3-evidence/github-actions/evidence-collector.yml) | DevOps engineers | Deploy and validate GitHub Actions workflows |
| [phase2-integration/n8n/n8n-setup-guide.md](phase2-integration/n8n/n8n-setup-guide.md) | DevOps engineers | Deploy and configure n8n sync |
| [phase5-docs/auditor-guide.md](phase5-docs/auditor-guide.md) | Auditors, assessors | Understand and verify evidence package contents |
| [phase5-docs/configuration-runbook.md](phase5-docs/configuration-runbook.md) | Platform engineers, DevOps | Day-to-day operations, troubleshooting, upgrades |
| [phase3-evidence/schema/standard-mappings.md](phase3-evidence/schema/standard-mappings.md) | All technical | Evidence schema and standard mappings |

---

## How Evidence Collection Works (Brief Summary)

1. A developer opens a GitHub Pull Request proposing a code change.
2. The `jira-ticket-validator` GitHub Actions workflow checks that the PR references a valid JIRA ticket and that the ticket has completed all required workflow stages. The PR is blocked from merging until this check passes.
3. The CI test suite runs. The PR is blocked from merging until all tests pass.
4. One or more qualified reviewers (enforced by CODEOWNERS and branch protection) approve the PR.
5. The PR is merged. The `evidence-collector` workflow runs immediately and writes a structured evidence record to the evidence store.
6. At release time (triggered by a version tag), the `traceability-builder` workflow collects all evidence records for the release, builds the traceability matrix and summary artifacts, computes SHA-256 integrity hashes, and writes the complete evidence package to the evidence store.
7. The evidence package is available for auditor review at any time via the evidence store web interface or CLI.

---

## Getting Help

- **Operations issues (evidence not generating, workflows failing):** Refer to `phase5-docs/configuration-runbook.md` troubleshooting section first.
- **Auditor questions about evidence contents:** Refer to `phase5-docs/auditor-guide.md` FAQ section.
- **Schema questions:** Refer to `phase3-evidence/schema/standard-mappings.md` and `phase3-evidence/schema/evidence-record.schema.json`.
