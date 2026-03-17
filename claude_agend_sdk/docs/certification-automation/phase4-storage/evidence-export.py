#!/usr/bin/env python3
"""
evidence-export.py - Package and export release certification evidence.

Usage:
    python evidence-export.py --release-tag v1.0.0 --github-repo owner/repo \
        --jira-project PROJ [--output-dir ./export] [--format zip|tar]

Environment variables:
    GITHUB_TOKEN      - GitHub personal access token (required)
    JIRA_URL          - Jira base URL, e.g. https://org.atlassian.net (required)
    JIRA_USER         - Jira user email (required)
    JIRA_API_TOKEN    - Jira API token (required)
    S3_BUCKET         - MinIO/S3 bucket name (optional; triggers upload if set)
    S3_ENDPOINT_URL   - Override S3 endpoint for MinIO (optional)
    AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY - S3 credentials (optional)
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def require_env(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        print(f"ERROR: required environment variable {name} is not set.", file=sys.stderr)
        sys.exit(1)
    return val


# ---------------------------------------------------------------------------
# GitHub API client
# ---------------------------------------------------------------------------

class GitHubClient:
    def __init__(self, token: str, repo: str):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        self.repo = repo
        self.base = "https://api.github.com"

    def get(self, path: str, params: dict | None = None) -> Any:
        url = f"{self.base}{path}"
        r = self.session.get(url, params=params)
        r.raise_for_status()
        return r.json()

    def paginate(self, path: str, params: dict | None = None) -> list:
        params = dict(params or {})
        params.setdefault("per_page", 100)
        results = []
        page = 1
        while True:
            params["page"] = page
            data = self.get(path, params)
            if not data:
                break
            results.extend(data)
            if len(data) < params["per_page"]:
                break
            page += 1
        return results

    def get_release_by_tag(self, tag: str) -> dict:
        return self.get(f"/repos/{self.repo}/releases/tags/{tag}")

    def list_artifacts(self) -> list:
        data = self.get(f"/repos/{self.repo}/actions/artifacts", params={"per_page": 100})
        return data.get("artifacts", [])

    def download_artifact(self, artifact_id: int, dest_dir: Path) -> Path:
        """Download a zip artifact and extract it into dest_dir."""
        url = f"{self.base}/repos/{self.repo}/actions/artifacts/{artifact_id}/zip"
        r = self.session.get(url, stream=True)
        r.raise_for_status()
        zip_path = dest_dir / f"artifact-{artifact_id}.zip"
        with open(zip_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)
        extract_dir = dest_dir / f"artifact-{artifact_id}"
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)
        zip_path.unlink()
        return extract_dir

    def list_prs_in_release(self, tag: str) -> list[dict]:
        """
        Return merged PRs whose merge_commit_sha appears in the commit range
        between the previous release and this tag.
        Falls back to listing all closed PRs sorted by merged_at if no previous
        release is found.
        """
        releases = self.paginate(f"/repos/{self.repo}/releases")
        sorted_releases = sorted(
            [r for r in releases if not r["draft"] and not r["prerelease"]],
            key=lambda r: r["published_at"],
        )
        tag_names = [r["tag_name"] for r in sorted_releases]
        previous_tag = None
        if tag in tag_names:
            idx = tag_names.index(tag)
            if idx > 0:
                previous_tag = tag_names[idx - 1]

        if previous_tag:
            comparison = self.get(
                f"/repos/{self.repo}/compare/{previous_tag}...{tag}"
            )
            commit_shas = {c["sha"] for c in comparison.get("commits", [])}
        else:
            commit_shas = None

        all_prs = self.paginate(
            f"/repos/{self.repo}/pulls",
            params={"state": "closed", "sort": "updated", "direction": "desc"},
        )
        merged_prs = [pr for pr in all_prs if pr.get("merged_at")]

        if commit_shas is not None:
            merged_prs = [
                pr for pr in merged_prs
                if pr.get("merge_commit_sha") in commit_shas
            ]

        return merged_prs

    def get_pr_ci_summary(self, pr_number: int) -> dict:
        """Return a dict summarising CI check runs for a PR's head SHA."""
        pr = self.get(f"/repos/{self.repo}/pulls/{pr_number}")
        head_sha = pr["head"]["sha"]
        check_runs_data = self.get(
            f"/repos/{self.repo}/commits/{head_sha}/check-runs",
            params={"per_page": 100},
        )
        check_runs = check_runs_data.get("check_runs", [])
        return {
            "pr_number": pr_number,
            "pr_title": pr["title"],
            "head_sha": head_sha,
            "merged_at": pr.get("merged_at"),
            "check_runs": [
                {
                    "name": cr["name"],
                    "status": cr["status"],
                    "conclusion": cr.get("conclusion"),
                    "started_at": cr.get("started_at"),
                    "completed_at": cr.get("completed_at"),
                }
                for cr in check_runs
            ],
            "all_passed": all(
                cr.get("conclusion") in ("success", "skipped", "neutral")
                for cr in check_runs
                if cr["status"] == "completed"
            ),
        }


