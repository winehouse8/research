# MinIO Evidence Storage Setup

## Overview

MinIO provides an S3-compatible object storage backend for long-term retention of certification
evidence artifacts. This guide covers single-node deployment, bucket configuration, WORM object
locking, lifecycle policies, and integration with GitHub Actions CI/CD pipelines.

---

## Docker Compose: Single-Node MinIO

```yaml
# docker-compose.yml
version: "3.8"

services:
  minio:
    image: minio/minio:RELEASE.2024-01-01T00-00-00Z
    container_name: minio-evidence
    restart: unless-stopped
    ports:
      - "9000:9000"   # S3 API
      - "9001:9001"   # Web console
    environment:
      MINIO_ROOT_USER: ${MINIO_ROOT_USER}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD}
      # Enable audit logging
      MINIO_AUDIT_WEBHOOK_ENABLE_target1: "on"
      MINIO_AUDIT_WEBHOOK_ENDPOINT_target1: "http://audit-receiver:8080/audit"
    volumes:
      - minio-data:/data
    command: server /data --console-address ":9001"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 30s
      timeout: 20s
      retries: 3

volumes:
  minio-data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /opt/minio/data
```

> **Note**: For production, bind-mount `/opt/minio/data` to a dedicated disk or NFS share.
> Pin the image tag to a specific release rather than `latest` for reproducibility.

---

## Bucket Creation

Use the MinIO client (`mc`) to create buckets with object locking enabled. Object locking
**must** be enabled at bucket creation time and cannot be added later.

```bash
# Configure mc alias
mc alias set evidence-store http://localhost:9000 \
  "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}"

# Create buckets with object locking (required for WORM)
mc mb --with-lock evidence-store/evidence-records
mc mb --with-lock evidence-store/traceability-matrices
mc mb --with-lock evidence-store/approval-ledgers

# Enable versioning (required alongside object locking)
mc version enable evidence-store/evidence-records
mc version enable evidence-store/traceability-matrices
mc version enable evidence-store/approval-ledgers

# Verify
mc ls evidence-store
mc stat evidence-store/evidence-records
```

---

## Object Locking: WORM Configuration

WORM (Write Once Read Many) prevents modification or deletion of stored evidence, satisfying
immutability requirements for IEC 62304 and ISO 26262 audits.

```bash
# Set default retention: COMPLIANCE mode, 10 years (3650 days)
# COMPLIANCE mode: even the root user cannot delete locked objects before expiry
mc retention set --default COMPLIANCE "10y" evidence-store/evidence-records
mc retention set --default COMPLIANCE "10y" evidence-store/traceability-matrices
mc retention set --default COMPLIANCE "10y" evidence-store/approval-ledgers

# Verify retention settings
mc retention info evidence-store/evidence-records
```

**Retention modes:**

| Mode        | Description                                              |
|-------------|----------------------------------------------------------|
| COMPLIANCE  | No user, including root, can delete before expiry        |
| GOVERNANCE  | Root/privileged users can override (not recommended here)|

Use `COMPLIANCE` mode for regulatory evidence. This aligns with:
- **IEC 62304**: Minimum 10-year retention for software lifecycle documentation
- **ISO 26262**: Vehicle lifetime retention (configure as 15 years where required)
- **DO-178C**: Aircraft lifetime retention (configure per program schedule)

---

## Lifecycle Policies

Apply lifecycle policies for archival tiering and automatic deletion after the maximum
regulatory window.

```json
{
  "Rules": [
    {
      "ID": "archive-after-2-years",
      "Status": "Enabled",
      "Filter": {
        "Prefix": ""
      },
      "Transition": {
        "Days": 730,
        "StorageClass": "GLACIER"
      }
    },
    {
      "ID": "expire-after-15-years",
      "Status": "Enabled",
      "Filter": {
        "Prefix": ""
      },
      "Expiration": {
        "Days": 5475
      }
    },
    {
      "ID": "clean-incomplete-multipart",
      "Status": "Enabled",
      "Filter": {
        "Prefix": ""
      },
      "AbortIncompleteMultipartUpload": {
        "DaysAfterInitiation": 7
      }
    }
  ]
}
```

