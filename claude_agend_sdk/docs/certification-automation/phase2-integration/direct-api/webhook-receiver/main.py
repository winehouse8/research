"""
Webhook receiver for JIRA + GitHub CI/CD certification evidence automation.
Requirements: fastapi, uvicorn, httpx, python-dotenv, pydantic
"""

import hashlib
import hmac
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Optional

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request, status
from pydantic import BaseModel

from github_client import GitHubClient, extract_jira_ticket
from jira_client import JiraClient

load_dotenv()

# ---------------------------------------------------------------------------
# Structured JSON logger
# ---------------------------------------------------------------------------

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
        }
        if hasattr(record, "extra"):
            log_entry.update(record.extra)
        return json.dumps(log_entry)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


logger = get_logger("webhook_receiver")

# ---------------------------------------------------------------------------
# Audit logger – emits the canonical evidence record shape
# ---------------------------------------------------------------------------

def audit_log(
    event_type: str,
    jira_ticket: Optional[str],
    github_pr: Optional[str],
    actor: str,
    action: str,
    result: str,
    details: Optional[dict] = None,
) -> None:
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "jira_ticket": jira_ticket or "",
        "github_pr": github_pr or "",
        "actor": actor,
        "action": action,
        "result": result,
        "details": details or {},
    }
    print(json.dumps(record), flush=True)


# ---------------------------------------------------------------------------
# Environment / clients
# ---------------------------------------------------------------------------

GITHUB_WEBHOOK_SECRET: str = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
JIRA_WEBHOOK_TOKEN: str = os.environ.get("JIRA_WEBHOOK_TOKEN", "")

jira = JiraClient(
    base_url=os.environ["JIRA_BASE_URL"],
    email=os.environ["JIRA_EMAIL"],
    api_token=os.environ["JIRA_API_TOKEN"],
)

github = GitHubClient(token=os.environ["GITHUB_TOKEN"])

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Certification Evidence Webhook Receiver", version="1.0.0")


# ---------------------------------------------------------------------------
# Signature / token verification helpers
# ---------------------------------------------------------------------------

def _verify_github_signature(payload: bytes, signature_header: Optional[str]) -> None:
    """Validate X-Hub-Signature-256 HMAC."""
    if not GITHUB_WEBHOOK_SECRET:
        logger.warning("GITHUB_WEBHOOK_SECRET not set – skipping signature check")
        return
    if not signature_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Hub-Signature-256 header",
        )
    algorithm, _, provided_digest = signature_header.partition("=")
    if algorithm != "sha256":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported signature algorithm",
        )
    expected = hmac.new(
        GITHUB_WEBHOOK_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, provided_digest):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid GitHub webhook signature",
        )


def _verify_jira_token(token_header: Optional[str]) -> None:
    """Validate JIRA webhook token passed as X-Jira-Webhook-Token."""
    if not JIRA_WEBHOOK_TOKEN:
        logger.warning("JIRA_WEBHOOK_TOKEN not set – skipping token check")
        return
    if not token_header or not hmac.compare_digest(token_header, JIRA_WEBHOOK_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid JIRA webhook token",
        )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


# ---------------------------------------------------------------------------
# GitHub webhook handler
# ---------------------------------------------------------------------------

@app.post("/webhook/github", status_code=status.HTTP_200_OK)
async def github_webhook(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None),
    x_github_event: Optional[str] = Header(None),
) -> dict:
    payload_bytes = await request.body()
    _verify_github_signature(payload_bytes, x_hub_signature_256)

    try:
        payload: dict[str, Any] = json.loads(payload_bytes)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    event = x_github_event or "unknown"
    action = payload.get("action", "")
    logger.info("GitHub event received", extra={"event": event, "action": action})

    if event == "pull_request":
        await _handle_pull_request(payload, action)
    elif event == "pull_request_review":
        await _handle_pr_review(payload, action)
    else:
        logger.info("Unhandled GitHub event", extra={"event": event})

    return {"received": True}


