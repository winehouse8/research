#!/usr/bin/env python3
"""
traceability_matrix.py

Generates a software certification traceability matrix by correlating
JIRA issues with GitHub pull requests, commits, CI results, and approvals.

Usage:
    python traceability_matrix.py \
        --jira-project PROJ \
        --github-repo owner/repo \
        --release-tag v1.0.0 \
        [--output-format csv|json|md] \
        [--output-file matrix.csv]

Environment Variables:
    JIRA_BASE_URL     e.g. https://yourorg.atlassian.net
    JIRA_EMAIL        Atlassian account email
    JIRA_API_TOKEN    Atlassian API token
    GITHUB_TOKEN      GitHub personal access token or app token
"""

import argparse
import csv
import json
import os
import sys
import time
import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from urllib.parse import quote

try:
    import httpx
except ImportError:
    sys.exit("Missing dependency: pip install httpx")

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

JIRA_RATE_LIMIT_DELAY = 1.0          # seconds between JIRA requests
GITHUB_MAX_REQUESTS_PER_HOUR = 5000
GITHUB_RATE_LIMIT_DELAY = 3600 / GITHUB_MAX_REQUESTS_PER_HOUR  # ~0.72 s

MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2  # exponential backoff base (seconds)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class Requirement:
    req_id: str
    summary: str
    jira_key: str


@dataclass
class TestCase:
    test_id: str
    summary: str
    status: str


@dataclass
class Commit:
    sha: str
    message: str
    author: str
    committed_at: str


@dataclass
class CIResult:
    name: str
    status: str       # success | failure | pending | skipped
    conclusion: str
    run_url: str


@dataclass
class Approval:
    reviewer: str
    approved_at: str
    review_state: str


@dataclass
class PullRequest:
    pr_number: int
    pr_url: str
    title: str
    merged_at: Optional[str]
    merge_commit_sha: Optional[str]
    commits: List[Commit] = field(default_factory=list)
    ci_results: List[CIResult] = field(default_factory=list)
    approvals: List[Approval] = field(default_factory=list)


