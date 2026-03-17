# Open Questions

## autoresearch-long-term-memory - 2026-03-16

- [ ] SUMMARY.md의 "유망한 미탐색 방향" 포맷: 자유 텍스트 vs 구조화 포맷(JSON-like) — 자유 텍스트는 에이전트 자율성에 유리하나 파싱 일관성 위험. 에이전트가 직접 서술하도록 두고 형식 강제는 하지 않는 것이 현재로서는 단순하나, 실제 루프에서 포맷 드리프트가 발생하는지 관찰 필요.
- [ ] 멀티 에이전트 전환 시점의 파일 잠금 전략: `flock` vs SQLite WAL — 현재 단일 에이전트 가정이지만 이 결정이 파일 구조 설계에 영향을 줌. SQLite WAL이 더 안전하나 의존성 추가 없이도 flock으로 충분할 수 있음.
- [ ] 메타 루프(사고실험 3)의 최적 주기: "10번에 1번"이 고정 주기로 적절한가? 초기(1-20회)에는 너무 잦고 후기(80-100회)에는 너무 드물 수 있음. 적응형 주기(예: 연속 5번 discard 시 자동 전략 검토 트리거)가 더 나을 수 있음.

## autoresearch-v2-ecosystem - 2026-03-17

- [ ] Claude Agent SDK exact API surface: The strategy report references `claude_agent_sdk.query()`, `ClaudeAgentOptions`, `AgentDefinition` -- these need verification against the actual installed package. The SDK may have evolved since the report was written. — Incorrect API usage would block all 3 agent implementations.
- [ ] Agent output parsing reliability: All 3 agents are expected to return structured JSON. LLM outputs may include markdown fencing, extra text, or malformed JSON. — Needs a robust `parse_agent_output(raw_text) -> dict` utility with fallback/retry logic.
- [ ] Optimal initial topic_tags for MAP-Elites: The strategy report suggests 5-10 fixed tags. Which specific tags to use for the "agentic_memory" seed topic? — Determines whether MAP-Elites cells are meaningful or mostly empty at cold start. Suggest starting with 4 perspective-based tags only (empirical/theoretical/applied/critical) and deferring topic sub-tags until 50+ papers accumulate.
- [ ] WebSearch/WebFetch availability in Agent SDK: The strategy report assumes these tools are available. Need to confirm they work within `AgentDefinition` tool lists. — If unavailable, research_agent falls back to generating papers from context-only (no web grounding), which reduces quality but does not block MVP.
- [ ] Seed paper extraction strategy: `seed_data.py` plans to extract claims from existing `260317_*.md` docs. How many claims per doc? What quality threshold? — Too few seeds (< 5) means MAP-Elites grid is nearly empty; too many (> 20) wastes manual effort when the loop will generate papers anyway.
- [ ] Cost monitoring and budget alerting: The system runs indefinitely at ~$0.04/cycle. At what cumulative cost should the system emit a warning or pause? — Prevents unexpected large bills during unattended overnight runs. Suggest a configurable `--max-cost` CLI flag with default $50.

## agent-sdk-refactor - 2026-03-18

- [ ] `ResultMessage.result` format: Does `query()` return the final LLM text in `ResultMessage.result` as a plain string, or does it wrap it in a structured object? — The JSON parsing logic in all 3 agents depends on receiving raw text. If `result` is structured differently, parsing will break silently.
- [ ] `query()` with empty `allowed_tools=[]`: Does the SDK accept an empty tools list for pure prompt-in/text-out usage (compare_agent, reflector_agent)? — If not, we may need to omit the parameter entirely or pass a minimal tool set.
- [ ] Cost impact of SDK overhead: Does `query()` add system-prompt overhead (e.g., tool descriptions) that increases token usage compared to raw `messages.create()`? — For haiku agents running 3+ calls per cycle, even small overhead compounds over overnight runs.
- [ ] Async signal handling on macOS: `asyncio.run()` on macOS uses `kqueue`-based event loops. Does `signal.signal(SIGINT, handler)` work reliably inside `asyncio.run()`, or must we use `loop.add_signal_handler()`? — Broken signal handling means the system cannot shut down gracefully and may corrupt the SQLite WAL.
