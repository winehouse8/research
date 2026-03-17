# Phase 0: Prerequisites Checklist

> Complete every section below before proceeding to Phase 1.
> Commit this filled-in file to the repository as the first traceability artifact.

---

## 1. JIRA Deployment Model Selection

Select exactly one deployment model. Your choice determines which workflow enforcement mechanisms are available throughout the entire implementation.

**Selected model (circle/mark one):**

- [ ] Cloud Company-Managed
- [ ] Cloud Team-Managed
- [ ] Data Center (self-hosted)

### Impact Table

| Capability | Cloud Company-Managed | Cloud Team-Managed | Data Center |
|---|---|---|---|
| Workflow editor (full control) | Yes | No (simplified only) | Yes |
| Native Status History Validator | No | No | Yes (built-in) |
| ScriptRunner Groovy validators | No | No | Yes |
| Automation Rules (built-in) | Yes | Yes | Yes (separate license) |
| Permission Validators on transitions | Yes | No | Yes |
| Transition Conditions | Yes | No | Yes |
| REST API access (full) | Yes | Yes | Yes |
| Recommended for IEC 62304 / ISO 26262 | Acceptable with Automation Rules | Not recommended; upgrade advised | Preferred |
| Audit log retention (default) | 90 days (paid tier) | 90 days (paid tier) | Configurable (unlimited) |

**Recorded selection:** `___________________________`

---

## 2. GitHub Tier Selection

Select exactly one tier. Your choice determines whether branch protection, required status checks, and audit log streaming are available natively.

**Selected tier (circle/mark one):**

- [ ] Free / Team (github.com)
- [ ] Enterprise Cloud (github.com, enterprise org)
- [ ] Enterprise Server (self-hosted GHES)

### Impact Table

| Capability | Free / Team | Enterprise Cloud | Enterprise Server |
|---|---|---|---|
| Branch protection rules | Yes (basic) | Yes (advanced) | Yes (advanced) |
| Required status checks | Yes | Yes | Yes |
| Required reviewers (CODEOWNERS) | Yes | Yes | Yes |
| Audit log streaming (SIEM) | No | Yes | Yes |
| SAML SSO enforcement | No | Yes | Yes |
| GitHub Actions minutes (private repos) | Limited | Large pool | Self-hosted runners only |
| IP allow-list | No | Yes | Yes |
| GitHub Advanced Security (GHAS) | No (public only) | Add-on | Add-on |
| Webhook delivery guarantees | Best-effort | Best-effort | Best-effort + internal |
| Recommended for regulated workloads | Low | High | Highest (air-gapped) |

**Recorded selection:** `___________________________`

---

## 3. Existing Infrastructure Inventory

Check every item that is already available and operational in your environment. Items left unchecked will require provisioning before Phase 2.

### Compute / Orchestration

- [ ] Kubernetes cluster accessible (version: `_______`; namespace for tools: `_______`)
- [ ] `kubectl` configured and tested against target cluster
- [ ] Helm 3 installed on deployment workstation
- [ ] Docker (or containerd) available for local image builds and testing

### Storage

- [ ] S3-compatible object storage available
  - Provider (AWS S3 / MinIO / Ceph / other): `___________________________`
  - Bucket name reserved for evidence artifacts: `___________________________`
  - Credentials/IAM role documented in secrets manager: [ ] Yes [ ] No
- [ ] MinIO operator deployed in cluster (if using in-cluster MinIO): [ ] Yes [ ] No / N/A

### CI Runners

- [ ] GitHub Actions runners available
  - Type: [ ] GitHub-hosted [ ] Self-hosted
  - Labels/tags: `___________________________`
- [ ] Runner has network access to JIRA instance: [ ] Yes [ ] No (need firewall rule)
- [ ] Runner has network access to S3/MinIO: [ ] Yes [ ] No
- [ ] Runner service account / secrets configured in GitHub repo: [ ] Yes [ ] No

### Networking / Security

- [ ] DNS entry reserved for n8n (if deploying): `___________________________`
- [ ] TLS certificate provisioned or cert-manager available for auto-issuance
- [ ] Ingress controller deployed (type: `___________________________`)
- [ ] Outbound HTTPS from cluster to github.com: [ ] Yes [ ] Blocked (proxy: `_______`)
- [ ] Outbound HTTPS from cluster to JIRA cloud (*.atlassian.net): [ ] Yes [ ] Blocked