async def _handle_pull_request(payload: dict, action: str) -> None:
    pr = payload.get("pull_request", {})
    pr_number: int = pr.get("number", 0)
    repo_full: str = payload.get("repository", {}).get("full_name", "")
    pr_ref = f"{repo_full}#{pr_number}"
    actor: str = pr.get("user", {}).get("login", "unknown")
    head_sha: str = pr.get("head", {}).get("sha", "")

    # Extract JIRA ticket from title + body
    title: str = pr.get("title", "")
    body: str = pr.get("body", "") or ""
    ticket = extract_jira_ticket(f"{title} {body}")

    owner, _, repo = repo_full.partition("/")

    if action == "opened":
        if ticket:
            pr_url = pr.get("html_url", "")
            ok = jira.link_to_github_pr(ticket, pr_url)
            audit_log(
                event_type="github.pr.opened",
                jira_ticket=ticket,
                github_pr=pr_ref,
                actor=actor,
                action="link_pr_to_jira",
                result="success" if ok else "failure",
                details={"pr_url": pr_url},
            )

            ok2 = jira.transition_issue(ticket, "In Review")
            audit_log(
                event_type="github.pr.opened",
                jira_ticket=ticket,
                github_pr=pr_ref,
                actor=actor,
                action="transition_to_in_review",
                result="success" if ok2 else "failure",
            )
        else:
            logger.warning("No JIRA ticket found in PR", extra={"pr": pr_ref})

    elif action == "closed":
        merged: bool = pr.get("merged", False)
        if merged and ticket:
            ok = jira.transition_issue(ticket, "Merged")
            audit_log(
                event_type="github.pr.merged",
                jira_ticket=ticket,
                github_pr=pr_ref,
                actor=actor,
                action="transition_to_merged",
                result="success" if ok else "failure",
            )
            # Trigger evidence collection comment
            comment = (
                f"PR {pr_ref} has been **merged** by @{actor} on "
                f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}. "
                "Evidence collection triggered."
            )
            ok2 = jira.add_comment(ticket, comment)
            audit_log(
                event_type="github.pr.merged",
                jira_ticket=ticket,
                github_pr=pr_ref,
                actor=actor,
                action="add_merge_comment",
                result="success" if ok2 else "failure",
            )

    else:
        logger.info("Unhandled PR action", extra={"action": action})


async def _handle_pr_review(payload: dict, action: str) -> None:
    if action != "submitted":
        return

    review = payload.get("review", {})
    review_state: str = review.get("state", "").lower()
    if review_state != "approved":
        return

    pr = payload.get("pull_request", {})
    pr_number: int = pr.get("number", 0)
    repo_full: str = payload.get("repository", {}).get("full_name", "")
    pr_ref = f"{repo_full}#{pr_number}"
    approver: str = review.get("user", {}).get("login", "unknown")
    submitted_at: str = review.get("submitted_at", datetime.now(timezone.utc).isoformat())

    title: str = pr.get("title", "")
    body: str = pr.get("body", "") or ""
    ticket = extract_jira_ticket(f"{title} {body}")

    if ticket:
        comment = (
            f"GitHub PR {pr_ref} was **approved** by @{approver} at {submitted_at}."
        )
        ok = jira.add_comment(ticket, comment)
        audit_log(
            event_type="github.pr_review.approved",
            jira_ticket=ticket,
            github_pr=pr_ref,
            actor=approver,
            action="add_approval_comment",
            result="success" if ok else "failure",
            details={"submitted_at": submitted_at},
        )
    else:
        logger.warning("No JIRA ticket found in PR for review event", extra={"pr": pr_ref})


# ---------------------------------------------------------------------------
# JIRA webhook handler
# ---------------------------------------------------------------------------

@app.post("/webhook/jira", status_code=status.HTTP_200_OK)
async def jira_webhook(
    request: Request,
    x_jira_webhook_token: Optional[str] = Header(None),
) -> dict:
    _verify_jira_token(x_jira_webhook_token)

    payload_bytes = await request.body()
    try:
        payload: dict[str, Any] = json.loads(payload_bytes)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    webhook_event: str = payload.get("webhookEvent", "")
    logger.info("JIRA event received", extra={"webhookEvent": webhook_event})

    if webhook_event == "jira:issue_updated":
        await _handle_jira_issue_updated(payload)
    else:
        logger.info("Unhandled JIRA event", extra={"webhookEvent": webhook_event})

    return {"received": True}


