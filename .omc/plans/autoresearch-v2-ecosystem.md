# Plan: Autonomous Research Ecosystem v2 — Full Implementation

> Created: 2026-03-17
> Revised: 2026-03-17 (R1 — Architect + Critic consensus fixes)
> Source: `260317_final-strategy-report.md` + `260317_agent-ecosystem-minimal-v2.md` + `260317_autoresearch-agent-sdk.md`
> Target: `/Users/jaewoo/Desktop/Project/research/auto_research/`

---

## RALPLAN-DR Summary

### Principles (5)

1. **Selection Pressure**: All generated knowledge competes via pairwise LLM-as-Judge comparison. Survival = fitness.
2. **Diversity Maintenance**: MAP-Elites (topic x perspective) grid ensures minority viewpoints survive local competition even if they lose globally.
3. **Explicit State**: Every piece of knowledge has externalized state (fitness, status, relations, audit trail) in SQLite. Agents are stateless; the DB is the brain.
4. **Hierarchical Memory**: L0/L1/L2 tiered loading prevents token explosion. Only load what's needed at each depth.
5. **Incremental Resilience**: Synchronous writes within each cycle + append-only audit chain ensures no discovery is lost on crash or restart. (Phase 1 uses synchronous DB writes; async write-back deferred to Phase 2+.)

### Decision Drivers (Top 3)

1. **Cost efficiency**: The system runs indefinitely. Model allocation (haiku for cheap tasks, sonnet for research) and L0/L1/L2 token savings directly determine viability.
2. **Simplicity of dependencies**: Zero external services beyond SQLite (built-in) + networkx (PageRank). No vector DB, no graph DB, no Docker (Phase 1).
3. **Loop correctness**: The while-True loop must handle crashes, API errors, and state corruption gracefully without human intervention.

### Viable Options

**Option A: Claude Agent SDK (Python) -- SELECTED**
- Pros: Native Claude tool support (WebSearch, WebFetch), per-call model routing (haiku/sonnet), Python loop control
- Cons: Anthropic-only (no model switching), SDK is relatively new, requires verification of pip package availability

**Option B: Raw `anthropic` package with `messages.create()` + tool_use**
- Pros: Stable, well-documented, full control over tool definitions, works today
- Cons: Must implement WebSearch/WebFetch as custom tools or via separate HTTP calls, more boilerplate for structured output parsing
- **Status**: Viable fallback if `claude-agent-sdk` pip package is unavailable or unstable. Step 0 gates this decision.

**Option C: LangGraph + Anthropic API direct**
- Pros: Model-agnostic, minimal overhead, explicit state graph, MIT license
- Cons: Must implement all tool calls manually (file I/O, web search), no native WebSearch/WebFetch, more boilerplate for agent definitions
- **Invalidation rationale**: The strategy report explicitly chose Claude Agent SDK for its native tool integration (WebSearch, WebFetch). Reimplementing these in LangGraph adds significant effort for Phase 1 MVP with no immediate benefit. LangGraph remains a valid Phase 3 migration target if model flexibility becomes needed.

**Option D: CrewAI / AutoGen**
- **Invalidated**: Strategy report analysis showed 3x overhead vs LangGraph, 56% extra tokens. AutoGen in maintenance mode. Both frameworks add complexity without matching Claude Agent SDK's native tool support.

### ADR

- **Decision**: Claude Agent SDK with standalone `query()` calls for each agent role (research, compare, reflector-LLM), Python-side deterministic logic for fitness/lifecycle/MAP-Elites, SQLite+WAL storage, while-True main loop
- **Drivers**: Cost efficiency (model routing), zero-dependency storage, native tool access
- **Alternatives considered**: Raw `anthropic` SDK (viable fallback, Step 0 gates), LangGraph (viable but more boilerplate), CrewAI/AutoGen (rejected for overhead)
- **Why chosen**: Directly aligns with strategy report's confirmed architecture; minimizes time to working MVP; native WebSearch/WebFetch eliminates custom tool implementation
- **Consequences**: Locked to Anthropic models; must handle SDK API changes; reflector split means LLM does annotation extraction only (deterministic work stays in Python)
- **Follow-ups**: Evaluate LangGraph migration if multi-model support needed (Phase 3); monitor SDK stability; populate `edges` table in Phase 2

---

## Context

