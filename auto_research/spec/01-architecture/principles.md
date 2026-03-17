# 3대 설계 원칙

전략 보고서(`docs/260317_final-strategy-report.md`)는 7개 오픈소스 에이전트 프레임워크 분석을 통해 성공적인 에이전트 지식 시스템이 공통으로 갖는 3가지 원칙을 도출했다. 이 원칙들은 v2의 모든 설계 결정의 근거다.

---

## ① 평가압력 (Selection Pressure)

### 원칙

생성된 지식이 비교 경쟁에서 도태되는 메커니즘. 판단 기준은 "좋은가/나쁜가"가 아니라 "지금 이 셀에서 상대보다 나은가"로 충분하다.

기존 `ralph.sh`의 근본 결함은 평가 없음이었다. 좋은 결과와 나쁜 결과가 동등하게 취급됐다. `results.tsv`는 선형 로그일 뿐이었고, 에이전트는 "지금 무엇을 알고 있는가"가 아니라 "지금까지 무엇을 했는가"만 볼 수 있었다.

### 구현: comparisons 테이블

```sql
CREATE TABLE comparisons (
    winner      TEXT REFERENCES papers(id),
    loser       TEXT REFERENCES papers(id),
    created_at  TEXT
);
-- 3컬럼이 전부. agent_id, judge_score, rubric 없음.
```

"누가 평가했나"는 의미 없다. 결과 사실만 기록한다. fitness는 이 테이블에서 파생된다.

### 구현: Pairwise LLM-as-Judge

**판단 기준 (4단계 우선순위)**:

```
opposing인 경우 (우선순위 순서):
  1. RELEVANCE: research question에 더 직접적으로 답하는 논문이 우선
  2. EVIDENCE QUALITY: 근거의 질 (peer-reviewed > technical report > blog)
  3. FALSIFIABILITY: 반증 가능한 구체적 assumptions을 가진 논문이 우선
     (vague assumptions에 PENALTY 적용)
  4. LAKATOS PROGRESSIVENESS: 새 예측을 제시하는 논문이 우선

complementary인 경우:
  경쟁 없이 양쪽 모두 승리 기록 (상호 보강)
```

**claim 분류 선행**:

```
opposing     → 서로 모순. pairwise 대결.
complementary → 같은 결론, 다른 근거. 상호 보강 (둘 다 fitness 상승).
orthogonal   → 무관. 비교 없이 공존.
```

`agents/compare_agent.py:_classify_claims()` — claude-haiku-4-5, max_turns=1, chain-of-thought + research_question 맥락

### 구현: Position Bias 제거

LLM 판사는 먼저 제시된 쪽을 선호하는 위치 편향(position bias)을 갖는다. 제거 방법:

```
1회차: A를 첫 번째로 제시 → 판정 결과 r1
2회차: B를 첫 번째로 제시 → 판정 결과 r2
만장일치(r1 == r2)인 경우만 comparisons 테이블에 기록
불일치 → 기록 없음 (해당 비교는 없던 것으로)
```

`agents/compare_agent.py:run_comparison()` — forward/reverse 두 번 호출

### 구현: PageRank Fitness

comparisons 그래프에서 `loser → winner` 방향의 유향 그래프를 구성한다.

```python
# core/fitness.py:calculate_fitness()
G = nx.DiGraph()
for comp in comparisons:
    G.add_edge(comp["loser"], comp["winner"])  # 패자가 승자에게 투표
pr = nx.pagerank(G, alpha=0.85, max_iter=100)
```

단순 승률(wins/total)은 모든 승리를 동등하게 취급한다. PageRank는 강한 상대를 이겼을 때 더 높은 점수를 부여한다. 학계 인용 분석과 같은 원리다: 중요한 논문에게 인용될수록 중요해진다.

수렴 실패(`PowerIterationFailedConvergence`) 시 단순 win ratio로 자동 폴백한다.

**코드 위치 매핑**:

