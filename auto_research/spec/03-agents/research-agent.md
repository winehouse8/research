# Research Agent — `agents/research_agent.py`

## 역할

실제 웹 검색으로 증거를 수집하고, 수집된 증거를 바탕으로 논문 JSON을 생성합니다. 에코시스템에 새 지식을 주입하는 유일한 에이전트입니다.

---

## 설정

| 항목 | 값 |
|------|----|
| 모델 | `claude-sonnet-4-6` |
| 도구 | `WebSearch`, `WebFetch` |
| OMC | 사용 (`OMC_OPTS`) |
| `max_turns` | 15 |
| `permission_mode` | `bypassPermissions` |
| Stop Hook | `enforce_research_quality` (품질 미달 시 중지 거부) |

sonnet을 사용하는 이유: 검색 결과를 읽고 판단하여 구조화된 논문을 생성하는 작업은 실행력이 필요합니다. compare/reflector의 단순 판단 작업과 달리 비용보다 품질이 우선입니다.

### Stop Hook 품질 게이트

`enforce_research_quality` 훅이 논문의 최소 품질을 강제합니다:
- 결과 300자 미만 → 거부 ("논문이 너무 짧습니다")
- `evidence_sources: []` → 거부 ("증거가 없습니다")
- assumptions가 "None stated" 등 → 거부 ("Popper 게이트 미충족")
- 최대 3회 거부 후 안전 밸브로 통과 (`MAX_STOP_RETRIES=3`)

---

## 프롬프트 설계 원칙

```
- Research question은 NORTH STAR — 부가적 참고가 아님
- Popper: 모든 claim은 반증 가능한 assumptions + 테스트 가능한 경계 조건을 가져야 함
- Bayes: 증거는 기존 컨텍스트의 믿음을 UPDATE해야 함 (단순 확인이 아님)
- Lakatos: 새 예측 > ad hoc 패치 (특히 반박 논문에서)
- 기존 지식 위에 구축, 이미 알려진 것을 반복하지 않음
```

---

## 시스템 프롬프트 구조

### `RESEARCH_SYSTEM_PROMPT` (기본)

에이전트에게 다음을 강제합니다:

**1. North Star 지향**

```
Your mission is to advance collective understanding of a specific research question
by producing a well-evidenced, falsifiable research paper.

The user's research question defines what matters. Every search query you form,
every source you evaluate, and every claim you make must demonstrably serve
that question.
```

**2. Evidence Gathering Protocol (5단계)**

```
1. DECOMPOSE the research question into 2-3 searchable sub-questions
2. Use WebSearch for EACH sub-question (minimum 3 searches, targeting different facets)
3. Use WebFetch to read the most promising sources IN FULL
4. EVALUATE source quality:
   - Peer-reviewed > technical report > blog post > opinion
   - Recency matters: prefer sources from the last 3 years
   - Cross-reference: a claim supported by 2+ independent sources is stronger
5. If the existing context already covers a finding, DO NOT repeat it
```

**3. Paper Requirements (Popper + Bayes)**

```
- claim MUST be falsifiable: state specific conditions under which it would be FALSE
- assumptions must list TESTABLE boundary conditions, not vague caveats
  Bad: "Assumes standard conditions."
  Good: "Assumes write-heavy workload (>70% writes), single-region deployment"
- Evidence should UPDATE beliefs from the existing context (Bayesian)
```

**4. Building on Existing Knowledge**

```
- Do NOT repeat claims already established with high fitness
- Do NOT ignore contradictions or limitations in prior annotations
- DO build on, refine, or challenge existing findings
- DO explore gaps and unanswered sub-questions
```

최종 메시지는 JSON 오브젝트만 출력하도록 명시합니다(`no other text`).

### `REBUTTAL_ADDITION` (반박 논문용 추가 지시)

`is_rebuttal=True`일 때 기본 프롬프트 뒤에 덧붙입니다.

```
SPECIAL INSTRUCTION: You are writing a REBUTTAL paper.

## Champion's Position
The current champion claims: "{champion_claim}"

## Your Rebuttal Mission
1. Search for evidence that CONTRADICTS, LIMITS, or SUPERSEDES this claim
2. You MUST propose an ALTERNATIVE claim, not just point out flaws
   (Lakatos criterion: your rebuttal must be a PROGRESSIVE research program
   that makes NEW testable predictions the champion cannot make)
3. Your paper must answer: "If the champion is wrong/limited, what is the
   BETTER explanation, and what NEW prediction does it make?"

ANTI-PATTERNS TO AVOID:
- "The champion is wrong because [one exception]" — this is a DEGENERATIVE patch
- "More research is needed" — this is not a claim
- Repeating the champion's framework with minor modifications
```