async def _handle_jira_issue_updated(payload: dict) -> None:
    issue = payload.get("issue", {})
    ticket_id: str = issue.get("key", "")
    actor: str = payload.get("user", {}).get("displayName", "unknown")

    changelog = payload.get("changelog", {})
    items: list = changelog.get("items", [])

    for item in items:
        field: str = item.get("field", "")
        if field.lower() != "status":
            continue

        new_status: str = item.get("toString", "")
        old_status: str = item.get("fromString", "")

        audit_log(
            event_type="jira.issue.status_changed",
            jira_ticket=ticket_id,
            github_pr=None,
            actor=actor,
            action="status_changed",
            result="success",
            details={"from": old_status, "to": new_status},
        )

        if new_status.lower() == "approved":
            await _on_jira_approved(ticket_id, actor)
        elif new_status.lower() == "rejected":
            await _on_jira_rejected(ticket_id, actor)


async def _on_jira_approved(ticket_id: str, actor: str) -> None:
    """Set a successful commit status on the linked GitHub PR's head SHA."""
    issue = jira.get_issue(ticket_id)
    if not issue:
        logger.error("Could not fetch JIRA issue", extra={"ticket": ticket_id})
        return

    pr_url = _extract_pr_url_from_issue(issue)
    if not pr_url:
        logger.warning("No linked GitHub PR found for ticket", extra={"ticket": ticket_id})
        return

    owner, repo, pr_number = _parse_pr_url(pr_url)
    if not (owner and repo and pr_number):
        return

    pr_data = github.get_pr(owner, repo, int(pr_number))
    sha: str = (pr_data or {}).get("head", {}).get("sha", "")
    if not sha:
        return

    ok = github.create_commit_status(
        owner=owner,
        repo=repo,
        sha=sha,
        state="success",
        description=f"JIRA ticket {ticket_id} approved by {actor}",
        context="jira/approval",
    )
    pr_ref = f"{owner}/{repo}#{pr_number}"
    audit_log(
        event_type="jira.issue.approved",
        jira_ticket=ticket_id,
        github_pr=pr_ref,
        actor=actor,
        action="set_github_commit_status_success",
        result="success" if ok else "failure",
        details={"sha": sha},
    )


async def _on_jira_rejected(ticket_id: str, actor: str) -> None:
    """Add a blocking label to the linked GitHub PR."""
    issue = jira.get_issue(ticket_id)
    if not issue:
        logger.error("Could not fetch JIRA issue", extra={"ticket": ticket_id})
        return

    pr_url = _extract_pr_url_from_issue(issue)
    if not pr_url:
        logger.warning("No linked GitHub PR found for ticket", extra={"ticket": ticket_id})
        return

    owner, repo, pr_number = _parse_pr_url(pr_url)
    if not (owner and repo and pr_number):
        return

    ok = github.add_pr_label(owner, repo, int(pr_number), "jira-rejected")
    pr_ref = f"{owner}/{repo}#{pr_number}"
    audit_log(
        event_type="jira.issue.rejected",
        jira_ticket=ticket_id,
        github_pr=pr_ref,
        actor=actor,
        action="add_rejected_label",
        result="success" if ok else "failure",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_pr_url_from_issue(issue: dict) -> Optional[str]:
    """Return the first GitHub PR URL from JIRA remote links embedded in issue."""
    remote_links: list = issue.get("remoteLinks", [])
    for link in remote_links:
        url: str = link.get("object", {}).get("url", "")
        if "github.com" in url and "/pull/" in url:
            return url
    return None


def _parse_pr_url(url: str) -> tuple[str, str, str]:
    """
    Parse 'https://github.com/owner/repo/pull/123' into (owner, repo, pr_number).
    Returns ('', '', '') on failure.
    """
    try:
        parts = url.rstrip("/").split("/")
        # [..., 'github.com', owner, repo, 'pull', pr_number]
        idx = parts.index("pull")
        pr_number = parts[idx + 1]
        repo = parts[idx - 1]
        owner = parts[idx - 2]
        return owner, repo, pr_number
    except (ValueError, IndexError):
        return "", "", ""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        log_config=None,  # use our own JSON logger
    )