```bash
# Save the above JSON as lifecycle.json, then apply:
mc ilm import evidence-store/evidence-records < lifecycle.json
mc ilm import evidence-store/traceability-matrices < lifecycle.json
mc ilm import evidence-store/approval-ledgers < lifecycle.json

# Verify
mc ilm ls evidence-store/evidence-records
```

> **ISO 26262 note**: Set `Expiration.Days` to `5475` (15 years) for vehicle-lifetime programs.
> Override per bucket as needed.

---

## Bucket Policies

### Auditor Policy (read-only)

Grants read-only access to auditor accounts across all three evidence buckets.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AuditorReadOnly",
      "Effect": "Allow",
      "Principal": {
        "AWS": ["arn:aws:iam:::user/auditor"]
      },
      "Action": [
        "s3:GetObject",
        "s3:GetObjectVersion",
        "s3:GetObjectRetention",
        "s3:ListBucket",
        "s3:ListBucketVersions",
        "s3:GetBucketObjectLockConfiguration"
      ],
      "Resource": [
        "arn:aws:s3:::evidence-records",
        "arn:aws:s3:::evidence-records/*",
        "arn:aws:s3:::traceability-matrices",
        "arn:aws:s3:::traceability-matrices/*",
        "arn:aws:s3:::approval-ledgers",
        "arn:aws:s3:::approval-ledgers/*"
      ]
    }
  ]
}
```

### CI/CD Service Account Policy (write-only, no delete)

Allows the CI/CD pipeline to upload objects but not read, list, or delete them.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CICDWriteOnly",
      "Effect": "Allow",
      "Principal": {
        "AWS": ["arn:aws:iam:::user/cicd-service"]
      },
      "Action": [
        "s3:PutObject",
        "s3:PutObjectRetention",
        "s3:GetBucketObjectLockConfiguration"
      ],
      "Resource": [
        "arn:aws:s3:::evidence-records/*",
        "arn:aws:s3:::traceability-matrices/*",
        "arn:aws:s3:::approval-ledgers/*"
      ]
    },
    {
      "Sid": "DenyDelete",
      "Effect": "Deny",
      "Principal": {
        "AWS": ["arn:aws:iam:::user/cicd-service"]
      },
      "Action": [
        "s3:DeleteObject",
        "s3:DeleteObjectVersion"
      ],
      "Resource": [
        "arn:aws:s3:::evidence-records/*",
        "arn:aws:s3:::traceability-matrices/*",
        "arn:aws:s3:::approval-ledgers/*"
      ]
    }
  ]
}
```

```bash
# Create service accounts
mc admin user add evidence-store auditor "${AUDITOR_PASSWORD}"
mc admin user add evidence-store cicd-service "${CICD_PASSWORD}"

# Apply policies
mc admin policy create evidence-store auditor-policy auditor-policy.json
mc admin policy create evidence-store cicd-policy cicd-policy.json

mc admin policy attach evidence-store auditor-policy --user auditor
mc admin policy attach evidence-store cicd-policy --user cicd-service
```

---

## Integrity Verification

MinIO automatically computes and stores an MD5 ETag for every uploaded object. For stronger
integrity guarantees, use SHA-256 checksums at upload time.

```bash
# Upload with SHA-256 checksum
aws s3 cp evidence.zip s3://evidence-records/v1.0.0/evidence.zip \
  --endpoint-url http://localhost:9000 \
  --checksum-algorithm SHA256

# Verify ETag after upload
mc stat evidence-store/evidence-records/v1.0.0/evidence.zip
```

Versioning ensures every overwrite creates a new version rather than replacing the object,
providing a complete audit trail of all uploads to each key.

---

## GitHub Actions Integration

MinIO is S3-compatible, so the standard `aws` CLI works without modification. Store credentials
as GitHub Actions secrets.

```yaml
# .github/workflows/upload-evidence.yml
- name: Upload evidence package to MinIO
  env:
    AWS_ACCESS_KEY_ID: ${{ secrets.MINIO_CICD_ACCESS_KEY }}
    AWS_SECRET_ACCESS_KEY: ${{ secrets.MINIO_CICD_SECRET_KEY }}
    AWS_DEFAULT_REGION: us-east-1
  run: |
    aws s3 cp evidence-package.zip \
      s3://evidence-records/${{ github.ref_name }}/evidence-package.zip \
      --endpoint-url ${{ secrets.MINIO_ENDPOINT }} \
      --checksum-algorithm SHA256

    # Verify upload integrity
    aws s3api head-object \
      --bucket evidence-records \
      --key "${{ github.ref_name }}/evidence-package.zip" \
      --endpoint-url ${{ secrets.MINIO_ENDPOINT }}
```

