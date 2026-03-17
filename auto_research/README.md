# Auto Research Ecosystem v2

**지식이 축적되고 경쟁하고 진화하는 자율 연구 생태계.**

---

## 1. 개요

### 이 프로젝트는 무엇인가

LLM이 생성한 연구 논문들이 pairwise 비교 경쟁을 통해 자연선택되고, 장기 기억과 함께 세션을 넘어 지속적으로 진화하는 자율 연구 루프다.

### 핵심 설계 철학

> **"에이전트가 좋은 논문을 쓰도록 하는 것이 아니라, 나쁜 논문이 자연스럽게 도태되는 생태계를 설계하는 것."**

AlphaGo가 "이기면 좋다"만 정의하고 전략은 스스로 찾았듯, 이 시스템은 "살아남으면 좋다"만 정의한다. 좋은 지식을 생산하는 방법은 에이전트가 발견한다.

### 기존 autoresearch의 한계

기존 `ralph.sh` 방식은 단순한 `while true` + `claude -p` 루프다:

```
while true:
  claude -p "$(cat program.md)" → 단일 에이전트 → 결과
  sleep 5
```

이 방식의 근본 문제:

| 문제 | 설명 |
|---|---|
| **학습 없음** | 각 이터레이션이 이전 이터레이션을 기억하지 못한다 |
| **평가 없음** | 좋은 결과와 나쁜 결과가 동등하게 취급된다 |
| **진화 없음** | 생산만 있고 도태와 선택이 없다 |

`results.tsv`는 선형 로그일 뿐이다. 에이전트는 "지금 무엇을 알고 있는가"가 아니라 "지금까지 무엇을 했는가"만 볼 수 있다.

### 이 시스템이 해결하는 것

| 해결책 | 구현 |
|---|---|
| **장기기억** | L0/L1/L2 계층화 + SHA-256 ID + annotations 테이블 |
| **평가압** | `comparisons(winner, loser)` 테이블 — pairwise LLM 판단이 자연선택압이 된다 |
| **진화** | MAP-Elites 다양성 + PageRank 중요도 + archived 상태 |

### 3원칙

**① 평가압력 (Selection Pressure)**
생성된 지식이 비교 경쟁에서 도태되는 메커니즘. "좋은가/나쁜가"가 아니라 "지금 이 셀에서 상대보다 나은가"로 충분하다.

**② 다양성 보존 (Diversity Maintenance)**
MAP-Elites 원리: `topic × perspective` 2차원 격자에서 각 셀에 최소 1개 생존자 보장. 전역 순위에서 지더라도, 자신의 셀에서 이기면 살아남는다.

**③ 상태 명시성 (Explicit State)**
에이전트는 상태를 기억하지 못한다. 모든 지식의 현재 상태(fitness, 관계, 나이)는 외부 저장소에 명시적으로 기록된다.

### 핵심 비유

> 인간 학계 2000년이 학술지, 학회, 동료 심사, 저자 명성을 통해 구현한 것을,
> **while 루프 하나 + SQLite DB 하나 + LLM 판사 하나**로 구현한다.

### 아키텍처 다이어그램

```
┌─────────────────────────────────────────────────┐
│              while True 메인 루프                 │
│                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │
│  │ Research  │→│ Compare  │→│  Reflector    │   │
│  │ Agent    │  │ Agent    │  │  (LLM)       │   │
│  │ (sonnet) │  │ (haiku)  │  │  (haiku)     │   │
│  └────┬─────┘  └────┬─────┘  └──────┬───────┘   │
│       │              │               │           │
│       ▼              ▼               ▼           │
│  ┌─────────────────────────────────────────┐     │
│  │         SQLite (knowledge.db)           │     │
│  │  papers | comparisons | annotations     │     │
│  │  edges  | audit_chain                   │     │
│  └─────────────────────────────────────────┘     │
│       │              │               │           │
│       ▼              ▼               ▼           │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │
│  │ PageRank │  │MAP-Elites│  │  Lifecycle   │   │
│  │ Fitness  │  │ Diversity│  │  States      │   │
│  └──────────┘  └──────────┘  └──────────────┘   │
└─────────────────────────────────────────────────┘
```

