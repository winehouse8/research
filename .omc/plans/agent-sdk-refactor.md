# Plan: Refactor Auto Research Agents to Claude Agent SDK

**Date:** 2026-03-18
**Status:** Draft (pending consensus review)
**Complexity:** MEDIUM
**Scope:** 5 files, 3 agents, 1 main loop, 1 dependency file

---

## RALPLAN-DR Summary

### Principles
1. **Minimal blast radius** -- Only the agent invocation layer changes. Core architecture (SQLite schema, memory, fitness, MAP-Elites) is untouched.
2. **Real tool access over simulated search** -- The research agent currently asks the LLM to "pretend to search." The SDK gives it real WebSearch/WebFetch tools, which is the primary quality improvement.
3. **Sync-to-async migration must be safe** -- `query()` is async. The main loop must become async without breaking signal handling, SQLite access, or the cold-start flow.
4. **Keep simple agents simple** -- compare_agent and reflector_agent are prompt-in/JSON-out with no tool use. They should use `query()` with minimal/no tools, not be over-engineered with subagents.
5. **Preserve public interfaces** -- `run_research()`, `run_comparison()`, `run_reflection()` keep the same signatures (add async) so the main loop changes are minimal.

### Decision Drivers (Top 3)
1. **Research quality** -- WebSearch/WebFetch give the research agent real evidence grounding instead of hallucinated sources.
2. **Migration safety** -- The system runs unattended overnight. A broken refactor means silent failures and wasted API spend.
3. **Cost efficiency** -- compare_agent and reflector_agent run haiku. The SDK must allow model selection per agent to avoid accidentally running everything on sonnet/opus.

### Viable Options

#### Option A: Incremental per-agent migration (RECOMMENDED)
Migrate each agent file independently. Each agent's `run_*` function becomes `async` and calls `query()` internally. The main loop gets `async/await` added. No subagent orchestration pattern.

| Pros | Cons |
|------|------|
| Each agent can be tested independently | 3 separate migration steps (more PRs if desired) |
| Rollback granularity: revert one file | Main loop still needs async conversion regardless |
| Simple mental model: each file is self-contained | No inter-agent coordination benefits |

#### Option B: Orchestrator subagent pattern
Define all 3 agents as `AgentDefinition` subagents. A parent orchestrator agent manages the research cycle via the `Agent` tool.

| Pros | Cons |
|------|------|
| Single entry point for the whole cycle | Loses fine-grained Python control over the 5-phase loop |
| SDK handles agent routing | SQLite access from subagents is unclear/unsupported |
| Cleaner architecture long-term | Deterministic Phase 5 (fitness/lifecycle/MAP-Elites) cannot run inside an LLM agent |
| | Compare agent's position-bias-removal (A-B then B-A) requires programmatic control |
| | Over-engineering for the current use case |

**Decision: Option A.** The main loop has critical deterministic phases (fitness calculation, lifecycle updates, MAP-Elites) that must remain in Python. The compare agent's position-bias-removal pattern requires programmatic control of two sequential LLM calls with result mapping. These constraints invalidate the orchestrator pattern. Option B would force either moving deterministic logic into prompts (fragile) or splitting the orchestrator in unnatural ways.

---

## Context

The auto_research project has 3 LLM agents using `anthropic.Anthropic().messages.create()` directly:

| Agent | Model | Purpose | Current LLM Calls | Tool Benefit |
|-------|-------|---------|-------------------|--------------|
| `research_agent.py` | claude-sonnet-4-6 | Generate research papers | 1 call per paper | HIGH: WebSearch + WebFetch for real evidence |
| `compare_agent.py` | claude-haiku-4-5 | Classify claims + judge pairs | 3 calls per comparison (1 classify + 2 judge) | LOW: no tools needed |
| `reflector_agent.py` | claude-haiku-4-5 | Extract annotations | 1 call per reflection | LOW: no tools needed |

The `query()` function from `claude-agent-sdk` replaces `client.messages.create()`. It is async and returns an async iterator of messages.

---

## Work Objectives
- Replace all `anthropic` SDK usage with `claude-agent-sdk`
- Give research_agent real WebSearch/WebFetch capability
- Convert the main loop to async
- Maintain all existing behavior and interfaces
- Tests must pass after refactoring

## Guardrails