We are building a self-evolving research ecosystem where AI agents continuously generate papers, evaluate them via pairwise comparison, and maintain a knowledge graph with natural selection pressure. The system runs in an infinite loop (ralph-style), with knowledge accumulating in SQLite across sessions.

The strategy report has fully specified: schema (5 tables), agent roles (3 agents), evaluation protocol (LLM-as-Judge with position bias removal), diversity mechanism (MAP-Elites), and importance scoring (PageRank). The `auto_research/autoresearch/` directory is currently empty.

**Phase 1 MVP goal**: A working infinite evolution loop that generates papers, compares them, updates fitness, and persists state across restarts. Target: 10 seed papers, 10+ cycles running successfully, 30+ comparisons logged.

---

## Work Objectives

0. Verify SDK availability: install `claude-agent-sdk`, confirm import path and tool availability; gate all subsequent steps
1. Create SQLite schema with all 5 tables + WAL mode + audit chain immutability triggers + single-connection strategy
2. Implement L0/L1/L2 hierarchical memory loading with annotation injection
3. Implement PageRank fitness scoring + MAP-Elites diversity grid
4. Build 3 agent modules as standalone `query()` calls (research, compare, reflector-LLM); reflector-LLM extracts annotations only
5. Wire the main infinite loop with all 4 phases + cold start seeding + deterministic post-reflection logic + logging infrastructure
6. Ensure crash resilience: graceful error handling, synchronous writes, restart recovery

---

## Guardrails

**Must Have:**
- SQLite WAL mode enabled for concurrent read safety
- Single `sqlite3.Connection` with `busy_timeout=5000` (no connection pooling in Phase 1)
- All DB writes synchronous within each cycle (no `asyncio.create_task` for DB writes)
- `audit_chain` table is append-only (UPDATE/DELETE triggers raise errors)
- Position bias removal: every comparison runs A->B then B->A, only unanimous results count
- SHA-256 content-hash IDs using `claim + l1_summary` as hash input for deterministic paper identification
- Graceful error handling in main loop: no single failure kills the infinite loop
- Cold start seeding: system must bootstrap itself with initial papers before comparison begins
- Logging to file (`logs/research.log`) + stdout for overnight run observability

**Must NOT Have:**
- No vector embeddings (FAISS, sqlite-vss) -- L0 + LLM filtering is sufficient
- No external graph database (Neo4j, ArangoDB) -- SQLite edges table is sufficient
- No CrewAI/AutoGen/LangGraph -- Claude Agent SDK only for Phase 1
- No Docker isolation -- timeout + ulimit for Phase 1
- No new research topics beyond the initial seed topic -- single topic for MVP validation
- No async DB writes in Phase 1 (deferred to Phase 2)

---

## Task Flow (7 Steps)

### Step 0: SDK Verification (Pre-Implementation Gate)
**Files**: `requirements.txt` (draft)
**Complexity**: LOW

Verify that `claude-agent-sdk` is installable and functional before proceeding.

Implementation details:
- Run `pip install claude-agent-sdk` and confirm installation succeeds
- Verify import: `from claude_agent_sdk import query, ClaudeAgentOptions`
- Verify tool availability: confirm `WebSearch` and `WebFetch` are available as allowed_tools strings
- Run a minimal smoke test: `query(prompt="Say hello", options=ClaudeAgentOptions(model="claude-haiku-4-5"))`

**Fallback**: If `claude-agent-sdk` is unavailable or broken:
- Use `anthropic` package with `client.messages.create()` + tool_use
- Research agent: implement web search via `WebFetch`-equivalent HTTP calls or Tavily/Serper API
- Compare/reflector agents: straightforward `messages.create()` calls with structured output
- All agent module interfaces (`run_research`, `run_comparison`, `run_reflection`) remain identical regardless of backend

Acceptance criteria:
- [ ] `pip install claude-agent-sdk` succeeds OR fallback decision documented
- [ ] Import path verified: `from claude_agent_sdk import query, ClaudeAgentOptions`
- [ ] `WebSearch` and `WebFetch` confirmed as valid tool names
- [ ] Smoke test `query()` call returns a result without error
- [ ] `requirements.txt` finalized with correct package name and version pin

---

### Step 1: Project Setup + SQLite Schema
**Files**: `core/schema.sql`, `core/__init__.py`, `__init__.py`, `requirements.txt`
**Complexity**: LOW
**Depends on**: Step 0

