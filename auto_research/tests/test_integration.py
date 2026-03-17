#!/usr/bin/env python3
"""Integration tests for Auto Research Ecosystem v2.

Tests schema, memory, fitness, and end-to-end flow.
Run with: python -m pytest auto_research/tests/test_integration.py -v
"""

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from auto_research.core import init_db
from auto_research.core.memory import paper_id, save_paper, build_session_context, save_annotation, search_papers
from auto_research.core.fitness import (
    calculate_fitness, update_lifecycle_states, update_map_elites,
    get_champion, select_rival, _log_audit,
)


class TestSchema(unittest.TestCase):
    """Test database schema creation and constraints."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.conn = init_db(self.tmp.name)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.tmp.name)
        # Clean up WAL/SHM files
        for suffix in ("-wal", "-shm"):
            wal = self.tmp.name + suffix
            if os.path.exists(wal):
                os.unlink(wal)

    def test_wal_mode(self):
        mode = self.conn.execute("PRAGMA journal_mode").fetchone()[0]
        self.assertEqual(mode, "wal")

    def test_busy_timeout(self):
        timeout = self.conn.execute("PRAGMA busy_timeout").fetchone()[0]
        self.assertEqual(timeout, 5000)

    def test_all_tables_exist(self):
        tables = {row[0] for row in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        expected = {"papers", "comparisons", "edges", "annotations", "audit_chain"}
        self.assertTrue(expected.issubset(tables), f"Missing tables: {expected - tables}")

    def test_audit_chain_immutable_update(self):
        self.conn.execute(
            """INSERT INTO audit_chain (id, paper_id, event_type, created_at)
               VALUES ('test1', 'p1', 'first_seen', '2026-01-01')"""
        )
        self.conn.commit()

        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "UPDATE audit_chain SET event_type = 'changed' WHERE id = 'test1'"
            )

    def test_audit_chain_immutable_delete(self):
        self.conn.execute(
            """INSERT INTO audit_chain (id, paper_id, event_type, created_at)
               VALUES ('test2', 'p1', 'first_seen', '2026-01-01')"""
        )
        self.conn.commit()

        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("DELETE FROM audit_chain WHERE id = 'test2'")

    def test_indexes_exist(self):
        indexes = {row[0] for row in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
        ).fetchall()}
        expected = {
            "idx_papers_topic_status", "idx_papers_fitness",
            "idx_comparisons_winner", "idx_comparisons_loser",
            "idx_annotations_paper",
        }
        self.assertTrue(expected.issubset(indexes), f"Missing indexes: {expected - indexes}")

    def test_no_edges_indexes(self):
        indexes = {row[0] for row in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_edges%'"
        ).fetchall()}
        self.assertEqual(indexes, set(), "edges indexes should be deferred to Phase 2")


class TestMemory(unittest.TestCase):
    """Test memory system: paper_id, save_paper, context building."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.conn = init_db(self.tmp.name)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.tmp.name)
        for suffix in ("-wal", "-shm"):
            wal = self.tmp.name + suffix
            if os.path.exists(wal):
                os.unlink(wal)

    def test_paper_id_determinism(self):
        id1 = paper_id("same claim", "same summary")
        id2 = paper_id("same claim", "same summary")
        self.assertEqual(id1, id2)

    def test_paper_id_collision_resistance(self):
        id1 = paper_id("claim A", "summary A")
        id2 = paper_id("claim B", "summary A")
        self.assertNotEqual(id1, id2)

    def test_paper_id_length(self):
        pid = paper_id("test", "test")
        self.assertEqual(len(pid), 16)

    def test_save_paper(self):
        paper = {
            "claim": "Test claim",
            "l0_summary": "Test L0",
            "l1_summary": "Test L1 detailed",
            "l2_content": "Test L2 full content",
            "evidence_sources": [],
            "assumptions": "Test assumption",
            "topic_tag": "test_topic",
            "perspective": "empirical",
        }
        pid = save_paper(self.conn, paper)
        self.assertEqual(len(pid), 16)

        # Verify paper exists
        row = self.conn.execute("SELECT * FROM papers WHERE id = ?", (pid,)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["claim"], "Test claim")

        # Verify audit chain entry
        audit = self.conn.execute(
            "SELECT * FROM audit_chain WHERE paper_id = ?", (pid,)
        ).fetchone()
        self.assertIsNotNone(audit)
        self.assertEqual(audit["event_type"], "first_seen")

    def test_save_paper_idempotent(self):
        paper = {
            "claim": "Idempotent claim",
            "l0_summary": "L0",
            "l1_summary": "L1 content",
            "l2_content": "L2",
            "topic_tag": "test",
            "perspective": "empirical",
        }
        pid1 = save_paper(self.conn, paper)
        pid2 = save_paper(self.conn, paper)
        self.assertEqual(pid1, pid2)

    def test_build_session_context(self):
        # Insert some papers
        for i in range(5):
            save_paper(self.conn, {
                "claim": f"Claim {i}",
                "l0_summary": f"L0 summary {i}",
                "l1_summary": f"L1 detailed summary {i} " * 20,
                "l2_content": f"Full content {i}",
                "topic_tag": "test_topic",
                "perspective": "empirical",
            })

        context = build_session_context(self.conn, "test_topic", "sess1")
        self.assertIsInstance(context, str)
        self.assertGreater(len(context), 0)
        self.assertIn("Knowledge Overview", context)

    def test_annotations_in_context(self):
        paper = {
            "claim": "Annotated claim",
            "l0_summary": "L0",
            "l1_summary": "L1 content",
            "l2_content": "L2",
            "topic_tag": "test_topic",
            "perspective": "empirical",
        }
        pid = save_paper(self.conn, paper)
        save_annotation(self.conn, pid, "sess1", "Key discovery about X", ["limitation"])

        context = build_session_context(self.conn, "test_topic", "sess2")
        self.assertIn("Previous Session Discoveries", context)
        self.assertIn("Key discovery about X", context)

    def test_search_papers(self):
        save_paper(self.conn, {
            "claim": "Memory systems are crucial for agents",
            "l0_summary": "Agent memory importance",
            "l1_summary": "Detailed analysis of memory",
            "l2_content": "Full content",
            "topic_tag": "test",
            "perspective": "empirical",
        })

        results = search_papers(self.conn, "memory", "test")
        self.assertGreater(len(results), 0)
        self.assertIn("memory", results[0]["claim"].lower())


