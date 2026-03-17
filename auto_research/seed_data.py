#!/usr/bin/env python3
"""Cold start seed data: 10 papers on agentic memory.

Extracted from the research docs (260317_*.md files).
Provides deterministic cold start alternative to LLM-generated seeds.

Usage:
    python seed_data.py --db db/knowledge.db --topic agentic_memory
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from auto_research.core import init_db
from auto_research.core.memory import save_paper


SEED_PAPERS = [
    {
        "claim": "L0/L1/L2 hierarchical memory loading reduces token costs by 91% while maintaining retrieval quality.",
        "l0_summary": "Hierarchical memory (L0 filter, L1 reasoning, L2 full) achieves 91% token savings per OpenViking.",
        "l1_summary": "The OpenViking (ByteDance 2026) pattern demonstrates that three-tier memory loading drastically reduces token consumption. L0 summaries (~50 tokens) enable fast relevance filtering across hundreds of items. Only relevant items are promoted to L1 (~2000 tokens) for planning and reasoning. L2 full content is loaded on-demand. This prevents the token explosion problem that makes naive approaches unviable at scale. The 91% reduction was measured in production deployment.",
        "l2_content": "Full analysis of hierarchical memory loading patterns across 7 open-source implementations...",
        "evidence_sources": [{"title": "OpenViking ByteDance 2026", "url": "https://github.com/bytedance/openviking", "excerpt": "91% token reduction with L0/L1/L2 tiered loading"}],
        "assumptions": "LLM can accurately assess relevance from L0 summaries alone; L0 summaries capture sufficient semantic content for filtering",
        "topic_tag": "agentic_memory",
        "perspective": "empirical",
    },
    {
        "claim": "SHA-256 content-hash IDs enable deterministic cross-session node reconnection without external coordination.",
        "l0_summary": "Content-hash IDs allow agents to rediscover same nodes across sessions without UUID registries.",
        "l1_summary": "The Wrkr pattern uses SHA-256 hashes of content to generate deterministic IDs. When an agent restarts and encounters the same knowledge, it automatically reconnects to the existing node rather than creating duplicates. This eliminates the need for external ID registries or session state persistence for identity management. The key insight is that knowledge identity should be derived from content, not from creation context.",
        "l2_content": "Detailed analysis of content-addressable storage patterns in agent memory systems...",
        "evidence_sources": [{"title": "Wrkr Agent Framework", "url": "https://github.com/wrkr-ai/wrkr", "excerpt": "Deterministic content-hash IDs for cross-session continuity"}],
        "assumptions": "Content is the primary identity signal; two semantically equivalent but textually different items should have different IDs",
        "topic_tag": "agentic_memory",
        "perspective": "theoretical",
    },
    {
        "claim": "Pairwise LLM-as-Judge comparison with position bias removal is sufficient for knowledge quality assessment.",
        "l0_summary": "LLM judges can evaluate paper quality via pairwise comparison; A/B B/A dedup removes position bias.",
        "l1_summary": "Instead of complex rubric-based evaluation, a simple pairwise comparison approach works: present two papers and ask which is better supported by evidence. Running each comparison twice (A-first then B-first) and only counting unanimous results removes position bias. This approach requires only a comparisons(winner, loser, created_at) table — no judge metadata, scores, or rubrics. The simplicity of the evaluation mechanism is a feature, not a limitation.",
        "l2_content": "Analysis of LLM-as-Judge evaluation patterns and bias mitigation strategies...",
        "evidence_sources": [{"title": "LLM-as-Judge Survey", "url": "https://arxiv.org/abs/2310.17631", "excerpt": "Pairwise comparison is most reliable LLM evaluation method"}],
        "assumptions": "LLM can judge evidence quality; position bias is the dominant bias mode; unanimous agreement indicates reliable judgment",
        "topic_tag": "agentic_memory",
        "perspective": "applied",
    },
    {
        "claim": "MAP-Elites diversity grids prevent premature convergence by protecting minority viewpoints in local competition.",
        "l0_summary": "MAP-Elites (topic x perspective) ensures minority views survive by competing only within their cell.",
        "l1_summary": "In a global ranking system, minority perspectives are quickly eliminated. MAP-Elites creates a 2D grid where papers compete only within their (topic_tag, perspective) cell. An applied perspective paper only competes against other applied papers on the same topic. This ensures at least one survivor per cell, preventing the ecosystem from collapsing to a single dominant narrative. Combined with 30% random rival selection, this creates SGD-inspired exploration.",
        "l2_content": "Detailed MAP-Elites implementation for knowledge diversity in agent ecosystems...",
        "evidence_sources": [{"title": "MAP-Elites: Illuminating Search", "url": "https://arxiv.org/abs/1504.04909", "excerpt": "Quality-diversity optimization via feature-space discretization"}],
        "assumptions": "4 perspective categories (empirical/theoretical/applied/critical) are sufficient; cell-local competition is meaningful",
        "topic_tag": "agentic_memory",
        "perspective": "theoretical",
    },
    {
        "claim": "Append-only audit chains with immutability triggers provide reliable provenance tracking for agent-generated knowledge.",
        "l0_summary": "Immutable audit_chain table tracks all state transitions with SQLite triggers preventing modification.",
        "l1_summary": "The Wrkr proof chain pattern logs every state change (first_seen, status_changed, evaluated, archived, revived) as an append-only record. SQLite BEFORE UPDATE and BEFORE DELETE triggers enforce immutability at the database level. This allows full reconstruction of 'why was this paper archived?' without relying on agent memory. The audit chain is the ground truth for provenance, not agent logs.",
        "l2_content": "Implementation of append-only audit trails in SQLite for agent knowledge systems...",
        "evidence_sources": [{"title": "Wrkr Proof Chain", "url": "https://github.com/wrkr-ai/wrkr", "excerpt": "Append-only audit trail with database-enforced immutability"}],
        "assumptions": "SQLite triggers are sufficient for immutability enforcement; audit granularity at event level is adequate",
        "topic_tag": "agentic_memory",
        "perspective": "applied",
    },
    {
        "claim": "Session annotations (Context Hub pattern) enable cross-session discovery persistence without full state serialization.",
        "l0_summary": "Annotations from previous sessions are auto-injected into new session prompts for continuity.",
        "l1_summary": "Andrew Ng's Context Hub pattern stores session-level discoveries as annotations attached to papers. When a new session starts, recent annotations are prepended to the agent's context, providing continuity without serializing the agent's entire state. This is lighter than full checkpoint/restore and more targeted than loading all papers. Annotations capture 'what was discovered' rather than 'what was processed', making them semantically richer than raw logs.",
        "l2_content": "Analysis of session annotation patterns from Context Hub and similar systems...",
        "evidence_sources": [{"title": "Context Hub (Andrew Ng)", "url": "https://contextkit.ai", "excerpt": "Annotation-based cross-session discovery persistence"}],
        "assumptions": "5 recent annotations are sufficient for session continuity; annotations are more useful than raw session logs",
        "topic_tag": "agentic_memory",
        "perspective": "empirical",
    },
    {
        "claim": "PageRank on comparison graphs captures 'importance' better than simple win ratios because it weights opponent strength.",
        "l0_summary": "PageRank on winner->loser edges produces importance scores that account for opponent quality.",
        "l1_summary": "A simple wins/total ratio treats all victories equally. PageRank on the comparison graph (directed edges from winner to loser) naturally weights beating strong opponents higher. A paper that beats the champion gets more fitness than one that beats a weak paper. This mirrors academic citation analysis: being cited by important papers matters more than raw citation count. The implementation requires only 5 lines of networkx code.",
        "l2_content": "Comparison of fitness scoring methods for evolutionary knowledge systems...",
        "evidence_sources": [{"title": "PageRank Original Paper", "url": "https://ilpubs.stanford.edu:8090/422/", "excerpt": "Recursive importance scoring via link analysis"}],
        "assumptions": "The comparison graph is sufficiently dense for PageRank convergence; winner->loser directionality is semantically correct",
        "topic_tag": "agentic_memory",
        "perspective": "theoretical",
    },
    {
        "claim": "Real-time write-back during agent execution prevents discovery loss on unexpected termination.",
        "l0_summary": "Synchronous DB writes during each cycle phase prevent data loss on crash or interruption.",
        "l1_summary": "MiroFish and Hyperspace AGI demonstrated that agents must write discoveries to persistent storage immediately, not batch them at the end. If an agent crashes mid-cycle, any unwritten discoveries are lost. Synchronous write-back after each phase (paper generation, comparison, reflection) ensures that even partial cycles preserve their work. The cost is slightly higher I/O but the benefit is crash resilience.",
        "l2_content": "Analysis of write-back strategies for crash-resilient agent systems...",
        "evidence_sources": [{"title": "MiroFish Agent Framework", "url": "https://github.com/mirofish/mirofish", "excerpt": "Real-time write-back for agent memory persistence"}],
        "assumptions": "SQLite WAL mode handles concurrent writes safely; synchronous writes within a cycle are acceptable latency",
        "topic_tag": "agentic_memory",
        "perspective": "applied",
    },
    {
        "claim": "The Popper-Bayes-Lakatos triad provides a complete epistemological framework for automated research evaluation.",
        "l0_summary": "Three philosophies combined: Popper gates entry, Bayes updates confidence, Lakatos judges progress.",
        "l1_summary": "Each philosophy of science addresses a different evaluation need. Popper (falsifiability) gates entry: papers must state assumptions that could be disproven. Bayes (evidence updating) drives the fitness engine: new evidence updates confidence via comparisons. Lakatos (progressive vs degenerative research programs) is the tiebreaker: papers that make new predictions score higher than those that merely patch exceptions. Together they form a complete evaluation pipeline: gate -> score -> judge.",
        "l2_content": "Integration of philosophy of science principles into automated research evaluation...",
        "evidence_sources": [{"title": "Lakatos - Methodology of Scientific Research Programmes", "url": "https://en.wikipedia.org/wiki/Research_programme", "excerpt": "Progressive: new predictions; Degenerative: ad hoc patches"}],
        "assumptions": "LLMs can distinguish progressive from degenerative research; falsifiability is a meaningful filter for LLM-generated content",
        "topic_tag": "agentic_memory",
        "perspective": "critical",
    },
    {
        "claim": "SQLite with WAL mode is sufficient for single-process agent knowledge stores, eliminating the need for external databases.",
        "l0_summary": "SQLite+WAL handles concurrent reads with zero dependencies; no need for PostgreSQL, Neo4j, or Redis.",
        "l1_summary": "Analysis of 7 open-source agent frameworks reveals that none require more than SQLite for their knowledge store. WAL (Write-Ahead Logging) mode enables concurrent reads during writes, which is the only concurrency pattern needed for single-process agent loops. The zero-dependency benefit is significant: no database server to install, configure, or maintain. The entire knowledge base is a single file that can be backed up with cp. Vector search (FAISS, sqlite-vss) was evaluated and rejected: L0 summaries + LLM filtering proved more accurate in practice.",
        "l2_content": "Comparative analysis of storage solutions for agent knowledge systems...",
        "evidence_sources": [{"title": "SQLite WAL Mode", "url": "https://www.sqlite.org/wal.html", "excerpt": "WAL allows concurrent reads during writes with automatic recovery"}],
        "assumptions": "Single-process is sufficient for Phase 1; write throughput of ~1 paper/cycle is well within SQLite limits",
        "topic_tag": "agentic_memory",
        "perspective": "empirical",
    },
]


def seed_database(db_path: str, topic: str):
    """Seed the database with initial papers."""
    conn = init_db(db_path)

    existing = conn.execute(
        "SELECT COUNT(*) as cnt FROM papers WHERE topic_tag = ?", (topic,)
    ).fetchone()["cnt"]

    if existing >= 10:
        print(f"Database already has {existing} papers for '{topic}'. Skipping seed.")
        conn.close()
        return

    print(f"Seeding {len(SEED_PAPERS)} papers for topic '{topic}'...")

    for i, paper in enumerate(SEED_PAPERS):
        paper["topic_tag"] = topic
        pid = save_paper(conn, paper)
        print(f"  [{i+1}/{len(SEED_PAPERS)}] {pid}: {paper['claim'][:70]}")

    final = conn.execute(
        "SELECT COUNT(*) as cnt FROM papers WHERE topic_tag = ?", (topic,)
    ).fetchone()["cnt"]
    print(f"\nSeeding complete: {final} papers in database.")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed the research database")
    parser.add_argument("--db", default=str(Path(__file__).parent / "db" / "knowledge.db"))
    parser.add_argument("--topic", default="agentic_memory")
    args = parser.parse_args()
    seed_database(args.db, args.topic)