### Must Have
- All 3 agents use `claude-agent-sdk.query()` instead of `anthropic.messages.create()`
- `research_agent` has `WebSearch` and `WebFetch` in its allowed_tools
- Model selection per agent (sonnet for research, haiku for compare/reflector)
- Same function signatures (plus `async`) for all `run_*` functions
- Same JSON output parsing and fallback logic
- Existing tests pass without modification
- `requirements.txt` updated

### Must NOT Have
- Changes to SQLite schema, memory system, or fitness calculations
- Subagent/orchestrator patterns (keep agents as simple async functions)
- Changes to the 5-phase loop structure
- Removal of position-bias-removal logic in compare_agent
- New dependencies beyond `claude-agent-sdk`

---

## Task Flow

```
Step 1: research_agent.py    (highest value, most changes)
    |
Step 2: compare_agent.py     (3 LLM calls need careful async conversion)
    |
Step 3: reflector_agent.py   (simplest, 1 call)
    |
Step 4: autoresearch_v2.py   (async main loop + cold_start)
    |
Step 5: requirements.txt + smoke test
```

---

## Detailed TODOs

### Step 1: Migrate research_agent.py

**File:** `/Users/jaewoo/Desktop/Project/research/auto_research/agents/research_agent.py`

Changes:
1. Replace `from anthropic import Anthropic` with `from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, ResultMessage`
2. Remove `client = Anthropic()` global
3. Convert `run_research()` to `async def run_research()`
4. Replace `client.messages.create()` with:
   ```python
   result_text = ""
   async for message in query(
       prompt=user_prompt,
       options=ClaudeAgentOptions(
           allowed_tools=["WebSearch", "WebFetch"],
           permission_mode="bypassPermissions",
           system_prompt=system,
           model="sonnet",
       ),
   ):
       if isinstance(message, ResultMessage):
           result_text = message.result
   ```
5. Update the system prompt: remove "Search for at least 3 pieces of evidence" instruction (the agent now has real tools and will search autonomously). Replace with guidance to USE the WebSearch and WebFetch tools.
6. Keep `_parse_paper_json()` unchanged (still needed for output parsing)
7. Keep fallback paper generation in the except block

**Acceptance Criteria:**
- [ ] `run_research()` is async and uses `query()`
- [ ] WebSearch and WebFetch are in allowed_tools
- [ ] Model is set to "sonnet"
- [ ] System prompt references using search tools (not pretending to search)
- [ ] `_parse_paper_json()` is unchanged
- [ ] Fallback error handling is preserved

### Step 2: Migrate compare_agent.py

**File:** `/Users/jaewoo/Desktop/Project/research/auto_research/agents/compare_agent.py`

Changes:
1. Replace imports: `anthropic` -> `claude_agent_sdk`
2. Remove `client = Anthropic()` global
3. Convert `run_comparison()` to `async def run_comparison()`
4. Convert `_classify_claims()` to `async def _classify_claims()` -- replace `client.messages.create()` with `query()` call:
   ```python
   async for message in query(
       prompt=CLASSIFY_PROMPT.format(...),
       options=ClaudeAgentOptions(
           allowed_tools=[],  # No tools needed for classification
           permission_mode="bypassPermissions",
           model="haiku",
       ),
   ):
       if isinstance(message, ResultMessage):
           result = message.result.strip().lower()
   ```
5. Convert `_judge()` to `async def _judge()` -- same pattern, no tools, haiku model
6. Update `run_comparison()` to `await` both `_classify_claims()` and `_judge()` calls
7. Position-bias-removal logic stays exactly the same (sequential: forward then reverse)

**Acceptance Criteria:**
- [ ] All 3 functions are async
- [ ] No tools in allowed_tools (classification and judging are pure reasoning)
- [ ] Model is set to "haiku"
- [ ] Position-bias-removal flow unchanged (forward judge, then reverse judge, then unanimity check)
- [ ] JSON parsing and fallback logic unchanged
- [ ] Comparison recording to SQLite unchanged

### Step 3: Migrate reflector_agent.py

**File:** `/Users/jaewoo/Desktop/Project/research/auto_research/agents/reflector_agent.py`

Changes:
1. Replace imports: `anthropic` -> `claude_agent_sdk`
2. Remove `client = Anthropic()` global
3. Convert `run_reflection()` to `async def run_reflection()`
4. Replace `client.messages.create()` with `query()` -- no tools, haiku model
5. Keep `_parse_annotations()` unchanged (synchronous helper, no LLM call)

