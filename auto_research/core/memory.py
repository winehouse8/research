"""Memory system with L0/L1/L2 hierarchical loading and annotation injection.

Implements the OpenViking pattern for token-efficient memory access:
- L0 (~50 tokens): Quick relevance filtering
- L1 (~2000 tokens): Planning and reasoning context
- L2 (full text): On-demand deep reading

Also implements Context Hub pattern for session annotation injection.
"""

import hashlib
import json
import logging
import random
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("autoresearch.memory")


def paper_id(claim: str, l1_summary: str) -> str:
    """Generate deterministic paper ID from claim + l1_summary.

    Uses SHA-256 hash truncated to 16 hex chars (64 bits).
    Hashing claim + l1_summary avoids collision risk from papers
    with similar openings on the same topic.
    """
    content = claim + l1_summary
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def save_paper(conn: sqlite3.Connection, paper: dict) -> str:
    """Save a paper to the database with audit trail.

    Args:
        conn: SQLite connection.
        paper: Dict with keys: claim, l0_summary, l1_summary, l2_content,
               evidence_sources, assumptions, topic_tag, perspective.

    Returns:
        The paper ID (SHA-256 hash).
    """
    pid = paper_id(paper["claim"], paper["l1_summary"])
    now = datetime.now(timezone.utc).isoformat()

    # Check if paper already exists (deterministic ID means same content = same ID)
    existing = conn.execute("SELECT id FROM papers WHERE id = ?", (pid,)).fetchone()
    if existing:
        return pid

    # Popper falsifiability gate: warn if assumptions are weak/missing
    assumptions = paper.get("assumptions", "")
    if not assumptions or assumptions in ("None stated", "This is a placeholder paper."):
        logger.warning(f"Popper gate: paper '{paper['claim'][:60]}' has weak/missing assumptions")

    conn.execute(
        """INSERT INTO papers
           (id, claim, l0_summary, l1_summary, l2_content, evidence_sources,
            assumptions, fitness, status, topic_tag, perspective, created_at, source_uri)
           VALUES (?, ?, ?, ?, ?, ?, ?, 0.5, 'active', ?, ?, ?, ?)""",
        (
            pid,
            paper["claim"],
            paper.get("l0_summary", ""),
            paper.get("l1_summary", ""),
            paper.get("l2_content", ""),
            json.dumps(paper.get("evidence_sources", []), ensure_ascii=False),
            assumptions,
            paper.get("topic_tag", "general"),
            paper.get("perspective", "empirical"),
            now,
            paper.get("source_uri", ""),
        ),
    )

    # Audit trail
    audit_id = uuid.uuid4().hex[:16]
    conn.execute(
        """INSERT INTO audit_chain
           (id, paper_id, event_type, previous_state, new_state, agent_id, created_at)
           VALUES (?, ?, 'first_seen', NULL, 'active', 'system', ?)""",
        (audit_id, pid, now),
    )

    conn.commit()
    return pid