Create the project skeleton and the complete SQLite schema with all 5 tables.

Implementation details:
- `core/schema.sql`: CREATE TABLE statements for `papers`, `comparisons`, `edges`, `annotations`, `audit_chain` exactly as specified in the strategy report
- Add WAL pragma, immutability triggers for audit_chain (BEFORE UPDATE and BEFORE DELETE raise ABORT)
- Add indexes: `papers(topic_tag, status)`, `papers(fitness DESC)`, `comparisons(winner)`, `comparisons(loser)`, `annotations(paper_id)`
- **`edges` table**: CREATE TABLE included in schema.sql (prepares for Phase 2), but **no indexes on `edges`** in Phase 1. Add SQL comment: `-- edges indexes deferred to Phase 2 when edge population is implemented`
- `requirements.txt`: `claude-agent-sdk` (or `anthropic` per Step 0 result), `networkx`
- `core/__init__.py`: `init_db(db_path) -> sqlite3.Connection` function that:
  1. Creates DB file and parent directories
  2. Enables WAL mode: `PRAGMA journal_mode=wal`
  3. Sets `busy_timeout=5000` for write contention handling
  4. Runs schema.sql to create all tables
  5. Returns the single `sqlite3.Connection` instance (caller holds this for the session lifetime)

**SQLite Connection Strategy (Phase 1)**:
- One `sqlite3.Connection` per process, created at startup by `init_db()`
- All reads and writes use this single connection
- All writes are synchronous within the cycle (no `asyncio.create_task` for DB operations)
- Connection closed on graceful shutdown (SIGINT/SIGTERM handler)

Acceptance criteria:
- [ ] Running `init_db("db/knowledge.db")` creates the SQLite file with all 5 tables
- [ ] `PRAGMA journal_mode` returns `wal`
- [ ] `PRAGMA busy_timeout` returns `5000`
- [ ] `INSERT INTO audit_chain ...` succeeds; `UPDATE audit_chain ...` raises error; `DELETE FROM audit_chain ...` raises error
- [ ] Indexes exist on `papers(topic_tag, status)`, `papers(fitness DESC)`, `comparisons(winner)`, `comparisons(loser)`, `annotations(paper_id)`
- [ ] No indexes on `edges` table (deferred to Phase 2)
- [ ] `init_db()` returns a `sqlite3.Connection` object

---

### Step 2: Memory System (L0/L1/L2 + Annotations)
**Files**: `core/memory.py`
**Complexity**: MEDIUM
**Depends on**: Step 1

Implement the hierarchical memory loading system and session context builder.

Implementation details:
- `paper_id(claim: str, l1_summary: str) -> str`: SHA-256 of `claim + l1_summary`, truncated to 16 hex chars. This avoids collision risk from similar paper openings (as opposed to hashing `content[:500]`).
- `save_paper(conn, paper_dict)`: Insert paper with all L0/L1/L2 fields + audit_chain "first_seen" entry. Uses the single `conn` passed in.
- `build_session_context(conn, topic, session_id, max_tokens=4000) -> str`:
  1. Load all L0 summaries for the topic (fast scan)
  2. Select top-fitness papers + 2 random papers
  3. Load L1 summaries within token budget
  4. Prepend recent annotations (last 5 for this topic)
  5. Return assembled context string
- `save_annotation(conn, paper_id, session_id, content, tags)`: Store session discovery
- `search_papers(conn, query_text, topic) -> list`: Simple SQL LIKE search on claim + l0_summary fields (no vector search)

Acceptance criteria:
- [ ] `paper_id("same claim", "same summary")` always returns the same hash
- [ ] `paper_id("claim A", "summary A") != paper_id("claim B", "summary A")` (different claims produce different IDs)
- [ ] `build_session_context` with 100 papers in DB returns a string under `max_tokens` word count
- [ ] Annotations from a previous session appear at the top of the context string
- [ ] `save_paper` creates both a `papers` row and an `audit_chain` entry

---

### Step 3: Fitness + Diversity System
**Files**: `core/fitness.py`
**Complexity**: MEDIUM
**Depends on**: Step 1

Implement PageRank-based fitness scoring and MAP-Elites diversity grid.

Implementation details:
- `calculate_fitness(conn, topic)`:
  1. Build directed graph from `comparisons` table (winner -> loser edges)
  2. Run `networkx.pagerank()` on the graph
  3. Update `papers.fitness` for all papers in the topic