---

## 2. 퀵스타트

### Prerequisites

- Python 3.9+
- Anthropic API 키

### 설치

```bash
# 저장소 클론
git clone <repo-url>
cd auto_research

# 의존성 설치
pip install -r requirements.txt
```

### API 키 설정

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

### 방법 A: 시드 데이터로 빠르게 시작 (권장)

`agentic_memory` 주제에 대한 논문 10편이 미리 준비되어 있다. LLM 호출 없이 즉시 데이터베이스를 초기화한다.

```bash
python auto_research/seed_data.py --db auto_research/db/knowledge.db --topic agentic_memory
```

출력 예시:

```
Seeding 10 papers for topic 'agentic_memory'...
  [1/10] a3f8b2c1d4e5f6a7: L0/L1/L2 hierarchical memory loading reduces token costs by 91%...
  [2/10] b1c2d3e4f5a6b7c8: SHA-256 content-hash IDs enable deterministic cross-session...
  ...
Seeding complete: 10 papers in database.
```

### 방법 B: Cold Start (LLM 자동 생성)

시드 데이터 없이 시작하면 메인 루프가 자동으로 10편의 시드 논문을 LLM으로 생성한다 (API 비용 약 $0.30 추가 소요).

### 메인 루프 실행

```bash
python auto_research/autoresearch_v2.py --topic agentic_memory
```

#### CLI 옵션

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--topic` | `agentic_memory` | 연구 주제 태그. MAP-Elites 셀 주소로 사용된다 |
| `--db` | `db/knowledge.db` | SQLite 데이터베이스 경로 |

#### 실행 예시

```bash
# 기본값으로 실행
python auto_research/autoresearch_v2.py

# 다른 주제로 실행
python auto_research/autoresearch_v2.py --topic llm_performance

# 별도 DB 경로 지정
python auto_research/autoresearch_v2.py --topic agentic_memory --db /data/research.db
```

### 실행 후 기대 출력

```
14:32:01 [INFO] ============================================================
14:32:01 [INFO] Auto Research Ecosystem v2 — Starting
14:32:01 [INFO] Topic: agentic_memory
14:32:01 [INFO] Database: auto_research/db/knowledge.db
14:32:01 [INFO] ============================================================
14:32:01 [INFO] Session ID: a3f8b2c1d4e5
14:32:01 [INFO] Cold start skipped: 10 papers already exist for 'agentic_memory'
14:32:45 [INFO] === Cycle 1 Complete ===
14:32:45 [INFO]   Papers: 11 total (10 active, 0 archived)
14:32:45 [INFO]   Comparisons: 1 | Annotations: 2
14:32:45 [INFO]   Champion fitness: 0.823 — L0/L1/L2 hierarchical memory loading reduces...
14:32:45 [INFO]   Elapsed: 44.1s
```

### 중지 방법

`Ctrl+C`를 누르면 현재 사이클이 완료된 후 안전하게 종료된다. 진행 중인 작업은 DB에 이미 기록되어 있으므로 데이터 손실이 없다.

```
^C
14:45:12 [INFO] Shutdown signal received (signal 2). Finishing current cycle...
14:45:58 [INFO] Closing database connection...
14:45:58 [INFO] Auto Research Ecosystem v2 — Stopped
14:45:58 [INFO] Total cycles completed: 18
```

### 로그 확인

```bash
# 실시간 모니터링
tail -f auto_research/logs/research.log

# 최근 100줄
tail -100 auto_research/logs/research.log
```

- `logs/research.log`: DEBUG 레벨, 타임스탬프 포함 전체 로그
- 콘솔 출력: INFO 레벨, 간결한 사이클 요약

---

## 3. 자세한 원리

### 3.1 데이터 모델 (SQLite 스키마)

데이터베이스는 5개 테이블로 구성된다. 각 테이블은 명확한 단일 책임을 가진다.

#### 테이블 관계도

```
papers (노드)
  ├── comparisons (평가압력 — winner/loser 엣지)
  ├── annotations (세션 간 발견 메모)
  ├── audit_chain (불변 상태 이력)
  └── edges       (관계 그래프 — Phase 2 예정)