| 기능 | 파일 | 함수 |
|------|------|------|
| claim 분류 | `agents/compare_agent.py` | `_classify_claims()` |
| pairwise 판정 | `agents/compare_agent.py` | `_judge()` |
| position bias 제거 | `agents/compare_agent.py` | `run_comparison()` |
| PageRank 계산 | `core/fitness.py` | `calculate_fitness()` |
| rival 선택 | `core/fitness.py` | `select_rival()` |
| champion 조회 | `core/fitness.py` | `get_champion()` |

---

## ② 다양성 보존 (Diversity Maintenance)

### 원칙

MAP-Elites 원리: `topic × perspective` 2차원 격자에서 각 셀에 최소 1개 생존자를 보장한다. 전역 순위에서 지더라도, 자신의 셀에서 이기면 살아남는다.

전역 경쟁만 허용하면 시스템은 빠르게 단일 지배적 내러티브로 수렴한다. critical 관점이나 theoretical 관점처럼 empirical 증거가 적은 논문들은 자동으로 도태된다. 이는 학계에서 소수설이 사라지는 것과 같은 문제다.

### 구현: MAP-Elites 격자

격자 차원:

- **행**: `topic_tag` (예: `agentic_memory`, `llm_performance`)
- **열**: `perspective` (4종: `empirical`, `theoretical`, `applied`, `critical`)

```
셀 (agentic_memory, empirical)   → 상위 3개 보존
셀 (agentic_memory, theoretical) → 상위 3개 보존
셀 (agentic_memory, applied)     → 상위 3개 보존
셀 (agentic_memory, critical)    → 상위 3개 보존
```

각 셀에서 4위 이하 논문은 `archived` 상태로 전환된다. **삭제가 아니다.** `audit_chain`에 기록되고, 이론적으로 `revived` 상태로 복원 가능하다.

```python
# core/fitness.py:update_map_elites()
if len(cell_papers) > 3:
    for paper in cell_papers[3:]:
        if paper["status"] in ("active", "contested"):
            conn.execute("UPDATE papers SET status = 'archived' WHERE id = ?", (paper["id"],))
            _log_audit(conn, paper["id"], "archived", paper["status"], "archived", now)
```

### 구현: 셀 내 경쟁

비교 판정은 전역 경쟁이 아니다. rival 선택 시 같은 `topic_tag`에서 선택하고, lifecycle 상태 전환도 같은 topic 내에서만 계산한다.

```python
# core/fitness.py:select_rival()
if random.random() < 0.7:
    rival = get_champion(conn, topic)   # 70%: 챔피언 도전
else:
    # 랜덤 active 논문 (30%: SGD-inspired 탐색)
    papers = conn.execute(
        "SELECT * FROM papers WHERE topic_tag = ? AND status IN ('active', 'contested', 'foundational') ORDER BY RANDOM() LIMIT 1",
        (topic,),
    ).fetchone()
```

30% 랜덤 선택은 SGD(확률적 경사 하강법)의 미니배치 랜덤성과 같은 역할을 한다. 챔피언 과적합을 방지하고 local minima 탈출을 돕는다.

### 구현: 소수설 보호 (30% 반박 논문)

매 사이클 30% 확률로 챔피언 주장에 반박하는 논문을 생성한다. 단순한 "동의하지 않음"은 허용되지 않는다. 챔피언의 주장이 좁은 조건에서만 성립함을 보이거나 모순 증거를 찾아야 한다.

```python
# autoresearch_v2.py:research_loop()
is_rebuttal = random.random() < 0.3
```

라카토슈 기준: 반박 논문이 "새로운 예측을 제시하는가(진보적)" 아니면 "예외만 덧붙이는가(퇴행적)"를 judge 프롬프트에서 평가한다.

**코드 위치 매핑**:

| 기능 | 파일 | 함수/위치 |
|------|------|-----------|
| MAP-Elites 셀 갱신 | `core/fitness.py` | `update_map_elites()` |
| 반박 논문 생성 | `agents/research_agent.py` | `REBUTTAL_ADDITION` 프롬프트, `run_research()` |
| perspective 유효성 검사 | `agents/research_agent.py` | `_parse_paper_json()` |
| 랜덤 rival 선택 | `core/fitness.py` | `select_rival()` |
| lifecycle 전환 | `core/fitness.py` | `update_lifecycle_states()` |

