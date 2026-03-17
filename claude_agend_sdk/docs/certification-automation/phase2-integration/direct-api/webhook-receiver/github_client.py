"""
GitHub REST API client for certification evidence automation.
Uses httpx for HTTP transport.
"""

import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Optional

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


logger = _make_logger("github_client")

# ---------------------------------------------------------------------------
# Standalone helper – importable directly by main.py
# ---------------------------------------------------------------------------

_JIRA_TICKET_RE = re.compile(r"\b([A-Z]+-\d+)\b")


def extract_jira_ticket(text: str) -> Optional[str]:
    """
    Return the first JIRA-style ticket key found in *text* (e.g. 'PROJ-123'),
    or None if no match is found.
    """
    match = _JIRA_TICKET_RE.search(text or "")
    return match.group(1) if match else None


# ---------------------------------------------------------------------------
# GitHubClient
# ---------------------------------------------------------------------------

class GitHubClient:
    """Thin wrapper around the GitHub REST API v3."""

    _BASE = "https://api.github.com"

    def __init__(self, token: str) -> None:
        self._token = token
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _client(self) -> httpx.Client:
        return httpx.Client(headers=self._headers, timeout=30.0)

    def _log(self, method: str, result: str, details: dict) -> None:
        logger.info(
            f"github_client.{method}",
            extra={"method": method, "result": result, **details},
        )

    # ------------------------------------------------------------------
    # get_pr
    # ------------------------------------------------------------------

    def get_pr(self, owner: str, repo: str, pr_number: int) -> Optional[dict]:
        """
        Fetch a pull request by number.
        Returns the PR dict or None on error.
        """
        url = f"{self._BASE}/repos/{owner}/{repo}/pulls/{pr_number}"
        try:
            with self._client() as client:
                resp = client.get(url)
                resp.raise_for_status()
                pr: dict = resp.json()
            self._log(
                "get_pr",
                "success",
                {"owner": owner, "repo": repo, "pr_number": pr_number},
            )
            return pr
        except httpx.HTTPStatusError as exc:
            self._log(
                "get_pr",
                "failure",
                {
                    "owner": owner,
                    "repo": repo,
                    "pr_number": pr_number,
                    "status_code": exc.response.status_code,
                },
            )
            return None
        except Exception as exc:
            self._log(
                "get_pr",
                "failure",
                {"owner": owner, "repo": repo, "pr_number": pr_number, "error": str(exc)},
            )
            return None

    # ------------------------------------------------------------------
    # create_commit_status
    # ------------------------------------------------------------------

    def create_commit_status(
        self,
        owner: str,
        repo: str,
        sha: str,
        state: str,
        description: str,
        context: str,
    ) -> bool:
        """
        Create or update a commit status.

        state: 'error' | 'failure' | 'pending' | 'success'
        context: identifier string shown in GitHub UI (e.g. 'jira/approval')
        Returns True on success.
        """
        url = f"{self._BASE}/repos/{owner}/{repo}/statuses/{sha}"
        body = {
            "state": state,
            "description": description[:140],  # GitHub limit
            "context": context,
        }
        try:
            with self._client() as client:
                resp = client.post(url, json=body)
                resp.raise_for_status()
            self._log(
                "create_commit_status",
                "success",
                {
                    "owner": owner,
                    "repo": repo,
                    "sha": sha[:12],
                    "state": state,
                    "context": context,
                },
            )
            return True
        except httpx.HTTPStatusError as exc:
            self._log(
                "create_commit_status",
                "failure",
                {
                    "owner": owner,
                    "repo": repo,
                    "sha": sha[:12],
                    "state": state,
                    "status_code": exc.response.status_code,
                    "response_body": exc.response.text[:500],
                },
            )
            return False
        except Exception as exc:
            self._log(
                "create_commit_status",
                "failure",
                {"owner": owner, "repo": repo, "sha": sha[:12], "error": str(exc)},
            )
            return False

    # ------------------------------------------------------------------
    # add_pr_label
    # ------------------------------------------------------------------

    def add_pr_label(
        self, owner: str, repo: str, pr_number: int, label: str
    ) -> bool:
        """
        Add a label to a pull request.
        Creates the label in the repo if it does not already exist.
        Returns True on success.
        """
        self._ensure_label_exists(owner, repo, label)
        url = f"{self._BASE}/repos/{owner}/{repo}/issues/{pr_number}/labels"
        body = {"labels": [label]}
        try:
            with self._client() as client:
                resp = client.post(url, json=body)
                resp.raise_for_status()
            self._log(
                "add_pr_label",
                "success",
                {"owner": owner, "repo": repo, "pr_number": pr_number, "label": label},
            )
            return True
        except httpx.HTTPStatusError as exc:
            self._log(
                "add_pr_label",
                "failure",
                {
                    "owner": owner,
                    "repo": repo,
                    "pr_number": pr_number,
                    "label": label,
                    "status_code": exc.response.status_code,
                },
            )
            return False
        except Exception as exc:
            self._log(
                "add_pr_label",
                "failure",
                {
                    "owner": owner,
                    "repo": repo,
                    "pr_number": pr_number,
                    "label": label,
                    "error": str(exc),
                },
            )
            return False

    # ------------------------------------------------------------------
    # remove_pr_label
    # ------------------------------------------------------------------

    def remove_pr_label(
        self, owner: str, repo: str, pr_number: int, label: str
    ) -> bool:
        """
        Remove a label from a pull request.
        Returns True on success (also True if the label was not present).
        """
        url = (
            f"{self._BASE}/repos/{owner}/{repo}/issues/{pr_number}/labels/"
            + label.replace(" ", "%20")
        )
        try:
            with self._client() as client:
                resp = client.delete(url)
                if resp.status_code == 404:
                    # Label not present – treat as success
                    self._log(
                        "remove_pr_label",
                        "success",
                        {
                            "owner": owner,
                            "repo": repo,
                            "pr_number": pr_number,
                            "label": label,
                            "note": "label_not_present",
                        },
                    )
                    return True
                resp.raise_for_status()
            self._log(
                "remove_pr_label",
                "success",
                {"owner": owner, "repo": repo, "pr_number": pr_number, "label": label},
            )
            return True
        except httpx.HTTPStatusError as exc:
            self._log(
                "remove_pr_label",
                "failure",
                {
                    "owner": owner,
                    "repo": repo,
                    "pr_number": pr_number,
                    "label": label,
                    "status_code": exc.response.status_code,
                },
            )
            return False
        except Exception as exc:
            self._log(
                "remove_pr_label",
                "failure",
                {
                    "owner": owner,
                    "repo": repo,
                    "pr_number": pr_number,
                    "label": label,
                    "error": str(exc),
                },
            )
            return False

    # ------------------------------------------------------------------
    # get_pr_reviews
    # ------------------------------------------------------------------

    def get_pr_reviews(self, owner: str, repo: str, pr_number: int) -> list:
        """
        Return all reviews for a pull request, newest first.
        """
        url = f"{self._BASE}/repos/{owner}/{repo}/pulls/{pr_number}/reviews"
        reviews: list = []
        page = 1
        try:
            with self._client() as client:
                while True:
                    resp = client.get(url, params={"per_page": 100, "page": page})
                    resp.raise_for_status()
                    page_data: list = resp.json()
                    if not page_data:
                        break
                    reviews.extend(page_data)
                    page += 1
                    if len(page_data) < 100:
                        break
            self._log(
                "get_pr_reviews",
                "success",
                {
                    "owner": owner,
                    "repo": repo,
                    "pr_number": pr_number,
                    "count": len(reviews),
                },
            )
            return reviews
        except httpx.HTTPStatusError as exc:
            self._log(
                "get_pr_reviews",
                "failure",
                {
                    "owner": owner,
                    "repo": repo,
                    "pr_number": pr_number,
                    "status_code": exc.response.status_code,
                },
            )
            return []
        except Exception as exc:
            self._log(
                "get_pr_reviews",
                "failure",
                {
                    "owner": owner,
                    "repo": repo,
                    "pr_number": pr_number,
                    "error": str(exc),
                },
            )
            return []

    # ------------------------------------------------------------------
    # Private: ensure label exists in repo
    # ------------------------------------------------------------------

    def _ensure_label_exists(self, owner: str, repo: str, label: str) -> None:
        """Create the label in the repo if it does not already exist."""
        check_url = f"{self._BASE}/repos/{owner}/{repo}/labels/{label.replace(' ', '%20')}"
        create_url = f"{self._BASE}/repos/{owner}/{repo}/labels"
        try:
            with self._client() as client:
                resp = client.get(check_url)
                if resp.status_code == 200:
                    return  # already exists
                # Create it
                client.post(
                    create_url,
                    json={"name": label, "color": "d73a4a"},  # red
                )
        except Exception:
            pass  # best-effort; add_pr_label will surface any real error
