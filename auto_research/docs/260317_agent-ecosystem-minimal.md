# 오컴의 면도날 에이전트 지식 생태계
## 단순화 설계 + 그래프 메모리 조사 보고서

**작성일**: 2026-03-17
**대상**: 에이전트 자율 연구 시스템 설계자
**전제**: 기존 `docs/260317_agent-science-community.md`에서 설계한 액터/크리틱 시스템을 단순화

---

## 개요

인간 학계 2000년의 노하우를 에이전트 환경에 그대로 이식할 필요는 없다. 오컴의 면도날(Occam's Razor)은 동일한 현상을 설명하는 두 이론이 있을 때, 더 단순한 것을 선택하라고 말한다. 이 보고서는 세 가지 질문에 답한다:

1. **무엇을 버릴 것인가**: 인간 학계에서 에이전트 환경에 불필요한 요소
2. **무엇을 지킬 것인가**: 최소 필요 조건 ≤3개
3. **어떻게 기억할 것인가**: 선형 TSV를 대체하는 그래프 메모리 아키텍처

각 판단은 혼자 내리지 않았다. 아래 4개 카테고리에서 11개 이상의 논문과 블로그를 조사했다.

---

## 1부. 선행 연구 조사 (US-001)

### 1.1 에이전트 메모리 아키텍처 (5개 연구)

#### MemGPT / Letta (Park et al., 2023 · arXiv:2310.08560)
OS의 가상 메모리 개념을 LLM에 적용한 계층적 3단계 메모리 시스템이다.
- **Core Memory**: 컨텍스트 창 내 RAM 역할, 에이전트가 직접 편집 가능
- **Recall Memory**: 전체 대화 히스토리, 자동 디스크 저장 후 검색
- **Archival Memory**: 벡터/그래프 DB 기반 외부 장기 저장소

*적용 인사이트*: 에이전트가 "이 보고서가 기존 보고서 X의 주장을 지지/반박한다"는 메타 노트를 Core Memory에 직접 기록하도록 설계하면, 관계 추적의 명시적 레이어를 만들 수 있다.

#### A-MEM / Agentic Memory (Xu et al., 2025 · arXiv:2502.12110, NeurIPS 2025)
Zettelkasten 노트 방법론을 LLM 메모리에 적용한 시스템. 핵심 혁신은 **양방향 메모리 진화(bidirectional memory evolution)**로, 새 메모리가 유입될 때 기존 메모리의 컨텍스트 표현도 함께 업데이트된다.

*적용 인사이트*: 보고서 B가 보고서 A의 주장을 반박할 경우, B 노드 생성 시 A의 노드에도 "반박됨" 링크가 자동 추가된다. 단순 저장이 아닌 **생태계 전체를 갱신**하는 구조다.

#### Zep / Graphiti (McDonald & Poyiadzi, 2025 · arXiv:2501.13956)
**Temporal Knowledge Graph** 기반 에이전트 메모리 엔진. 각 엣지(관계)에 4개 타임스탬프를 부여한다:
- `t_created`: 관계가 시스템에 입력된 시각
- `t_expired`: 관계가 만료 처리된 시각
- `t_valid`: 실세계에서 관계가 성립하기 시작한 시각
- `t_invalid`: 실세계에서 관계가 더 이상 유효하지 않은 시각

모순이 발생하면 기존 엣지를 삭제하는 대신 만료(invalidation) 처리하여 역사적 변화 과정을 보존한다. Deep Memory Retrieval 벤치마크에서 94.8% 달성(MemGPT 93.4% 상회).

*적용 인사이트*: **지지/반박 관계 추적에 가장 직접적으로 적합한 아키텍처**다. "언제 어떤 근거가 반박되었는가"의 감사 추적(audit trail)이 자연스럽게 구현된다.

#### Mem0 (2024~2025 · arXiv:2504.19413)
벡터 DB + 그래프 DB 이중 저장 아키텍처. **Conflict Detector + LLM-powered Update Resolver** 파이프라인이 내장되어 신규 정보가 기존 그래프와 충돌할 때 추가/병합/무효화/스킵을 자동 판단한다. LOCOMO 벤치마크에서 OpenAI 메모리(52.9%) 대비 66.9% 달성, p95 지연 91% 감소, 토큰 사용 90% 절감.

*적용 인사이트*: Conflict Detector를 **문서 간 반박 자동 탐지기**로 재활용 가능. 보고서 A의 주장 "X는 Y다"가 존재할 때, B가 "X는 Z다"를 주장하면 자동으로 `contradicts` 엣지가 생성된다.

#### GraphRAG (Edge et al., Microsoft 2024 · arXiv:2404.16130)
텍스트 코퍼스에서 엔티티·관계·주요 주장을 추출해 지식 그래프를 구축하고, Leiden 알고리즘으로 커뮤니티를 탐지, 각 커뮤니티 요약을 사전 생성한다. 기존 RAG 대비 26~97% 적은 토큰으로 더 높은 정보 밀도의 컨텍스트를 제공한다.

*적용 인사이트*: 실시간 업데이트보다 배치 인덱싱에 최적화되어 있으므로, Zep/Mem0와 병행하는 **하이브리드 설계**가 현실적이다.

---

### 1.2 진화 알고리즘 기반 지식 시스템 (5개 연구)

#### MAP-Elites (Mouret & Clune, 2015 · arXiv:1504.04909)
탐색 공간을 행동 특성(behavioral dimensions)에 따라 격자(grid)로 분할하고, 각 셀마다 최고 성능 솔루션 하나만 보존한다. 결과물은 단일 최적해가 아니라 "다양하면서도 각자의 영역에서 고품질인 해들의 지도(illuminated map)"다.

*적용 인사이트*: 지식을 단일 순위로 줄 세우는 대신, **주제 축 × 관점 축** 다차원 격자에 배치하면 틈새 고품질 지식도 살아남는다. Selection pressure가 전역 경쟁이 아닌 **국소 셀 내 경쟁**으로 작동한다.

#### Open-Endedness (Stanley & Lehman, 2015)
"목표 역설(objective paradox)": 목표를 고정하는 순간 그 목표에 도달하는 능력이 저하된다. 핵심 비유는 **디딤돌(stepping stones)** — 위대한 발견으로 가는 경로는 사전에 계획 불가능하며, 탐색 전략은 목표 최적화가 아니라 새로움(novelty)의 지속적 생성이어야 한다.

*적용 인사이트*: 지식 시스템에서 "가장 정확한 답"을 목표로 삼으면 탐색이 조기 수렴한다. 지식 아카이브는 **미래 발견을 위한 디딤돌 저장소**로 설계되어야 한다.

#### EvoAgent (Chen et al., 2024 · arXiv:2406.14228, NAACL 2025)
단일 전문화 LLM 에이전트를 초기 개체(individual)로 삼아, mutation/crossover/selection 연산자를 적용해 자동으로 다중 에이전트 시스템을 생성한다.

*적용 인사이트*: 에이전트의 **전문화 프로필(역할, 관심 영역, 추론 스타일)** 자체를 진화의 대상으로 삼을 수 있다. 고정된 정답 없이도 "이 에이전트가 이 유형의 질문에 더 유용한가?"를 기준으로 진화를 구동할 수 있다.

#### Darwin-Gödel Machine (Sakana AI, 2025 · arXiv:2505.22954)
에이전트가 자신의 코드를 직접 수정하고, 수정의 유효성을 실제 벤치마크로 검증하는 자기 개선 시스템. 아카이브 기반 분기 탐색으로 조기 수렴을 방지한다. 제공되는 컴퓨팅이 많을수록 성능이 지속적으로 향상되는 open-ended scaling을 보인다.

*적용 인사이트*: 최고 성능 경로만 따라가면 조기 수렴한다. 낮은 성능이더라도 **아카이브에 보존하고 어느 지점에서든 분기 가능**하게 하면, 현재 쓸모없어 보이는 지식 조각이 미래의 결정적 디딤돌이 된다.

#### POET / Enhanced POET (Wang et al., 2019~2020 · arXiv:1901.01753)
환경 생성과 에이전트 훈련을 동시에 진화시키는 **공진화(coevolution)** 프레임워크. 새 환경은 두 가지 필터를 통과해야 한다: (1) **최소 기준(minimal criterion)** — 너무 쉽거나 너무 어렵지 않을 것, (2) **신선도(novelty)** — 기존 환경들과 충분히 다를 것.

*적용 인사이트*: **"문제(환경)와 해법(에이전트)을 함께 진화시켜야 한다"**. 질문의 난이도와 형태 자체도 진화의 대상이 된다.

---

### 1.3 그래프 기반 지식 표현 및 랭킹 알고리즘 (3개 연구)

#### PageRank (Page et al., 1998)
수신 링크 개수와 출처의 중요도로 점수 결정. 방향성 인용 네트워크를 위해 명시적으로 설계됐다. 인용 네트워크 분석 연구에서 실제 중요도와 **r > 0.9** 상관성 보임.

```
PR(A) = (1-d)/N + d × Σ(PR(Ti)/out_degree(Ti))
```
d=0.85, 반박 엣지도 피인용으로 처리 → "많이 반박되는 논문 = 중요한 논문"

#### HITS (Kleinberg, 1999)
Hub(많은 논문을 참조) vs Authority(많이 인용됨) 2가지 점수. 반박 전문 논문(hub)과 핵심 이론 논문(authority)을 자동 구분한다.

#### Betweenness Centrality
다른 논문 쌍 간 최단경로 통과 빈도. "가교 논문" 찾기에 최적. 학제간 연결 지표로 활용된다.

**추천**: 인용/지지/반박 네트워크에는 **PageRank가 최선**. 상위 20% 논문에 대해 Betweenness로 가교 역할을 추가 분석하는 하이브리드가 가장 실용적이다.

---

## 2부. 오컴의 면도날 — 에이전트 환경에 필요한 것만 추출 (US-002)

### 2.1 버릴 것: 인간 학계에서 에이전트에 불필요한 5가지

| 인간 학계 요소 | 존재 이유 | 에이전트에 불필요한 이유 |
|---|---|---|
| **학회·저널 게이트키핑** | 품질 필터, 물리적 자원 희소성 | 에이전트는 무한 복제 가능, 게이트가 아닌 선택압으로 충분 |
| **저자 명성·사회적 권위** | 신뢰 신호, 인맥 기반 평가 | 에이전트는 익명이며 출력 자체만 평가 가능 |
| **발표 순서·선점 경쟁** | 희소한 시간 슬롯, 우선권 분쟁 | 에이전트는 동시다발적으로 생성 가능 |
| **동료 심사 지연(6~18개월)** | 인간의 시간 및 인지 제약 | 에이전트는 밀리초 단위로 평가 가능 |
| **인용 조작·자기인용** | 지표 게임, 개인 이익 | 에이전트는 개인 이익이 없으며, 시스템 설계로 방지 가능 |

### 2.2 지킬 것: 최소 필요 조건 3개

다음 세 가지만 있으면 지식 생태계가 작동한다:

**① 평가압력 (Selection Pressure)**
생성된 지식이 비교 경쟁에서 도태되는 메커니즘이 없으면, 생태계가 아니라 단순한 저장소다. 기준은 "좋은가/나쁜가"가 아니라 "지금 이 셀에서 상대보다 나은가"로 충분하다.

**② 다양성 보존 (Diversity Maintenance)**
최고 성능만 살아남으면 생태계가 수렴한다. MAP-Elites의 교훈: 주제 × 관점 격자에서 각 셀에 최소 하나의 생존자를 보장해야 한다. 이것이 "다음 발견의 디딤돌"이 된다.

**③ 상태 명시성 (Explicit State)**
에이전트는 상태를 기억하지 못한다. 모든 지식 조각의 현재 상태(신뢰도, 지지/반박 관계, 나이)는 외부 저장소에 명시적으로 기록되어야 한다. 암묵적 맥락에 의존하는 순간 에이전틱 환경에서는 붕괴된다.

### 2.3 에이전트 고유 장점을 활용하는 새 메커니즘

인간 학계가 절대 못 하는 것들:

| 에이전트 고유 능력 | 활용 메커니즘 |
|---|---|
| **동시다발 생성** | 동일 주제에 대해 N개 관점을 병렬 생성 후 토너먼트 |
| **역할 전환** | 동일 에이전트가 저자/비평가/판사 역할을 사이클마다 교체 |
| **무한 재시도** | 반박당한 지식 조각이 즉시 개정판을 생성할 수 있음 |
| **메타 학습** | 어떤 유형의 지식이 더 많이 살아남는지를 에이전트가 스스로 학습 |
| **즉각적 비교** | 두 지식 조각의 전체 내용을 컨텍스트에 동시에 올려 직접 비교 |

---

## 3부. 그래프 메모리 아키텍처 설계 (US-003)

### 3.1 선형 TSV vs 그래프 메모리 비교

| 속성 | results.tsv (선형) | 그래프 메모리 |
|---|---|---|
| **구조** | 행 = 실험 기록, 시간순 | 노드 = 지식 조각, 엣지 = 관계 |
| **조회 방식** | 전체 파일 스캔 | 그래프 순회 (PageRank, BFS) |
| **관계 표현** | 없음 (암묵적) | 지지/반박/파생/확장 엣지 |
| **시간 정보** | 행 순서 = 시간 | 엣지에 타임스탬프 명시 |
| **다중 에이전트** | 경합 조건(race condition) 위험 | WAL 모드로 동시 쓰기 가능 |
| **쿼리 표현력** | grep/awk | SQL + 그래프 순회 |
| **반박 전파** | 불가 | 반박 엣지 타고 영향도 계산 가능 |
| **진화 추적** | 불가 | 조상-후손 체인 추적 가능 |

### 3.2 구현 옵션 비교

| 스토리지 | 복잡도 | 성능 | 에이전트 친화성 | 비고 |
|---|---|---|---|---|
| **SQLite + JSON + WAL** | ★☆☆ | ★★★ | ★★★ | Python 내장, 의존성 0 |
| **DuckDB** | ★★☆ | ★★★★ | ★★☆ | 분석 쿼리 최강, 대용량 적합 |
| **파일시스템 그래프** | ★☆☆ | ★☆☆ | ★★☆ | 간단하지만 확장성 낮음 |
| **NetworkX pickle** | ★☆☆ | ★★☆ | ★★☆ | Python 친화적, 동시성 약점 |
| **Neo4j/ArangoDB** | ★★★ | ★★★★★ | ★★☆ | 과잉 설계, 인프라 부담 |

**최종 추천: SQLite + JSON + WAL 모드**

이유:
1. Python 내장 (`import sqlite3`) — 추가 의존성 없음
2. WAL(Write-Ahead Logging) 모드로 다중 에이전트 동시 쓰기 가능
3. SQL로 PageRank 입력 데이터 구성, JSON 컬럼으로 메타데이터 유연 저장
4. 에이전트가 읽고 쓰는 스키마를 자연어로 쉽게 설명 가능

### 3.3 최소 스키마 제안

```sql
-- 논문/보고서 노드
CREATE TABLE papers (
    id          TEXT PRIMARY KEY,  -- "paper_20260317_001"
    title       TEXT NOT NULL,
    content     TEXT,              -- 전체 텍스트
    summary     TEXT,              -- 핵심 주장 1-3문장
    status      TEXT DEFAULT 'active',  -- active | contested | foundational | archived
    fitness     REAL DEFAULT 0.0,  -- PageRank 기반 중요도
    created_at  TEXT,
    topic_tag   TEXT,              -- MAP-Elites 셀 주소 (예: "memory:graph")
    perspective TEXT               -- 관점 태그 (예: "empirical")
);

-- 평가 엣지 (지지/반박/파생)
CREATE TABLE edges (
    id          TEXT PRIMARY KEY,
    src         TEXT REFERENCES papers(id),
    dst         TEXT REFERENCES papers(id),
    relation    TEXT,  -- 'supports' | 'contradicts' | 'extends' | 'derived_from'
    strength    REAL DEFAULT 1.0,  -- 관계 강도 (0.0~1.0)
    judge_score REAL,              -- LLM-as-Judge 점수
    created_at  TEXT,
    valid_until TEXT               -- Zep 방식 만료 시각 (NULL = 여전히 유효)
);

-- 에이전트 평가 이력
CREATE TABLE evaluations (
    id          TEXT PRIMARY KEY,
    paper_id    TEXT REFERENCES papers(id),
    judge_model TEXT,
    rubric      TEXT,              -- 평가에 사용된 루브릭
    score       REAL,
    verdict     TEXT,              -- 'survive' | 'archive' | 'contested'
    created_at  TEXT
);
```

이 세 테이블이면 충분하다. `papers` — 지식 조각, `edges` — 관계, `evaluations` — 평가 이력. 복잡한 온톨로지나 벡터 임베딩은 나중에 추가하면 된다.

### 3.4 그래프 쿼리 예시

```python
import sqlite3
import networkx as nx

def build_graph(db_path: str) -> nx.DiGraph:
    """SQLite에서 지식 그래프 구성"""
    conn = sqlite3.connect(db_path)
    G = nx.DiGraph()

    # 노드 추가
    for row in conn.execute("SELECT id, title, fitness, status FROM papers"):
        G.add_node(row[0], title=row[1], fitness=row[2], status=row[3])

    # 엣지 추가 (유효한 관계만)
    for row in conn.execute(
        "SELECT src, dst, relation, strength FROM edges WHERE valid_until IS NULL"
    ):
        G.add_edge(row[0], row[1], relation=row[2], weight=row[3])

    return G

def compute_importance(G: nx.DiGraph) -> dict:
    """PageRank로 중요도 계산"""
    pr = nx.pagerank(G, alpha=0.85)
    # 상위 20% 가교 논문도 탐지
    top_20pct = sorted(pr, key=pr.get, reverse=True)[:max(1, len(pr)//5)]
    subg = G.subgraph(top_20pct)
    bc = nx.betweenness_centrality(subg)
    return {"pagerank": pr, "bridge_papers": bc}
```

---

## 4부. 최소 유효 평가압력 설계 (US-004)

### 4.1 평가압력 메커니즘 비교

5개 평가압력 메커니즘을 조사했다:

| 메커니즘 | 핵심 | 편향/한계 | 우리 시스템 적합도 |
|---|---|---|---|
| **Debate** (Irving 2018) | 두 에이전트가 토론, 판사가 승자 선택 | 설득력이 정확성을 이길 수 있음 | 중 (복잡도 높음) |
| **Constitutional AI** (Anthropic 2022) | 원칙 목록 기반 자기비판 | 같은 모델의 맹점 공유 | 중 (전처리 단계로 유용) |
| **LLM-as-Judge** (Zheng, NeurIPS 2023) | LLM이 두 출력을 직접 비교 | Position bias, Verbosity bias | **최고** (단순·효과적) |
| **Self-Play** (AlphaGo, 2016) | 챔피언 vs 도전자 루프 | Mode collapse 위험 | 높 (챔피언 메커니즘으로 통합) |
| **Scalable Oversight** (Bowman 2022) | 약한 판사가 강한 에이전트 평가 | 복잡성 페널티 | 낮 (검증 미흡) |

**결론**: LLM-as-Judge가 모든 다른 메커니즘의 공통 기반이다. 다른 4가지는 LLM-as-Judge 위에 복잡도를 얹는다. 최소 시스템은 LLM-as-Judge + bias 보정 2개다.

### 4.2 평가압력 최소 규칙 3개

```
규칙 1: COMPARE
  두 보고서 A와 B를 쌍으로 LLM에게 제시한다.
  순서를 바꿔 두 번 비교하고, 두 번 모두 같은 승자가 나오면 확정한다.
  (Position bias 제거)

규칙 2: JUDGE WITH RUBRIC
  판사 LLM에게 명시적 루브릭을 고정 제공한다:
    - 주장의 명확성 (0~3점)
    - 근거의 구체성 (0~3점)
    - 반박 가능성 (0~2점)
    - 새로운 연결 발견 (0~2점)
  (Verbosity bias 억제, 총점 10점)

규칙 3: SURVIVE OR ARCHIVE
  패자는 즉시 삭제하지 않는다. 'archived' 상태로 보존한다.
  (다양성 유지, 미래 디딤돌 보존)
```

### 4.3 전체 사이클 의사코드 (20줄 이내)

```python
def evolution_cycle(db: str, topic: str):
    papers = db_load(db, topic, status="active")    # 1: 활성 보고서 로드

    new_paper = agent_generate(topic, papers)        # 2: 새 보고서 생성
    db_save(db, new_paper)                           # 3: 저장

    rival = select_rival(papers, new_paper)          # 4: 대결 상대 선택
                                                     #    (챔피언 or 같은 셀 최강자)

    score_ab = llm_judge(new_paper, rival, RUBRIC)   # 5: 순서 A→B 평가
    score_ba = llm_judge(rival, new_paper, RUBRIC)   # 6: 순서 B→A 평가

    if score_ab.winner == score_ba.winner:           # 7: 두 평가 일치?
        winner = score_ab.winner
        loser  = score_ab.loser
        db_update_edge(db, winner.id, loser.id,      # 8: 관계 엣지 기록
                       relation="defeats")
        db_update_status(db, loser.id, "archived")  # 9: 패자 아카이브
        db_update_fitness(db, recompute_pagerank(db))# 10: 중요도 재계산

    db_update_grid(db, new_paper)                    # 11: MAP-Elites 셀 업데이트
```

### 4.4 기존 ralph.sh와의 차이

| 항목 | ralph.sh (기존) | 에이전트 생태계 (신규) |
|---|---|---|
| **메모리** | results.tsv (선형 append) | SQLite 그래프 (노드 + 엣지) |
| **상태 파악** | "results.tsv를 읽어 현재 상태를 파악하라" | 구조적 쿼리로 즉시 상태 확인 |
| **평가** | 없음 (에이전트가 판단) | LLM-as-Judge + rubric |
| **도태** | 없음 | archived 상태로 전환 |
| **다양성** | 없음 | MAP-Elites 셀 보장 |
| **관계** | 없음 | 지지/반박/파생 엣지 |
| **선택압** | 없음 | 토너먼트 방식 생존 경쟁 |
| **루프 구조** | `while true; do ... done` | `while true; do evolution_cycle(); done` |

핵심 변화: ralph.sh는 **저장 + 반복** 루프다. 새 시스템은 **생성 + 평가 + 도태 + 보존** 루프다.

### 4.5 에이전트 친화적 설계 원칙 확인

| 원칙 | 충족 여부 | 근거 |
|---|---|---|
| **컨텍스트 효율** | ✅ | summary 필드로 핵심 주장만 컨텍스트에 로드 |
| **독립적 비교** | ✅ | 두 보고서를 독립적으로 비교 (이전 평가 이력 불필요) |
| **상태 명시성** | ✅ | 모든 상태(status, fitness, edges)가 DB에 명시 저장 |
| **원자적 쓰기** | ✅ | WAL 모드로 경합 조건 방지 |
| **재현 가능성** | ✅ | 동일 rubric + 동일 비교 쌍 → 동일 결과 |

---

## 5부. 종합 아키텍처 — 최소 에이전트 지식 생태계

### 전체 시스템 다이어그램

```
┌─────────────────────────────────────────────────┐
│              Knowledge Ecosystem Loop            │
│                                                 │
│  ┌──────────┐    generate    ┌──────────────┐   │
│  │  Topic   │ ──────────────>│  New Paper   │   │
│  │  Queue   │                │  (Agent)     │   │
│  └──────────┘                └──────┬───────┘   │
│                                     │ save       │
│                                     ▼            │
│  ┌──────────────────────────────────────────┐   │
│  │         SQLite Knowledge Graph           │   │
│  │  papers(id, summary, status, fitness)    │   │
│  │  edges(src, dst, relation, timestamp)    │   │
│  │  evaluations(paper_id, score, verdict)   │   │
│  └──────────────────┬───────────────────────┘   │
│                     │                            │
│          select_rival│                           │
│                     ▼                            │
│  ┌──────────────────────────────────────────┐   │
│  │         LLM-as-Judge Tournament          │   │
│  │  A vs B (order 1) → score               │   │
│  │  B vs A (order 2) → score               │   │
│  │  consistent winner? → survive/archive   │   │
│  └──────────────────────────────────────────┘   │
│                     │                            │
│         recompute   │ pagerank                   │
│                     ▼                            │
│  ┌──────────────────────────────────────────┐   │
│  │         MAP-Elites Grid Update           │   │
│  │  topic × perspective cells              │   │
│  │  each cell: best paper survives         │   │
│  └──────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

### 시스템이 자동으로 만들어내는 것

1. **지식 족보**: `derived_from` 엣지가 아이디어의 계보를 추적
2. **논쟁 지도**: `contradicts` 엣지가 활발한 논쟁 클러스터를 드러냄
3. **디딤돌 보존**: archived 보고서가 미래 아이디어의 씨앗이 됨
4. **중요도 분포**: PageRank가 자동으로 핵심 지식을 부상시킴
5. **다양성 지도**: MAP-Elites 그리드가 탐색된/미탐색된 영역을 시각화

---

## 결론

오컴의 면도날을 적용하면 복잡한 인간 학계 시스템에서 세 가지만 남는다:

**평가압력 + 다양성 보존 + 상태 명시성**

이 세 가지를 구현하는 최소 기술 스택은:

- **저장**: SQLite (Python 내장, 의존성 0)
- **평가**: LLM-as-Judge + rubric (에이전트 1개)
- **다양성**: MAP-Elites 그리드 (topic × perspective 셀)
- **중요도**: PageRank (networkx 5줄)
- **관계**: 지지/반박/파생 엣지 (3개 관계 유형)

인간 학계가 학술지, 학회, 동료 심사, 저자 명성, 선점 경쟁을 통해 수백 년에 걸쳐 구현한 것을, 에이전트 환경에서는 **while 루프 하나 + SQLite DB 하나 + LLM 판사 하나**로 구현할 수 있다.

시스템이 스스로 질문을 발전시키고, 스스로 지식을 평가하고, 스스로 디딤돌을 보존한다. 설계자가 할 일은 최초 주제를 주입하고, 루프를 시작하는 것뿐이다.

---

## 참고 문헌

### 에이전트 메모리 아키텍처
- MemGPT: [arXiv:2310.08560](https://arxiv.org/abs/2310.08560) | [GitHub: letta-ai/letta](https://github.com/letta-ai/letta)
- A-MEM: [arXiv:2502.12110](https://arxiv.org/abs/2502.12110) | [GitHub: agiresearch/A-mem](https://github.com/agiresearch/A-mem)
- Zep/Graphiti: [arXiv:2501.13956](https://arxiv.org/abs/2501.13956) | [GitHub: getzep/graphiti](https://github.com/getzep/graphiti)
- Mem0: [arXiv:2504.19413](https://arxiv.org/abs/2504.19413) | [mem0.ai](https://mem0.ai/)
- GraphRAG: [arXiv:2404.16130](https://arxiv.org/abs/2404.16130) | [microsoft/graphrag](https://github.com/microsoft/graphrag)

### 진화 알고리즘 기반 지식 시스템
- MAP-Elites: [arXiv:1504.04909](https://arxiv.org/abs/1504.04909)
- Open-Endedness: [Why Greatness Cannot Be Planned (Springer, 2015)](https://link.springer.com/book/10.1007/978-3-319-15524-1)
- EvoAgent: [arXiv:2406.14228](https://arxiv.org/abs/2406.14228)
- Darwin-Gödel Machine: [arXiv:2505.22954](https://arxiv.org/abs/2505.22954) | [sakana.ai/dgm](https://sakana.ai/dgm/)
- POET: [arXiv:1901.01753](https://arxiv.org/abs/1901.01753) / Enhanced: [arXiv:2003.08536](https://arxiv.org/abs/2003.08536)

### 그래프 기반 지식 표현 및 랭킹
- PageRank: [NetworkX docs](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.link_analysis.pagerank_alg.pagerank.html)
- HITS: [Wikipedia](https://en.wikipedia.org/wiki/HITS_algorithm)
- Betweenness Centrality: [PMC: Betweenness in Citation Networks](https://pmc.ncbi.nlm.nih.gov/articles/PMC7088853/)

### 평가압력 메커니즘
- AI Safety via Debate: [arXiv:1805.00899](https://arxiv.org/abs/1805.00899)
- Constitutional AI: [arXiv:2212.08073](https://arxiv.org/abs/2212.08073)
- LLM-as-Judge: [arXiv:2306.05685](https://arxiv.org/abs/2306.05685)
- AlphaGo: [Nature 2016](https://www.nature.com/articles/nature16961)
- Scalable Oversight: [arXiv:2211.03540](https://www.emergentmind.com/papers/2211.03540)