**Required GitHub Actions secrets:**

| Secret                    | Description                          |
|---------------------------|--------------------------------------|
| `MINIO_ENDPOINT`          | `http://minio.internal:9000`         |
| `MINIO_CICD_ACCESS_KEY`   | CI/CD service account access key     |
| `MINIO_CICD_SECRET_KEY`   | CI/CD service account secret key     |

---

## Backup: MinIO Site Replication

Configure active-active replication to a secondary MinIO instance for disaster recovery.

```bash
# Add both sites to replication group
mc admin replicate add \
  evidence-store-primary \
  evidence-store-secondary

# Verify replication status
mc admin replicate info evidence-store-primary
mc admin replicate status evidence-store-primary
```

For one-way replication (primary to DR site only):

```bash
mc replicate add evidence-store/evidence-records \
  --remote-bucket s3://evidence-records-dr \
  --endpoint http://minio-dr.internal:9000 \
  --access-key "${DR_ACCESS_KEY}" \
  --secret-key "${DR_SECRET_KEY}" \
  --replicate "delete,delete-marker,existing-objects"
```

---

## AWS S3 Equivalent Configuration

For teams using AWS S3 instead of self-hosted MinIO, the equivalent configuration is below.

### S3 Bucket Creation with Object Lock

```bash
aws s3api create-bucket \
  --bucket evidence-records-prod \
  --region us-east-1 \
  --object-lock-enabled-for-bucket

aws s3api put-bucket-versioning \
  --bucket evidence-records-prod \
  --versioning-configuration Status=Enabled
```

### S3 Object Lock Configuration (JSON)

```json
{
  "ObjectLockEnabled": "Enabled",
  "Rule": {
    "DefaultRetention": {
      "Mode": "COMPLIANCE",
      "Years": 10
    }
  }
}
```

```bash
aws s3api put-object-lock-configuration \
  --bucket evidence-records-prod \
  --object-lock-configuration file://object-lock.json
```

### S3 Lifecycle Policy (JSON)

```json
{
  "Rules": [
    {
      "ID": "transition-to-glacier",
      "Status": "Enabled",
      "Filter": {"Prefix": ""},
      "Transitions": [
        {
          "Days": 730,
          "StorageClass": "GLACIER"
        }
      ]
    },
    {
      "ID": "expire-after-15-years",
      "Status": "Enabled",
      "Filter": {"Prefix": ""},
      "Expiration": {"Days": 5475}
    }
  ]
}
```

```bash
aws s3api put-bucket-lifecycle-configuration \
  --bucket evidence-records-prod \
  --lifecycle-configuration file://lifecycle.json
```

### S3 Bucket Policy (JSON)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyNonTLSAccess",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": [
        "arn:aws:s3:::evidence-records-prod",
        "arn:aws:s3:::evidence-records-prod/*"
      ],
      "Condition": {
        "Bool": {"aws:SecureTransport": "false"}
      }
    },
    {
      "Sid": "AuditorReadOnly",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::123456789012:role/AuditorRole"
      },
      "Action": [
        "s3:GetObject",
        "s3:GetObjectVersion",
        "s3:ListBucket",
        "s3:ListBucketVersions"
      ],
      "Resource": [
        "arn:aws:s3:::evidence-records-prod",
        "arn:aws:s3:::evidence-records-prod/*"
      ]
    }
  ]
}
```

---

## Checklist

- [ ] MinIO deployed with pinned image tag
- [ ] All three buckets created with `--with-lock` flag
- [ ] Versioning enabled on all buckets
- [ ] COMPLIANCE retention set to minimum 10 years
- [ ] Auditor policy applied (read-only)
- [ ] CI/CD service account policy applied (write-only, deny delete)
- [ ] Lifecycle policy applied for archival and expiry
- [ ] GitHub Actions secrets configured
- [ ] Replication to secondary site verified
- [ ] Integrity check (ETag / SHA-256) validated on test upload