@dataclass
class TraceabilityRecord:
    jira_key: str
    jira_summary: str
    jira_status: str
    requirements: List[Requirement] = field(default_factory=list)
    test_cases: List[TestCase] = field(default_factory=list)
    design_doc_links: List[str] = field(default_factory=list)
    pull_requests: List[PullRequest] = field(default_factory=list)

    # Derived / flattened fields for CSV output
    def flatten(self) -> List[Dict[str, Any]]:
        """Return one row per (requirement x PR x approver) combination."""
        rows = []
        req_ids = [r.req_id for r in self.requirements] or ["(none)"]
        test_results = self._aggregate_test_result()
        prs = self.pull_requests or [None]

        for req_id in req_ids:
            for pr in prs:
                if pr is None:
                    rows.append({
                        "req_id": req_id,
                        "jira_ticket": self.jira_key,
                        "jira_summary": self.jira_summary,
                        "pr_url": "",
                        "pr_merged_at": "",
                        "test_result": test_results,
                        "approver": "",
                        "approved_at": "",
                    })
                else:
                    approvers = pr.approvals or [None]
                    for approval in approvers:
                        rows.append({
                            "req_id": req_id,
                            "jira_ticket": self.jira_key,
                            "jira_summary": self.jira_summary,
                            "pr_url": pr.pr_url,
                            "pr_merged_at": pr.merged_at or "",
                            "test_result": test_results,
                            "approver": approval.reviewer if approval else "",
                            "approved_at": approval.approved_at if approval else "",
                        })
        return rows

    def _aggregate_test_result(self) -> str:
        all_ci = [ci for pr in self.pull_requests for ci in pr.ci_results]
        if not all_ci:
            return "no-ci"
        if any(ci.conclusion == "failure" for ci in all_ci):
            return "FAIL"
        if all(ci.conclusion == "success" for ci in all_ci):
            return "PASS"
        return "PARTIAL"


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _retry_request(
    client: httpx.Client,
    method: str,
    url: str,
    delay: float,
    **kwargs,
) -> httpx.Response:
    """Synchronous HTTP request with exponential backoff retry."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            time.sleep(delay)
            resp = client.request(method, url, **kwargs)
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", RETRY_BACKOFF_BASE ** attempt))
                _log(f"Rate limited on {url}. Waiting {retry_after}s...")
                time.sleep(retry_after)
                continue
            if resp.status_code >= 500:
                wait = RETRY_BACKOFF_BASE ** attempt
                _log(f"Server error {resp.status_code} on {url}. Retry {attempt}/{MAX_RETRIES} in {wait}s...")
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


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", file=sys.stderr)


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

    def search_issues(self, jql: str, fields: List[str], max_results: int = 100) -> List[Dict]:
        """Paginated JQL search."""
        all_issues: List[Dict] = []
        start_at = 0
        while True:
            data = self._get("search", params={
                "jql": jql,
                "fields": ",".join(fields),
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

    def get_issue(self, issue_key: str) -> Dict:
        return self._get(f"issue/{issue_key}")

    def get_issue_transitions(self, issue_key: str) -> List[Dict]:
        data = self._get(f"issue/{issue_key}/transitions")
        return data.get("transitions", [])

    def get_issue_changelog(self, issue_key: str) -> List[Dict]:
        """Return changelog entries (requires 'changelog' expand)."""
        data = self._get(f"issue/{issue_key}", params={"expand": "changelog"})
        return data.get("changelog", {}).get("histories", [])


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
        params = params or {}
        params.setdefault("per_page", 100)
        results: List[Any] = []
        page = 1
        while True:
            params["page"] = page
            data = self._get(path, params=params)
            if not data:
                break
            if isinstance(data, list):
                results.extend(data)
                if len(data) < params["per_page"]:
                    break
            else:
                # single object (e.g., search results)
                items = data.get("items", data)
                results.extend(items if isinstance(items, list) else [items])
                break
            page += 1
        return results

    def get_release(self, repo: str, tag: str) -> Dict:
        return self._get(f"repos/{repo}/releases/tags/{tag}")

    def get_prs_for_commit(self, repo: str, commit_sha: str) -> List[Dict]:
        return self._get(f"repos/{repo}/commits/{commit_sha}/pulls") or []

    def list_release_commits(self, repo: str, tag: str, base_tag: Optional[str] = None) -> List[Dict]:
        """List commits included in a release (between base and tag)."""
        if base_tag:
            compare = self._get(f"repos/{repo}/compare/{base_tag}...{tag}")
            return compare.get("commits", [])
        # Fall back: list commits on the default branch up to tag
        release = self.get_release(repo, tag)
        target = release.get("target_commitish", "main")
        return self._paginate(f"repos/{repo}/commits", params={"sha": target})

    def get_pr_commits(self, repo: str, pr_number: int) -> List[Dict]:
        return self._paginate(f"repos/{repo}/pulls/{pr_number}/commits")

    def get_pr_reviews(self, repo: str, pr_number: int) -> List[Dict]:
        return self._paginate(f"repos/{repo}/pulls/{pr_number}/reviews")

    def get_check_runs(self, repo: str, ref: str) -> List[Dict]:
        data = self._get(f"repos/{repo}/commits/{ref}/check-runs")
        return data.get("check_runs", []) if isinstance(data, dict) else []

    def search_prs(self, repo: str, query_extra: str = "") -> List[Dict]:
        q = f"repo:{repo} is:pr is:merged {query_extra}"
        data = self._get("search/issues", params={"q": q, "per_page": 100})
        return data.get("items", [])

    def get_pr_detail(self, repo: str, pr_number: int) -> Dict:
        return self._get(f"repos/{repo}/pulls/{pr_number}")


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def extract_jira_keys_from_text(text: str, project: str) -> List[str]:
    """Extract JIRA issue keys (e.g. PROJ-123) from free-form text."""
    import re
    pattern = rf"\b{re.escape(project)}-\d+\b"
    return list(set(re.findall(pattern, text or "")))


def build_traceability_record(
    issue: Dict,
    jira: JiraClient,
    github: GitHubClient,
    repo: str,
    release_tag: str,
) -> TraceabilityRecord:
    key = issue["key"]
    fields = issue.get("fields", {})
    summary = fields.get("summary", "")
    status = fields.get("status", {}).get("name", "")

    record = TraceabilityRecord(
        jira_key=key,
        jira_summary=summary,
        jira_status=status,
    )

    # --- Linked issues: requirements ("implements"), test cases ("is tested by") ---
    issue_links = fields.get("issuelinks", [])
    for link in issue_links:
        link_type = link.get("type", {})
        inward_name = link_type.get("inward", "").lower()
        outward_name = link_type.get("outward", "").lower()

        linked_issue = link.get("outwardIssue") or link.get("inwardIssue")
        if not linked_issue:
            continue
        linked_key = linked_issue.get("key", "")
        linked_summary = linked_issue.get("fields", {}).get("summary", "")
        linked_status = linked_issue.get("fields", {}).get("status", {}).get("name", "")

        if "implement" in outward_name or "implement" in inward_name:
            record.requirements.append(Requirement(
                req_id=linked_key,
                summary=linked_summary,
                jira_key=linked_key,
            ))
        elif "test" in outward_name or "test" in inward_name:
            record.test_cases.append(TestCase(
                test_id=linked_key,
                summary=linked_summary,
                status=linked_status,
            ))

    # --- Remote links: design docs ---
    try:
        remote_links_data = jira._get(f"issue/{key}/remotelink")
        if isinstance(remote_links_data, list):
            for rl in remote_links_data:
                obj = rl.get("object", {})
                url = obj.get("url", "")
                if url:
                    record.design_doc_links.append(url)
    except Exception as exc:
        _log(f"  Warning: could not fetch remote links for {key}: {exc}")

    # --- GitHub PRs linked via branch name or PR title/body ---
    pr_numbers = _find_linked_pr_numbers(fields, key)
    for pr_num in pr_numbers:
        try:
            pr_detail = github.get_pr_detail(repo, pr_num)
            pr = _build_pr(github, repo, pr_num, pr_detail)
            record.pull_requests.append(pr)
        except Exception as exc:
            _log(f"  Warning: could not fetch PR #{pr_num} for {key}: {exc}")

    return record


def _find_linked_pr_numbers(fields: Dict, jira_key: str) -> List[int]:
    """
    Extract GitHub PR numbers from JIRA custom fields.
    Atlassian's GitHub integration stores PR links in custom field
    'development' (not always available via REST v3). We also scan
    the description and comment bodies for PR URLs as a fallback.
    """
    import re
    pr_numbers: List[int] = []

    # Check description
    desc = ""
    desc_field = fields.get("description")
    if isinstance(desc_field, dict):
        # Atlassian Document Format
        for block in desc_field.get("content", []):
            for inline in block.get("content", []):
                desc += inline.get("text", "") + " "
    elif isinstance(desc_field, str):
        desc = desc_field

    # Match GitHub PR URLs: https://github.com/owner/repo/pull/123
    urls = re.findall(r"github\.com/[^/]+/[^/]+/pull/(\d+)", desc)
    pr_numbers.extend(int(n) for n in urls)

    # Check custom field: "GitHub Pull Requests" (varies by org)
    for cf_key, cf_value in fields.items():
        if cf_key.startswith("customfield_") and isinstance(cf_value, str):
            found = re.findall(r"github\.com/[^/]+/[^/]+/pull/(\d+)", cf_value)
            pr_numbers.extend(int(n) for n in found)

    return list(set(pr_numbers))


def _build_pr(github: GitHubClient, repo: str, pr_number: int, pr_detail: Dict) -> PullRequest:
    pr_url = pr_detail.get("html_url", f"https://github.com/{repo}/pull/{pr_number}")
    merged_at = pr_detail.get("merged_at")
    merge_sha = pr_detail.get("merge_commit_sha")

    pr = PullRequest(
        pr_number=pr_number,
        pr_url=pr_url,
        title=pr_detail.get("title", ""),
        merged_at=merged_at,
        merge_commit_sha=merge_sha,
    )

    # Commits
    raw_commits = github.get_pr_commits(repo, pr_number)
    for c in raw_commits:
        commit_data = c.get("commit", {})
        author_data = commit_data.get("author", {})
        pr.commits.append(Commit(
            sha=c.get("sha", ""),
            message=commit_data.get("message", "").split("\n")[0],
            author=author_data.get("name", ""),
            committed_at=author_data.get("date", ""),
        ))

    # Reviews / approvals
    raw_reviews = github.get_pr_reviews(repo, pr_number)
    for r in raw_reviews:
        if r.get("state") == "APPROVED":
            user = r.get("user", {})
            pr.approvals.append(Approval(
                reviewer=user.get("login", ""),
                approved_at=r.get("submitted_at", ""),
                review_state="APPROVED",
            ))

    # CI check runs (on the merge commit or head SHA)
    head_sha = pr_detail.get("head", {}).get("sha", "")
    if head_sha:
        raw_checks = github.get_check_runs(repo, head_sha)
        for check in raw_checks:
            pr.ci_results.append(CIResult(
                name=check.get("name", ""),
                status=check.get("status", ""),
                conclusion=check.get("conclusion") or "pending",
                run_url=check.get("html_url", ""),
            ))

    return pr


def find_jira_issues_with_github_prs(jira: JiraClient, project: str, release_tag: str) -> List[Dict]:
    """
    Return all JIRA issues in the project that mention a GitHub PR
    or are labelled with the release tag/fix version.
    """
    jql_parts = [f'project = "{project}"']

    # Try fix version matching the release tag
    version_clean = release_tag.lstrip("v")
    jql_parts.append(
        f'(fixVersion = "{release_tag}" OR fixVersion = "{version_clean}" '
        f'OR labels = "{release_tag}" OR text ~ "{release_tag}")'
    )
    jql = " AND ".join(jql_parts)
    _log(f"JQL: {jql}")

    fields = [
        "summary", "status", "issuetype", "assignee", "description",
        "issuelinks", "fixVersions", "labels", "comment",
        "customfield_10000",  # Epic Link (common)
        "customfield_10014",  # Epic Link (alternate)
        "customfield_10016",  # Story Points
    ]
    # Add all custom fields to catch GitHub integration fields
    fields.append("*all")

    try:
        return jira.search_issues(jql, fields=["*all"])
    except Exception as exc:
        _log(f"Warning: JQL search failed ({exc}). Falling back to project-wide search.")
        fallback_jql = f'project = "{project}" ORDER BY updated DESC'
        return jira.search_issues(fallback_jql, fields=["*all"])


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def output_csv(records: List[TraceabilityRecord], output_file: Optional[str]) -> None:
    fieldnames = [
        "req_id", "jira_ticket", "jira_summary",
        "pr_url", "pr_merged_at", "test_result",
        "approver", "approved_at",
    ]
    rows = []
    for rec in records:
        rows.extend(rec.flatten())

    fh = open(output_file, "w", newline="", encoding="utf-8") if output_file else sys.stdout
    try:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    finally:
        if output_file:
            fh.close()


def output_json(records: List[TraceabilityRecord], output_file: Optional[str]) -> None:
    data = [asdict(r) for r in records]
    text = json.dumps(data, indent=2, default=str)
    if output_file:
        with open(output_file, "w", encoding="utf-8") as fh:
            fh.write(text)
    else:
        print(text)


def output_markdown(records: List[TraceabilityRecord], output_file: Optional[str]) -> None:
    lines = []
    lines.append("# Traceability Matrix\n")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}\n")
    lines.append("")
    lines.append("| Req ID | JIRA Ticket | Summary | PR | Merged At | Test Result | Approver | Approved At |")
    lines.append("|--------|-------------|---------|-----|-----------|-------------|----------|-------------|")

    for rec in records:
        for row in rec.flatten():
            pr_md = f"[PR]({row['pr_url']})" if row["pr_url"] else "-"
            lines.append(
                f"| {row['req_id']} "
                f"| [{row['jira_ticket']}]({row['jira_ticket']}) "
                f"| {row['jira_summary'][:60]} "
                f"| {pr_md} "
                f"| {row['pr_merged_at'][:10] if row['pr_merged_at'] else '-'} "
                f"| {row['test_result']} "
                f"| {row['approver'] or '-'} "
                f"| {row['approved_at'][:10] if row['approved_at'] else '-'} |"
            )

    text = "\n".join(lines) + "\n"
    if output_file:
        with open(output_file, "w", encoding="utf-8") as fh:
            fh.write(text)
    else:
        print(text)


# ---------------------------------------------------------------------------
# Gap analysis
# ---------------------------------------------------------------------------

def compute_summary(records: List[TraceabilityRecord]) -> Dict[str, Any]:
    total_tickets = len(records)
    orphans = [r.jira_key for r in records if not r.requirements]
    uncovered_reqs: List[str] = []
    all_req_ids: List[str] = []

    for rec in records:
        for req in rec.requirements:
            all_req_ids.append(req.req_id)
            if not rec.test_cases:
                if req.req_id not in uncovered_reqs:
                    uncovered_reqs.append(req.req_id)

    no_pr = [r.jira_key for r in records if not r.pull_requests]
    fail_ci = [
        r.jira_key for r in records
        if any(
            ci.conclusion == "failure"
            for pr in r.pull_requests
            for ci in pr.ci_results
        )
    ]

    return {
        "total_tickets": total_tickets,
        "tickets_with_requirements": total_tickets - len(orphans),
        "orphan_tickets": orphans,
        "total_requirements": len(set(all_req_ids)),
        "uncovered_requirements": uncovered_reqs,
        "tickets_without_pr": no_pr,
        "tickets_with_ci_failure": fail_ci,
    }


def print_summary(summary: Dict[str, Any]) -> None:
    sep = "-" * 60
    print(sep, file=sys.stderr)
    print("TRACEABILITY SUMMARY", file=sys.stderr)
    print(sep, file=sys.stderr)
    print(f"  Total JIRA tickets     : {summary['total_tickets']}", file=sys.stderr)
    print(f"  With requirements link : {summary['tickets_with_requirements']}", file=sys.stderr)
    print(f"  Total requirements     : {summary['total_requirements']}", file=sys.stderr)
    print(f"  Uncovered requirements : {len(summary['uncovered_requirements'])}", file=sys.stderr)
    if summary["uncovered_requirements"]:
        for r in summary["uncovered_requirements"]:
            print(f"    - {r}", file=sys.stderr)
    print(f"  Orphan tickets (no req): {len(summary['orphan_tickets'])}", file=sys.stderr)
    if summary["orphan_tickets"]:
        for t in summary["orphan_tickets"]:
            print(f"    - {t}", file=sys.stderr)
    print(f"  Tickets without PR     : {len(summary['tickets_without_pr'])}", file=sys.stderr)
    print(f"  Tickets with CI failure: {len(summary['tickets_with_ci_failure'])}", file=sys.stderr)
    print(sep, file=sys.stderr)


# ---------------------------------------------------------------------------
# Progress wrapper
# ---------------------------------------------------------------------------

def make_progress(iterable, desc: str, total: int):
    if HAS_TQDM:
        return tqdm(iterable, desc=desc, total=total, file=sys.stderr)
    # Simple fallback
    class _Simple:
        def __init__(self, it, d, n):
            self._it = iter(it)
            self._desc = d
            self._total = n
            self._i = 0
        def __iter__(self):
            return self
        def __next__(self):
            val = next(self._it)
            self._i += 1
            print(f"  [{self._desc}] {self._i}/{self._total}", file=sys.stderr)
            return val
    return _Simple(iterable, desc, total)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a software certification traceability matrix.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--jira-project", required=True, metavar="PROJ",
                        help="JIRA project key (e.g. MYPROJ)")
    parser.add_argument("--github-repo", required=True, metavar="owner/repo",
                        help="GitHub repository in owner/repo format")
    parser.add_argument("--release-tag", required=True, metavar="TAG",
                        help="Git release tag (e.g. v1.0.0)")
    parser.add_argument("--output-format", choices=["csv", "json", "md"], default="csv",
                        help="Output format (default: csv)")
    parser.add_argument("--output-file", metavar="FILE",
                        help="Write output to FILE instead of stdout")
    parser.add_argument("--summary-file", metavar="FILE",
                        help="Write JSON summary/gap analysis to FILE")
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

    _log(f"Initialising clients...")
    jira = JiraClient(env["JIRA_BASE_URL"], env["JIRA_EMAIL"], env["JIRA_API_TOKEN"])
    github = GitHubClient(env["GITHUB_TOKEN"])

    _log(f"Fetching JIRA issues for project={args.jira_project}, tag={args.release_tag}...")
    issues = find_jira_issues_with_github_prs(jira, args.jira_project, args.release_tag)
    _log(f"Found {len(issues)} JIRA issues.")

    records: List[TraceabilityRecord] = []
    progress = make_progress(issues, "Processing issues", len(issues))
    for issue in progress:
        key = issue["key"]
        _log(f"  Processing {key}...")
        try:
            rec = build_traceability_record(issue, jira, github, args.github_repo, args.release_tag)
            records.append(rec)
        except Exception as exc:
            _log(f"  ERROR processing {key}: {exc}")

    # Output
    _log(f"Writing output (format={args.output_format})...")
    if args.output_format == "csv":
        output_csv(records, args.output_file)
    elif args.output_format == "json":
        output_json(records, args.output_file)
    elif args.output_format == "md":
        output_markdown(records, args.output_file)

    # Summary / gap analysis
    summary = compute_summary(records)
    print_summary(summary)

    if args.summary_file:
        with open(args.summary_file, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2)
        _log(f"Summary written to {args.summary_file}")

    _log("Done.")


if __name__ == "__main__":
    main()