```

#### papers 테이블 — L0/L1/L2 계층화

```sql
CREATE TABLE papers (
    id              TEXT PRIMARY KEY,   -- SHA-256(claim + l1_summary)[:16]
    claim           TEXT NOT NULL,      -- 핵심 주장 한 문장
    l0_summary      TEXT,               -- ~50 토큰: 관련성 필터용
    l1_summary      TEXT,               -- ~2000 토큰: 계획·추론용
    l2_content      TEXT,               -- 전문: on-demand 로드
    evidence_sources TEXT,              -- JSON: [{title, url, citation_count, excerpt}]
    assumptions     TEXT,               -- 성립 조건 (포퍼 반증 가능성 게이트)
    fitness         REAL DEFAULT 0.5,   -- PageRank 기반 중요도
    status          TEXT DEFAULT 'active',  -- active|contested|foundational|archived
    topic_tag       TEXT,               -- MAP-Elites 셀 주소
    perspective     TEXT,               -- empirical|theoretical|applied|critical
    expires_at      TEXT,               -- TTL 기반 재검토 기준 시각
    created_at      TEXT,
    source_uri      TEXT                -- 검색 경로 감사 (OpenViking DRR 방식)
);
```

**L0/L1/L2 계층화 (OpenViking 패턴, 91% 토큰 절감)**

| 레벨 | 크기 | 용도 | 로딩 시점 |
|---|---|---|---|
| L0 | ~50 토큰 | 관련성 필터: "이 논문이 관련 있는가?" | 항상 (전체 스캔) |
| L1 | ~2000 토큰 | 추론 컨텍스트: "이 논문이 주장하는 바는?" | 관련성 0.7 이상인 경우만 |
| L2 | 전문 | 깊은 분석: "세부 증거와 논리는?" | on-demand |

수백 개의 논문이 축적되어도 세션 컨텍스트는 L0 스캔 후 상위 3개 + 랜덤 2개만 L1 로드한다. 나머지는 L0 요약(claim 100자 + 50토큰 요약)으로만 존재한다.

**결정론적 ID**: `SHA-256(claim + l1_summary)[:16]`

동일한 내용의 논문은 재시작 후에도 항상 같은 ID를 가진다. 세션 간 노드 재연결에 UUID 레지스트리가 필요 없다.

**Lifecycle 상태 전환**:

```
active → foundational  (fitness > 0.7 AND 5회 이상 승리)
active → contested     (최근 5회 비교 중 3회 이상 패배)
active/contested → archived  (MAP-Elites 셀 초과 시)
archived → revived     (audit_chain 기록 후 복원 가능)
```

#### comparisons 테이블 — 자연선택압의 핵심

```sql
CREATE TABLE comparisons (
    winner      TEXT REFERENCES papers(id),
    loser       TEXT REFERENCES papers(id),
    created_at  TEXT
);
-- 전부. agent_id, judge_score, rubric 없음.
```

3컬럼이 전부다. "누가 평가했나"는 의미 없다. 결과 사실만 기록한다. fitness는 이 테이블에서 PageRank로 파생된다:

```python
# loser → winner 방향 그래프에서 PageRank 계산
# "많이 반박받는 논문 = 중요한 논문"
G.add_edge(loser_id, winner_id)
pr = nx.pagerank(G, alpha=0.85)
```

#### edges 테이블 — 관계 그래프 (Phase 2에서 활성화)

```sql
CREATE TABLE edges (
    id          TEXT PRIMARY KEY,
    src         TEXT REFERENCES papers(id),
    dst         TEXT REFERENCES papers(id),
    relation    TEXT,   -- supports|contradicts|extends|derived_from|depend_on
    strength    REAL DEFAULT 1.0,
    created_at  TEXT,
    valid_until TEXT    -- NULL = 여전히 유효. 만료 시 삭제 대신 만료 처리.
);
```

Zep/Graphiti의 시간축 엣지 패턴을 따른다. "언제 반박됐는가"를 `valid_until` 필드로 추적한다. 현재는 테이블만 생성되어 있으며 Phase 2에서 채워진다.

#### annotations 테이블 — Context Hub 패턴

```sql
CREATE TABLE annotations (
    id          TEXT PRIMARY KEY,
    paper_id    TEXT REFERENCES papers(id),
    session_id  TEXT,
    content     TEXT NOT NULL,  -- "이 논문은 X 조건에서만 유효함"
    tags        TEXT,           -- JSON 배열
    created_at  TEXT
);
```

세션이 종료되어도 발견은 사라지지 않는다. 다음 세션 시작 시 최근 5개 annotation이 프롬프트 앞에 자동 주입된다 (Andrew Ng의 Context Hub 패턴). 에이전트의 개인 장기 메모리 역할을 한다.

annotation 태그 종류: `limitation`, `contradiction`, `confirmation`, `methodology`, `question`, `direction`, `condition`, `evidence_gap`

#### audit_chain 테이블 — Wrkr 패턴, 불변 감사 체인

```sql
CREATE TABLE audit_chain (
    id              TEXT PRIMARY KEY,
    paper_id        TEXT,
    event_type      TEXT,   -- first_seen|status_changed|evaluated|archived|revived
    previous_state  TEXT,
    new_state       TEXT,
    agent_id        TEXT,
    created_at      TEXT
);
```

SQLite `BEFORE UPDATE`와 `BEFORE DELETE` 트리거로 수정과 삭제가 데이터베이스 레벨에서 차단된다. "이 논문이 왜 archived됐는가?"를 항상 추적할 수 있다. 감사 체인 자체가 시스템의 ground truth다.

---

### 3.2 에이전트 구조

3개의 에이전트가 역할과 비용에 따라 분리된다.

#### research_agent (claude-sonnet-4-6)

**역할**: 새 논문 생성. 시스템에서 가장 비싼 에이전트.

**동작**:
1. 현재 세션 컨텍스트(상위 fitness 논문 L1 + 랜덤 2개 + 이전 세션 annotation)를 수신
2. 30% 확률로 챔피언 논문에 대한 반박 논문 생성 (라카토슈 진보: 새 예측 제시 강제)
3. 최소 증거 게이트: 3개 이상의 근거를 수집한 후에만 논문 작성
4. JSON 형식으로 출력: `claim`, `l0_summary`, `l1_summary`, `l2_content`, `evidence_sources`, `assumptions`, `perspective`

**반박 논문 (30% 확률)**:
챔피언의 주장에 모순되는 증거를 찾거나, 그 주장이 좁은 조건에서만 성립함을 보여야 한다. 단순한 "동의하지 않음"은 허용되지 않는다.

#### compare_agent (claude-haiku-4-5)

**역할**: Pairwise LLM-as-Judge. 반복이 많아 비용이 낮은 모델을 사용한다.

**동작**:
1. claim 분류: `opposing` / `complementary` / `orthogonal` 중 하나로 분류
2. `orthogonal`이면 비교 없이 공존 (두 논문 모두 fitness 변화 없음)
3. `opposing`이면 "어느 주장이 증거에 의해 더 잘 지지되는가?" 판정
4. `complementary`이면 "어느 쪽 근거가 더 강한가?" 판정
5. **Position bias 제거**: A→B 순서로 1회, B→A 순서로 1회 판정. 두 번 모두 같은 승자를 지목한 경우만 `comparisons` 테이블에 기록

**라카토슈 평가 기준**: 새 예측으로 응답한 쪽(진보적 연구 프로그램)을 단순 예외 처리(퇴행적 연구 프로그램)보다 높이 평가한다.

#### reflector_agent (claude-haiku-4-5)

**역할**: annotation 추출만 담당. 결정론적 작업은 Python에서 처리한다.

**중요**: 이 에이전트는 fitness 계산, lifecycle 전환, MAP-Elites 갱신을 하지 않는다. 그 작업들은 LLM 없이 Python의 `fitness.py`에서 결정론적으로 처리된다.

**출력**: 비교 결과에서 1~3개의 actionable 인사이트를 추출하여 `annotations` 테이블에 저장.

예시 annotation:
```
[limitation] 이 논문의 주장은 단일 프로세스 환경에서만 검증되었으며
             분산 시스템에서의 유효성은 불확실하다. (re: SQLite WAL mode...)