---

## ③ 상태 명시성 (Explicit State)

### 원칙

에이전트는 상태를 기억하지 못한다. 모든 지식의 현재 상태 (fitness, 관계, 나이) 는 외부 저장소에 명시적으로 기록되어야 한다.

LLM은 세션이 종료되면 아무것도 기억하지 못한다. 에이전트의 "메모리"는 환상이다. 진짜 지속성은 외부 저장소에서만 온다.

### 구현: SQLite + WAL

```python
# core/__init__.py:init_db()
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
conn.execute("PRAGMA journal_mode=wal")    # WAL 모드: 쓰기 중 읽기 가능
conn.execute("PRAGMA busy_timeout=5000")   # 쓰기 경합 시 5초 대기
conn.execute("PRAGMA foreign_keys=ON")     # 외래키 강제
```

WAL(Write-Ahead Logging) 모드는 단일 프로세스 에이전트 루프에서 유일하게 필요한 동시성 패턴을 제공한다: 쓰기 중에도 읽기가 가능하다. 외부 DB 서버가 필요 없다. 전체 지식 베이스는 단일 파일이다.

### 구현: SHA-256 결정론적 ID

```python
# core/memory.py:paper_id()
def paper_id(claim: str, l1_summary: str) -> str:
    content = claim + l1_summary
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
```

동일한 내용의 논문은 재시작 후에도 항상 같은 ID를 가진다. 세션 간 노드 재연결에 UUID 레지스트리가 필요 없다. 에이전트가 크래시 후 재시작하면 동일한 논문을 중복 생성하지 않고 기존 노드에 자동으로 연결된다. (Wrkr 패턴)

### 구현: audit_chain 불변성

```sql
-- core/schema.sql
CREATE TABLE audit_chain (
    id              TEXT PRIMARY KEY,
    paper_id        TEXT,
    event_type      TEXT,   -- first_seen|status_changed|evaluated|archived|revived
    previous_state  TEXT,
    new_state       TEXT,
    agent_id        TEXT,
    created_at      TEXT
);

CREATE TRIGGER prevent_audit_update
BEFORE UPDATE ON audit_chain
BEGIN
    SELECT RAISE(ABORT, 'audit_chain is append-only: updates are not allowed');
END;

CREATE TRIGGER prevent_audit_delete
BEFORE DELETE ON audit_chain
BEGIN
    SELECT RAISE(ABORT, 'audit_chain is append-only: deletes are not allowed');
END;
```

모든 상태 전환은 audit_chain에 기록된다. DB 레벨 트리거가 수정과 삭제를 차단한다. "이 논문이 왜 archived됐는가?"를 항상 추적할 수 있다. audit_chain이 시스템의 ground truth다.

모든 상태 전환을 기록하는 코드:

```python
# core/fitness.py:_log_audit()
conn.execute(
    """INSERT INTO audit_chain
       (id, paper_id, event_type, previous_state, new_state, agent_id, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)""",
    (audit_id, paper_id, event_type, previous_state, new_state, agent_id, created_at),
)
```

### 구현: L0/L1/L2 계층 메모리 (OpenViking 패턴)

상태 명시성의 메모리 측면: 에이전트에게 주입하는 컨텍스트의 양을 결정론적으로 제어한다.

| 레벨 | 크기 | 용도 | 로딩 시점 |
|------|------|------|-----------|
| L0 | ~50 토큰 | 관련성 필터 | 항상, 전체 스캔 |
| L1 | ~2000 토큰 | 추론 컨텍스트 | 상위 3개 + 랜덤 2개만 |
| L2 | 전문 | 깊은 분석 | on-demand (현재 미구현) |

수백 개의 논문이 축적되어도 세션 컨텍스트는 토큰 예산(기본 4000) 내에서 작동한다.

```python
# core/memory.py:build_session_context()
all_papers = conn.execute(
    "SELECT id, claim, l0_summary, fitness, status, perspective FROM papers "
    "WHERE topic_tag = ? AND status != 'archived' ORDER BY fitness DESC",
    (topic,),
).fetchall()

top_papers = all_papers[:3]            # 상위 fitness 3개
random_picks = random.sample(remaining, min(2, len(remaining)))  # 랜덤 2개
```