- `update_map_elites(conn, topic)`:
  1. Group papers by `(topic_tag, perspective)` cells
  2. In each cell, keep the highest-fitness paper as `active`, mark lower-fitness as `archived` (not deleted)
  3. Ensure at least 1 survivor per occupied cell
- `update_lifecycle_states(conn, topic)`:
  1. Papers with fitness > 0.7 and > 5 wins: `active` -> `foundational`
  2. Papers that lost 3+ recent comparisons: `active` -> `contested`
  3. Papers archived by MAP-Elites: `contested`/`active` -> `archived`
  4. All transitions logged to `audit_chain`
- `get_champion(conn, topic) -> dict`: Return highest-fitness active paper
- `select_rival(conn, topic) -> dict`: 70% chance champion, 30% chance random active paper

Acceptance criteria:
- [ ] After inserting 5 comparisons, `calculate_fitness` updates all paper fitness values to non-default values
- [ ] MAP-Elites grid preserves at least 1 paper per occupied (topic, perspective) cell
- [ ] `select_rival` returns champion ~70% of the time over 100 calls
- [ ] All state transitions produce `audit_chain` entries with correct `previous_state` and `new_state`

---

### Step 4: Agent Modules (Research + Compare + Reflector-LLM)
**Files**: `agents/research_agent.py`, `agents/compare_agent.py`, `agents/reflector_agent.py`, `agents/__init__.py`
**Complexity**: MEDIUM
**Depends on**: Steps 2, 3

Build three agent modules, each using standalone `query()` calls with `ClaudeAgentOptions`. No sub-agent nesting; Python controls the sequencing.

**SDK API Pattern**: Each agent module wraps a top-level `query()` call:
```python
from claude_agent_sdk import query, ClaudeAgentOptions

async for msg in query(
    prompt="...",
    options=ClaudeAgentOptions(
        model="claude-sonnet-4-6",
        allowed_tools=["WebSearch", "WebFetch"],
        permission_mode="acceptEdits",
    ),
):
    if hasattr(msg, "result"):
        result = msg.result
```

If Step 0 selected the `anthropic` fallback:
```python
from anthropic import Anthropic
client = Anthropic()
response = client.messages.create(
    model="claude-sonnet-4-6",
    messages=[{"role": "user", "content": "..."}],
    tools=[...],  # tool definitions for web search etc.
)
```

Implementation details:

**`agents/research_agent.py`**:
- `run_research(conn, topic, session_id, context) -> dict`
- Standalone `query()` call with model `claude-sonnet-4-6`
- Tools: `WebSearch`, `WebFetch` (native SDK tools for evidence gathering)
- Prompt instructs: read session context, perform minimum 3 evidence queries before generating, output structured paper with claim/l0_summary/l1_summary/l2_content/evidence_sources/assumptions/topic_tag/perspective
- 30% chance the prompt instructs "write a rebuttal paper against the current champion"
- Parses LLM output, calls `save_paper(conn, ...)` to persist

**`agents/compare_agent.py`**:
- `run_comparison(conn, paper_a, paper_b) -> Optional[tuple]`
- Standalone `query()` call with model `claude-haiku-4-5`
- Tools: none (read-only comparison -- pass paper content directly in prompt)
- Three judge prompts based on claim classification: opposing (which claim is better supported?), complementary (which evidence is stronger?), orthogonal (skip comparison)
- Flow:
  1. First `query()` call: classify claims (opposing/complementary/orthogonal) -- default to orthogonal when uncertain
  2. If not orthogonal: `query()` A->B judge, then `query()` B->A judge
  3. If both agree on winner: return (winner_id, loser_id)
  4. If disagreement: return None (no comparison recorded)
  5. Record result in `comparisons` table via `conn`

**`agents/reflector_agent.py`** (LLM part only):
- `run_reflection(conn, session_id, topic, comparison_result, new_paper) -> list[dict]`
- Standalone `query()` call with model `claude-haiku-4-5`
- Tools: none (read-only -- receives comparison reasoning as text input)
- **The reflector LLM does ONE thing**: extract annotations from the comparison reasoning
  - Input: comparison result text, new paper summary, session context
  - Output: structured JSON list of annotations (e.g., `[{"content": "Paper X is only valid under condition Y", "tags": ["limitation", "conditional"]}]`)
