#!/usr/bin/env python3
"""
approval_collector.py

Collects and reconciles all software approval evidence from JIRA and GitHub,
producing a tamper-evident approval ledger for certification purposes.

Usage:
    python approval_collector.py \
        --jira-project PROJ \
        --github-repo owner/repo \
        --release-tag v1.0.0 \
        [--start-date 2024-01-01] \
        [--output-file approvals.json]

Environment Variables:
    JIRA_BASE_URL     e.g. https://yourorg.atlassian.net
    JIRA_EMAIL        Atlassian account email
    JIRA_API_TOKEN    Atlassian API token
    GITHUB_TOKEN      GitHub personal access token or app token
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any


try:
    import httpx
except ImportError:
    sys.exit("Missing dependency: pip install httpx")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

JIRA_RATE_LIMIT_DELAY = 1.0          # seconds between JIRA requests
GITHUB_RATE_LIMIT_DELAY = 0.72       # ~5000 req/hour
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2

JIRA_APPROVED_STATUSES = {"approved", "merged", "done", "closed", "released"}
JIRA_TRANSITION_TARGETS = {"approved", "merged"}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class JiraApproval:
    ticket_id: str
    ticket_summary: str
    approver: str           # displayName or accountId
    approved_at: str        # ISO-8601
    from_status: str
    to_status: str


@dataclass
class GitHubApproval:
    pr_number: int
    pr_url: str
    pr_title: str
    reviewer: str           # GitHub login
    approved_at: str        # ISO-8601
    commit_sha: str         # HEAD SHA at time of review
    merged_at: Optional[str]
    merge_commit_sha: Optional[str]
    linked_jira_keys: List[str] = field(default_factory=list)


@dataclass
class ApprovalRecord:
    """Merged approval ledger entry - one record per JIRA ticket."""
    ticket_id: str
    pr_url: str
    pr_number: Optional[int]
    jira_approver: str
    jira_approved_at: str
    github_approver: str
    github_approved_at: str
    code_merged_at: str
    merge_commit_sha: str
    discrepancies: List[str] = field(default_factory=list)
    record_hash: str = ""   # SHA-256 of the record contents (set after creation)

    def compute_hash(self) -> str:
        """Compute SHA-256 over all meaningful fields for tamper detection."""
        payload = "|".join([
            self.ticket_id,
            self.pr_url,
            self.jira_approver,
            self.jira_approved_at,
            self.github_approver,
            self.github_approved_at,
            self.code_merged_at,
            self.merge_commit_sha,
        ])
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def seal(self) -> None:
        self.record_hash = self.compute_hash()

    def verify(self) -> bool:
        return self.record_hash == self.compute_hash()


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", file=sys.stderr)


def _retry_request(
    client: httpx.Client,
    method: str,
    url: str,
    delay: float,
    **kwargs,
) -> httpx.Response:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            time.sleep(delay)
            resp = client.request(method, url, **kwargs)
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", RETRY_BACKOFF_BASE ** attempt))
                _log(f"Rate limited. Waiting {retry_after}s...")
                time.sleep(retry_after)
                continue
            if resp.status_code >= 500:
                wait = RETRY_BACKOFF_BASE ** attempt
                _log(f"Server error {resp.status_code}. Retry {attempt}/{MAX_RETRIES} in {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        except httpx.RequestError as exc:
            if attempt == MAX_RETRIES:
                raise
            wait = RETRY_BACKOFF_BASE ** attempt
            _log(f"Request error: {exc}. Retry {attempt}/{MAX_RETRIES} in {wait}s...")
            time.sleep(wait)
    raise RuntimeError(f"Failed after {MAX_RETRIES} retries: {url}")


# ---------------------------------------------------------------------------
# JIRA client
# ---------------------------------------------------------------------------

class JiraClient:
    def __init__(self, base_url: str, email: str, api_token: str):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(
            auth=(email, api_token),
            headers={"Accept": "application/json"},
            timeout=30,
        )

    def _get(self, path: str, params: Optional[Dict] = None) -> Any:
        url = f"{self.base_url}/rest/api/3/{path}"
        resp = _retry_request(self.client, "GET", url, JIRA_RATE_LIMIT_DELAY, params=params)
        return resp.json()

    def search_issues(self, jql: str, max_results: int = 100) -> List[Dict]:
        all_issues: List[Dict] = []
        start_at = 0
        while True:
            data = self._get("search", params={
                "jql": jql,
                "fields": "*all",
                "expand": "changelog",
                "startAt": start_at,
                "maxResults": max_results,
            })
            issues = data.get("issues", [])
            all_issues.extend(issues)
            total = data.get("total", 0)
            start_at += len(issues)
            if start_at >= total or not issues:
                break
        return all_issues

    def get_changelog(self, issue_key: str) -> List[Dict]:
        """Return all changelog history entries for an issue."""
        data = self._get(f"issue/{issue_key}", params={"expand": "changelog", "fields": "summary,status"})
        return data.get("changelog", {}).get("histories", [])

    def get_summary(self, issue_key: str) -> str:
        try:
            data = self._get(f"issue/{issue_key}", params={"fields": "summary"})
            return data.get("fields", {}).get("summary", "")
        except Exception:
            return ""


# ---------------------------------------------------------------------------
# GitHub client
# ---------------------------------------------------------------------------

class GitHubClient:
    BASE = "https://api.github.com"

    def __init__(self, token: str):
        self.client = httpx.Client(
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30,
        )

    def _get(self, path: str, params: Optional[Dict] = None) -> Any:
        url = f"{self.BASE}/{path.lstrip('/')}"
        resp = _retry_request(self.client, "GET", url, GITHUB_RATE_LIMIT_DELAY, params=params)
        return resp.json()

    def _paginate(self, path: str, params: Optional[Dict] = None) -> List[Any]:
        params = dict(params or {})
        params.setdefault("per_page", 100)
        results: List[Any] = []
        page = 1
        while True:
            params["page"] = page
            data = self._get(path, params=params)
            if not data or not isinstance(data, list):
                break
            results.extend(data)
            if len(data) < params["per_page"]:
                break
            page += 1
        return results

    def list_merged_prs(self, repo: str, since: Optional[str] = None) -> List[Dict]:
        """Search for merged PRs, optionally filtered by date."""
        q = f"repo:{repo} is:pr is:merged"
        if since:
            q += f" merged:>={since}"
        data = self._get("search/issues", params={"q": q, "per_page": 100, "sort": "updated"})
        items = data.get("items", [])
        # search/issues returns PR stubs; fetch full PR details
        full_prs = []
        for item in items:
            pr_num = item.get("number")
            try:
                full_prs.append(self._get(f"repos/{repo}/pulls/{pr_num}"))
            except Exception as exc:
                _log(f"  Warning: could not fetch PR #{pr_num}: {exc}")
        return full_prs

    def get_pr_reviews(self, repo: str, pr_number: int) -> List[Dict]:
        return self._paginate(f"repos/{repo}/pulls/{pr_number}/reviews")

    def get_release_prs(self, repo: str, tag: str) -> List[Dict]:
        """
        Get PRs included in a release by comparing the release tag to its
        previous tag (or the tag's commit ancestry).
        """
        try:
            release = self._get(f"repos/{repo}/releases/tags/{tag}")
            target_sha = release.get("target_commitish", "")
        except Exception:
            target_sha = tag

        # List all merged PRs associated with the commit range
        # GitHub doesn't have a direct "PRs in release" API, so we use
        # the compare endpoint against the previous release.
        try:
            releases = self._get(f"repos/{repo}/releases", params={"per_page": 10})
            if isinstance(releases, list) and len(releases) >= 2:
                # Find position of current tag
                tags = [r.get("tag_name") for r in releases]
                if tag in tags:
                    idx = tags.index(tag)
                    if idx + 1 < len(tags):
                        prev_tag = tags[idx + 1]
                        compare = self._get(f"repos/{repo}/compare/{prev_tag}...{tag}")
                        commits = compare.get("commits", [])
                        shas = {c["sha"] for c in commits}
                        # Search for merged PRs whose merge commit is in range
                        prs = self.list_merged_prs(repo)
                        return [p for p in prs if p.get("merge_commit_sha") in shas]
        except Exception as exc:
            _log(f"  Warning: could not narrow PRs to release range: {exc}")

        return self.list_merged_prs(repo)


# ---------------------------------------------------------------------------
# JIRA approval collection
# ---------------------------------------------------------------------------

def extract_jira_keys(text: str, project: str) -> List[str]:
    pattern = rf"\b{re.escape(project)}-\d+\b"
    return list(set(re.findall(pattern, text or "")))


def collect_jira_approvals(
    jira: JiraClient,
    project: str,
    release_tag: str,
    start_date: Optional[str],
) -> List[JiraApproval]:
    """
    Fetch all JIRA issues in the project and extract changelog transitions
    to approved/merged statuses.
    """
    _log("Fetching JIRA issues...")

    version_clean = release_tag.lstrip("v")
    jql_parts = [f'project = "{project}"']
    version_filter = (
        f'(fixVersion = "{release_tag}" OR fixVersion = "{version_clean}" '
        f'OR labels = "{release_tag}")'
    )
    jql_parts.append(version_filter)
    if start_date:
        jql_parts.append(f'updated >= "{start_date}"')

    jql = " AND ".join(jql_parts)
    _log(f"JQL: {jql}")

    try:
        issues = jira.search_issues(jql)
    except Exception as exc:
        _log(f"Warning: filtered JQL failed ({exc}). Using project-wide fallback.")
        fallback = f'project = "{project}"'
        if start_date:
            fallback += f' AND updated >= "{start_date}"'
        issues = jira.search_issues(fallback)

    _log(f"Found {len(issues)} JIRA issues.")

    approvals: List[JiraApproval] = []
    for issue in issues:
        key = issue["key"]
        summary = issue.get("fields", {}).get("summary", "")
        changelog = issue.get("changelog", {}).get("histories", [])

        for history in changelog:
            author = history.get("author", {})
            author_name = author.get("displayName") or author.get("emailAddress") or author.get("accountId", "unknown")
            created = history.get("created", "")

            for item in history.get("items", []):
                if item.get("field", "").lower() != "status":
                    continue
                to_str = (item.get("toString") or "").lower()
                from_str = (item.get("fromString") or "").lower()

                if to_str in JIRA_TRANSITION_TARGETS:
                    approvals.append(JiraApproval(
                        ticket_id=key,
                        ticket_summary=summary,
                        approver=author_name,
                        approved_at=created,
                        from_status=from_str,
                        to_status=to_str,
                    ))

    _log(f"Collected {len(approvals)} JIRA approval transitions.")
    return approvals


# ---------------------------------------------------------------------------
# GitHub approval collection
# ---------------------------------------------------------------------------

def collect_github_approvals(
    github: GitHubClient,
    repo: str,
    release_tag: str,
    start_date: Optional[str],
    project: str,
) -> List[GitHubApproval]:
    """
    Collect all APPROVED reviews from merged PRs in the release.
    Also extract linked JIRA keys from PR title and body.
    """
    _log("Fetching GitHub PRs for release...")
    prs = github.get_release_prs(repo, release_tag)
    _log(f"Found {len(prs)} merged PRs.")

    gh_approvals: List[GitHubApproval] = []

    for pr in prs:
        pr_number = pr.get("number")
        pr_url = pr.get("html_url", f"https://github.com/{repo}/pull/{pr_number}")
        pr_title = pr.get("title", "")
        merged_at = pr.get("merged_at")
        merge_sha = pr.get("merge_commit_sha")
        head_sha = pr.get("head", {}).get("sha", "")

        # Filter by start_date if provided
        if start_date and merged_at:
            if merged_at < start_date:
                continue

        # Extract linked JIRA keys from title + body
        body = pr.get("body") or ""
        linked_keys = extract_jira_keys(pr_title + " " + body, project)

        # Get reviews
        try:
            reviews = github.get_pr_reviews(repo, pr_number)
        except Exception as exc:
            _log(f"  Warning: could not fetch reviews for PR #{pr_number}: {exc}")
            reviews = []

        approved_reviews = [r for r in reviews if r.get("state") == "APPROVED"]

        if not approved_reviews:
            # Record a placeholder with no approver so we can detect discrepancies
            gh_approvals.append(GitHubApproval(
                pr_number=pr_number,
                pr_url=pr_url,
                pr_title=pr_title,
                reviewer="",
                approved_at="",
                commit_sha=head_sha,
                merged_at=merged_at,
                merge_commit_sha=merge_sha,
                linked_jira_keys=linked_keys,
            ))
        else:
            for review in approved_reviews:
                user = review.get("user", {})
                gh_approvals.append(GitHubApproval(
                    pr_number=pr_number,
                    pr_url=pr_url,
                    pr_title=pr_title,
                    reviewer=user.get("login", ""),
                    approved_at=review.get("submitted_at", ""),
                    commit_sha=head_sha,
                    merged_at=merged_at,
                    merge_commit_sha=merge_sha,
                    linked_jira_keys=linked_keys,
                ))

    _log(f"Collected {len(gh_approvals)} GitHub approval entries.")
    return gh_approvals


# ---------------------------------------------------------------------------
# Merge and reconcile
# ---------------------------------------------------------------------------

def build_approval_ledger(
    jira_approvals: List[JiraApproval],
    gh_approvals: List[GitHubApproval],
) -> List[ApprovalRecord]:
    """
    Correlate JIRA approvals with GitHub approvals by JIRA key.
    Produce one ApprovalRecord per (JIRA ticket, PR) pair.
    """
    # Index JIRA approvals by ticket_id
    jira_by_ticket: Dict[str, List[JiraApproval]] = {}
    for ja in jira_approvals:
        jira_by_ticket.setdefault(ja.ticket_id, []).append(ja)

    # Index GitHub approvals by linked JIRA key
    gh_by_jira_key: Dict[str, List[GitHubApproval]] = {}
    gh_unlinked: List[GitHubApproval] = []
    for ga in gh_approvals:
        if ga.linked_jira_keys:
            for key in ga.linked_jira_keys:
                gh_by_jira_key.setdefault(key, []).append(ga)
        else:
            gh_unlinked.append(ga)

    records: List[ApprovalRecord] = []
    processed_prs: set = set()

    # --- Tickets present in JIRA ---
    all_jira_keys = set(jira_by_ticket.keys()) | set(gh_by_jira_key.keys())

    for ticket_id in sorted(all_jira_keys):
        jira_entries = jira_by_ticket.get(ticket_id, [])
        gh_entries = gh_by_jira_key.get(ticket_id, [])

        # Pick the most recent JIRA approval
        best_jira: Optional[JiraApproval] = (
            max(jira_entries, key=lambda x: x.approved_at) if jira_entries else None
        )

        # For each GitHub PR linked to this ticket
        if not gh_entries:
            # JIRA approved but no GitHub PR found
            rec = ApprovalRecord(
                ticket_id=ticket_id,
                pr_url="",
                pr_number=None,
                jira_approver=best_jira.approver if best_jira else "",
                jira_approved_at=best_jira.approved_at if best_jira else "",
                github_approver="",
                github_approved_at="",
                code_merged_at="",
                merge_commit_sha="",
            )
            if best_jira:
                rec.discrepancies.append("JIRA approved but no linked GitHub PR found")
            else:
                rec.discrepancies.append("No JIRA approval and no GitHub PR found")
            rec.seal()
            records.append(rec)
        else:
            seen_prs: Dict[int, bool] = {}
            for ga in gh_entries:
                pr_key = (ticket_id, ga.pr_number)
                if pr_key in processed_prs:
                    continue
                processed_prs.add(pr_key)

                discrepancies: List[str] = []

                if not best_jira:
                    discrepancies.append("GitHub PR approved/merged but no JIRA approval transition found")

                if not ga.reviewer:
                    discrepancies.append("GitHub PR merged without a recorded APPROVE review")

                rec = ApprovalRecord(
                    ticket_id=ticket_id,
                    pr_url=ga.pr_url,
                    pr_number=ga.pr_number,
                    jira_approver=best_jira.approver if best_jira else "",
                    jira_approved_at=best_jira.approved_at if best_jira else "",
                    github_approver=ga.reviewer,
                    github_approved_at=ga.approved_at,
                    code_merged_at=ga.merged_at or "",
                    merge_commit_sha=ga.merge_commit_sha or "",
                    discrepancies=discrepancies,
                )
                rec.seal()
                records.append(rec)

    # --- GitHub PRs with no JIRA link at all ---
    for ga in gh_unlinked:
        pr_key = ("(unlinked)", ga.pr_number)
        if pr_key in processed_prs:
            continue
        processed_prs.add(pr_key)

        rec = ApprovalRecord(
            ticket_id="(unlinked)",
            pr_url=ga.pr_url,
            pr_number=ga.pr_number,
            jira_approver="",
            jira_approved_at="",
            github_approver=ga.reviewer,
            github_approved_at=ga.approved_at,
            code_merged_at=ga.merged_at or "",
            merge_commit_sha=ga.merge_commit_sha or "",
            discrepancies=["GitHub PR has no JIRA ticket link in title or body"],
        )
        rec.seal()
        records.append(rec)

    return records


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def write_json_ledger(records: List[ApprovalRecord], output_file: Optional[str]) -> None:
    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_records": len(records),
        "records": [asdict(r) for r in records],
    }
    text = json.dumps(data, indent=2, default=str)
    if output_file:
        with open(output_file, "w", encoding="utf-8") as fh:
            fh.write(text)
        _log(f"JSON ledger written to {output_file}")
    else:
        print(text)


def write_markdown_summary(
    records: List[ApprovalRecord],
    jira_approvals: List[JiraApproval],
    gh_approvals: List[GitHubApproval],
    output_file: Optional[str],
) -> None:
    lines = []
    lines.append("# Approval Ledger Summary\n")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}\n")
    lines.append("")

    total = len(records)
    discrepant = [r for r in records if r.discrepancies]
    clean = [r for r in records if not r.discrepancies]

    lines.append("## Statistics\n")
    lines.append(f"- Total approval records: **{total}**")
    lines.append(f"- Clean records (no discrepancies): **{len(clean)}**")
    lines.append(f"- Records with discrepancies: **{len(discrepant)}**")
    lines.append(f"- JIRA approval transitions collected: **{len(jira_approvals)}**")
    lines.append(f"- GitHub approval reviews collected: **{len(gh_approvals)}**")
    lines.append("")

    lines.append("## Approval Ledger\n")
    lines.append("| Ticket | PR | JIRA Approver | JIRA Approved At | GitHub Approver | GH Approved At | Merged At | Hash (first 12) |")
    lines.append("|--------|----|---------------|-----------------|----------------|----------------|-----------|-----------------|")

    for rec in records:
        pr_md = f"[#{rec.pr_number}]({rec.pr_url})" if rec.pr_url else "-"
        hash_short = rec.record_hash[:12] if rec.record_hash else "-"
        lines.append(
            f"| {rec.ticket_id} "
            f"| {pr_md} "
            f"| {rec.jira_approver or '-'} "
            f"| {rec.jira_approved_at[:10] if rec.jira_approved_at else '-'} "
            f"| {rec.github_approver or '-'} "
            f"| {rec.github_approved_at[:10] if rec.github_approved_at else '-'} "
            f"| {rec.code_merged_at[:10] if rec.code_merged_at else '-'} "
            f"| `{hash_short}` |"
        )

    if discrepant:
        lines.append("")
        lines.append("## Discrepancies\n")
        for rec in discrepant:
            pr_info = f" (PR #{rec.pr_number})" if rec.pr_number else ""
            lines.append(f"### {rec.ticket_id}{pr_info}\n")
            for d in rec.discrepancies:
                lines.append(f"- {d}")
            lines.append("")

    lines.append("\n## Integrity Verification\n")
    lines.append("Each record's `record_hash` is SHA-256 of:")
    lines.append("`ticket_id | pr_url | jira_approver | jira_approved_at | github_approver | github_approved_at | code_merged_at | merge_commit_sha`\n")
    lines.append("To verify a record, recompute the hash and compare.")

    text = "\n".join(lines) + "\n"

    md_path = None
    if output_file:
        # Write markdown alongside the JSON file
        if output_file.endswith(".json"):
            md_path = output_file.replace(".json", "_summary.md")
        else:
            md_path = output_file + "_summary.md"

    if md_path:
        with open(md_path, "w", encoding="utf-8") as fh:
            fh.write(text)
        _log(f"Markdown summary written to {md_path}")
    else:
        print("\n" + text, file=sys.stderr)


def print_console_summary(records: List[ApprovalRecord]) -> None:
    sep = "-" * 60
    total = len(records)
    discrepant = [r for r in records if r.discrepancies]
    print(sep, file=sys.stderr)
    print("APPROVAL COLLECTION SUMMARY", file=sys.stderr)
    print(sep, file=sys.stderr)
    print(f"  Total records      : {total}", file=sys.stderr)
    print(f"  Clean records      : {total - len(discrepant)}", file=sys.stderr)
    print(f"  With discrepancies : {len(discrepant)}", file=sys.stderr)
    if discrepant:
        print("  Discrepant tickets:", file=sys.stderr)
        for rec in discrepant:
            pr_info = f" PR#{rec.pr_number}" if rec.pr_number else ""
            print(f"    - {rec.ticket_id}{pr_info}: {'; '.join(rec.discrepancies)}", file=sys.stderr)
    print(sep, file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect and reconcile software approval evidence from JIRA and GitHub.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--jira-project", required=True, metavar="PROJ",
                        help="JIRA project key (e.g. MYPROJ)")
    parser.add_argument("--github-repo", required=True, metavar="owner/repo",
                        help="GitHub repository in owner/repo format")
    parser.add_argument("--release-tag", required=True, metavar="TAG",
                        help="Git release tag (e.g. v1.0.0)")
    parser.add_argument("--start-date", metavar="YYYY-MM-DD",
                        help="Only include approvals on or after this date")
    parser.add_argument("--output-file", metavar="FILE",
                        help="Write JSON approval ledger to FILE (also writes FILE_summary.md)")
    return parser.parse_args()


def load_env() -> Dict[str, str]:
    required = ["JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "GITHUB_TOKEN"]
    config: Dict[str, str] = {}
    missing = []
    for var in required:
        val = os.environ.get(var, "")
        if not val:
            missing.append(var)
        config[var] = val
    if missing:
        sys.exit(f"Missing required environment variables: {', '.join(missing)}")
    return config


def main() -> None:
    args = parse_args()
    env = load_env()

    _log("Initialising clients...")
    jira = JiraClient(env["JIRA_BASE_URL"], env["JIRA_EMAIL"], env["JIRA_API_TOKEN"])
    github = GitHubClient(env["GITHUB_TOKEN"])

    # --- Collect JIRA approvals ---
    jira_approvals = collect_jira_approvals(
        jira,
        args.jira_project,
        args.release_tag,
        args.start_date,
    )

    # --- Collect GitHub approvals ---
    gh_approvals = collect_github_approvals(
        github,
        args.github_repo,
        args.release_tag,
        args.start_date,
        args.jira_project,
    )

    # --- Merge and reconcile ---
    _log("Building approval ledger...")
    records = build_approval_ledger(jira_approvals, gh_approvals)

    # --- Output ---
    write_json_ledger(records, args.output_file)
    write_markdown_summary(records, jira_approvals, gh_approvals, args.output_file)
    print_console_summary(records)

    _log("Done.")


if __name__ == "__main__":
    main()