```

#### 과학철학 3종 조합

| 역할 | 철학 | 구현 위치 |
|---|---|---|
| 게이트키퍼 (진입 필터) | **포퍼**: 반증 불가능 주장 제외 | `assumptions` 필드 필수 |
| 주 엔진 (신뢰도 갱신) | **베이즈**: evidence 기반 fitness 업데이트 | comparisons → PageRank |
| 평가 기준 (진보/퇴행) | **라카토슈**: 새 예측 vs 땜질 | judge 프롬프트 보너스 |

---

### 3.3 진화 메커니즘

#### PageRank 기반 Fitness

comparisons 그래프에서 `loser → winner` 방향의 유향 그래프를 구성한다.

```
논문 A가 B를 이겼다 → B에서 A로 엣지 추가
논문 A가 C를 이겼다 → C에서 A로 엣지 추가
논문 D가 A를 이겼다 → A에서 D로 엣지 추가
```

PageRank 결과: "많은 논문에게 반박받는 논문 = 중요한 논문"이 된다. 단순한 승률(wins/total)과 달리, 강한 상대를 이겼을 때 더 높은 점수를 받는다.

```python
pr = nx.pagerank(G, alpha=0.85, max_iter=100)
# PowerIterationFailedConvergence 시 win_ratio로 fallback
```

수렴 실패 시 단순 win ratio로 자동 폴백한다.

#### MAP-Elites — 다양성 보존

`topic_tag × perspective` 2차원 격자에서 셀 내 경쟁만 허용한다.

```
셀 (agentic_memory, empirical)   → 최강 3개 보존
셀 (agentic_memory, theoretical) → 최강 3개 보존
셀 (agentic_memory, applied)     → 최강 3개 보존
셀 (agentic_memory, critical)    → 최강 3개 보존
```

각 셀에서 4번째 이하 논문은 `archived` 상태로 전환된다 (삭제가 아님). 전역 순위에서 꼴찌인 `critical` 관점 논문도, 자신의 셀에서 최강이면 살아남는다.

#### Lifecycle 상태 전환

```python
# active → foundational: fitness > 0.7 AND 5회 이상 승리
# active → contested: 최근 5회 비교 중 3회 패배
# contested/active → archived: MAP-Elites 셀 초과 (상위 3개만 보존)
```

모든 전환은 `audit_chain`에 기록된다.

#### Rival 선택 — SGD-inspired 탐색

```python
if random.random() < 0.7:
    rival = get_champion(conn, topic)   # 70%: 챔피언 도전