- Returns the annotation list to the caller
- **Does NOT call** `calculate_fitness()`, `update_lifecycle_states()`, or `update_map_elites()` -- those are deterministic Python functions called by the main loop (Step 5)

Acceptance criteria:
- [ ] `run_research` produces a paper dict with all required fields (claim, l0, l1, l2, evidence, assumptions, topic_tag, perspective)
- [ ] `run_comparison` with two opposing papers returns a (winner, loser) tuple
- [ ] `run_comparison` with identical paper order A,B vs B,A correctly detects position bias
- [ ] `run_reflection` returns a list of annotation dicts with `content` and `tags` fields
- [ ] `run_reflection` does NOT call any fitness/lifecycle/MAP-Elites functions (those are called by the main loop)

---

### Step 5: Main Loop (while True)
**Files**: `autoresearch_v2.py`
**Complexity**: MEDIUM-HIGH
**Depends on**: Steps 1-4

Wire everything into the infinite research loop with logging infrastructure.

Implementation details:

**Logging setup**:
- Use Python `logging` module with two handlers:
  - `FileHandler` to `logs/research.log` (DEBUG level, includes timestamps)
  - `StreamHandler` to stdout (INFO level, concise)
- `log_cycle_stats(conn, cycle_num, topic)`: Log cycle number, papers count, comparisons count, top fitness score, elapsed time for cycle. Output to both log file and stdout.
- `log_error(exception, context_msg)`: Log full exception traceback to log file, summary to stdout.
- Create `logs/` directory at startup if it does not exist.

**Main loop**:
- `cold_start(conn, topic, session_id)`: If papers count < 10, use research_agent to generate seed papers. Block until 10 papers exist.
- `research_loop(db_path, topic, session_id)`:
  ```
  conn = init_db(db_path)  # single connection for session lifetime
  setup_logging()
  cold_start(conn, topic, session_id)

  while True:
    try:
      # Session context (L0 filter -> L1 load -> annotation inject)
      context = build_session_context(conn, topic, session_id)

      # Phase 1: Generate new paper (30% rebuttal)
      new_paper = run_research(conn, topic, session_id, context)

      # Phase 2: Claim classification + pairwise comparison
      rival = select_rival(conn, topic)
      comparison = run_comparison(conn, new_paper, rival)

      # Phase 3: Reflector LLM -- annotation extraction ONLY
      annotations = run_reflection(conn, session_id, topic, comparison, new_paper)
      for ann in annotations:
          save_annotation(conn, new_paper["id"], session_id, ann["content"], ann["tags"])

      # Phase 4: Deterministic state updates (Python, not LLM)
      calculate_fitness(conn, topic)
      update_lifecycle_states(conn, topic)
      update_map_elites(conn, topic)

      # Cycle stats
      log_cycle_stats(conn, cycle_num, topic)

      await asyncio.sleep(5)
    except Exception as e:
      log_error(e, f"cycle {cycle_num}")
      await asyncio.sleep(30)  # backoff on error
  ```
- CLI interface: `python autoresearch_v2.py --topic "agentic_memory" --db db/knowledge.db`
- Signal handling: SIGINT/SIGTERM triggers graceful shutdown (finish current cycle, close `conn`)

Acceptance criteria:
- [ ] `python autoresearch_v2.py --topic agentic_memory` starts, seeds 10 papers, and begins cycling
- [ ] After 10 cycles: `comparisons` table has 5+ entries (some comparisons skip due to orthogonal/bias disagreement)
- [ ] After a KeyboardInterrupt, the DB is left in a consistent state (no partial writes)
- [ ] After restarting the script, it resumes with existing papers (no re-seeding, annotations carry over)
- [ ] `logs/research.log` contains cycle stats (cycle number, paper count, comparison count, top fitness, elapsed time)
- [ ] Errors are logged with full tracebacks to `logs/research.log` and summaries to stdout
- [ ] Cost per cycle is logged and estimated < $0.50
- [ ] Deterministic functions (`calculate_fitness`, `update_lifecycle_states`, `update_map_elites`) are called in the main loop, not inside the reflector agent

---

### Step 6: Integration Test + Cold Start Seeding
**Files**: `tests/test_integration.py`, `seed_data.py`
**Complexity**: LOW
**Depends on**: Step 5

