#!/usr/bin/env python3
"""Autonomous Research Ecosystem v2 — Main Loop.

An infinitely-running evolutionary research system that:
1. Generates papers via Claude Agent SDK research agent (with real WebSearch)
2. Evaluates them via pairwise comparison with position bias removal
3. Evolves knowledge via MAP-Elites diversity + PageRank fitness
4. Persists state in SQLite across sessions

Each cycle is identified by a unique TRIAL ID: YYYYMMDDHHMMSS_HASH
(e.g., 20260318020359_a3f8b2). This ID is used throughout the system
to track specific cycles in logs, DB, and debugging.

Usage:
    python autoresearch_v2.py --topic "agentic_memory" --db db/knowledge.db
    python autoresearch_v2.py --topic agentic_memory --prompt "최적의 에이전틱 메모리..."
"""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import random
import signal
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from auto_research.core import init_db
from auto_research.core.memory import (
    build_session_context,
    save_annotation,
    get_paper,
)
from auto_research.core.fitness import (
    calculate_fitness,
    update_lifecycle_states,
    update_map_elites,
    get_champion,
    select_rival,
)
from auto_research.agents.research_agent import run_research
from auto_research.agents.compare_agent import run_comparison
from auto_research.agents.reflector_agent import run_reflection


# --- Trial ID ---

def generate_trial_id() -> str:
    """Generate a unique, sortable trial ID: YYYYMMDDHHMMSS_HASH.

    Format: 20260318020359_a3f8b2
    - Timestamp prefix ensures chronological sorting
    - 6-char hash suffix ensures uniqueness even within the same second
    """
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%d%H%M%S")
    hash_suffix = hashlib.sha256(
        f"{timestamp}{uuid.uuid4().hex}".encode()
    ).hexdigest()[:6]
    return f"{timestamp}_{hash_suffix}"


# --- Logging Setup ---

def setup_logging(log_dir: str = "logs") -> logging.Logger:
    """Configure session-level logging to research.log + stdout.

    Per-trial log files are created separately in each cycle.
    """
    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger("autoresearch")
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger

    # Session-level file handler (DEBUG)
    fh = logging.FileHandler(
        os.path.join(log_dir, "research.log"),
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    logger.addHandler(fh)

    # Console handler (INFO)
    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)
    sh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    ))
    logger.addHandler(sh)

    return logger


def setup_logger(log_dir: str, trial_id: str) -> logging.FileHandler:
    """Attach a per-trial file handler to the ROOT autoresearch logger.

    This means ALL logging from every sub-logger (autoresearch.research,
    autoresearch.compare, autoresearch.reflector, autoresearch.memory, etc.)
    automatically goes to the trial log file — no separate logger needed.

    Returns the handler so it can be removed at cycle end.
    """
    fh = logging.FileHandler(
        os.path.join(log_dir, f"{trial_id}.log"),
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))

    # Attach to ROOT autoresearch logger — captures ALL child loggers
    root_logger = logging.getLogger("autoresearch")
    root_logger.addHandler(fh)

    return fh


# --- Cycle Stats ---

def log_cycle_stats(conn, cycle_num: int, topic: str, elapsed: float,
                    logger, trial_id: str):
    """Log cycle statistics to session log, console, and trial log."""
    papers_count = conn.execute(
        "SELECT COUNT(*) as cnt FROM papers WHERE topic_tag = ?", (topic,)
    ).fetchone()["cnt"]

    active_count = conn.execute(
        "SELECT COUNT(*) as cnt FROM papers WHERE topic_tag = ? AND status = 'active'",
        (topic,),
    ).fetchone()["cnt"]

    archived_count = conn.execute(
        "SELECT COUNT(*) as cnt FROM papers WHERE topic_tag = ? AND status = 'archived'",
        (topic,),
    ).fetchone()["cnt"]

    comparisons_count = conn.execute(
        "SELECT COUNT(*) as cnt FROM comparisons"
    ).fetchone()["cnt"]

    champion = get_champion(conn, topic)
    top_fitness = champion.get("fitness", 0.0) if champion else 0.0
    champion_claim = champion.get("claim", "N/A")[:60] if champion else "N/A"

    annotations_count = conn.execute(
        "SELECT COUNT(*) as cnt FROM annotations"
    ).fetchone()["cnt"]

    stats = (
        f"=== Cycle {cycle_num} Complete [Trial: {trial_id}] ===\n"
        f"  Papers: {papers_count} total ({active_count} active, {archived_count} archived)\n"
        f"  Comparisons: {comparisons_count} | Annotations: {annotations_count}\n"
        f"  Champion fitness: {top_fitness:.3f} — {champion_claim}\n"
        f"  Elapsed: {elapsed:.1f}s"
    )

    logger.info(stats)
    logger.info(stats)


