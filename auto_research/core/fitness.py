"""Fitness scoring (PageRank) and diversity maintenance (MAP-Elites).

Implements the two core evolutionary mechanisms:
- PageRank on the comparisons graph: "papers that beat many strong papers are important"
- MAP-Elites grid (topic x perspective): preserves diversity by only competing within cells
"""

import random
import sqlite3
import uuid
from datetime import datetime, timezone

import networkx as nx


def calculate_fitness(conn: sqlite3.Connection, topic: str) -> None:
    """Recalculate fitness scores using PageRank on the comparisons graph.

    Builds a directed graph where edges go from loser to winner (losers "vote for" winners).
    Papers that beat many strong papers get higher PageRank scores.
    Updates the fitness column for all papers in the given topic.
    """
    # Get all papers for this topic
    papers = conn.execute(
        "SELECT id FROM papers WHERE topic_tag = ? AND status != 'archived'",
        (topic,),
    ).fetchall()

    paper_ids = {row["id"] for row in papers}
    if len(paper_ids) < 2:
        return

    # Build directed graph: loser -> winner (losers "vote for" winners)
    # PageRank gives high scores to nodes with many incoming links,
    # so winners accumulate votes from the papers they beat.
    G = nx.DiGraph()
    G.add_nodes_from(paper_ids)

    comparisons = conn.execute(
        """SELECT c.winner, c.loser FROM comparisons c
           JOIN papers pw ON c.winner = pw.id
           JOIN papers pl ON c.loser = pl.id
           WHERE pw.topic_tag = ? AND pl.topic_tag = ?""",
        (topic, topic),
    ).fetchall()

    for comp in comparisons:
        if comp["winner"] in paper_ids and comp["loser"] in paper_ids:
            G.add_edge(comp["loser"], comp["winner"])

    # Calculate PageRank
    if G.number_of_edges() == 0:
        return

    try:
        pr = nx.pagerank(G, alpha=0.85, max_iter=100)
    except nx.PowerIterationFailedConvergence:
        # Fallback to simple win ratio
        pr = {}
        for pid in paper_ids:
            wins = conn.execute(
                "SELECT COUNT(*) as cnt FROM comparisons WHERE winner = ?", (pid,)
            ).fetchone()["cnt"]
            total = conn.execute(
                "SELECT COUNT(*) as cnt FROM comparisons WHERE winner = ? OR loser = ?",
                (pid, pid),
            ).fetchone()["cnt"]
            pr[pid] = wins / max(total, 1)

    # Normalize to [0, 1]
    if pr:
        max_pr = max(pr.values())
        min_pr = min(pr.values())
        pr_range = max_pr - min_pr if max_pr != min_pr else 1.0

        for pid, score in pr.items():
            normalized = (score - min_pr) / pr_range
            conn.execute(
                "UPDATE papers SET fitness = ? WHERE id = ?",
                (round(normalized, 4), pid),
            )

    conn.commit()


def update_lifecycle_states(conn: sqlite3.Connection, topic: str) -> None:
    """Update paper lifecycle states based on fitness and comparison history.

    State transitions:
    - active -> foundational: fitness > 0.7 AND > 5 wins
    - active -> contested: lost 3+ recent comparisons
    - contested/active -> archived: handled by MAP-Elites (separate function)

    All transitions are logged to audit_chain.
    """
    now = datetime.now(timezone.utc).isoformat()

    # active -> foundational: high fitness + proven track record
    foundational_candidates = conn.execute(
        """SELECT p.id, p.status FROM papers p
           WHERE p.topic_tag = ? AND p.status = 'active' AND p.fitness > 0.7
           AND (SELECT COUNT(*) FROM comparisons WHERE winner = p.id) > 5""",
        (topic,),
    ).fetchall()

    for paper in foundational_candidates:
        conn.execute(
            "UPDATE papers SET status = 'foundational' WHERE id = ?",
            (paper["id"],),
        )
        _log_audit(conn, paper["id"], "status_changed", paper["status"], "foundational", now)

    # active -> contested: lost 3+ of last 5 comparisons (wins AND losses)
    contested_candidates = conn.execute(
        """SELECT p.id, p.status FROM papers p
           WHERE p.topic_tag = ? AND p.status = 'active'
           AND (SELECT COUNT(*) FROM (
                SELECT CASE WHEN loser = p.id THEN 1 ELSE 0 END as was_loss
                FROM comparisons
                WHERE winner = p.id OR loser = p.id
                ORDER BY created_at DESC LIMIT 5
           ) WHERE was_loss = 1) >= 3""",
        (topic,),
    ).fetchall()

    for paper in contested_candidates:
        conn.execute(
            "UPDATE papers SET status = 'contested' WHERE id = ?",
            (paper["id"],),
        )
        _log_audit(conn, paper["id"], "status_changed", paper["status"], "contested", now)

    conn.commit()