**Acceptance Criteria:**
- [ ] `run_reflection()` is async and uses `query()`
- [ ] No tools in allowed_tools
- [ ] Model is set to "haiku"
- [ ] `_parse_annotations()` unchanged
- [ ] Error fallback annotation preserved

### Step 4: Convert autoresearch_v2.py to async

**File:** `/Users/jaewoo/Desktop/Project/research/auto_research/autoresearch_v2.py`

Changes:
1. Add `import asyncio`
2. Convert `cold_start()` to `async def cold_start()` -- await `run_research()` calls
3. Convert `research_loop()` to `async def research_loop()`:
   - `await run_research(...)` in Phase 2
   - `await run_comparison(...)` in Phase 3
   - `await run_reflection(...)` in Phase 4
   - Replace `time.sleep()` with `await asyncio.sleep()`
4. Update `main()` to use `asyncio.run(research_loop(...))`
5. Signal handling: use `loop.add_signal_handler()` instead of `signal.signal()` for proper async signal handling, or keep the current `signal.signal()` approach (which works fine with asyncio.run)
6. All deterministic code in Phase 5 stays synchronous (no async needed for SQLite operations via the same connection)

**Acceptance Criteria:**
- [ ] `cold_start()` and `research_loop()` are async
- [ ] All agent calls use `await`
- [ ] `time.sleep()` replaced with `await asyncio.sleep()`
- [ ] `main()` uses `asyncio.run()`
- [ ] Signal handling works (SIGINT/SIGTERM graceful shutdown)
- [ ] Phase 5 deterministic logic untouched
- [ ] Cycle stats logging unchanged

### Step 5: Update requirements.txt and smoke test

**File:** `/Users/jaewoo/Desktop/Project/research/auto_research/requirements.txt`

Changes:
1. Replace `anthropic>=0.85.0` with `claude-agent-sdk`
2. Keep `networkx>=3.0`, `numpy>=2.0`, `scipy>=1.13`

Verification:
1. Run `pip install -r requirements.txt` to confirm package installs
2. Run `python -m pytest auto_research/tests/test_integration.py -v` -- must pass (tests don't touch agents)
3. Run `python autoresearch_v2.py --topic test_topic --db /tmp/test.db` for 1-2 cycles, verify:
   - Papers are generated with real evidence_sources (from WebSearch)
   - Comparisons produce winners/losers
   - Annotations are extracted
   - No import errors or runtime exceptions

**Acceptance Criteria:**
- [ ] `requirements.txt` has `claude-agent-sdk` instead of `anthropic`
- [ ] `pip install` succeeds
- [ ] Existing tests pass
- [ ] Smoke test completes 1+ cycles without errors
- [ ] Research agent papers contain real web-sourced evidence

---

## Success Criteria
1. All `from anthropic import Anthropic` removed from codebase
2. All agent functions use `claude_agent_sdk.query()`
3. Research agent produces papers with real web evidence (WebSearch/WebFetch)
4. Compare agent preserves position-bias-removal behavior
5. Main loop runs async with proper signal handling
6. Existing integration tests pass unchanged
7. System can run 5+ cycles without errors

---

## ADR: Agent SDK Migration

**Decision:** Migrate all 3 agents from raw `anthropic` SDK to `claude-agent-sdk` using incremental per-agent approach (Option A).

**Drivers:**
1. Research quality improvement via real WebSearch/WebFetch tools
2. Migration safety for an unattended overnight system
3. Cost control via per-agent model selection

**Alternatives Considered:**
- **Option B: Orchestrator subagent pattern** -- Invalidated because the main loop has deterministic Python phases (fitness, lifecycle, MAP-Elites) that cannot run inside LLM agents, and the compare agent's position-bias-removal requires programmatic control of sequential LLM calls.

**Why Chosen:** Option A preserves the existing control flow, allows independent testing of each agent, and provides rollback granularity at the file level. The main loop remains the orchestrator (in Python), which is the correct abstraction for a system that mixes LLM calls with deterministic state updates.

**Consequences:**
- The main loop must become async (one-time migration cost)
- Each agent file gets simpler (no manual client management)
- Research agent output quality should improve (real evidence)
- Future agents can be added using the same pattern

**Follow-ups:**
- Monitor research agent paper quality after migration (do evidence_sources contain real URLs?)
- Evaluate whether compare_agent benefits from WebFetch to verify cited evidence (Phase 2 enhancement)
- Consider adding retry logic via SDK hooks if transient failures increase
