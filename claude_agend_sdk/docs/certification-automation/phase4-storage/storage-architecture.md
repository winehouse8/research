# Evidence Storage Architecture

## Overview

This document defines the storage architecture for certification evidence artifacts produced
by the JIRA + GitHub CI/CD evidence automation system. It covers storage option trade-offs,
the recommended deployment topology, directory layout in object storage, retention policies
by standard, access control, integrity verification, and disaster recovery.

---

## Storage Options Comparison

| Dimension                  | GitHub Actions Artifacts          | MinIO / AWS S3                          | Git-based Evidence Repo                  |
|----------------------------|-----------------------------------|-----------------------------------------|------------------------------------------|
| **Retention**              | 90 days max (configurable to 400) | Unlimited; lifecycle policies for 10–15yr | Unlimited (commits are permanent)        |
| **Immutability**           | No (artifacts can be deleted)     | Yes — WORM / Object Lock (COMPLIANCE)   | Partial — history rewrite possible       |
| **Auditability**           | Workflow run logs only            | Full access log + versioning            | Git log; requires signed commits          |
| **Access control**         | GitHub org roles                  | Fine-grained bucket policies (IAM-like) | Branch protection + CODEOWNERS            |
| **Storage cost**           | Included in GitHub plan           | Low (self-hosted) / tiered (AWS)        | Low for text; large for binaries          |
| **Search / query**         | Manual download required          | S3 Select or custom indexing            | `git log`, `grep`; limited for binary     |
| **Regulatory suitability** | Not suitable as primary store     | Suitable — WORM satisfies IEC 62304     | Not suitable as sole primary store        |
| **Complexity**             | Zero — built into CI              | Medium (deploy + configure)             | Low for text, high for scale             |
| **Backup / replication**   | Managed by GitHub                 | Site replication or cross-region sync   | `git push` to multiple remotes            |
| **Binary artifact support**| Yes (ZIP bundles)                 | Yes (arbitrary objects)                 | Poor (LFS required; cost and friction)    |

---

## Recommended Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  CI/CD Pipeline (GitHub Actions)                                │
│                                                                 │
│  1. Generate evidence JSON          2. Upload artifact          │
│     (evidence-record-*.json)  ───►  (GitHub Actions Artifacts) │
│                                           │                     │
│  3. Package release evidence              │ backup copy         │
│     (evidence-export.py)      ────────────┼──────────────────► │
│                                           │                     │
└───────────────────────────────────────────┼─────────────────────┘
                                            │
                            ┌───────────────▼──────────────────┐
                            │   MinIO / S3  (PRIMARY STORE)    │
                            │                                  │
                            │   evidence-records/              │
                            │   traceability-matrices/         │
                            │   approval-ledgers/              │
                            │                                  │
                            │   Object Lock: COMPLIANCE        │
                            │   Versioning: enabled            │
                            │   Lifecycle: archive → expire    │
                            └───────────────┬──────────────────┘
                                            │ replication
                            ┌───────────────▼──────────────────┐
                            │   Secondary MinIO / S3  (DR)     │
                            │   (separate datacenter / region) │
                            └──────────────────────────────────┘
```

**Decision rationale:**

- MinIO/S3 is the primary store because it supports WORM object locking in COMPLIANCE mode,
  satisfying immutability requirements for IEC 62304 and ISO 26262.
- GitHub Actions Artifacts serve as a short-term backup and convenience layer for engineers
  reviewing recent pipeline runs. They are not relied upon for long-term retention.
- A Git-based evidence repo is used optionally for human-readable traceability matrices and
  release manifests, providing a reviewable diff history but not as the regulatory primary.

---

## Directory Structure in Object Storage

```
evidence/
├── {release_tag}/
│   ├── manifest.json                          # Release index with SHA-256 of all files
│   ├── evidence-records/
│   │   ├── {JIRA_TICKET}-{PR_NUMBER}.json     # One file per ticket/PR pair
│   │   └── ...
│   ├── traceability-matrix.csv                # CSV matrix: tickets × PRs × tests × status
│   ├── traceability-matrix.json               # JSON equivalent for machine consumption
│   ├── approval-ledger.json                   # All approval records with GPG signatures
│   └── ci-summary.json                        # CI check run results for all PRs
│
├── audit-logs/
│   ├── {YYYY-MM}/
│   │   ├── jira-audit-{YYYY-MM}.json
│   │   └── github-audit-{YYYY-MM}.json
│   └── unified-audit-{YYYY-MM}.json
│
└── packages/
    └── {release_tag}/
        ├── evidence-{release_tag}.zip         # Full packaged archive (from evidence-export.py)
        └── evidence-{release_tag}.zip.sha256  # Detached checksum file
