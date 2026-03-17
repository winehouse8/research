#!/usr/bin/env python3
"""
audit-aggregator.py - Aggregate audit logs from JIRA and GitHub into a unified timeline.

Usage:
    python audit-aggregator.py --jira-project PROJ --github-repo owner/repo \
        [--start-date 2024-01-01] [--end-date 2024-12-31] \
        [--output-format json|csv|md]

Environment variables:
    GITHUB_TOKEN      - GitHub personal access token (required)
    JIRA_URL          - Jira base URL, e.g. https://org.atlassian.net (required)
    JIRA_USER         - Jira user email (required)
    JIRA_API_TOKEN    - Jira API token (required)
"""

import argparse
import csv
import io
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

import requests


# ---------------------------------------------------------------------------
# Shared types
# ---------------------------------------------------------------------------

AuditEvent = dict  # keys: timestamp, system, event_type, actor, target, details, anomaly_flag


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def require_env(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        print(f"ERROR: required environment variable {name} is not set.", file=sys.stderr)
        sys.exit(1)
    return val


def parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    # Handle both Z and +00:00 suffixes
    ts = ts.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def fmt_iso(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# JIRA audit log collector
# ---------------------------------------------------------------------------

JIRA_ANOMALY_ACTIONS = {
    "jira:issue_updated:status":        "admin_workflow_transition",
    "jira:workflow_updated":            "workflow_schema_change",
    "jira:permission_updated":          "permission_change",
    "jira:project_permission_changed":  "permission_change",
    "jira:field_configuration_changed": "config_change",
    "jira:admin_forced_transition":     "admin_override",
}

JIRA_ANOMALY_KEYWORDS = [
    "admin override",
    "forced transition",
    "bypass",
    "skip",
    "manual transition",
]


def is_jira_anomaly(record: dict) -> bool:
    summary = record.get("summary", "").lower()
    category = record.get("category", "").lower()
    if any(kw in summary for kw in JIRA_ANOMALY_KEYWORDS):
        return True
    if "admin" in summary and ("transition" in summary or "override" in summary):
        return True
    if category in ("permission", "workflow") and "admin" in summary:
        return True
    return False


class JiraAuditCollector:
    def __init__(self, base_url: str, user: str, api_token: str, project: str):
        self.session = requests.Session()
        self.session.auth = (user, api_token)
        self.session.headers.update({"Accept": "application/json"})
        self.base_url = base_url.rstrip("/")
        self.project = project

    def _get(self, path: str, params: dict | None = None) -> Any:
        url = f"{self.base_url}{path}"
        r = self.session.get(url, params=params)
        r.raise_for_status()
        return r.json()

    def collect(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[AuditEvent]:
        """
        Collect audit records from /rest/api/3/auditing/record.
        Filters by date range and project key where possible.
        """
        log("Collecting JIRA audit log...")
        params: dict[str, Any] = {"limit": 1000, "offset": 0}
        if start:
            params["from"] = fmt_iso(start)
        if end:
            params["to"] = fmt_iso(end)

        events: list[AuditEvent] = []
        while True:
            data = self._get("/rest/api/3/auditing/record", params)
            records = data.get("records", [])
            if not records:
                break

            for record in records:
                # Filter by project where the objectItem refers to the project key
                object_item = record.get("objectItem", {})
                associated = record.get("associatedItems", [])

                # Loose project filter: include if project key appears anywhere
                project_match = (
                    self.project in json.dumps(record)
                )
                if not project_match:
                    params["offset"] += len(records)
                    continue

                ts_str = record.get("created", "")
                ts = parse_iso(ts_str)
                author = record.get("authorKey") or record.get("authorAccountId", "unknown")
                summary = record.get("summary", "")
                category = record.get("category", "")

                # Build target string
                target_parts = []
                if object_item.get("name"):
                    target_parts.append(object_item["name"])
                if object_item.get("id"):
                    target_parts.append(f"(id={object_item['id']})")
                target = " ".join(target_parts) or "n/a"

                anomaly = is_jira_anomaly(record)

                events.append({
                    "timestamp": fmt_iso(ts) if ts else ts_str,
                    "system": "JIRA",
                    "event_type": f"{category}:{summary[:80]}".strip(":"),
                    "actor": author,
                    "target": target,
                    "details": {
                        "summary": summary,
                        "category": category,
                        "changed_values": record.get("changedValues", []),
                        "associated_items": [
                            {"name": i.get("name"), "id": i.get("id")}
                            for i in associated
                        ],
                    },
                    "anomaly_flag": anomaly,
                })

            total = data.get("total", 0)
            params["offset"] += len(records)
            if params["offset"] >= total:
                break

        log(f"  Collected {len(events)} JIRA audit event(s).")
        return events


# ---------------------------------------------------------------------------
# GitHub audit log collector
# ---------------------------------------------------------------------------

GITHUB_ANOMALY_EVENTS = {
    "protected_branch.admin_enforced",
    "protected_branch.policy_override",
    "protected_branch.destroy",
    "repo.create",
    "repo.destroy",
    "org.update_member",
    "org.remove_member",
    "team.add_repository",
    "team.remove_repository",
    "business.set_actions_fork_pr_approvals_policy",
    "pull_request_review_protection.disable",
}

GITHUB_ANOMALY_KEYWORDS = [
    "force_push",
    "bypass",
    "admin_override",
    "admin_enforced",
    "policy_override",
    "dismiss_review",
]


def is_github_anomaly(action: str, payload: dict) -> bool:
    if action in GITHUB_ANOMALY_EVENTS:
        return True
    if any(kw in action for kw in GITHUB_ANOMALY_KEYWORDS):
        return True
    # Detect force pushes in push events
    if action == "git.push" and payload.get("forced"):
        return True
    return False


class GitHubAuditCollector:
    def __init__(self, token: str, repo: str):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        owner, self.repo_name = repo.split("/", 1)
        self.org = owner
        self.repo = repo
        self.base = "https://api.github.com"

    def _get(self, path: str, params: dict | None = None) -> Any:
        url = f"{self.base}{path}"
        r = self.session.get(url, params=params)
        r.raise_for_status()
        return r.json()

    def _paginate_link(self, url: str, params: dict | None = None) -> list:
        """Follow GitHub's Link header pagination."""
        results = []
        current_url: str | None = url
        current_params = dict(params or {})
        while current_url:
            r = self.session.get(current_url, params=current_params)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, list):
                results.extend(data)
            elif isinstance(data, dict):
                # Audit log returns {"events": [...]}
                results.extend(data.get("events", []))
            # Follow Link: <url>; rel="next"
            link_header = r.headers.get("Link", "")
            next_url = None
            for part in link_header.split(","):
                part = part.strip()
                if 'rel="next"' in part:
                    next_url = part.split(";")[0].strip().strip("<>")
                    break
            current_url = next_url
            current_params = {}  # params are embedded in next_url
        return results

    def collect_enterprise_audit_log(
        self,
        start: datetime | None,
        end: datetime | None,
    ) -> list[AuditEvent]:
        """
        Collect from /orgs/{org}/audit-log (requires GitHub Enterprise or
        GitHub.com with audit log API access).
        """
        log("  Attempting GitHub Enterprise audit log endpoint...")
        params: dict[str, Any] = {"per_page": 100, "include": "all"}
        if start:
            params["after"] = ""  # placeholder; use created filter below
        url = f"{self.base}/orgs/{self.org}/audit-log"
        try:
            raw = self._paginate_link(url, params)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code in (404, 403):
                log("  Enterprise audit log not available; falling back to repo events.")
                return []
            raise

        events: list[AuditEvent] = []
        for entry in raw:
            ts_ms = entry.get("@timestamp")
            if ts_ms:
                ts = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
            else:
                ts = None

            # Date range filter
            if start and ts and ts < start:
                continue
            if end and ts and ts > end:
                continue

            action = entry.get("action", "unknown")
            actor = entry.get("actor", "unknown")
            repo_field = entry.get("repo", entry.get("repository", ""))
            anomaly = is_github_anomaly(action, entry)

            events.append({
                "timestamp": fmt_iso(ts) if ts else "",
                "system": "GitHub",
                "event_type": action,
                "actor": actor,
                "target": repo_field or entry.get("name", ""),
                "details": {k: v for k, v in entry.items()
                            if k not in ("action", "actor", "@timestamp")},
                "anomaly_flag": anomaly,
            })

        log(f"  Collected {len(events)} GitHub Enterprise audit event(s).")
        return events

    def collect_repo_events(
        self,
        start: datetime | None,
        end: datetime | None,
    ) -> list[AuditEvent]:
        """
        Fallback: collect from /repos/{repo}/events (public, limited to ~300 events).
        Supplements with PR review events and branch protection changes.
        """
        log("  Collecting GitHub repo events (free-tier fallback)...")
        raw = self._paginate_link(
            f"{self.base}/repos/{self.repo}/events",
            {"per_page": 100},
        )

        events: list[AuditEvent] = []
        for entry in raw:
            ts_str = entry.get("created_at", "")
            ts = parse_iso(ts_str)

            if start and ts and ts < start:
                continue
            if end and ts and ts > end:
                continue

            event_type = entry.get("type", "unknown")
            actor = entry.get("actor", {}).get("login", "unknown")
            payload = entry.get("payload", {})

            # Detect force pushes
            forced = False
            if event_type == "PushEvent":
                forced = payload.get("forced", False)

            action_detail = payload.get("action", "")
            full_type = f"{event_type}.{action_detail}".strip(".")
            anomaly = is_github_anomaly(full_type, payload) or forced

            events.append({
                "timestamp": fmt_iso(ts) if ts else ts_str,
                "system": "GitHub",
                "event_type": full_type,
                "actor": actor,
                "target": self.repo,
                "details": {
                    "event_id": entry.get("id"),
                    "forced_push": forced,
                    "ref": payload.get("ref"),
                    "pr_number": payload.get("number"),
                },
                "anomaly_flag": anomaly,
            })

        # Also collect PR review events for the repo's recent PRs
        pr_review_events = self._collect_pr_review_events(start, end)
        events.extend(pr_review_events)

        log(f"  Collected {len(events)} GitHub repo event(s).")
        return events

    def _collect_pr_review_events(
        self,
        start: datetime | None,
        end: datetime | None,
    ) -> list[AuditEvent]:
        """Collect PR review dismissals and approval events."""
        try:
            prs = self._paginate_link(
                f"{self.base}/repos/{self.repo}/pulls",
                {"state": "closed", "per_page": 100},
            )
        except requests.HTTPError:
            return []

        events: list[AuditEvent] = []
        for pr in prs[:50]:  # limit to most recent 50 PRs for performance
            pr_number = pr["number"]
            try:
                reviews = self._get(
                    f"/repos/{self.repo}/pulls/{pr_number}/reviews"
                )
            except requests.HTTPError:
                continue

            for review in reviews:
                ts_str = review.get("submitted_at", "")
                ts = parse_iso(ts_str)
                if start and ts and ts < start:
                    continue
                if end and ts and ts > end:
                    continue

                state = review.get("state", "")
                actor = review.get("user", {}).get("login", "unknown")
                anomaly = state == "DISMISSED"

                events.append({
                    "timestamp": fmt_iso(ts) if ts else ts_str,
                    "system": "GitHub",
                    "event_type": f"pull_request_review.{state.lower()}",
                    "actor": actor,
                    "target": f"{self.repo}#PR-{pr_number}",
                    "details": {
                        "pr_number": pr_number,
                        "pr_title": pr.get("title"),
                        "review_state": state,
                        "review_id": review.get("id"),
                        "dismissal_reason": review.get("body"),
                    },
                    "anomaly_flag": anomaly,
                })

        return events

    def collect(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[AuditEvent]:
        events = self.collect_enterprise_audit_log(start, end)
        if not events:
            events = self.collect_repo_events(start, end)
        return events


# ---------------------------------------------------------------------------
# Anomaly detection pass
# ---------------------------------------------------------------------------

SKIP_PATTERNS = [
    "stage_skipped",
    "workflow_skipped",
    "step_skipped",
    "bypass_check",
    "rollback_triggered",
]


def detect_anomalies(events: list[AuditEvent]) -> list[AuditEvent]:
    """
    Second-pass anomaly detection over the merged event list.
    Sets anomaly_flag=True and enriches details.anomaly_reason.
    """
    for event in events:
        if event["anomaly_flag"]:
            # Already flagged; just add reason if missing
            if "anomaly_reason" not in event.get("details", {}):
                event["details"]["anomaly_reason"] = "flagged_at_collection"
            continue

        # Check for stage-skipping patterns in event_type or details
        event_str = json.dumps(event).lower()
        for pattern in SKIP_PATTERNS:
            if pattern in event_str:
                event["anomaly_flag"] = True
                event.setdefault("details", {})["anomaly_reason"] = pattern
                break

        # Detect admin enforcement of branch protection changes mid-release
        if (
            event["system"] == "GitHub"
            and "protected_branch" in event["event_type"]
        ):
            event["anomaly_flag"] = True
            event.setdefault("details", {})["anomaly_reason"] = "branch_protection_change"

    return events


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

FIELDNAMES = [
    "timestamp",
    "system",
    "event_type",
    "actor",
    "target",
    "anomaly_flag",
    "details",
]


def output_json(events: list[AuditEvent], summary: dict) -> str:
    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "summary": summary,
        "events": events,
    }
    return json.dumps(payload, indent=2)


def output_csv(events: list[AuditEvent]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=FIELDNAMES, extrasaction="ignore")
    writer.writeheader()
    for event in events:
        row = dict(event)
        row["details"] = json.dumps(event.get("details", {}))
        writer.writerow(row)
    return buf.getvalue()


def output_md(events: list[AuditEvent], summary: dict) -> str:
    lines = [
        "# Unified Audit Log",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "",
        "## Summary",
        "",
        f"- Total events: {summary['total_events']}",
        f"- Anomalies detected: {summary['anomaly_count']}",
        "",
        "### Events by Type",
        "",
    ]
    for etype, count in sorted(summary["by_event_type"].items()):
        lines.append(f"- `{etype}`: {count}")
    lines += [
        "",
        "### Events by System",
        "",
    ]
    for system, count in sorted(summary["by_system"].items()):
        lines.append(f"- {system}: {count}")
    lines += [
        "",
        "### User Activity",
        "",
    ]
    for actor, count in sorted(
        summary["by_actor"].items(), key=lambda x: -x[1]
    )[:20]:
        lines.append(f"- `{actor}`: {count} event(s)")
    lines += [
        "",
        "---",
        "",
        "## Event Timeline",
        "",
        "| Timestamp | System | Event Type | Actor | Target | Anomaly |",
        "|-----------|--------|------------|-------|--------|---------|",
    ]
    for event in events:
        anomaly_marker = "YES" if event["anomaly_flag"] else ""
        target = event["target"].replace("|", "/")[:60]
        etype = event["event_type"][:60]
        lines.append(
            f"| {event['timestamp']} | {event['system']} "
            f"| {etype} | {event['actor']} | {target} | {anomaly_marker} |"
        )
    if any(e["anomaly_flag"] for e in events):
        lines += [
            "",
            "---",
            "",
            "## Anomalies",
            "",
            "| Timestamp | System | Event Type | Actor | Target | Reason |",
            "|-----------|--------|------------|-------|--------|--------|",
        ]
        for event in events:
            if not event["anomaly_flag"]:
                continue
            reason = event.get("details", {}).get("anomaly_reason", "detected")
            target = event["target"].replace("|", "/")[:60]
            lines.append(
                f"| {event['timestamp']} | {event['system']} "
                f"| {event['event_type']} | {event['actor']} "
                f"| {target} | {reason} |"
            )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Summary builder
# ---------------------------------------------------------------------------

def build_summary(events: list[AuditEvent]) -> dict:
    by_type: dict[str, int] = {}
    by_system: dict[str, int] = {}
    by_actor: dict[str, int] = {}
    anomaly_count = 0

    for event in events:
        by_type[event["event_type"]] = by_type.get(event["event_type"], 0) + 1
        by_system[event["system"]] = by_system.get(event["system"], 0) + 1
        by_actor[event["actor"]] = by_actor.get(event["actor"], 0) + 1
        if event["anomaly_flag"]:
            anomaly_count += 1

    return {
        "total_events": len(events),
        "anomaly_count": anomaly_count,
        "by_event_type": by_type,
        "by_system": by_system,
        "by_actor": by_actor,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate JIRA and GitHub audit logs into a unified timeline."
    )
    parser.add_argument("--jira-project", required=True, help="Jira project key, e.g. PROJ")
    parser.add_argument("--github-repo", required=True, help="GitHub repo in owner/repo format")
    parser.add_argument(
        "--start-date",
        default=None,
        help="Start date filter (ISO-8601, e.g. 2024-01-01)",
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="End date filter (ISO-8601, e.g. 2024-12-31)",
    )
    parser.add_argument(
        "--output-format",
        choices=["json", "csv", "md"],
        default="json",
        help="Output format (default: json)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output file path (default: stdout)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    github_token = require_env("GITHUB_TOKEN")
    jira_url = require_env("JIRA_URL")
    jira_user = require_env("JIRA_USER")
    jira_api_token = require_env("JIRA_API_TOKEN")

    start: datetime | None = None
    end: datetime | None = None

    if args.start_date:
        start = datetime.fromisoformat(args.start_date).replace(tzinfo=timezone.utc)
    if args.end_date:
        end = datetime.fromisoformat(args.end_date).replace(tzinfo=timezone.utc)

    # Collect JIRA events
    jira_collector = JiraAuditCollector(
        base_url=jira_url,
        user=jira_user,
        api_token=jira_api_token,
        project=args.jira_project,
    )
    jira_events = jira_collector.collect(start=start, end=end)

    # Collect GitHub events
    gh_collector = GitHubAuditCollector(
        token=github_token,
        repo=args.github_repo,
    )
    gh_events = gh_collector.collect(start=start, end=end)

    # Merge and sort by timestamp (None timestamps go to end)
    all_events: list[AuditEvent] = jira_events + gh_events
    all_events.sort(
        key=lambda e: e["timestamp"] if e["timestamp"] else "9999"
    )

    # Second-pass anomaly detection
    all_events = detect_anomalies(all_events)

    summary = build_summary(all_events)

    log(
        f"Total events: {summary['total_events']}  |  "
        f"Anomalies: {summary['anomaly_count']}"
    )

    # Format output
    if args.output_format == "json":
        output = output_json(all_events, summary)
    elif args.output_format == "csv":
        output = output_csv(all_events)
    else:
        output = output_md(all_events, summary)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        log(f"Written to {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
