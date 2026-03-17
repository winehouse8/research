-- Auto Research v2 Schema
-- Evolutionary knowledge ecosystem with selection pressure

PRAGMA journal_mode=wal;

-- Papers/reports (L0/L1/L2 hierarchical, OpenViking pattern)
CREATE TABLE IF NOT EXISTS papers (
    id              TEXT PRIMARY KEY,   -- SHA-256(claim + l1_summary)[:16]
    claim           TEXT NOT NULL,      -- Core claim, one sentence
    l0_summary      TEXT,               -- ~50 tokens: relevance filter
    l1_summary      TEXT,               -- ~2000 tokens: planning/reasoning
    l2_content      TEXT,               -- Full content: on-demand load
    evidence_sources TEXT,              -- JSON: [{title, url, citation_count, excerpt}]
    assumptions     TEXT,               -- Conditions for validity (falsifiability gate)
    fitness         REAL DEFAULT 0.5,   -- PageRank-based importance
    status          TEXT DEFAULT 'active',  -- active|contested|foundational|archived
    topic_tag       TEXT,               -- MAP-Elites cell address
    perspective     TEXT,               -- empirical|theoretical|applied|critical
    expires_at      TEXT,               -- TTL-based review deadline
    created_at      TEXT,
    source_uri      TEXT                -- Search path audit (OpenViking DRR)
);

-- Pairwise comparison results (selection pressure core)
CREATE TABLE IF NOT EXISTS comparisons (
    winner      TEXT REFERENCES papers(id),
    loser       TEXT REFERENCES papers(id),
    created_at  TEXT
);

-- Knowledge relationship graph (Zep temporal axis pattern)
-- NOTE: edges population deferred to Phase 2
CREATE TABLE IF NOT EXISTS edges (
    id          TEXT PRIMARY KEY,
    src         TEXT REFERENCES papers(id),
    dst         TEXT REFERENCES papers(id),
    relation    TEXT,   -- supports|contradicts|extends|derived_from|depend_on
    strength    REAL DEFAULT 1.0,
    created_at  TEXT,
    valid_until TEXT    -- NULL = still valid
);
-- edges indexes deferred to Phase 2 when edge population is implemented

-- Session annotations (Context Hub pattern: agent's personal long-term memory)
CREATE TABLE IF NOT EXISTS annotations (
    id          TEXT PRIMARY KEY,
    paper_id    TEXT REFERENCES papers(id),
    session_id  TEXT,
    content     TEXT NOT NULL,
    tags        TEXT,           -- JSON array
    created_at  TEXT
);

-- Immutable audit chain (Wrkr pattern: append-only)
CREATE TABLE IF NOT EXISTS audit_chain (
    id              TEXT PRIMARY KEY,
    paper_id        TEXT,
    event_type      TEXT,   -- first_seen|status_changed|evaluated|archived|revived
    previous_state  TEXT,
    new_state       TEXT,
    agent_id        TEXT,
    created_at      TEXT
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_papers_topic_status ON papers(topic_tag, status);
CREATE INDEX IF NOT EXISTS idx_papers_fitness ON papers(fitness DESC);
CREATE INDEX IF NOT EXISTS idx_comparisons_winner ON comparisons(winner);
CREATE INDEX IF NOT EXISTS idx_comparisons_loser ON comparisons(loser);
CREATE INDEX IF NOT EXISTS idx_annotations_paper ON annotations(paper_id);

-- Immutability triggers for audit_chain
CREATE TRIGGER IF NOT EXISTS prevent_audit_update
BEFORE UPDATE ON audit_chain
BEGIN
    SELECT RAISE(ABORT, 'audit_chain is append-only: updates are not allowed');
END;

CREATE TRIGGER IF NOT EXISTS prevent_audit_delete
BEFORE DELETE ON audit_chain
BEGIN
    SELECT RAISE(ABORT, 'audit_chain is append-only: deletes are not allowed');
END;