### 구현: Context Hub (세션 간 연속성)

```python
# core/memory.py:build_session_context()
annotations = conn.execute(
    """SELECT a.content, a.tags, a.created_at, p.claim
       FROM annotations a JOIN papers p ON a.paper_id = p.id
       WHERE p.topic_tag = ? ORDER BY a.created_at DESC LIMIT 5""",
    (topic,),
).fetchall()
```

세션이 종료돼도 발견은 사라지지 않는다. 다음 세션 시작 시 최근 5개 annotation이 프롬프트 앞에 자동 주입된다. (Andrew Ng의 Context Hub 패턴)

**코드 위치 매핑**:

| 기능 | 파일 | 함수 |
|------|------|------|
| DB 초기화 + WAL | `core/__init__.py` | `init_db()` |
| SHA-256 ID 생성 | `core/memory.py` | `paper_id()` |
| 논문 저장 (Popper 게이트 포함) | `core/memory.py` | `save_paper()` |
| L0/L1 계층 로딩 | `core/memory.py` | `build_session_context()` |
| annotation 저장 | `core/memory.py` | `save_annotation()` |
| audit 기록 | `core/fitness.py` | `_log_audit()` |
| audit 불변 트리거 | `core/schema.sql` | `prevent_audit_update`, `prevent_audit_delete` |

---

## 과학철학 3종 조합

3원칙은 3가지 과학철학과 대응한다. 이 조합은 전략 보고서에서 "완전한 평가 파이프라인"으로 정의됐다.

| 단계 | 역할 | 철학 | 구현 위치 |
|------|------|------|-----------|
| 진입 필터 | 게이트키퍼 | **포퍼**: 반증 불가능한 주장은 과학이 아니다 | `core/memory.py:save_paper()` — `assumptions` 필드 미약 시 경고 |
| 신뢰도 갱신 | 주 엔진 | **베이즈**: 새 증거가 나올 때마다 신뢰도를 갱신하라 | `core/fitness.py:calculate_fitness()` — comparisons → PageRank |
| 진보/퇴행 판단 | 평가 기준 | **라카토슈**: 새 예측을 제시하는 프로그램이 단순 땜질보다 낫다 | `agents/compare_agent.py` — `JUDGE_OPPOSING_PROMPT`의 라카토슈 기준 |

### 포퍼 게이트 (진입 필터)

```python
# core/memory.py:save_paper()
assumptions = paper.get("assumptions", "")
if not assumptions or assumptions in ("None stated", "This is a placeholder paper."):
    logger.warning(f"Popper gate: paper '{paper['claim'][:60]}' has weak/missing assumptions")
```

현재는 경고만 발행하고 저장은 허용한다. 강제 차단은 Phase 2 이후 검토 예정.

### 베이즈 엔진 (fitness 갱신)

새 비교 결과가 나올 때마다 `calculate_fitness()`가 전체 comparisons 그래프를 PageRank로 재계산한다. "이전에 강했던 논문을 이기면 더 많이 올라간다"는 베이즈적 증거 누적과 같다.

### 라카토슈 기준 (judge 프롬프트)

```python
# agents/compare_agent.py:JUDGE_OPPOSING_PROMPT
"""Apply the Lakatos criterion: a claim that makes NEW predictions (progressive)
is better than one that merely patches exceptions (degenerative)."""
```

반박 논문 생성 시에도 라카토슈 기준을 강제한다. 단순 반박의 안티패턴을 구체적으로 열거한다:

```python
# agents/research_agent.py:REBUTTAL_ADDITION
"""(Lakatos criterion: your rebuttal must be a PROGRESSIVE research program
that makes NEW testable predictions the champion cannot make)

ANTI-PATTERNS TO AVOID:
- "The champion is wrong because [one exception]" — this is a DEGENERATIVE patch
- "More research is needed" — this is not a claim
- Repeating the champion's framework with minor modifications"""
```