def update_map_elites(conn: sqlite3.Connection, topic: str) -> None:
    """Update MAP-Elites grid: keep best per (topic_tag, perspective) cell.

    In each cell, the highest-fitness paper stays active.
    Lower-fitness papers are archived (not deleted).
    At least 1 survivor per occupied cell is guaranteed.
    """
    now = datetime.now(timezone.utc).isoformat()

    # Get all perspective values for this topic
    perspectives = conn.execute(
        """SELECT DISTINCT perspective FROM papers
           WHERE topic_tag = ? AND status IN ('active', 'contested')""",
        (topic,),
    ).fetchall()

    for row in perspectives:
        perspective = row["perspective"]

        # Get all non-archived papers in this cell, ordered by fitness
        cell_papers = conn.execute(
            """SELECT id, fitness, status FROM papers
               WHERE topic_tag = ? AND perspective = ? AND status IN ('active', 'contested', 'foundational')
               ORDER BY fitness DESC""",
            (topic, perspective),
        ).fetchall()

        if len(cell_papers) <= 1:
            continue  # Keep at least 1 survivor

        # Keep the champion (first one), archive the rest if cell is overcrowded
        # Only archive if there are more than 3 papers per cell (allow some diversity)
        if len(cell_papers) > 3:
            for paper in cell_papers[3:]:
                if paper["status"] in ("active", "contested"):
                    conn.execute(
                        "UPDATE papers SET status = 'archived' WHERE id = ?",
                        (paper["id"],),
                    )
                    _log_audit(
                        conn, paper["id"], "archived",
                        paper["status"], "archived", now,
                    )

    conn.commit()


def get_champion(conn: sqlite3.Connection, topic: str) -> dict:
    """Return the highest-fitness active/foundational paper for a topic."""
    row = conn.execute(
        """SELECT * FROM papers
           WHERE topic_tag = ? AND status IN ('active', 'foundational')
           ORDER BY fitness DESC LIMIT 1""",
        (topic,),
    ).fetchone()
    return dict(row) if row else {}


def select_rival(conn: sqlite3.Connection, topic: str) -> dict:
    """Select a rival paper for comparison.

    70% chance: champion (highest fitness)
    30% chance: random active paper

    SGD-inspired exploration: mostly challenge the best,
    sometimes explore weaker alternatives.
    """
    if random.random() < 0.7:
        rival = get_champion(conn, topic)
        if rival:
            return rival

    # Random active paper
    papers = conn.execute(
        """SELECT * FROM papers
           WHERE topic_tag = ? AND status IN ('active', 'contested', 'foundational')
           ORDER BY RANDOM() LIMIT 1""",
        (topic,),
    ).fetchone()

    return dict(papers) if papers else {}


def _log_audit(
    conn: sqlite3.Connection,
    paper_id: str,
    event_type: str,
    previous_state: str,
    new_state: str,
    created_at: str,
    agent_id: str = "system",
) -> None:
    """Log a state change to the immutable audit chain."""
    audit_id = uuid.uuid4().hex[:16]
    conn.execute(
        """INSERT INTO audit_chain
           (id, paper_id, event_type, previous_state, new_state, agent_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (audit_id, paper_id, event_type, previous_state, new_state, agent_id, created_at),
    )