챔피언 claim을 직접 삽입하여 에이전트가 무엇에 반박해야 하는지 명확히 합니다. 라카토슈 기준의 **진보적 vs 퇴행적** 구별을 안티패턴으로 구체화했습니다.

---

## `run_research()` 함수

```python
async def run_research(
    conn,
    topic: str,
    session_id: str,
    context: str,
    champion_claim: str = None,
    is_rebuttal: bool = False,
    research_question: str = "",
) -> dict:
```

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `conn` | SQLite connection | 논문 저장에 사용 |
| `topic` | `str` | 연구 주제 태그 (예: `agentic_memory`) |
| `session_id` | `str` | 현재 세션 ID |
| `context` | `str` | `build_session_context()`가 생성한 L0/L1/annotation 컨텍스트 |
| `champion_claim` | `str` \| `None` | 반박 대상 챔피언 claim |
| `is_rebuttal` | `bool` | `True`이면 `REBUTTAL_ADDITION`을 시스템 프롬프트에 추가 |
| `research_question` | `str` | 사용자가 지정한 상세 연구 질문 (에이전트의 North Star) |

반환값: `id` 키가 추가된 논문 딕셔너리.

### 실행 흐름

1. `is_rebuttal`이면 시스템 프롬프트에 `REBUTTAL_ADDITION` 결합
2. `research_question`이 있으면 user prompt에 `## Research Question` 섹션 추가
3. `query()` 비동기 스트림 시작 (`max_turns=15`)
4. 스트림에서 `ResultMessage` 수신 시 `result_text` 저장
5. 중간 메시지의 tool use 블록을 DEBUG 로그로 기록
6. `_parse_paper_json()`으로 결과 파싱
7. `save_paper(conn, paper)`로 DB 저장 후 `id` 부여
8. 예외 발생 시 fallback 논문 생성 후 동일하게 저장

### User Prompt 구조

```
## Research Mission
Topic: {topic}

## Research Question (항상 이 질문을 염두에 두고 연구하세요)
{research_question}

## Current Knowledge Context
{context}

## Your Task
1. ANALYZE the context above: What is well-established? What is contradicted?
   What gaps remain relative to the research question?
2. CHOOSE a gap or unresolved tension to investigate
3. SEARCH the web for evidence that addresses this specific gap
4. WRITE a paper that ADVANCES the ecosystem's knowledge beyond its current state

Do NOT produce a paper that merely restates what the context already covers.
Your paper will be compared against existing papers — redundancy loses.
```

### 30% 반박 논문 메커니즘

메인 루프(`autoresearch_v2.py`)에서 결정합니다.

```python
champion = get_champion(conn, topic)
is_rebuttal = random.random() < 0.3 and bool(champion)
new_paper = await run_research(..., champion_claim=champion.get("claim") if is_rebuttal and champion else None,
                               is_rebuttal=is_rebuttal, research_question=research_question)
```

챔피언이 존재할 때만 반박 논문을 생성합니다. run_research 자체는 플래그를 받아 프롬프트만 변경합니다.

---

## `_parse_paper_json()` 파싱 로직

LLM 출력에서 JSON을 추출합니다.

```
1. ```json ... ``` 블록이 있으면 추출
2. ``` ... ``` 블록이 있으면 추출
3. json.loads() 파싱
4. 필수 필드 누락 시 "[Missing {field}]"로 채움
5. perspective가 유효하지 않으면 "empirical"로 보정
```

파싱 완전 실패 시(JSONDecodeError 등) 원문 텍스트를 그대로 각 필드에 잘라 넣은 폴백 딕셔너리를 반환합니다.

---

## 출력 형식

| 필드 | 설명 |
|------|------|
| `claim` | 핵심 주장 한 문장 |
| `l0_summary` | ~50 단어 요약 (관련성 필터용) |
| `l1_summary` | ~500 단어 상세 요약 (추론 컨텍스트용) |
| `l2_content` | 전문 (1000-2000 단어) |
| `evidence_sources` | `[{title, url, excerpt}]` 리스트 |
| `assumptions` | claim이 성립하는 조건 (테스트 가능한 경계 조건) |
| `topic_tag` | MAP-Elites 셀 주소 |
| `perspective` | `empirical` \| `theoretical` \| `applied` \| `critical` |
| `id` | `save_paper()` 반환값 (SHA-256 기반 결정론적 ID) |

---

## 에러 처리

예외 발생 시 fallback 논문을 생성하고 DB에 저장합니다. 루프를 중단하지 않고 다음 사이클로 진행할 수 있도록 합니다.

```python
paper = {
    "claim": f"Research on {topic} requires further investigation.",
    "l0_summary": f"Preliminary findings on {topic}.",
    ...
    "evidence_sources": [],
    "assumptions": "This is a placeholder paper.",
    "perspective": "empirical",
}
```