```

### manifest.json schema

```json
{
  "release_tag": "v1.0.0",
  "packaged_at": "2024-03-15T10:30:00Z",
  "package_sha256": "abc123...",
  "contents": [
    {
      "type": "evidence_record",
      "file": "evidence-records/PROJ-42-123.json",
      "sha256": "def456..."
    },
    {
      "type": "traceability_matrix",
      "file": "traceability-matrix.json",
      "sha256": "ghi789..."
    },
    {
      "type": "approval_ledger",
      "file": "approval-ledger.json",
      "sha256": "jkl012..."
    },
    {
      "type": "ci_summary",
      "file": "ci-summary.json",
      "sha256": "mno345..."
    }
  ],
  "standards_covered": ["IEC_62304", "ISO_26262"],
  "total_tickets": 12,
  "total_prs": 9
}
```

---

## Retention Policy by Standard

| Standard      | Scope                             | Minimum Retention           | Recommended Setting  | Notes                                               |
|---------------|-----------------------------------|-----------------------------|----------------------|-----------------------------------------------------|
| **IEC 62304** | Medical device software           | 10 years post market release| 10 years             | From last device manufacture or market withdrawal   |
| **ISO 26262** | Automotive functional safety      | Vehicle lifetime            | 15 years             | From end of production; agree with OEM if longer    |
| **DO-178C**   | Airborne software                 | Aircraft lifetime           | 30+ years            | Coordinate with DAL and program schedule            |
| **ISO 13485** | Medical device QMS                | Minimum 5 years (device life + 2) | 10 years       | Aligns with IEC 62304 in combined programs          |
| **GDPR / privacy** | Personal data in logs        | Minimum required only       | Pseudonymise + 3 yr  | Minimise personal data in evidence records          |

> **Implementation note**: Configure object lock retention at bucket level (see `minio-setup.md`).
> For programs spanning multiple standards, apply the longest applicable retention period.
> Use `COMPLIANCE` mode to prevent early deletion even by administrators.

---

## Access Control Matrix

| Role                    | evidence-records | traceability-matrices | approval-ledgers | audit-logs | packages |
|-------------------------|------------------|-----------------------|------------------|------------|----------|
| **CI/CD Service Acct**  | Write            | Write                 | Write            | Write      | Write    |
| **Auditor**             | Read             | Read                  | Read             | Read       | Read     |
| **Developer**           | None             | None                  | None             | None       | None     |
| **Security Officer**    | Read             | Read                  | Read             | Read       | Read     |
| **Storage Admin**       | Admin (no delete)| Admin (no delete)     | Admin (no delete)| Admin      | Admin    |
| **Root / Superuser**    | Governance only* | Governance only*      | Governance only* | Full       | Full     |

\* With COMPLIANCE object lock, root cannot delete locked objects before expiry regardless
of IAM permissions. Governance mode overrides are logged and trigger anomaly alerts.

### IAM roles (MinIO / AWS)

```
cicd-service    PutObject, PutObjectRetention, GetBucketObjectLockConfiguration
auditor         GetObject, GetObjectVersion, ListBucket, ListBucketVersions,
                GetObjectRetention, GetBucketObjectLockConfiguration
storage-admin   PutBucketPolicy, PutLifecycleConfiguration, GetBucketVersioning
                (explicitly DenyDelete on COMPLIANCE buckets)
```

Developers have **no direct access** to the evidence store. They interact with evidence
exclusively through the CI/CD pipeline, which writes evidence on their behalf using the
`cicd-service` account.

---

## Integrity Verification

### SHA-256 checksums

Every file stored in object storage is accompanied by a SHA-256 digest recorded in
`manifest.json`. The packaging step in `evidence-export.py` computes checksums before
packaging and embeds them in the manifest.

```bash
# Verify a downloaded package against its manifest
sha256sum -c evidence-v1.0.0.zip.sha256

# Verify individual files inside the package
python - <<'EOF'
import hashlib, json, zipfile, sys

pkg = sys.argv[1]
with zipfile.ZipFile(pkg) as zf:
    manifest = json.loads(zf.read("index.json"))
    for item in manifest["contents"]:
        data = zf.read(item["file"])
        actual = hashlib.sha256(data).hexdigest()
        status = "OK" if actual == item["sha256"] else "MISMATCH"
        print(f"{status}  {item['file']}")
EOF evidence-v1.0.0.zip
```

### GPG signing (optional, recommended for DO-178C)

```bash
# Sign the package
gpg --armor --detach-sign evidence-v1.0.0.zip

# Upload signature alongside package
aws s3 cp evidence-v1.0.0.zip.asc \
  s3://evidence-records/v1.0.0/evidence-v1.0.0.zip.asc \
  --endpoint-url "${MINIO_ENDPOINT}"

