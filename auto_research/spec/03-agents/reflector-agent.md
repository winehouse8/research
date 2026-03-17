# Reflector Agent — `agents/reflector_agent.py`

## 역할

비교 결과에서 annotation을 추출합니다. LLM이 담당하는 작업은 이것뿐입니다. fitness 갱신, lifecycle 전환, MAP-Elites 업데이트는 모두 메인 루프의 Python 코드에서 결정론적으로 처리합니다.

---

## 설정

| 항목 | 값 |
|------|----|
| 모델 | `claude-haiku-4-5-20251001` |
| 도구 | 없음 (`allowed_tools=[]`) |
| OMC | 사용 안 함 (OMC_OPTS 미적용) |
| `max_turns` | 3 (Stop hook 재시도 허용) |
| `permission_mode` | `bypassPermissions` |
| Stop Hook | `enforce_reflection_quality` (annotation 품질 미달 시 중지 거부) |

### Stop Hook 품질 게이트

`enforce_reflection_quality` 훅이 annotation의 actionability를 강제합니다:
- JSON 배열 형식이 아님 (`[`와 `"content"` 없음) → 거부
- "more research is needed", "추가 연구가 필요" 등 모호한 표현 → 거부
- 최대 3회 거부 후 안전 밸브로 통과

---

## 프롬프트 설계 원칙

```
- Research question이 모든 인사이트를 평가하는 렌즈
- 3개 구조화된 카테고리: knowledge gaps, boundary conditions, methodology
- 모든 annotation은 ACTIONABLE (다음 에이전트가 행동할 수 있는가?)
- suggested_search 필드가 다음 연구 사이클을 직접 안내
- Judge REASONING을 수신하여 증거 기반 반성 수행 (단순 승/패가 아님)
```

---

## `REFLECTION_PROMPT` 구조

```
You are a research reflector in an evolutionary knowledge ecosystem.
Your job is to extract ACTIONABLE insights that will guide the NEXT research cycle.

## Research Question (the north star)
{research_question}

## New Paper
Claim: {new_claim}
Summary: {new_summary}          ← l1_summary 앞 500자
Assumptions: {new_assumptions}

## Comparison Result
{comparison_result}             ← 승/패 + Judge의 reasoning

## Current Knowledge State
{context}                       ← 세션 컨텍스트 앞 1000자

## Your Task
Analyze this cycle's outcome and extract insights in THREE categories:

1. KNOWLEDGE GAPS: What aspects of the research question remain unanswered
   or poorly evidenced? What should the NEXT paper investigate?
   (Tag: evidence_gap, question, direction)

2. BOUNDARY CONDITIONS: What limitations, conditions, or contradictions
   were revealed? Under what circumstances does the claim fail or weaken?
   (Tag: limitation, condition, contradiction, scope_boundary)

3. METHODOLOGY: What worked or failed in the evidence-gathering approach?
   What search strategies or source types should future papers prioritize?
   (Tag: methodology, confirmation)

Output a JSON array of 2-4 annotations:
[
  {"content": "Specific, actionable insight", "tags": ["tag1", "tag2"],
   "suggested_search": "A specific search query the next researcher could use"}
]

Output ONLY the JSON array, nothing else.
```

### `comparison_result` 문자열 조립

| 상황 | `comparison_result` 문자열 |
|------|---------------------------|
| 새 논문이 이긴 경우 | `The new paper WON against rival {loser_id}.` |
| 새 논문이 진 경우 | `The new paper LOST against rival {winner_id}.` |
| 비교 없음 | `No comparison was made (claims were orthogonal or position bias detected).` |

Judge의 reasoning이 있으면 추가됩니다:

```python
if reasoning:
    comp_text += f"\nJudge's reasoning: {reasoning}"
```

---

## `run_reflection()` 함수

```python
async def run_reflection(
    conn,
    session_id: str,
    topic: str,
    comparison_result,
    new_paper: dict,
    context: str = "",
    research_question: str = "",
) -> List[Dict]:
```

| 파라미터 | 설명 |
|----------|------|
| `conn` | 인터페이스 일관성을 위해 받지만 내부에서 사용하지 않음 |
| `comparison_result` | `(winner_id, loser_id, reasoning)` 3-tuple 또는 `None` |
| `new_paper` | 이번 사이클에 생성된 논문 딕셔너리 |
| `context` | 세션 컨텍스트 문자열 |
| `research_question` | 사용자가 지정한 상세 연구 질문 |

반환값: `List[Dict]` — 각 항목은 `{"content": str, "tags": List[str], "suggested_search": str}`.

---

## `_parse_annotations()` 파싱 로직

```
1. ```json ... ``` 블록 추출 시도
2. ``` ... ``` 블록 추출 시도
3. json.loads() 파싱
4. 리스트가 아니면 단일 항목 리스트로 감쌈
5. 각 항목의 tags를 유효 태그 집합과 교차 검증
6. 유효 태그가 없으면 ["general"]로 대체
7. suggested_search 필드 보존
```

파싱 실패 시: `[{"content": text[:300], "tags": ["error"]}]`

---

## 유효 태그 목록

| 태그 | 의미 |
|------|------|
| `limitation` | claim의 적용 범위 제한 |
| `contradiction` | 다른 논문과의 모순 |
| `confirmation` | 다른 논문의 확인/복제 |
| `methodology` | 방법론적 통찰 |
| `question` | 새로운 연구 질문 |
| `direction` | 새로운 연구 방향 |
| `condition` | claim이 성립하는 조건 |
| `evidence_gap` | 증거 부족 영역 |
| `scope_boundary` | claim의 적용 범위 경계 |
| `superseded` | 이전 지식을 대체하는 발견 |
| `convergence` | 여러 증거가 수렴하는 지점 |
| `prediction` | 검증 가능한 새로운 예측 |
| `relevance_gap` | 연구 질문과의 관련성 부족 |

내부적으로 `"error"` 태그도 허용합니다(파싱 실패 annotation에 사용).

---

## `suggested_search` 필드

각 annotation에 포함되는 선택적 필드로, 다음 연구 사이클의 research_agent가 사용할 수 있는 구체적인 검색 쿼리를 제안합니다.

```json
{
  "content": "The claim about memory consolidation lacks evidence for distributed systems with >100 nodes.",
  "tags": ["evidence_gap", "scope_boundary"],
  "suggested_search": "distributed memory consolidation benchmarks 100+ nodes latency"
}
```

이 필드는 `_parse_annotations()`에서 보존되어 annotation에 저장됩니다. 현재 `annotations` 테이블의 `content` 필드에는 저장되지 않지만, 향후 research_agent의 컨텍스트에 주입될 수 있습니다.

---

## 결정론적 작업 분리 원칙

reflector_agent는 의미 추출만 담당합니다. 상태 변경은 메인 루프가 담당합니다.

```
reflector_agent (LLM):     비교 결과 + reasoning → annotation 텍스트 추출
메인 루프 (Python):         fitness 재계산, lifecycle 전환, MAP-Elites 갱신
```

이 분리로 LLM 호출 실패가 상태 일관성에 영향을 주지 않습니다.
