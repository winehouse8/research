# 시스템 아키텍처 개요

## 한 문장 정의

Auto Research Ecosystem v2는 LLM이 생성한 연구 논문들이 pairwise 비교 경쟁을 통해 자연선택되고, SQLite 장기 기억과 함께 세션을 넘어 지속적으로 진화하는 자율 연구 루프다.

---

## 핵심 설계 철학

> **"에이전트가 좋은 논문을 쓰도록 하는 것이 아니라, 나쁜 논문이 자연스럽게 도태되는 생태계를 설계하는 것."**

AlphaGo는 "이기면 좋다"만 정의했다. 전략은 에이전트가 스스로 찾았다. 이 시스템은 "살아남으면 좋다"만 정의한다. 좋은 지식을 생산하는 방법은 에이전트가 발견한다.

기존 `ralph.sh` 방식은 단순한 `while true` + `claude -p` 루프였다. 각 이터레이션이 이전을 기억하지 못하고, 좋은 결과와 나쁜 결과가 동등하게 취급되며, 생산만 있고 도태가 없었다. 이 시스템은 그 세 가지 부재를 모두 해결한다.

---

## 핵심 비유

> 인간 학계 2000년이 학술지, 학회, 동료 심사, 저자 명성을 통해 구현한 것을,
> **while 루프 하나 + SQLite DB 하나 + LLM 판사 하나**로 구현한다.

---

## ASCII 아키텍처 다이어그램

```
┌──────────────────────────────────────────────────────────────┐
│                    while True 메인 루프                       │
│                  (autoresearch_v2.py)                        │
│                                                              │
│  ┌─────────────┐   ┌─────────────┐   ┌──────────────────┐   │
│  │  Research   │──▶│   Compare   │──▶│    Reflector     │   │
│  │   Agent     │   │   Agent     │   │    Agent         │   │
│  │ (sonnet-4-6)│   │ (haiku-4-5) │   │  (haiku-4-5)     │   │
│  │             │   │             │   │                  │   │
│  │ WebSearch   │   │ 분류+판정   │   │ annotation 추출  │   │
│  │ WebFetch    │   │ position    │   │ (LLM 역할 끝)    │   │
│  │ 최대 15턴   │   │ bias 제거   │   │                  │   │
│  └──────┬──────┘   └──────┬──────┘   └────────┬─────────┘   │
│         │                 │                   │             │
│         ▼                 ▼                   ▼             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                SQLite (knowledge.db)                 │   │
│  │   papers │ comparisons │ annotations │ audit_chain   │   │
│  │          │    edges (Phase 2 예정)                    │   │
│  └──────────────────────────────────────────────────────┘   │
│         │                 │                   │             │
│         ▼                 ▼                   ▼             │
│  ┌─────────────┐   ┌─────────────┐   ┌──────────────────┐   │
│  │  PageRank   │   │  MAP-Elites │   │    Lifecycle     │   │
│  │  Fitness    │   │  Diversity  │   │    States        │   │
│  │ (fitness.py)│   │ (fitness.py)│   │  (fitness.py)    │   │
│  └─────────────┘   └─────────────┘   └──────────────────┘   │
│                                                              │
│  ▲ 진화 엔진 3종 — 순수 Python, LLM 호출 없음              │
└──────────────────────────────────────────────────────────────┘
```

### 구성 요소 요약

| 구성 요소 | 파일 | 역할 |
|-----------|------|------|
| 메인 루프 | `autoresearch_v2.py` | 5단계 사이클 조율, Trial ID 추적, SIGINT 우아한 종료, research_question 전파 |
| Research Agent | `agents/research_agent.py` | WebSearch+WebFetch로 실증거 수집, 논문 생성 |
| Compare Agent | `agents/compare_agent.py` | claim 분류, pairwise 판정, position bias 제거 |
| Reflector Agent | `agents/reflector_agent.py` | 비교 결과에서 annotation 1~3개 추출 |
| 메모리 시스템 | `core/memory.py` | L0/L1/L2 계층 로딩, annotation 주입, SHA-256 ID |
| 진화 엔진 | `core/fitness.py` | PageRank fitness, MAP-Elites, lifecycle 상태 전환 |
| DB 초기화 | `core/__init__.py` | WAL 모드, foreign keys, busy_timeout 설정 |
| 스키마 | `core/schema.sql` | 5개 테이블 + 인덱스 + audit_chain 불변 트리거 |

---

## 데이터 흐름: 사이클 5단계

### Phase 1 — 컨텍스트 구성

```
annotations 테이블 (최근 5개)
        ↓ 프롬프트 앞에 주입 (Context Hub 패턴)
papers 테이블 전체 L0 스캔 (claim 100자 + l0_summary 50토큰)
        ↓ 상위 fitness 3개 + 랜덤 2개 선택
선택된 논문들 L1 로드 (~2000토큰/편, 토큰 예산 4000 내)
        ↓
build_session_context() → context 문자열 반환
```

`core/memory.py:build_session_context()`

### Phase 2 — 논문 생성

