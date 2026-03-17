# SDK 통합 — `agents/_sdk.py`

## 역할

`_sdk.py`는 두 가지 역할을 수행하는 공통 모듈입니다:

1. **OMC 플러그인 경로 탐색** — oh-my-claudecode 플러그인을 동적으로 발견하여 research_agent에 주입
2. **Quality-Enforcement Stop Hooks** — 각 에이전트의 출력 품질을 SDK 레벨에서 강제 (Mini-Ralph 패턴)

---

## OMC 플러그인 경로 탐색 — `_find_omc_plugin_path()`

플러그인 경로를 다음 순서로 탐색합니다.

| 우선순위 | 탐색 위치 | 조건 |
|----------|-----------|------|
| 1 | 환경변수 `OMC_PLUGIN_PATH` | 디렉토리가 존재하면 즉시 반환 |
| 2 | `~/.claude/plugins/cache/omc/oh-my-claudecode/` | 하위 버전 디렉토리 중 최신 버전 반환 |
| 3 | 빈 문자열 `""` | 플러그인 없이 계속 진행 (폴백) |

```python
OMC_PLUGIN_PATH = _find_omc_plugin_path()

OMC_OPTS = dict(
    setting_sources=["user", "project"],
    plugins=[{"type": "local", "path": OMC_PLUGIN_PATH}] if OMC_PLUGIN_PATH else [],
)
```

---

## `OMC_OPTS` 딕셔너리

| 키 | 값 | 설명 |
|----|-----|------|
| `setting_sources` | `["user", "project"]` | `CLAUDE.md`, 스킬, 훅을 에이전트 세션에 로드 |
| `plugins` | `[{"type": "local", "path": ...}]` | OMC 플러그인 주입. 경로 없으면 빈 리스트 |

`OMC_OPTS`는 research_agent의 `ClaudeAgentOptions`에 `**OMC_OPTS`로 언패킹되어 전달됩니다. compare/reflector는 OMC_OPTS를 사용하지 않지만, 품질 훅은 사용합니다.

---

## Quality-Enforcement Stop Hooks (Mini-Ralph 패턴)

### 개요

각 에이전트에게 Stop hook을 주입하여 출력 품질이 미달이면 중지를 거부하고 작업을 계속하도록 강제합니다. 이는 OMC의 `persistent-mode.cjs`의 Python SDK 등가물입니다.

```
OMC:     Stop hook → shell script → "Work is NOT done. Continue."
SDK:     Stop hook → Python callback → "품질 미달. 계속 연구해."
```

### 안전 밸브: `MAX_STOP_RETRIES = 3`

무한 루프를 방지하기 위해 각 에이전트별로 최대 3번 거부 후 통과시킵니다.

```python
_stop_attempt_counts = {}
MAX_STOP_RETRIES = 3

# 각 훅 내부:
_stop_attempt_counts[key] += 1
if _stop_attempt_counts[key] > MAX_STOP_RETRIES:
    _stop_attempt_counts[key] = 0
    return {}  # 통과
```

### SDK 사용 패턴: `HookMatcher`

```python
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage, HookMatcher

options=ClaudeAgentOptions(
    ...
    hooks={
        "Stop": [HookMatcher(matcher="*", hooks=[enforce_research_quality])]
    },
)
```

`HookMatcher(matcher="*", hooks=[callback])`: 모든 Stop 이벤트에 대해 콜백을 실행합니다.

---

## `enforce_research_quality()` — Research Agent Stop Hook

```python
async def enforce_research_quality(input_data, tool_use_id, context):
```

| 검사 | 조건 | 거부 메시지 (요약) |
|------|------|-------------------|
| 결과 길이 | `len(result) < 300` | "논문이 너무 짧습니다" |
| 증거 존재 | `evidence_sources: []` | "증거가 없습니다! WebSearch/WebFetch 사용하세요" |
| Assumptions 구체성 | `"None stated"`, `""`, `"N/A"`, `"placeholder"` | "Popper 반증 가능성 게이트 미충족" |

모든 검사 통과 시 빈 딕셔너리 반환 (중지 허용).

---

## `enforce_comparison_quality()` — Compare Agent Stop Hook

```python
async def enforce_comparison_quality(input_data, tool_use_id, context):
```

| 검사 | 조건 | 거부 메시지 (요약) |
|------|------|-------------------|
| 분류/판정 존재 | 응답에 `opposing/complementary/orthogonal` 또는 `"winner"` 없음 | "분류 또는 판정 결과가 명확하지 않습니다" |

분류기(`_classify_claims`)와 판정기(`_judge`) 모두에 같은 훅이 적용됩니다.

---

## `enforce_reflection_quality()` — Reflector Agent Stop Hook

```python
async def enforce_reflection_quality(input_data, tool_use_id, context):
```

| 검사 | 조건 | 거부 메시지 (요약) |
|------|------|-------------------|
| JSON 배열 형식 | `[`와 `"content"` 없음 | "유효한 annotation JSON 배열을 출력하세요" |
| 구체성 | "more research is needed", "추가 연구가 필요" 등 | "너무 모호합니다. 구체적으로 명시하세요" |

---

## 에이전트별 Stop Hook 매핑

| 에이전트 | 훅 함수 | 임포트 경로 |
|----------|---------|------------|
| research_agent | `enforce_research_quality` | `from auto_research.agents._sdk import OMC_OPTS, enforce_research_quality` |
| compare_agent | `enforce_comparison_quality` | `from auto_research.agents._sdk import enforce_comparison_quality` |
| reflector_agent | `enforce_reflection_quality` | `from auto_research.agents._sdk import enforce_reflection_quality` |

### max_turns 변경

Stop hook이 거부하면 에이전트가 추가 턴을 소비합니다. 이를 수용하기 위해:

| 에이전트 | 이전 max_turns | 현재 max_turns |
|----------|---------------|---------------|
| research_agent | 15 | 15 (변경 없음 — 이미 충분) |
| compare_agent | 1 | 3 (Stop hook 재시도 허용) |
| reflector_agent | 1 | 3 (Stop hook 재시도 허용) |