### Secrets Management

- [ ] Kubernetes Secrets or external secrets manager available
  - Tool (Vault / AWS Secrets Manager / Azure Key Vault / k8s Secrets): `_______________`
- [ ] JIRA API token created and stored: [ ] Yes [ ] No
- [ ] GitHub PAT (or GitHub App private key) created and stored: [ ] Yes [ ] No

---

## 4. Certification Scope Selection

Select all standards that apply to your product. Each selection activates additional field and workflow requirements detailed in Phase 1.

- [ ] **IEC 62304** (Medical device software lifecycle)
  - Software Safety Class (A / B / C): `_______`
  - Notified body or internal audit: `___________________________`
- [ ] **ISO 26262** (Automotive functional safety)
  - ASIL level (A / B / C / D): `_______`
  - Development interface agreement (DIA) required: [ ] Yes [ ] No
- [ ] **DO-178C** (Airborne software)
  - Design Assurance Level (A / B / C / D / E): `_______`
  - Tool Qualification required (DO-330): [ ] Yes [ ] No
- [ ] **Multiple standards** (list all): `___________________________`

### Notes on scope

Record any exclusions, derogations, or partial applicability here:

```
_______________________________________________________________________________
_______________________________________________________________________________
```

---

## 5. Integration Platform Decision

Select the platform that will orchestrate evidence collection between JIRA and GitHub. This decision affects deployment complexity, licensing cost, and the availability of enterprise features such as SSO, audit logs, and credential vaults.

**Selected platform (circle/mark one):**

- [ ] n8n Community Edition (CE) — self-hosted, no license cost
- [ ] n8n Enterprise Edition (EE) — self-hosted, requires license key
- [ ] Direct API (custom scripts / GitHub Actions only, no n8n)

### Decision Matrix

| Criterion | n8n CE | n8n EE | Direct API |
|---|---|---|---|
| License cost | Free (fair-code) | Paid (contact n8n) | Free |
| Deployment | Docker / Kubernetes | Docker / Kubernetes | N/A (runs in CI) |
| Visual workflow editor | Yes | Yes | No |
| Built-in credential vault | Basic (encrypted DB) | Yes (external secrets) | No (use CI secrets) |
| SSO / SAML for n8n UI | No | Yes | N/A |
| Audit log for workflow executions | Basic | Full | CI logs only |
| Webhook receiver (for JIRA/GitHub) | Yes | Yes | Via GitHub Actions |
| Retry / error handling | Manual nodes | Advanced | Custom code |
| Suitable for IEC 62304 Class C | Marginal | Yes | Yes (if audited) |
| Suitable for air-gapped environments | Yes | Yes | Yes |
| Maintenance burden | Medium | Medium | High (custom code) |

**Recorded selection:** `___________________________`

**Justification (required for audit trail):**

```
_______________________________________________________________________________
_______________________________________________________________________________
```

---

## 6. Team and Access Confirmation

| Role | Name | JIRA Account ID | GitHub Username | Confirmed |
|---|---|---|---|---|
| JIRA Administrator | | | | [ ] |
| GitHub Organization Owner | | | | [ ] |
| Compliance / Quality Lead | | | | [ ] |
| DevOps / Platform Engineer | | | | [ ] |
| n8n Administrator (if applicable) | | | | [ ] |

---

## 7. Summary and Go/No-Go Gate

Before proceeding to Phase 1, verify that every item below is true:

- [ ] Section 1 (JIRA model) has exactly one selection recorded
- [ ] Section 2 (GitHub tier) has exactly one selection recorded
- [ ] Section 3 (Infrastructure) has been fully reviewed; all unchecked items have a remediation owner and date
- [ ] Section 4 (Certification scope) has at least one standard selected with safety class/level recorded
- [ ] Section 5 (Integration platform) has exactly one selection recorded with written justification
- [ ] Section 6 (Team) is fully populated and all team members have confirmed access
- [ ] This file has been committed to the repository with a signed commit (or commit hash recorded below)

**Commit hash of this checklist:** `___________________________`

**Date completed:** `___________________________`

**Completed by (name + role):** `___________________________`

---

> Proceed to `phase1-jira/workflow-config.md` only after all checkboxes above are marked.