def build_session_context(
    conn: sqlite3.Connection,
    topic: str,
    session_id: str,
    max_tokens: int = 4000,
) -> str:
    """Build session context using L0/L1/L2 hierarchical loading.

    Process:
    1. Load all L0 summaries for the topic (fast scan)
    2. Select top-fitness papers + 2 random papers
    3. Load L1 summaries within token budget
    4. Prepend recent annotations (last 5 for this topic)
    5. Return assembled context string

    Args:
        conn: SQLite connection.
        topic: Topic tag to filter papers.
        session_id: Current session ID for annotation filtering.
        max_tokens: Approximate token budget (word count proxy).

    Returns:
        Assembled context string for agent consumption.
    """
    parts = []

    # --- Annotations (prepended first, Context Hub pattern) ---
    annotations = conn.execute(
        """SELECT a.content, a.tags, a.created_at, p.claim
           FROM annotations a
           JOIN papers p ON a.paper_id = p.id
           WHERE p.topic_tag = ?
           ORDER BY a.created_at DESC
           LIMIT 5""",
        (topic,),
    ).fetchall()

    if annotations:
        parts.append("## Previous Session Discoveries\n")
        for ann in annotations:
            tags = json.loads(ann["tags"]) if ann["tags"] else []
            tag_str = ", ".join(tags) if tags else "general"
            parts.append(f"- [{tag_str}] {ann['content']} (re: {ann['claim'][:80]})")
        parts.append("")

    # --- L0 scan: all papers for this topic ---
    all_papers = conn.execute(
        """SELECT id, claim, l0_summary, fitness, status, perspective
           FROM papers
           WHERE topic_tag = ? AND status != 'archived'
           ORDER BY fitness DESC""",
        (topic,),
    ).fetchall()

    if not all_papers:
        return "\n".join(parts) + "\nNo existing papers found for this topic."

    # --- Select papers to load at L1 level ---
    # Top-fitness papers (up to 3)
    top_papers = all_papers[:3]

    # Random papers (up to 2, excluding top papers)
    remaining = all_papers[3:]
    random_picks = random.sample(remaining, min(2, len(remaining))) if remaining else []

    selected_ids = [p["id"] for p in top_papers] + [p["id"] for p in random_picks]

    # --- L0 overview ---
    parts.append(f"## Knowledge Overview ({len(all_papers)} active papers)\n")
    for p in all_papers:
        marker = "★" if p["id"] in selected_ids else " "
        parts.append(
            f"{marker} [{p['perspective']}] (fitness={p['fitness']:.2f}) {p['claim'][:100]}"
        )
    parts.append("")

    # --- L1 detailed context (within token budget) ---
    parts.append("## Detailed Context (L1)\n")
    token_count = sum(len(part.split()) for part in parts)

    for pid in selected_ids:
        if token_count >= max_tokens:
            break
        row = conn.execute(
            "SELECT claim, l1_summary, fitness, perspective, assumptions FROM papers WHERE id = ?",
            (pid,),
        ).fetchone()
        if row:
            block = (
                f"### [{row['perspective']}] {row['claim']}\n"
                f"Fitness: {row['fitness']:.2f}\n"
                f"Assumptions: {row['assumptions'] or 'None stated'}\n"
                f"{row['l1_summary']}\n"
            )
            block_tokens = len(block.split())
            if token_count + block_tokens <= max_tokens:
                parts.append(block)
                token_count += block_tokens

    return "\n".join(parts)


def save_annotation(
    conn: sqlite3.Connection,
    paper_id_val: str,
    session_id: str,
    content: str,
    tags: list,
) -> str:
    """Save a session annotation for a paper.

    Args:
        conn: SQLite connection.
        paper_id_val: The paper this annotation relates to.
        session_id: Current session ID.
        content: Annotation content text.
        tags: List of tag strings.

    Returns:
        The annotation ID.
    """
    ann_id = uuid.uuid4().hex[:16]
    now = datetime.now(timezone.utc).isoformat()

    conn.execute(
        """INSERT INTO annotations (id, paper_id, session_id, content, tags, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (ann_id, paper_id_val, session_id, content, json.dumps(tags, ensure_ascii=False), now),
    )
    conn.commit()
    return ann_id


def search_papers(
    conn: sqlite3.Connection,
    query_text: str,
    topic: str,
) -> list:
    """Search papers using SQL LIKE on claim + l0_summary.

    No vector embeddings — L0 + LLM filtering is sufficient per strategy report.

    Args:
        conn: SQLite connection.
        query_text: Search query string.
        topic: Topic tag to filter.

    Returns:
        List of matching paper dicts (id, claim, l0_summary, fitness).
    """
    pattern = f"%{query_text}%"
    rows = conn.execute(
        """SELECT id, claim, l0_summary, fitness, status, perspective
           FROM papers
           WHERE topic_tag = ? AND status != 'archived'
             AND (claim LIKE ? OR l0_summary LIKE ?)
           ORDER BY fitness DESC
           LIMIT 10""",
        (topic, pattern, pattern),
    ).fetchall()

    return [dict(row) for row in rows]


def get_paper(conn: sqlite3.Connection, pid: str) -> Optional[dict]:
    """Get a single paper by ID with all fields."""
    row = conn.execute("SELECT * FROM papers WHERE id = ?", (pid,)).fetchone()
    return dict(row) if row else None