Validate the full loop end-to-end and provide manual seed data option.

Implementation details:
- `seed_data.py`: Generate 10 seed papers on "agentic memory" topic by extracting key claims from the existing research docs (`260317_*.md` files). Insert directly into DB with proper L0/L1/L2 and SHA-256 IDs (using `claim + l1_summary` hash). This provides a deterministic cold start alternative to LLM-generated seeds.
- `tests/test_integration.py`:
  1. Test schema creation + WAL mode + busy_timeout
  2. Test paper_id determinism (hash of claim + l1_summary)
  3. Test paper_id collision resistance (different claims -> different IDs)
  4. Test memory context assembly with mock data
  5. Test fitness calculation with known comparison graph
  6. Test MAP-Elites archival logic
  7. Test main loop runs 3 cycles without crash (with mocked LLM calls for CI)
  8. Test logging output (log file created, cycle stats present)

Acceptance criteria:
- [ ] `python seed_data.py` populates DB with 10 papers, each having valid L0/L1/L2 fields
- [ ] All integration tests pass
- [ ] 3-cycle smoke test completes without errors
- [ ] DB state after smoke test shows: 10+ papers, 1+ comparisons, 1+ audit_chain entries

---

## Final File Structure

```
auto_research/autoresearch/
  __init__.py
  autoresearch_v2.py        <- Main loop (Step 5)
  seed_data.py              <- Cold start seeding (Step 6)
  requirements.txt          <- Dependencies (Step 0/1)
  db/
    .gitkeep                <- DB directory (knowledge.db created at runtime)
  logs/
    .gitkeep                <- Log directory (research.log created at runtime)
  agents/
    __init__.py
    research_agent.py       <- Paper generation via query() (Step 4)
    compare_agent.py        <- Pairwise comparison via query() (Step 4)
    reflector_agent.py      <- Annotation extraction via query() (Step 4)
  core/
    __init__.py             <- init_db() with single connection (Step 1)
    schema.sql              <- SQLite schema (Step 1)
    memory.py               <- L0/L1/L2 + annotations (Step 2)
    fitness.py              <- PageRank + MAP-Elites (Step 3)
  tests/
    __init__.py
    test_integration.py     <- Integration tests (Step 6)
```

**Total: 14 files** (5 directories, 14 files)

---

## Implementation Order (Dependency Graph)

```
Step 0 (SDK verification -- GATE)
  |
  +---> Step 1 (schema + setup + connection strategy)
          |
          +---> Step 2 (memory.py)
          |       |
          +---> Step 3 (fitness.py)
          |       |
          +-------+---> Step 4 (3 agent modules as query() calls)
                          |
                          +---> Step 5 (main loop + logging + deterministic post-reflection)
                                  |
                                  +---> Step 6 (tests + seed)
```

Steps 2 and 3 can be implemented in parallel. All other steps are sequential.
Step 0 is a hard gate: if SDK verification fails, the fallback path must be chosen before Step 1 proceeds.

---

## Model Allocation (Cost Reference)

| Role | Model | Est. tokens/cycle | Est. cost/cycle |
|------|-------|-------------------|-----------------|
| Research agent (`query()`) | claude-sonnet-4-6 | ~4,000 in + ~2,000 out | ~$0.03 |
| Compare agent (x2 `query()` calls) | claude-haiku-4-5 | ~2,000 in + ~200 out (x2) | ~$0.004 |
| Reflector agent (`query()`) | claude-haiku-4-5 | ~1,000 in + ~500 out | ~$0.002 |
| **Total per cycle** | | | **~$0.04** |

At $0.04/cycle, 100 cycles/day = ~$4/day. Well under the $0.50/cycle budget.

---

## Key Design Decisions Per File

