"""
JIRA REST API v3 client for certification evidence automation.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Optional

import httpx


# ---------------------------------------------------------------------------
# Structured JSON logger
# ---------------------------------------------------------------------------

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "extra"):
            entry.update(record.extra)
        return json.dumps(entry)


def _make_logger(name: str) -> logging.Logger:
    log = logging.getLogger(name)
    if not log.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(JsonFormatter())
        log.addHandler(h)
    log.setLevel(logging.INFO)
    return log


logger = _make_logger("jira_client")


# ---------------------------------------------------------------------------
# JiraClient
# ---------------------------------------------------------------------------

class JiraClient:
    """Thin wrapper around the JIRA REST API v3."""

    def __init__(self, base_url: str, email: str, api_token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self._auth = (email, api_token)
        self._headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _client(self) -> httpx.Client:
        return httpx.Client(
            auth=self._auth,
            headers=self._headers,
            timeout=30.0,
        )

    def _log(self, method: str, result: str, details: dict) -> None:
        logger.info(
            f"jira_client.{method}",
            extra={"method": method, "result": result, **details},
        )

    # ------------------------------------------------------------------
    # get_issue
    # ------------------------------------------------------------------

    def get_issue(self, ticket_id: str) -> Optional[dict]:
        """
        Fetch a JIRA issue by key.
        Returns the full issue dict (with remoteLinks merged in) or None on error.
        """
        url = f"{self.base_url}/rest/api/3/issue/{ticket_id}"
        try:
            with self._client() as client:
                resp = client.get(url)
                resp.raise_for_status()
                issue: dict = resp.json()

            # Also fetch remote links and embed them
            issue["remoteLinks"] = self._fetch_remote_links(ticket_id)

            self._log("get_issue", "success", {"ticket": ticket_id})
            return issue
        except httpx.HTTPStatusError as exc:
            self._log(
                "get_issue",
                "failure",
                {"ticket": ticket_id, "status_code": exc.response.status_code},
            )
            return None
        except Exception as exc:
            self._log("get_issue", "failure", {"ticket": ticket_id, "error": str(exc)})
            return None

    def _fetch_remote_links(self, ticket_id: str) -> list:
        url = f"{self.base_url}/rest/api/3/issue/{ticket_id}/remotelink"
        try:
            with self._client() as client:
                resp = client.get(url)
                resp.raise_for_status()
                return resp.json()
        except Exception:
            return []

    # ------------------------------------------------------------------
    # get_issue_transitions
    # ------------------------------------------------------------------

    def get_issue_transitions(self, ticket_id: str) -> list:
        """Return all available transitions for the given issue."""
        url = f"{self.base_url}/rest/api/3/issue/{ticket_id}/transitions"
        try:
            with self._client() as client:
                resp = client.get(url)
                resp.raise_for_status()
                transitions: list = resp.json().get("transitions", [])
            self._log(
                "get_issue_transitions",
                "success",
                {"ticket": ticket_id, "count": len(transitions)},
            )
            return transitions
        except httpx.HTTPStatusError as exc:
            self._log(
                "get_issue_transitions",
                "failure",
                {"ticket": ticket_id, "status_code": exc.response.status_code},
            )
            return []
        except Exception as exc:
            self._log(
                "get_issue_transitions",
                "failure",
                {"ticket": ticket_id, "error": str(exc)},
            )
            return []

    # ------------------------------------------------------------------
    # transition_issue
    # ------------------------------------------------------------------

    def transition_issue(self, ticket_id: str, target_status: str) -> bool:
        """
        Transition an issue to the given status name.
        Resolves the transition ID automatically.
        Returns True on success.
        """
        transitions = self.get_issue_transitions(ticket_id)
        transition_id: Optional[str] = None
        for t in transitions:
            if t.get("to", {}).get("name", "").lower() == target_status.lower():
                transition_id = t["id"]
                break
            # Some JIRA configurations expose the name directly on the transition
            if t.get("name", "").lower() == target_status.lower():
                transition_id = t["id"]
                break

        if not transition_id:
            self._log(
                "transition_issue",
                "failure",
                {
                    "ticket": ticket_id,
                    "target_status": target_status,
                    "error": "transition_not_found",
                },
            )
            return False

        url = f"{self.base_url}/rest/api/3/issue/{ticket_id}/transitions"
        body = {"transition": {"id": transition_id}}
        try:
            with self._client() as client:
                resp = client.post(url, json=body)
                resp.raise_for_status()
            self._log(
                "transition_issue",
                "success",
                {
                    "ticket": ticket_id,
                    "target_status": target_status,
                    "transition_id": transition_id,
                },
            )
            return True
        except httpx.HTTPStatusError as exc:
            self._log(
                "transition_issue",
                "failure",
                {
                    "ticket": ticket_id,
                    "target_status": target_status,
                    "status_code": exc.response.status_code,
                    "response_body": exc.response.text[:500],
                },
            )
            return False
        except Exception as exc:
            self._log(
                "transition_issue",
                "failure",
                {"ticket": ticket_id, "error": str(exc)},
            )
            return False

    # ------------------------------------------------------------------
    # add_comment
    # ------------------------------------------------------------------

    def add_comment(self, ticket_id: str, comment_body: str) -> bool:
        """
        Add a comment to a JIRA issue using the Atlassian Document Format (ADF).
        Returns True on success.
        """
        url = f"{self.base_url}/rest/api/3/issue/{ticket_id}/comment"
        adf_body = {
            "version": 1,
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": comment_body}],
                }
            ],
        }
        body = {"body": adf_body}
        try:
            with self._client() as client:
                resp = client.post(url, json=body)
                resp.raise_for_status()
            self._log("add_comment", "success", {"ticket": ticket_id})
            return True
        except httpx.HTTPStatusError as exc:
            self._log(
                "add_comment",
                "failure",
                {
                    "ticket": ticket_id,
                    "status_code": exc.response.status_code,
                    "response_body": exc.response.text[:500],
                },
            )
            return False
        except Exception as exc:
            self._log("add_comment", "failure", {"ticket": ticket_id, "error": str(exc)})
            return False

    # ------------------------------------------------------------------
    # link_to_github_pr
    # ------------------------------------------------------------------

    def link_to_github_pr(self, ticket_id: str, pr_url: str) -> bool:
        """
        Create a remote link on the JIRA issue pointing to the GitHub PR.
        Uses the JIRA Remote Link API.
        Returns True on success.
        """
        url = f"{self.base_url}/rest/api/3/issue/{ticket_id}/remotelink"
        body = {
            "globalId": f"github-pr:{pr_url}",
            "object": {
                "url": pr_url,
                "title": f"GitHub PR: {pr_url}",
                "icon": {
                    "url16x16": "https://github.com/favicon.ico",
                    "title": "GitHub",
                },
                "status": {
                    "resolved": False,
                    "icon": {},
                },
            },
            "application": {
                "type": "com.github",
                "name": "GitHub",
            },
            "relationship": "mentioned in",
        }
        try:
            with self._client() as client:
                resp = client.post(url, json=body)
                resp.raise_for_status()
            self._log(
                "link_to_github_pr",
                "success",
                {"ticket": ticket_id, "pr_url": pr_url},
            )
            return True
        except httpx.HTTPStatusError as exc:
            self._log(
                "link_to_github_pr",
                "failure",
                {
                    "ticket": ticket_id,
                    "pr_url": pr_url,
                    "status_code": exc.response.status_code,
                    "response_body": exc.response.text[:500],
                },
            )
            return False
        except Exception as exc:
            self._log(
                "link_to_github_pr",
                "failure",
                {"ticket": ticket_id, "pr_url": pr_url, "error": str(exc)},
            )
            return False

    # ------------------------------------------------------------------
    # get_audit_records
    # ------------------------------------------------------------------

    def get_audit_records(
        self,
        project_key: str,
        start_date: str,
        end_date: str,
    ) -> list:
        """
        Retrieve audit records for a project within a date range.

        Uses the JIRA Audit API: GET /rest/api/3/auditing/record
        start_date / end_date: ISO-8601 date strings, e.g. '2024-01-01'.

        Returns a list of audit record dicts.
        """
        url = f"{self.base_url}/rest/api/3/auditing/record"
        params: dict[str, Any] = {
            "from": start_date,
            "to": end_date,
            "limit": 1000,
            "offset": 0,
        }
        records: list = []
        try:
            with self._client() as client:
                while True:
                    resp = client.get(url, params=params)
                    resp.raise_for_status()
                    data: dict = resp.json()
                    page_records: list = data.get("records", [])
                    # Filter to the relevant project
                    for rec in page_records:
                        summary: str = rec.get("summary", "")
                        obj_items: list = rec.get("objectItem", {}).get("typeName", "")
                        # Include record if it mentions the project key
                        if project_key in str(rec):
                            records.append(rec)
                    total: int = data.get("total", 0)
                    params["offset"] += len(page_records)
                    if params["offset"] >= total or not page_records:
                        break

            self._log(
                "get_audit_records",
                "success",
                {
                    "project_key": project_key,
                    "start_date": start_date,
                    "end_date": end_date,
                    "count": len(records),
                },
            )
            return records
        except httpx.HTTPStatusError as exc:
            self._log(
                "get_audit_records",
                "failure",
                {
                    "project_key": project_key,
                    "status_code": exc.response.status_code,
                    "response_body": exc.response.text[:500],
                },
            )
            return []
        except Exception as exc:
            self._log(
                "get_audit_records",
                "failure",
                {"project_key": project_key, "error": str(exc)},
            )
            return []