else:
    rival = get_random_active(conn, topic)  # 30%: 랜덤 탐색
```

SGD(확률적 경사 하강법)에서 미니배치 랜덤성이 local minima 탈출을 돕듯, 30% 랜덤 선택이 챔피언 과적합을 방지한다.

---

### 3.4 메인 루프 사이클

`autoresearch_v2.py`의 `research_loop()`는 5단계로 구성된다.

#### 사이클 상세

**Phase 1: 세션 컨텍스트 구성**

```python
context = build_session_context(conn, topic, session_id)
```

1. `annotations` 테이블에서 최근 5개 annotation 로드 → 프롬프트 앞에 주입 (Context Hub)
2. 해당 topic의 비archived 논문 전체 L0 스캔 (빠른 관련성 필터)
3. 상위 fitness 3개 + 랜덤 2개만 L1 로드 (토큰 예산 내)
4. 토큰 예산(기본 4000 토큰) 초과 시 자동 차단

**Phase 2: 새 논문 생성**

```python
is_rebuttal = random.random() < 0.3
new_paper = run_research(conn, topic, session_id, context,
                         champion_claim=..., is_rebuttal=is_rebuttal)
```

- 70%: 일반 논문 생성 (현재 지식 공백 탐색)
- 30%: 챔피언 반박 논문 생성 (강한 주장에 도전)
- 생성 직후 `papers` 테이블에 저장 (write-back)

**Phase 3: Pairwise 비교**

```python
rival = select_rival(conn, topic)  # 70% 챔피언, 30% 랜덤
comparison = run_comparison(conn, new_paper, rival)
```

1. claim 분류 (opposing / complementary / orthogonal)
2. `orthogonal`이면 비교 없이 진행
3. A→B 판정, B→A 판정
4. 만장일치인 경우만 `comparisons` 테이블에 기록

**Phase 4: Annotation 추출**

```python
annotations = run_reflection(conn, session_id, topic, comparison, new_paper, context)
for ann in annotations:
    save_annotation(conn, new_paper["id"], session_id, ann["content"], ann["tags"])