| File | Key Decision | Rationale |
|------|-------------|-----------|
| `schema.sql` | 3-column comparisons table (no judge metadata) | Strategy report: "who judged" is meaningless; only results matter |
| `schema.sql` | `edges` table created but no indexes | Prepares for Phase 2; no module reads/writes edges in Phase 1 |
| `core/__init__.py` | Single `sqlite3.Connection` with `busy_timeout=5000` | Simplest correct strategy for single-process Phase 1; no async write contention |
| `memory.py` | `paper_id` hashes `claim + l1_summary` (not `content[:500]`) | Avoids collision risk from papers with similar openings |
| `memory.py` | SQL LIKE search, no vector embeddings | Strategy report: L0 + LLM > embeddings for accuracy |
| `fitness.py` | networkx PageRank (not custom implementation) | 5 lines of code, well-tested library |
| `compare_agent.py` | Default to "orthogonal" on uncertain classification | Strategy report issue #1 mitigation |
| `reflector_agent.py` | LLM extracts annotations only; deterministic work in main loop | Reflector should not call `calculate_fitness()`, `update_lifecycle_states()`, `update_map_elites()` -- those are pure Python |
| `autoresearch_v2.py` | Emit convergence event but never stop loop | Strategy report issue #5: human decides when to stop |
| `autoresearch_v2.py` | Python `logging` to file + stdout | Overnight runs need observable log trail |
| `seed_data.py` | Extract from existing docs, not random generation | Deterministic cold start; existing docs have quality claims |

---

## Success Criteria (Phase 1 MVP)

- [ ] System starts from empty DB, seeds 10 papers, and runs indefinitely
- [ ] After 10 cycles: `comparisons` table has 5+ entries
- [ ] After 20 cycles: at least 1 paper has `fitness > 0.7` (champion formation)
- [ ] After 20 cycles: at least 1 paper has `status = 'archived'` (selection pressure working)
- [ ] Session restart preserves all state: papers, comparisons, annotations, audit_chain
- [ ] Annotations from cycle N appear in session context for cycle N+1
- [ ] Cost per cycle < $0.50 (target: ~$0.04)
- [ ] No single API error or crash kills the main loop
- [ ] `logs/research.log` contains structured cycle statistics and error traces
- [ ] All DB writes are synchronous within each cycle (no async write-back in Phase 1)
- [ ] `edges` table exists but is empty (populated in Phase 2)

---

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| `claude-agent-sdk` pip package unavailable or broken | Step 0 gate: verify before proceeding; fallback to `anthropic` package with `messages.create()` + tool_use |
| Claude Agent SDK API instability | Pin version in requirements.txt; wrap all SDK calls in try/except |
| LLM outputs malformed JSON | Parse with fallback defaults; retry once on parse failure |
| SQLite WAL corruption on hard kill | WAL mode handles this natively; add periodic PRAGMA integrity_check |
| Claim classification unreliability | Default to "orthogonal" (skip comparison) when uncertain |
| Token budget overflow with many papers | L0 filtering caps loaded papers; max_tokens parameter enforced |
| Cold start: LLM generates low-quality seeds | Provide `seed_data.py` with hand-extracted claims as alternative |
| Overnight run unobservable | Python `logging` to `logs/research.log` with rotation; `log_cycle_stats` on every cycle |

---

## Revision History

### R1 (2026-03-17) — Architect + Critic Consensus Fixes

1. **SDK API Pattern Fix (HIGH)**: Rewrote Step 4 to use standalone `query()` calls with `ClaudeAgentOptions` instead of `AgentDefinition` as callable agents. Each agent is a top-level `query()` call. Added SDK code pattern examples.

2. **Reflector Split (HIGH)**: Split reflector into LLM part (annotation extraction in `agents/reflector_agent.py`) and deterministic part (fitness, lifecycle, MAP-Elites calls moved to Step 5 main loop). `run_reflection()` now returns annotations only.

3. **SQLite Connection Strategy (MEDIUM)**: Added single `sqlite3.Connection` with `busy_timeout=5000` to Step 1. All writes synchronous within cycle. Removed "async write-back" from Principle 5 for Phase 1.

4. **`edges` Table Deferral (MEDIUM)**: Kept CREATE TABLE in schema.sql, removed indexes on `edges` from Step 1. Added note that `edges` population is deferred to Phase 2.

5. **`paper_id` Hash Input (LOW)**: Changed from `SHA-256(content[:500])[:16]` to `SHA-256(claim + l1_summary)[:16]` to reduce collision risk from similar paper openings.

6. **Logging Strategy (MEDIUM)**: Added logging infrastructure to Step 5: Python `logging` module to `logs/research.log` + stdout. Defined `log_cycle_stats` and `log_error`. Added `logs/` directory to file structure.

7. **SDK Package Verification (MEDIUM)**: Added Step 0 as pre-implementation gate. Verify `claude-agent-sdk` install, import path, and tool availability. Fallback to `anthropic` package if SDK unavailable.