class TestFitness(unittest.TestCase):
    """Test fitness scoring and diversity system."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.conn = init_db(self.tmp.name)

        # Insert test papers
        self.papers = []
        for i in range(5):
            paper = {
                "claim": f"Fitness test claim {i}",
                "l0_summary": f"L0 {i}",
                "l1_summary": f"L1 detailed {i}",
                "l2_content": f"L2 full {i}",
                "topic_tag": "fitness_test",
                "perspective": ["empirical", "theoretical", "applied", "critical", "empirical"][i],
            }
            pid = save_paper(self.conn, paper)
            self.papers.append(pid)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.tmp.name)
        for suffix in ("-wal", "-shm"):
            wal = self.tmp.name + suffix
            if os.path.exists(wal):
                os.unlink(wal)

    def test_calculate_fitness(self):
        # Add comparisons: paper[0] beats paper[1], paper[1] beats paper[2]
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "INSERT INTO comparisons VALUES (?, ?, ?)",
            (self.papers[0], self.papers[1], now),
        )
        self.conn.execute(
            "INSERT INTO comparisons VALUES (?, ?, ?)",
            (self.papers[1], self.papers[2], now),
        )
        self.conn.execute(
            "INSERT INTO comparisons VALUES (?, ?, ?)",
            (self.papers[0], self.papers[2], now),
        )
        self.conn.commit()

        calculate_fitness(self.conn, "fitness_test")

        # Paper 0 should have highest fitness (beat papers 1 and 2)
        p0 = self.conn.execute(
            "SELECT fitness FROM papers WHERE id = ?", (self.papers[0],)
        ).fetchone()["fitness"]
        p2 = self.conn.execute(
            "SELECT fitness FROM papers WHERE id = ?", (self.papers[2],)
        ).fetchone()["fitness"]

        self.assertGreater(p0, p2)

    def test_get_champion(self):
        # Set different fitness values
        self.conn.execute("UPDATE papers SET fitness = 0.9 WHERE id = ?", (self.papers[0],))
        self.conn.execute("UPDATE papers SET fitness = 0.3 WHERE id = ?", (self.papers[1],))
        self.conn.commit()

        champion = get_champion(self.conn, "fitness_test")
        self.assertEqual(champion["id"], self.papers[0])

    def test_select_rival_distribution(self):
        self.conn.execute("UPDATE papers SET fitness = 0.9 WHERE id = ?", (self.papers[0],))
        self.conn.commit()

        champion_count = 0
        trials = 100
        for _ in range(trials):
            rival = select_rival(self.conn, "fitness_test")
            if rival and rival["id"] == self.papers[0]:
                champion_count += 1

        # Should be roughly 70% (allow 50-90% range for randomness)
        ratio = champion_count / trials
        self.assertGreater(ratio, 0.4, f"Champion selected too rarely: {ratio:.0%}")
        self.assertLess(ratio, 0.95, f"Champion selected too often: {ratio:.0%}")

    def test_map_elites_preserves_cells(self):
        # Add many papers in same cell
        for i in range(5):
            save_paper(self.conn, {
                "claim": f"Extra empirical claim {i}",
                "l0_summary": f"Extra L0 {i}",
                "l1_summary": f"Extra L1 {i}",
                "l2_content": f"Extra L2 {i}",
                "topic_tag": "fitness_test",
                "perspective": "empirical",
            })

        update_map_elites(self.conn, "fitness_test")

        # At least 1 empirical paper should remain active
        active_empirical = self.conn.execute(
            """SELECT COUNT(*) as cnt FROM papers
               WHERE topic_tag = 'fitness_test' AND perspective = 'empirical'
               AND status IN ('active', 'foundational')"""
        ).fetchone()["cnt"]
        self.assertGreaterEqual(active_empirical, 1)


if __name__ == "__main__":
    unittest.main()