```

LLM(reflector_agent)이 비교 결과에서 인사이트를 추출한다. 1~3개의 annotation을 생성한다.

**Phase 5: 결정론적 상태 갱신 (LLM 없음)**

```python
calculate_fitness(conn, topic)      # comparisons → PageRank → fitness 갱신
update_lifecycle_states(conn, topic) # active/contested/foundational 전환
update_map_elites(conn, topic)       # 셀별 초과 논문 archived 처리
```

이 단계는 순수 Python + networkx로 실행된다. LLM 호출 없음.

---

### 3.5 비용 추정

| 에이전트 | 모델 | 사이클당 호출 | 예상 비용 |
|---|---|---|---|
| research_agent | claude-sonnet-4-6 | 1회 | ~$0.030 |
| compare_agent (분류) | claude-haiku-4-5 | 1회 | ~$0.001 |
| compare_agent (판정) | claude-haiku-4-5 | 2회 | ~$0.003 |
| reflector_agent | claude-haiku-4-5 | 1회 | ~$0.002 |
| **합계** | | | **~$0.036/사이클** |

**일별 비용 예시**:
- 100 사이클/일 = **~$3.60/일**
- 50 사이클/일 = **~$1.80/일**
- 24시간 overnight 실행(사이클당 ~40초 기준) = 약 2,160 사이클 = **~$78/일**

> 비용은 논문 길이, 컨텍스트 크기에 따라 달라진다. `--topic` 주제당 L1 컨텍스트가 커질수록 research_agent 비용이 증가한다.

---

### 3.6 프로젝트 구조

```
auto_research/
├── autoresearch_v2.py      # 메인 루프 — research_loop() 진입점
├── seed_data.py            # 콜드 스타트용 시드 데이터 (10편, agentic_memory)
├── requirements.txt        # anthropic, networkx, numpy, scipy
│
├── core/
│   ├── __init__.py         # init_db() — DB 초기화 및 연결
│   ├── schema.sql          # 5개 테이블 정의 + 인덱스 + audit 트리거
│   ├── memory.py           # L0/L1/L2 로딩, annotation 저장/주입, 논문 저장
│   └── fitness.py          # PageRank fitness, MAP-Elites, lifecycle 상태 전환
│
├── agents/
│   ├── __init__.py
│   ├── research_agent.py   # 새 논문 생성 (sonnet-4-6, 30% 반박 논문)
│   ├── compare_agent.py    # Pairwise 비교 + position bias 제거 (haiku-4-5)
│   └── reflector_agent.py  # annotation 추출 전용 (haiku-4-5)
│
├── db/
│   └── knowledge.db        # SQLite DB (WAL 모드, git-ignored)
│
├── logs/
│   └── research.log        # DEBUG 레벨 전체 로그
│
├── tests/
│   └── test_integration.py # 통합 테스트
│
└── docs/
    ├── 260317_final-strategy-report.md   # 핵심 설계 결정 최종 정리
    ├── 260317_research-ecosystem-design.md
    ├── 260317_autoresearch-agent-sdk.md
    └── ...                               # 기타 연구 문서