# Verify
gpg --verify evidence-v1.0.0.zip.asc evidence-v1.0.0.zip
```

### MinIO / S3 ETag verification

MinIO computes and stores an MD5 ETag for every single-part upload. For multi-part uploads,
the ETag is a composite hash; use SHA-256 checksums (above) for multi-part verification.

```bash
# Confirm ETag after upload
aws s3api head-object \
  --bucket evidence-records \
  --key "v1.0.0/evidence-v1.0.0.zip" \
  --endpoint-url "${MINIO_ENDPOINT}"
```

### Versioning

Versioning is enabled on all buckets. Every PUT creates a new version; objects are never
silently overwritten. Version history provides a full audit trail of all uploads to a key.

```bash
# List all versions of a specific key
aws s3api list-object-versions \
  --bucket evidence-records \
  --prefix "v1.0.0/" \
  --endpoint-url "${MINIO_ENDPOINT}"
```

---

## Disaster Recovery

### RTO / RPO Targets

| Tier          | Target use case                    | RTO        | RPO        |
|---------------|------------------------------------|------------|------------|
| **Tier 1**    | Active audit / regulatory review   | 4 hours    | 1 hour     |
| **Tier 2**    | Historical release evidence        | 24 hours   | 4 hours    |
| **Tier 3**    | Archived evidence (> 2 years old)  | 72 hours   | 24 hours   |

### Backup procedure

1. **MinIO site replication** (active-active): any write to the primary site is synchronously
   replicated to the secondary site. Both sites hold a full copy at all times.

   ```bash
   mc admin replicate add minio-primary minio-secondary
   mc admin replicate info minio-primary   # verify both sites healthy
   ```

2. **Scheduled verification** (weekly): run a checksum audit across all objects to detect
   silent corruption.

   ```bash
   mc find evidence-store/evidence-records --json | \
     jq -r '.key' | \
     while read key; do
       mc stat "evidence-store/${key}" --json | jq '{key, etag: .etag, size: .size}'
     done
   ```

3. **Annual DR drill**: restore a sample release package from the secondary site to a
   clean environment and verify all checksums match. Document results in the QMS.

### Recovery procedure

```bash
# 1. Confirm secondary site is healthy
mc admin info minio-secondary

# 2. Point evidence-store alias to secondary
mc alias set evidence-store-dr http://minio-dr.internal:9000 \
  "${DR_ACCESS_KEY}" "${DR_SECRET_KEY}"

# 3. Download and verify a release package
mc cp evidence-store-dr/evidence-records/v1.0.0/evidence-v1.0.0.zip ./restore/
sha256sum -c ./restore/evidence-v1.0.0.zip.sha256

# 4. Update GitHub Actions secrets to point to DR endpoint
#    MINIO_ENDPOINT -> http://minio-dr.internal:9000
```

### AWS S3 cross-region replication

For teams using AWS S3, enable cross-region replication with the following policy:

```json
{
  "Role": "arn:aws:iam::123456789012:role/S3ReplicationRole",
  "Rules": [
    {
      "ID": "replicate-all-evidence",
      "Status": "Enabled",
      "Filter": {"Prefix": ""},
      "Destination": {
        "Bucket": "arn:aws:s3:::evidence-records-dr-us-west-2",
        "StorageClass": "STANDARD",
        "ReplicationTime": {
          "Status": "Enabled",
          "Time": {"Minutes": 15}
        },
        "Metrics": {
          "Status": "Enabled",
          "EventThreshold": {"Minutes": 15}
        }
      },
      "DeleteMarkerReplication": {"Status": "Disabled"},
      "SourceSelectionCriteria": {
        "SseKmsEncryptedObjects": {"Status": "Enabled"}
      }
    }
  ]
}
```

---

## Checklist

- [ ] Primary MinIO/S3 deployed with WORM object locking
- [ ] Three evidence buckets created: `evidence-records`, `traceability-matrices`, `approval-ledgers`
- [ ] Versioning enabled on all buckets
- [ ] COMPLIANCE retention configured (minimum 10 years; 15 years for ISO 26262 programs)
- [ ] Lifecycle policy applied: archive at 2 years, expire at applicable retention limit
- [ ] IAM roles created: `cicd-service` (write), `auditor` (read), developers excluded
- [ ] SHA-256 checksums embedded in every release manifest
- [ ] GPG signing configured (required for DO-178C; recommended for all)
- [ ] Site replication to secondary MinIO or S3 cross-region enabled
- [ ] Weekly checksum verification job scheduled
- [ ] Annual DR drill scheduled and procedure documented in QMS
- [ ] RTO/RPO targets documented and agreed with QA/regulatory team