# ---------------------------------------------------------------------------
# Evidence record artifact download
# ---------------------------------------------------------------------------

def download_evidence_artifacts(
    gh: GitHubClient,
    release_tag: str,
    dest_dir: Path,
) -> list[Path]:
    """Download all artifacts whose name starts with 'evidence-record-'."""
    log("Fetching artifact list from GitHub Actions...")
    artifacts = gh.list_artifacts()
    evidence_artifacts = [
        a for a in artifacts
        if a["name"].startswith("evidence-record-")
        and not a["expired"]
    ]
    log(f"Found {len(evidence_artifacts)} evidence-record artifact(s).")

    downloaded: list[Path] = []
    for artifact in evidence_artifacts:
        log(f"  Downloading artifact: {artifact['name']} (id={artifact['id']})")
        extract_dir = gh.download_artifact(artifact["id"], dest_dir)
        for json_file in extract_dir.rglob("*.json"):
            target = dest_dir / "evidence-records" / json_file.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(json_file, target)
            downloaded.append(target)

    return downloaded


# ---------------------------------------------------------------------------
# Subprocess helpers for traceability_matrix.py and approval_collector.py
# ---------------------------------------------------------------------------

def run_traceability_matrix(
    release_tag: str,
    jira_project: str,
    github_repo: str,
    output_dir: Path,
) -> Path | None:
    """Call traceability_matrix.py and return the output file path."""
    script = Path(__file__).parent.parent / "phase3-evidence" / "scripts" / "traceability_matrix.py"
    if not script.exists():
        log(f"WARNING: traceability_matrix.py not found at {script}; skipping.")
        return None

    out_file = output_dir / f"traceability-matrix-{release_tag}.json"
    cmd = [
        sys.executable, str(script),
        "--release-tag", release_tag,
        "--jira-project", jira_project,
        "--github-repo", github_repo,
        "--output", str(out_file),
    ]
    log(f"Running traceability matrix: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log(f"ERROR: traceability_matrix.py failed:\n{result.stderr}")
        return None
    log("Traceability matrix generated.")
    return out_file if out_file.exists() else None


def run_approval_collector(
    release_tag: str,
    jira_project: str,
    github_repo: str,
    output_dir: Path,
) -> Path | None:
    """Call approval_collector.py and return the output file path."""
    script = Path(__file__).parent.parent / "phase3-evidence" / "scripts" / "approval_collector.py"
    if not script.exists():
        log(f"WARNING: approval_collector.py not found at {script}; skipping.")
        return None

    out_file = output_dir / f"approval-ledger-{release_tag}.json"
    cmd = [
        sys.executable, str(script),
        "--release-tag", release_tag,
        "--jira-project", jira_project,
        "--github-repo", github_repo,
        "--output", str(out_file),
    ]
    log(f"Running approval collector: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log(f"ERROR: approval_collector.py failed:\n{result.stderr}")
        return None
    log("Approval ledger generated.")
    return out_file if out_file.exists() else None


# ---------------------------------------------------------------------------
# CI summary collection
# ---------------------------------------------------------------------------

def collect_ci_summary(
    gh: GitHubClient,
    prs: list[dict],
    output_dir: Path,
    release_tag: str,
) -> Path:
    log(f"Collecting CI summary for {len(prs)} PR(s)...")
    summaries = []
    for pr in prs:
        pr_number = pr["number"]
        log(f"  PR #{pr_number}: {pr['title']}")
        summary = gh.get_pr_ci_summary(pr_number)
        summaries.append(summary)

    out_file = output_dir / f"ci-summary-{release_tag}.json"
    out_file.write_text(json.dumps(summaries, indent=2))
    log(f"CI summary written: {out_file}")
    return out_file


# ---------------------------------------------------------------------------
# Manifest generation
# ---------------------------------------------------------------------------

def build_manifest(
    release_tag: str,
    package_sha256: str,
    contents: list[dict],
    total_tickets: int,
    total_prs: int,
) -> dict:
    return {
        "release_tag": release_tag,
        "packaged_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "package_sha256": package_sha256,
        "contents": contents,
        "standards_covered": ["IEC_62304", "ISO_26262"],
        "total_tickets": total_tickets,
        "total_prs": total_prs,
    }


def make_content_entry(file_path: Path, content_type: str, base_dir: Path) -> dict:
    relative = str(file_path.relative_to(base_dir))
    return {
        "type": content_type,
        "file": relative,
        "sha256": sha256_of_file(file_path),
    }


# ---------------------------------------------------------------------------
# Packaging
# ---------------------------------------------------------------------------

def create_zip(stage_dir: Path, output_path: Path) -> None:
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(stage_dir.rglob("*")):
            if file.is_file():
                zf.write(file, file.relative_to(stage_dir))


def create_tar(stage_dir: Path, output_path: Path) -> None:
    with tarfile.open(output_path, "w:gz") as tf:
        for file in sorted(stage_dir.rglob("*")):
            if file.is_file():
                tf.add(file, arcname=file.relative_to(stage_dir))


# ---------------------------------------------------------------------------
# S3 / MinIO upload
# ---------------------------------------------------------------------------

def upload_to_s3(
    local_path: Path,
    bucket: str,
    release_tag: str,
    endpoint_url: str | None,
) -> None:
    import boto3
    from botocore.config import Config

    log(f"Uploading {local_path.name} to s3://{bucket}/{release_tag}/...")

    kwargs: dict[str, Any] = {
        "config": Config(signature_version="s3v4"),
    }
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url

    s3 = boto3.client("s3", **kwargs)
    key = f"{release_tag}/{local_path.name}"

    with open(local_path, "rb") as f:
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=f,
            ChecksumAlgorithm="SHA256",
        )

    log(f"Uploaded to s3://{bucket}/{key}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Package and export release certification evidence."
    )
    parser.add_argument("--release-tag", required=True, help="Git release tag, e.g. v1.0.0")
    parser.add_argument("--github-repo", required=True, help="GitHub repo in owner/repo format")
    parser.add_argument("--jira-project", required=True, help="Jira project key, e.g. PROJ")
    parser.add_argument("--output-dir", default="./export", help="Local output directory")
    parser.add_argument(
        "--format",
        choices=["zip", "tar"],
        default="zip",
        help="Archive format (default: zip)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    release_tag = args.release_tag
    github_repo = args.github_repo
    jira_project = args.jira_project
    output_dir = Path(args.output_dir).resolve()
    archive_format = args.format

    github_token = require_env("GITHUB_TOKEN")
    s3_bucket = os.environ.get("S3_BUCKET", "").strip() or None
    s3_endpoint = os.environ.get("S3_ENDPOINT_URL", "").strip() or None

    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="evidence-export-") as tmpdir:
        stage_dir = Path(tmpdir) / release_tag
        stage_dir.mkdir()

        gh = GitHubClient(token=github_token, repo=github_repo)

        # 1. Download GitHub Actions evidence-record artifacts
        log("Step 1: Downloading evidence-record artifacts...")
        evidence_files = download_evidence_artifacts(gh, release_tag, stage_dir)

        # 2. Generate traceability matrix
        log("Step 2: Generating traceability matrix...")
        traceability_file = run_traceability_matrix(
            release_tag, jira_project, github_repo, stage_dir
        )

        # 3. Generate approval ledger
        log("Step 3: Collecting approvals...")
        approval_file = run_approval_collector(
            release_tag, jira_project, github_repo, stage_dir
        )

        # 4. Collect CI summary for all PRs in release
        log("Step 4: Collecting CI summaries for release PRs...")
        prs = gh.list_prs_in_release(release_tag)
        ci_summary_file = collect_ci_summary(gh, prs, stage_dir, release_tag)

        # Build content entries (pre-manifest; package_sha256 is computed after packaging)
        contents: list[dict] = []

        for ef in evidence_files:
            contents.append(make_content_entry(ef, "evidence_record", stage_dir))

        if traceability_file and traceability_file.exists():
            contents.append(
                make_content_entry(traceability_file, "traceability_matrix", stage_dir)
            )

        if approval_file and approval_file.exists():
            contents.append(
                make_content_entry(approval_file, "approval_ledger", stage_dir)
            )

        contents.append(make_content_entry(ci_summary_file, "ci_summary", stage_dir))

        # Derive counts
        total_tickets = len(
            set(
                c["file"].split("/")[-1].split("-")[0]
                for c in contents
                if c["type"] == "evidence_record"
            )
        )
        total_prs = len(prs)

        # Write placeholder manifest (without package_sha256 yet)
        manifest_path = stage_dir / "index.json"
        placeholder_manifest = build_manifest(
            release_tag=release_tag,
            package_sha256="PLACEHOLDER",
            contents=contents,
            total_tickets=total_tickets,
            total_prs=total_prs,
        )
        manifest_path.write_text(json.dumps(placeholder_manifest, indent=2))

        # 6. Package
        log(f"Step 6: Packaging as {archive_format.upper()}...")
        if archive_format == "zip":
            archive_name = f"evidence-{release_tag}.zip"
            archive_path = output_dir / archive_name
            create_zip(stage_dir, archive_path)
        else:
            archive_name = f"evidence-{release_tag}.tar.gz"
            archive_path = output_dir / archive_name
            create_tar(stage_dir, archive_path)

        # Compute final SHA-256 of the archive
        pkg_sha256 = sha256_of_file(archive_path)

        # Rewrite manifest with real hash, then repackage
        final_manifest = build_manifest(
            release_tag=release_tag,
            package_sha256=pkg_sha256,
            contents=contents,
            total_tickets=total_tickets,
            total_prs=total_prs,
        )
        manifest_path.write_text(json.dumps(final_manifest, indent=2))

        # Re-package with the final manifest included
        if archive_format == "zip":
            create_zip(stage_dir, archive_path)
        else:
            create_tar(stage_dir, archive_path)

        final_sha256 = sha256_of_file(archive_path)
        log(f"Package created: {archive_path}")
        log(f"SHA-256: {final_sha256}")

        # 7. Upload to MinIO/S3 if configured
        if s3_bucket:
            log("Step 7: Uploading to S3/MinIO...")
            upload_to_s3(archive_path, s3_bucket, release_tag, s3_endpoint)
        else:
            log("Step 7: S3_BUCKET not set; skipping upload.")

        # 8. Print summary
        file_count = len(contents)
        print("\n" + "=" * 60)
        print(f"EVIDENCE PACKAGE SUMMARY")
        print("=" * 60)
        print(f"  Release tag   : {release_tag}")
        print(f"  Archive       : {archive_path}")
        print(f"  Format        : {archive_format.upper()}")
        print(f"  SHA-256       : {final_sha256}")
        print(f"  Files packed  : {file_count}")
        print(f"  Total tickets : {total_tickets}")
        print(f"  Total PRs     : {total_prs}")
        print(f"  Standards     : IEC_62304, ISO_26262")
        if s3_bucket:
            print(f"  Uploaded to   : s3://{s3_bucket}/{release_tag}/{archive_name}")
        print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