```
champion = get_champion(conn, topic)
is_rebuttal = random() < 0.3 and bool(champion)
        ↓ 70%: 지식 공백 탐색 논문 (research_question 기반)
        ↓ 30%: 챔피언 주장에 반박하는 논문 (라카토슈: 새 예측 강제, 챔피언 존재 시만)

research_agent → WebSearch (최소 3회) → WebFetch (유망 소스)
        ↓ research_question을 North Star로 사용
JSON 출력: claim, l0_summary, l1_summary, l2_content,
           evidence_sources, assumptions, topic_tag, perspective
        ↓
save_paper() → SHA-256(claim + l1_summary)[:16] → papers 테이블 기록
```

`agents/research_agent.py:run_research()`

### Phase 3 — 비교 판정

```
select_rival() → 70% 챔피언, 30% 랜덤 active 논문
        ↓
claim 분류: opposing / complementary / orthogonal (research_question 맥락)
        ↓ orthogonal → 비교 없이 공존
        ↓ complementary → 상호 보강 (둘 다 comparisons에 기록)
        ↓ opposing →
            A→B 판정 (forward) → (winner, reasoning)
            B→A 판정 (reverse) → (winner, reasoning)
            ↓ 만장일치인 경우만
comparisons(winner, loser, created_at) 테이블에 단 1개 행 삽입
반환: (winner_id, loser_id, reasoning) 3-tuple
```

`agents/compare_agent.py:run_comparison()`

### Phase 4 — 반성 (annotation 추출)

```
비교 결과 (winner_id, loser_id, reasoning) + 새 논문 + 컨텍스트 + research_question
        ↓ reflector_agent (LLM, haiku)
        ↓ judge의 reasoning을 함께 수신하여 증거 기반 반성 수행
annotation 2~4개: [{content, tags, suggested_search}]
        ↓
save_annotation() → annotations 테이블에 기록
        (다음 사이클 Phase 1에서 자동 주입됨)
```

`agents/reflector_agent.py:run_reflection()`

### Phase 5 — 결정론적 상태 갱신

```
calculate_fitness()        comparisons 그래프 → PageRank → papers.fitness 갱신
update_lifecycle_states()  fitness > 0.7 + 5승 → foundational
                           최근 5회 중 3패 → contested
update_map_elites()        (topic_tag, perspective) 셀별 상위 3개 보존
                           4위 이하 → archived (삭제 아님)
```

`core/fitness.py` — LLM 호출 없음, 순수 Python + networkx

---

## 구성 요소 간 관계

```
autoresearch_v2.py (조율자)
├── core/__init__.py          init_db() 호출 → conn 생성 (세션 전체 단일 연결)
├── core/memory.py            build_session_context(), save_paper(), save_annotation()
├── core/fitness.py           calculate_fitness(), update_lifecycle_states(), update_map_elites()
├── agents/research_agent.py  run_research() — conn + context + research_question 수신, paper dict 반환
├── agents/compare_agent.py   run_comparison() — conn + 두 paper dict + research_question 수신, (winner, loser, reasoning) 반환
└── agents/reflector_agent.py run_reflection() — conn + comparison 결과(3-tuple) + research_question 수신

agents/_sdk.py (공유 설정 + 품질 훅)
├── OMC_OPTS                  research_agent에만 적용 (WebSearch 도구 사용)
└── Stop Hooks                3개 품질 강제 훅 (Mini-Ralph 패턴)
                              enforce_research_quality, enforce_comparison_quality, enforce_reflection_quality
```

### 의존 방향

- 에이전트들은 `core/memory.py`를 직접 호출한다 (`save_paper`).
- `core/fitness.py`는 에이전트를 호출하지 않는다. 순수한 DB 읽기/쓰기.
- `autoresearch_v2.py`만이 에이전트와 core를 함께 조율한다.

---

## 동기/비동기 경계

| 영역 | 방식 | 이유 |
|------|------|------|
| LLM 호출 (research/compare/reflect) | `async`/`await` | Claude Agent SDK의 `query()`가 async generator |
| DB 연산 (sqlite3) | 동기 (sync) | `sqlite3` 표준 라이브러리는 동기. Phase 5 상태 갱신 중 `await` 금지 |
| 메인 루프 | `asyncio.run()` | `research_loop()`는 `async def`, `asyncio.run()`으로 진입 |
| 사이클 간 대기 | `await asyncio.sleep(5)` | 블로킹 없이 5초 대기 |
| 오류 시 backoff | `await asyncio.sleep(30)` | 사이클 오류 후 30초 대기 |

핵심 제약: Phase 5의 `calculate_fitness()`, `update_lifecycle_states()`, `update_map_elites()`는 내부에 `conn.execute()`와 `conn.commit()`을 사용한다. 이 함수들 사이에 `await`를 삽입하면 안 된다. 코드 주석에 명시되어 있다.

```python
# NOTE: Never place an await between conn.execute() and conn.commit()
calculate_fitness(conn, topic)
update_lifecycle_states(conn, topic)
update_map_elites(conn, topic)
```