```

---

### 3.7 미해결 이슈 (Phase 2+)

#### 구현 확정 필요

| 이슈 | 현재 상태 | 권장 접근 |
|---|---|---|
| **claim 분류 신뢰성** | "직교" 기본값으로 운영 중 | 샘플링하여 분류 정확도 측정 후 정제 |
| **topic_tag 자동 할당** | 수동 지정만 가능 | 초기 5~10개 고정, 이후 LLM 클러스터링 재조정 |
| **코드 실행 환경 격리** | 미구현 | 우선 ulimit + 타임아웃, Phase 3에서 Docker |
| **수렴 판단 기준** | fitness 분산 임계값 후보만 있음 | 수렴 감지 시 루프 중단 말고 알림만 발행 |
| **edges 테이블 활성화** | 테이블만 생성, 데이터 없음 | Phase 2에서 compare_agent 결과로 채우기 |
| **Cross-Field Pollination** | 설계 아이디어만 있음 | 매 N 사이클마다 다른 topic 논문 1개 삽입 |

#### 수용된 철학적 한계

- **규범적 질문 (Q2형)**: 순수 철학적 질문은 이 시스템의 범위 밖. pairwise 비교가 "더 정교하게 들리는 쪽"을 선택하는 경향이 있다.
- **진리 vs 합리성**: 이 시스템은 "진리"가 아닌 "현재 증거 기준으로 가장 반박하기 어려운 가설"을 찾는다. 시스템 출력물에는 항상 이 한계가 명시되어야 한다.
- **LLM 평가 편향**: Position bias는 양방향 판정으로 제거하지만, LLM이 특정 문체를 선호하는 편향은 완전히 제거 불가능하다.

---

### 3.8 기술 스택

#### 선택한 것

| 기술 | 버전 | 역할 |
|---|---|---|
| Python | 3.9+ | 메인 루프, 결정론적 상태 갱신 |
| anthropic SDK | >=0.85.0 | LLM 호출 (research/compare/reflect) |
| networkx | >=3.0 | PageRank 계산 (5줄) |
| SQLite + WAL | Python 내장 | 지식 저장소, 의존성 0 |
| numpy / scipy | >=2.0 / >=1.13 | networkx 의존 라이브러리 |
| hashlib | Python 내장 | SHA-256 결정론적 ID |

#### 선택하지 않은 것

| 기술 | 이유 |
|---|---|
| FAISS / sqlite-vss (벡터 임베딩) | L0 요약 + LLM 필터링이 더 정확하다는 현장 검증 |
| Neo4j / ArangoDB | SQLite WAL로 충분. 외부 DB 서버 의존성 불필요 |
| CrewAI / AutoGen | 오버헤드 높음, 루프 제어 약함 |
| LangGraph | Claude Agent SDK가 claude 환경에 더 통합적 |

---

## 부록: 핵심 설계 결정 요약

| 결정 | 초기 혼동 | 최종 결론 |
|---|---|---|
| 그래프 DB 역할 | 검색 + 관계 동시 | 관계 기록만. 검색은 SQL + LLM |
| 임베딩 | FAISS 필수 | 불필요. L0 + LLM이 더 정확 |
| 평가 테이블 | agent_id, rubric, score | winner, loser, created_at (3컬럼 전부) |
| 피어리뷰/반박 구분 | 별도 처리 | 동일 인프라, 프롬프트만 다름 |
| claim 분류 | 복잡한 온톨로지 | 대립/보완/직교 3분류 |
| 평가 rubric | 6개 축 | "근거가 결론을 지지하는가?" (AlphaGo 원리) |
| 소스 신뢰도 | URL 기반 점수 | citation_count + 원문 발췌, judge가 판단 |
| 메모리 로딩 | 전체 로딩 | L0 → L1 → L2 계층화 (91% 토큰 절감) |
| 에이전트 ID | UUID | SHA-256(content) (세션 간 재연결) |
| 실행 기반 | claude -p | Claude Agent SDK (스킬/서브에이전트 필요) |

---

*전략 설계 기반 문서: `docs/260317_final-strategy-report.md`*