# --- Main Loop ---

async def research_loop(db_path: str, topic: str, max_cycles: int = None,
                        research_question: str = ""):
    """The infinite research evolution loop.

    Each cycle gets a unique trial_id (YYYYMMDDHHMMSS_HASH) and its own log file.

    Phases per cycle:
    1. Build session context (L0 filter -> L1 load -> annotation inject)
    2. Generate new paper (30% rebuttal against champion) — with real WebSearch
    3. Claim classification + pairwise comparison (position bias removal)
    4. Reflector LLM: annotation extraction
    5. Deterministic state updates: fitness, lifecycle, MAP-Elites
    """
    log_dir = str(Path(__file__).parent / "logs")
    logger = setup_logging(log_dir)

    logger.info("=" * 60)
    logger.info("Auto Research Ecosystem v2 — Starting (Claude Agent SDK)")
    logger.info(f"Topic: {topic}")
    logger.info(f"Database: {db_path}")
    if research_question:
        logger.info(f"Research Question: {research_question}")
    logger.info("=" * 60)

    conn = init_db(db_path)
    session_id = uuid.uuid4().hex[:12]
    logger.info(f"Session ID: {session_id}")

    # Graceful shutdown handler
    shutdown_requested = False

    def handle_signal(signum, frame):
        nonlocal shutdown_requested
        logger.info(f"Shutdown signal received (signal {signum}). Finishing current cycle...")
        shutdown_requested = True

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # Log initial state
    initial_count = conn.execute(
        "SELECT COUNT(*) as cnt FROM papers WHERE topic_tag = ?", (topic,)
    ).fetchone()["cnt"]
    if initial_count == 0:
        logger.info("Starting from empty DB — first cycles will build up naturally")
    else:
        logger.info(f"Resuming with {initial_count} existing papers for '{topic}'")

    cycle_num = 0

    while not shutdown_requested and (max_cycles is None or cycle_num < max_cycles):
        cycle_num += 1
        cycle_start = time.time()

        # Generate unique trial ID and attach trial log handler
        trial_id = generate_trial_id()
        trial_handler = setup_logger(log_dir, trial_id)

        logger.info("=" * 70)
        logger.info(f"TRIAL START: {trial_id}")
        logger.info(f"Cycle: {cycle_num} | Topic: {topic} | Session: {session_id}")
        if research_question:
            logger.info(f"Research Question: {research_question}")
        logger.info("=" * 70)

        logger.info(f"--- Cycle {cycle_num} [Trial: {trial_id}] ---")

        try:
            # --- Phase 1: Build session context ---
            logger.info("=== PHASE 1: Build Session Context ===")
            context = build_session_context(conn, topic, session_id)
            logger.debug(f"Session context ({len(context)} chars):\n{context}")

            # --- Phase 2: Generate new paper (30% rebuttal if champion exists) ---
            logger.info("=== PHASE 2: Generate New Paper ===")
            champion = get_champion(conn, topic)
            is_rebuttal = random.random() < 0.3 and bool(champion)
            logger.info(f"Mode: {'REBUTTAL' if is_rebuttal else 'NEW RESEARCH'}")
            if champion:
                logger.info(f"Current champion: {champion.get('id')} — {champion.get('claim', '')[:100]}")

            new_paper = await run_research(
                conn, topic, session_id, context,
                champion_claim=champion.get("claim") if is_rebuttal and champion else None,
                is_rebuttal=is_rebuttal,
                research_question=research_question,
            )

            logger.info(f"Paper generated: {new_paper.get('id')}")
            logger.info(f"Claim: {new_paper.get('claim', 'N/A')}")
            logger.info(f"Perspective: {new_paper.get('perspective', 'N/A')}")
            logger.info(f"Assumptions: {new_paper.get('assumptions', 'N/A')}")
            logger.debug(f"Evidence sources: {json.dumps(new_paper.get('evidence_sources', []), indent=2, ensure_ascii=False)}")
            logger.debug(f"L1 Summary:\n{new_paper.get('l1_summary', 'N/A')}")

            # --- Phase 3: Pairwise comparison ---
            logger.info("=== PHASE 3: Pairwise Comparison ===")
            rival = select_rival(conn, topic)

            if rival and rival.get("id") != new_paper.get("id"):
                logger.info(f"Rival selected: {rival.get('id')} — {rival.get('claim', '')[:100]}")
                logger.info(f"Rival fitness: {rival.get('fitness', 0):.3f}")

                comparison = await run_comparison(conn, new_paper, rival, research_question=research_question)

                if comparison:
                    logger.info(f"Comparison result: winner={comparison[0]}, loser={comparison[1]}")
                    if len(comparison) > 2:
                        logger.info(f"Judge reasoning: {comparison[2]}")
                else:
                    logger.info("Comparison result: None (orthogonal or bias detected)")
            else:
                comparison = None
                logger.info("No suitable rival found for comparison")
                logger.info("No suitable rival — skipping comparison")

            # --- Phase 4: Reflector LLM — annotation extraction ---
            logger.info("=== PHASE 4: Reflection & Annotation Extraction ===")
            annotations = await run_reflection(
                conn, session_id, topic, comparison, new_paper, context,
                research_question=research_question,
            )
            for i, ann in enumerate(annotations):
                logger.info(f"Annotation {i+1}: [{', '.join(ann.get('tags', []))}] {ann['content']}")
                if ann.get("suggested_search"):
                    logger.info(f"  → Suggested search: {ann['suggested_search']}")
                save_annotation(
                    conn,
                    new_paper.get("id", ""),
                    session_id,
                    ann["content"],
                    ann.get("tags", ["general"]),
                )

            # --- Phase 5: Deterministic state updates ---
            logger.info("=== PHASE 5: Deterministic State Updates ===")
            calculate_fitness(conn, topic)
            update_lifecycle_states(conn, topic)
            update_map_elites(conn, topic)

            # Log post-update state
            updated_paper = get_paper(conn, new_paper.get("id"))
            if updated_paper:
                logger.info(f"New paper fitness after update: {updated_paper.get('fitness', 0):.4f}")
                logger.info(f"New paper status: {updated_paper.get('status', 'unknown')}")

            # --- Cycle stats ---
            elapsed = time.time() - cycle_start
            log_cycle_stats(conn, cycle_num, topic, elapsed, logger, trial_id)

            logger.info(f"TRIAL END: {trial_id} (elapsed: {elapsed:.1f}s)")
            logger.info("=" * 70)

            # Remove trial handler (keep session handlers intact)
            trial_handler.close()
            logging.getLogger("autoresearch").removeHandler(trial_handler)

            # Brief pause between cycles
            if not shutdown_requested:
                await asyncio.sleep(5)

        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt — shutting down gracefully")
            break
        except Exception as e:
            elapsed = time.time() - cycle_start
            logger.error(f"Cycle {cycle_num} [{trial_id}] error after {elapsed:.1f}s: {e}", exc_info=True)
            logger.error(f"TRIAL ERROR: {e}", exc_info=True)
            # Remove trial handler on error too
            trial_handler.close()
            logging.getLogger("autoresearch").removeHandler(trial_handler)
            if not shutdown_requested:
                await asyncio.sleep(30)

    # Graceful shutdown
    logger.info("Closing database connection...")
    conn.close()
    logger.info("Auto Research Ecosystem v2 — Stopped")
    logger.info(f"Total cycles completed: {cycle_num}")


# --- CLI ---

def main():
    parser = argparse.ArgumentParser(
        description="Auto Research Ecosystem v2 — Evolutionary Knowledge Loop (Claude Agent SDK)"
    )
    parser.add_argument(
        "--topic", type=str, default="agentic_memory",
        help="Research topic tag (default: agentic_memory)",
    )
    parser.add_argument(
        "--db", type=str,
        default=str(Path(__file__).parent / "db" / "knowledge.db"),
        help="Path to SQLite database (default: db/knowledge.db)",
    )
    parser.add_argument(
        "--max-cycles", type=int, default=None,
        help="Maximum number of cycles (default: infinite)",
    )
    parser.add_argument(
        "--prompt", type=str, default="",
        help="Detailed research question for the agents",
    )

    args = parser.parse_args()
    asyncio.run(research_loop(args.db, args.topic,
                              max_cycles=args.max_cycles,
                              research_question=args.prompt))


if __name__ == "__main__":
    main()
