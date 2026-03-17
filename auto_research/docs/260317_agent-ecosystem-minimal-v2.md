# 오컴의 면도날 에이전트 지식 생태계 — v2
## 최신 오픈소스 7개 분석으로 업데이트된 에이전트 메모리 설계

**작성일**: 2026-03-17
**기반 보고서**: `260317_agent-ecosystem-minimal.md` (v1)
**신규 분석**: 7개 최신 GitHub 레포지토리 (2024~2026)

---

## 개요 — v1에서 v2로

v1 보고서는 학술 논문 기반으로 에이전트 메모리의 이상적 설계를 도출했다. v2는 실제로 작동하는 오픈소스 시스템 7개를 직접 분석하여 "현장에서 쓰이는 패턴"을 추가한다.

**v1의 핵심 결론**: SQLite+WAL + Zep 시간축 그래프 + A-MEM 양방향 갱신 + LLM-as-Judge 평가압력

**v2에서 추가되는 것**:
1. L0/L1/L2 계층화 로딩 (OpenViking) — 토큰 비용 91% 절감
2. 결정론적 콘텐츠 해시 ID (Wrkr) — 세션 간 에이전트 재연결
3. Reconcile() 상태 머신 (Wrkr) — 스냅샷 diff 기반 상태 갱신
4. 불변 감사 체인 (Wrkr) — append-only 전환 이력
5. 실행 중 비동기 write-back (MiroFish/Hyperspace) — 메모리가 실시간 진화
6. 최소 증거 게이트 (MiroFish) — 최소 N회 메모리 조회 후 출력
7. 스킬 조합 그래프 (SkillNet) — depend_on/compose_with 엣지
8. 세션 간 annotation 연속성 (context-hub) — 발견 지식이 다음 세션에 주입

---

## 1부. 7개 레포지토리 분석 (US-001)

### 1.1 Hyperspace AGI (`hyperspaceai/agi`)

중앙 서버 없이 수천 개 에이전트가 P2P로 ML 연구를 협력 수행하는 분산형 시스템. 메모리 아키텍처가 3단계로 설계됐다:

| 계층 | 기술 | 지연 | 역할 |
|---|---|---|---|
| 실시간 | GossipSub (libp2p) | ~1초 | 실험 결과 즉시 브로드캐스트 |
| 수렴 상태 | Loro CRDT | ~2분 | 충돌 없는 리더보드 동기화 |
| 영구 아카이브 | GitHub 브랜치 (에이전트별) | ~5분 | 불변 장기 메모리 |

에이전트 5단계 루프: `Hypothesis → Train → Synthesize → Critique → Discover`. 핵심은 **8점 이상 논문이 다음 사이클의 가설 생성 단계에 자동 재주입**되는 피드백 루프다. 새 노드가 접속하면 CRDT 리더보드를 즉시 읽어 콜드 스타트 문제를 제거한다.

*v1 대비 신규 인사이트*: P2P CRDT 수렴 패턴은 SQLite 단일 인스턴스보다 확장성이 높지만, 우리 시스템처럼 단일 인스턴스로 시작할 때는 **고점수 결과물을 다음 루프의 컨텍스트에 자동 주입하는 피드백 고리**가 핵심 takeaway다.

---

### 1.2 CodeGraphContext (`CodeGraphContext/CodeGraphContext`)

소스 코드를 AI 에이전트가 탐색 가능한 속성 그래프로 변환하는 MCP 서버. tree-sitter로 14개 언어를 파싱해 15가지 노드 타입(Function, Class, Module 등)과 7가지 관계 타입(CALLS, IMPORTS, INHERITS 등)을 추출한다. KuzuDB(기본)/FalkorDB/Neo4j 백엔드를 어댑터 패턴으로 교체 가능하다.

핵심 설계 원칙은 **스코프 기반 서브그래프 검색**: 전체 코드베이스를 컨텍스트에 올리는 대신 `repo_path + context(파일)` 파라미터로 쿼리 범위를 제한한다. 사전 인덱싱된 번들(nodes.jsonl + edges.jsonl)을 공유하면 재파싱 대비 60배 빠르다.

*v1 대비 신규 인사이트*: **복합 UID 패턴** — `name + path + line_number`로 노드를 영구 식별한다. 우리 시스템의 지식 그래프에서 각 주장(claim)을 `claim_text_hash + paper_id + paragraph_idx`로 식별하면 세션 간 동일 주장을 재연결할 수 있다.

---

### 1.3 Wrkr (`Clyra-AI/wrkr`)

AI 에이전트/MCP 서버의 보안 인벤토리 관리 CLI. "npm audit for AI agents"라는 포지셔닝으로, 에이전트 상태를 LLM 없이 결정론적으로 추적한다.

**핵심 설계 패턴 3가지**:

**① 콘텐츠 해시 기반 결정론적 ID**:
```go
// SHA-256(toolType::location) → 에이전트 영구 ID
func AgentID(toolType, location, org string) string {
    hash := sha256.Sum256([]byte(toolType + "::" + location))
    return fmt.Sprintf("wrkr:%x:%s", hash[:5], org)
}
```
세션/런타임 UUID 없이 설정 자체로 ID를 파생. 같은 설정 = 항상 같은 ID.

**② 3중 파일 영속성 계층**:
| 파일 | 형식 | 목적 |
|---|---|---|
| `last-scan.json` | JSON | diff용 스냅샷 |
| `manifest.yaml` | YAML | 현재 상태 진실 소스 (human-editable) |
| `identity-chain.json` | JSON | 불변 감사 로그 |

**③ Reconcile() 상태 머신**:
```go
func Reconcile(previous Manifest, observed []Tool, now time.Time) (Manifest, []Transition)
// previous: 디스크에서 읽은 이전 상태
// observed: 현재 스캔 결과
// → 새 Manifest + Transition 이벤트 목록
```

TTL 기반 자동 강등: 승인 90일 만료 시 `active → under_review`로 자동 강등. **메모리 유효기간** 개념을 구현한다.

*v1 대비 신규 인사이트*: v1은 단순 status 필드만 있었다. Wrkr의 3중 파일 분리 + Reconcile 패턴을 도입하면 에이전트가 재시작 후 이전 상태를 정확히 복원하고, 드리프트를 감지하며, 감사 이력을 유지할 수 있다.

---

### 1.4 SkillNet (`skillnet.openkg.cn` · arXiv:2603.04448)

AI 에이전트 스킬을 지식 그래프로 구조화한 오픈 인프라 ("npm for AI capabilities"). 20만 개 이상의 스킬을 3계층 온톨로지로 조직한다:

```
Skill Taxonomy (10개 카테고리)
    ↓
Skill Relation Graph
    - similar_to    (의미적 유사도)
    - belong_to     (카테고리 소속)
    - compose_with  (스킬 조합)
    - depend_on     (선행 의존성)
    ↓
Skill Package Library (재사용 가능한 번들)
```

스킬 자동 생성 파이프라인: 실행 궤적 → 표준화된 스킬 노드. 5축 평가: Safety / Completeness / Executability / Maintainability / Cost-awareness. 벤치마크(ALFWorld): 평균 보상 +40%, 상호작용 스텝 -30%.

*v1 대비 신규 인사이트*: v1의 지식 그래프는 논문 노드와 지지/반박 엣지만 있었다. SkillNet의 **depend_on / compose_with 엣지**를 추가하면 "이 지식 조각을 활용하려면 먼저 알아야 할 전제 지식"을 그래프에서 자동 탐색할 수 있다. 지식 생태계가 단순 평가 시스템을 넘어 **학습 경로 추천 시스템**으로 확장된다.

---

### 1.5 Context Hub (`andrewyng/context-hub`)

코딩 에이전트의 두 실패 모드(API 환각 + 세션 간 기억 상실)를 해결하는 허브-스포크 문서 관리 시스템. Andrew Ng 팀 작품.

**2계층 메모리 구조**:
| 계층 | 범위 | 저장 위치 | 수명 |
|---|---|---|---|
| 커뮤니티 문서 | 전역 (모든 에이전트) | 중앙 레지스트리 | 버전 관리, 영구 |
| Annotation | 로컬 (이 에이전트만) | `~/.chub/` 파일 | 세션 간 지속 |

핵심: annotation이 에이전트의 **개인 장기 메모리 저장소**가 된다. `chub annotate <id> "workaround: ..."` 명령으로 발견한 지식을 저장하면, 다음 세션에서 `chub get <id>` 호출 시 annotation이 자동 주입된다.

피드백 루프: `chub feedback <id> up/down` → 에이전트의 실패가 중앙 레지스트리를 개선.

*v1 대비 신규 인사이트*: v1은 세션 간 연속성이 없었다. **로컬 annotation + 자동 주입 패턴**을 도입하면, 에이전트가 이전 연구 세션에서 발견한 인사이트·실패 패턴·도메인 지식을 다음 세션에서 자동으로 활용할 수 있다. 토큰 효율적인 선택적 로딩도 핵심이다.

---

### 1.6 OpenViking (`volcengine/OpenViking`)

ByteDance(Volcengine)가 2026년 1월 공개한 AI 에이전트 전용 컨텍스트 데이터베이스. 기존 RAG의 평면적 벡터 저장을 버리고 `viking://` URI 기반 **파일시스템 패러다임**을 채택한다.

```
viking://
  ├── resources/        # 프로젝트 문서, 저장소, 외부 지식
  ├── user_memory/      # 사용자 선호도, 상호작용 이력
  └── agent_memory/     # 스킬, 태스크 지시사항, 과거 경험
```

**L0/L1/L2 계층화 지연 로딩**:
- L0: 한 줄 요약 (관련성 필터링용, 최소 토큰)
- L1: ~2,000 토큰 개요 (계획·추론용)
- L2: 전체 원문 (필요할 때만 on-demand 로드)

가상 메모리 페이징과 동일한 원리. 결과: **토큰 비용 91% 절감**, 검색 성능 43% 향상.

모든 검색 경로가 URI 시퀀스로 저장되어 RAG 블랙박스 문제를 해결한다. 매 세션 종료 후 사용자 선호·에이전트 경험을 자동 추출·업데이트하는 자기진화형 메모리.

*v1 대비 신규 인사이트*: v1 스키마의 papers 테이블에는 `content` 필드 하나뿐이었다. **L0/L1/L2 분리**를 도입하면 에이전트가 관련 논문을 찾을 때 L0만 읽어 필터링하고, 필요한 것만 L2를 로드한다. 수백 개 논문이 쌓여도 컨텍스트 폭발이 없다.

---

### 1.7 MiroFish (`666ghj/MiroFish`)

시드 문서에서 GraphRAG 지식 그래프를 구축하고, 그 그래프에서 에이전트 페르소나를 자동 생성한 뒤 소셜 미디어 시뮬레이션을 실행하는 집단 지능 예측 엔진.

**양방향 메모리 피드백 루프**:
```
Seed Doc → Zep GraphRAG → Agent Personas → Simulation
              ↑                                  ↓
              └── Episode Write-back ←── Agent Actions
```
에이전트가 행동할 때마다 그 결과를 자연어 에피소드로 변환하여 그래프에 비동기 쓰기. 이후 라운드의 에이전트는 이전 에이전트들의 행동까지 반영된 더 풍부한 그래프를 기반으로 작동한다.

**최소 증거 게이트(Minimum Evidence Gate)**: ReACT 에이전트가 최소 3회 메모리를 조회한 후에만 출력을 생성하도록 강제. 할루시네이션을 구조적으로 방지한다.

3계층 검색 도구: InsightForge (심층 분해·복합 검색) / PanoramaSearch (역사적 전체 스캔) / QuickSearch (빠른 직접 조회).

*v1 대비 신규 인사이트*: v1은 작업 완료 후 메모리를 저장했다. MiroFish의 **비동기 배치 write-back** 패턴을 도입하면 에이전트가 중간에 중단되어도 그때까지의 발견이 메모리에 보존된다. 최소 증거 게이트는 v1의 평가압력과 결합하면 생성과 검증 모두를 강화한다.

---

## 2부. v1 vs v2 비교 — 업데이트 내용 (US-002)

### 2.1 v1 추천의 유효성 검토

**유효한 것 (변경 없음)**:
- SQLite + WAL 모드: 7개 레포 모두 파일 기반 저장을 사용, 복잡한 DB는 사용하지 않음 ✅
- LLM-as-Judge + pairwise: MiroFish도 동일 패턴 사용 ✅
- 3원칙(평가압력 + 다양성 보존 + 상태 명시성): 모든 레포에서 유효 확인 ✅
- Zep 시간축 엣지: MiroFish가 실제로 Zep Cloud 사용, v1 추천 검증 ✅

**업데이트 필요한 것**:
- v1 스키마의 `content` 단일 필드 → **L0/L1/L2 3단계 분리** (OpenViking)
- v1에 없던 **결정론적 에이전트 ID** 추가 (Wrkr)
- v1에 없던 **세션 간 annotation 연속성** 추가 (context-hub)
- v1에 없던 **실시간 write-back** 메커니즘 추가 (MiroFish/Hyperspace)
- v1의 단순 status 필드 → **Reconcile 기반 상태 머신** (Wrkr)

### 2.2 v1에서 다루지 않은 새 패턴 4가지

**패턴 1: 메모리 페이징 (Memory Paging)**
OpenViking의 L0/L1/L2는 CPU의 가상 메모리 페이징과 동일한 원리다. 에이전트가 모든 메모리를 컨텍스트에 올리는 대신, 관련성 신호(L0)만 먼저 확인하고 필요한 깊이만큼 로드한다. 이것은 에이전트 메모리의 근본적 병목을 해결하는 패턴이다.

**패턴 2: 결정론적 메모리 ID**
Wrkr의 SHA-256 콘텐츠 해시 기반 ID는 "어떤 메모리가 이 노드인가"를 세션 없이 결정한다. 동일 논문이 두 번 추가되면 같은 ID → 자동 중복 제거. 재시작 후 이전 세션의 그래프 노드를 정확히 재연결할 수 있다.

**패턴 3: 실행 중 메모리 진화**
v1에서는 작업 완료 후 메모리를 저장했다. MiroFish와 Hyperspace는 **실행 도중 비동기로 메모리를 갱신**한다. 에이전트가 중단되어도 중간 발견이 보존되며, 동일 주제를 탐색하는 다른 에이전트들이 그 발견을 즉시 활용한다.

**패턴 4: 스킬 의존성 그래프**
SkillNet의 `depend_on` / `compose_with` 엣지는 v1에 없었다. 지식 노드 간에 "이것을 이해하려면 저것이 선행되어야 한다"는 관계를 추가하면, 단순 랭킹 시스템을 넘어 **학습 경로 그래프**가 된다.

### 2.3 오컴의 면도날 3원칙 검토

7개 레포 분석 후 v1의 3원칙은 여전히 유효하다. 단, 각 원칙의 구현 방법이 심화된다:

| 원칙 | v1 구현 | v2 심화 |
|---|---|---|
| 평가압력 | LLM-as-Judge pairwise | + 최소 증거 게이트 (출력 전 최소 N회 조회) |
| 다양성 보존 | MAP-Elites 셀 + archived | + TTL 기반 자동 강등 (오래된 상태 재검토 강제) |
| 상태 명시성 | 단일 SQLite papers 테이블 | + L0/L1/L2 분리 + 3중 파일 계층 + Reconcile 머신 |

---

## 3부. 업데이트된 구현 설계 (US-003)

### 3.1 v2 스키마 — L0/L1/L2 + 감사 체인

```sql
-- 논문/보고서 노드 (L0/L1/L2 계층화)
CREATE TABLE papers (
    id          TEXT PRIMARY KEY,  -- SHA-256(content[:500]) 결정론적 ID
    title       TEXT NOT NULL,
    l0_summary  TEXT,              -- 한 줄 요약 (관련성 필터용, ~50 토큰)
    l1_summary  TEXT,              -- 2000 토큰 개요 (계획·추론용)
    l2_content  TEXT,              -- 전체 원문 (on-demand)
    status      TEXT DEFAULT 'active',   -- active|contested|foundational|archived
    fitness     REAL DEFAULT 0.0,        -- PageRank 기반 중요도
    created_at  TEXT,
    expires_at  TEXT,              -- TTL 기반 자동 강등 기준 시각 (NULL=영구)
    topic_tag   TEXT,              -- MAP-Elites 셀 주소
    perspective TEXT,              -- 관점 태그
    source_uri  TEXT               -- 검색 경로 감사 (OpenViking DRR 방식)
);

-- 관계 엣지 (지지/반박/스킬 의존성 포함)
CREATE TABLE edges (
    id          TEXT PRIMARY KEY,
    src         TEXT REFERENCES papers(id),
    dst         TEXT REFERENCES papers(id),
    relation    TEXT,  -- supports|contradicts|extends|derived_from|depend_on|compose_with
    strength    REAL DEFAULT 1.0,
    judge_score REAL,
    created_at  TEXT,
    valid_until TEXT   -- Zep 방식 만료 시각
);

-- 세션 간 annotation (context-hub 방식)
CREATE TABLE annotations (
    id          TEXT PRIMARY KEY,
    paper_id    TEXT REFERENCES papers(id),
    session_id  TEXT,           -- 어느 세션에서 발견했는지
    content     TEXT NOT NULL,  -- "이 논문은 X 조건에서만 유효함"
    tags        TEXT,           -- JSON 배열 형태 태그
    created_at  TEXT
);

-- 불변 감사 체인 (Wrkr proof chain 방식)
CREATE TABLE audit_chain (
    id              TEXT PRIMARY KEY,
    paper_id        TEXT,
    event_type      TEXT,  -- first_seen|status_changed|evaluated|archived|revived
    previous_state  TEXT,
    new_state       TEXT,
    trigger         TEXT,  -- 변경 트리거 (에이전트 ID 등)
    created_at      TEXT   -- append-only, 절대 UPDATE/DELETE 없음
);
```

### 3.2 에이전트 워크플로우 — 읽기·쓰기 통합 (20줄 이내)

```python
import hashlib, sqlite3, asyncio

def paper_id(content: str) -> str:
    """결정론적 콘텐츠 해시 ID (Wrkr 패턴)"""
    return hashlib.sha256(content[:500].encode()).hexdigest()[:16]

async def research_cycle(db: str, topic: str, session_id: str):
    # 1. L0만 로드해서 관련 논문 필터링 (OpenViking 패턴)
    candidates = db_query(db, "SELECT id, l0_summary FROM papers WHERE topic_tag=?", topic)
    relevant = [p for p in candidates if llm_relevance(p["l0_summary"], topic) > 0.7]

    # 2. 관련 논문 L1만 컨텍스트에 로드 (토큰 효율)
    context = [db_query(db, "SELECT l1_summary FROM papers WHERE id=?", p["id"]) for p in relevant]

    # 3. 최소 증거 게이트: 3회 이상 조회 후 생성 (MiroFish 패턴)
    queries, evidence = 0, []
    while queries < 3:
        q = llm_generate_query(topic, context)
        evidence.append(db_search(db, q))
        queries += 1

    # 4. 새 보고서 생성 후 즉시 비동기 write-back (Hyperspace 패턴)
    new_paper = llm_synthesize(topic, evidence)
    pid = paper_id(new_paper["content"])
    asyncio.create_task(db_save_paper(db, pid, new_paper, session_id))  # 비동기

    # 5. 평가 후 감사 체인에 기록 (Wrkr 패턴)
    rival = select_rival(db, topic)
    verdict = llm_judge(new_paper, rival)
    db_append_audit(db, pid, "evaluated", verdict)

    return pid
```

### 3.3 멀티에이전트 메모리 충돌 방지 패턴

```python
# WAL 모드 + Reconcile 패턴 (Wrkr inspired)
def reconcile_papers(db: str, agent_id: str) -> list[dict]:
    """
    이전 스냅샷과 현재 상태를 비교해 변경 이벤트를 생성.
    여러 에이전트가 동시에 쓰더라도 최종 상태가 수렴한다.
    """
    conn = sqlite3.connect(db, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")  # 동시 읽기 허용

    # 이전 스냅샷 로드
    prev_snapshot = load_snapshot(db, agent_id)
    # 현재 상태 관찰
    current = conn.execute("SELECT id, status, fitness FROM papers").fetchall()

    transitions = []
    for row in current:
        pid, status, fitness = row
        prev = prev_snapshot.get(pid)
        if prev is None:
            transitions.append({"pid": pid, "event": "first_seen", "new": status})
        elif prev["status"] != status:
            transitions.append({"pid": pid, "event": "status_changed",
                                 "prev": prev["status"], "new": status})

    # 감사 체인에 배치 기록 (append-only)
    for t in transitions:
        conn.execute("INSERT INTO audit_chain VALUES (?,?,?,?,?,?,?)", ...)

    save_snapshot(db, agent_id, current)  # 다음 비교를 위해 저장
    return transitions
```

---

## 4부. v2 종합 설계 원칙

### 7개 레포에서 수렴하는 5가지 설계 법칙

**법칙 1: 메모리를 깊이 축으로 계층화하라** (OpenViking)
L0(필터) → L1(계획) → L2(실행)의 계층은 CPU 캐시 계층과 동일한 원리다. 모든 메모리를 같은 깊이로 다루는 것은 모든 데이터를 RAM에 올리는 것과 같다.

**법칙 2: ID를 세션이 아닌 콘텐츠에서 파생하라** (Wrkr, CodeGraphContext)
UUID + 타임스탬프 기반 ID는 재시작 후 동일 노드를 재연결할 수 없다. `SHA-256(content[:500])` 형태의 콘텐츠 해시 ID는 어떤 세션에서 생성되었든 같은 콘텐츠 = 같은 ID를 보장한다.

**법칙 3: 메모리는 실행 중에 진화해야 한다** (MiroFish, Hyperspace)
완료 후 저장은 중단 시 손실을 낳는다. 비동기 배치 write-back으로 에이전트가 작업하는 동안 메모리가 실시간으로 풍부해지면, 나중에 합류한 에이전트들이 선행 에이전트들의 발견을 즉시 활용한다.

**법칙 4: 출력 전에 메모리를 의무적으로 조회하라** (MiroFish)
최소 증거 게이트(N회 조회 강제)는 에이전트가 메모리를 무시하고 즉흥적으로 출력하는 것을 구조적으로 방지한다. 평가압력(LLM-as-Judge)과 결합하면 품질 기준이 두 겹이 된다.

**법칙 5: 모든 상태 전환을 불변 체인에 기록하라** (Wrkr)
현재 상태만 저장하면 "왜 이 지식이 archived 됐는가"를 알 수 없다. append-only 감사 체인은 디버깅, 재현, 신뢰도 계산의 기반이 된다.

### v2 업데이트 후 전체 시스템 흐름

```
┌─────────────────────────────────────────────────────────────┐
│                  v2 Knowledge Ecosystem                      │
│                                                              │
│  [세션 시작]                                                  │
│  1. L0 스캔 → 관련 논문 필터링 (OpenViking)                   │
│  2. Annotation 주입 → 이전 세션 인사이트 로드 (context-hub)   │
│  3. L1 로드 → 계획·추론 컨텍스트 구성                         │
│                                                              │
│  [연구 실행]                                                  │
│  4. 최소 3회 메모리 조회 → 증거 수집 (MiroFish)               │
│  5. 새 보고서 생성 + 비동기 write-back (Hyperspace)           │
│                                                              │
│  [평가]                                                       │
│  6. LLM-as-Judge pairwise → 승/패 결정 (v1)                  │
│  7. 감사 체인 기록 → 상태 전환 불변 보존 (Wrkr)               │
│                                                              │
│  [메모리 갱신]                                                │
│  8. PageRank 재계산 → 중요도 업데이트                         │
│  9. MAP-Elites 셀 업데이트 → 다양성 보장                      │
│  10. Reconcile() → 드리프트 감지 + Annotation 추출            │
│                                                              │
│  [다음 사이클]                                                │
│  고점수(fitness > 0.7) 논문 → 다음 가설 컨텍스트 재주입        │
└─────────────────────────────────────────────────────────────┘
```

---

## 5부. 7개 레포 패턴 비교 매트릭스

### 5.1 에이전트 메모리 패턴 분류

7개 레포에서 발견한 패턴을 4가지 축으로 분류한다:

| 레포 | 메모리 계층화 | ID 전략 | 진화 타이밍 | 증거 강제 |
|---|---|---|---|---|
| Hyperspace AGI | 실시간/수렴/영구 3층 | 브랜치명 기반 | 실행 중 즉시 | 없음 |
| CodeGraphContext | 노드 타입 기반 | 복합 UID (이름+경로+라인) | 파일 변경 시 증분 | 없음 |
| Wrkr | 스냅샷/매니페스트/체인 3파일 | SHA-256 콘텐츠 해시 | 스캔 시 Reconcile | 없음 |
| SkillNet | 분류/관계/패키지 3층 | 스킬 이름+카테고리 | 배치 (평가 후) | 5축 평가 통과 |
| Context Hub | 커뮤니티/annotation 2층 | 문서 ID | 발견 즉시 annotation | 없음 |
| OpenViking | L0/L1/L2 콘텐츠 깊이 | URI 경로 | 세션 종료 후 자동 | 없음 |
| MiroFish | 시드/시뮬레이션/보고서 3단계 | 엔티티명 | 에이전트 행동마다 | 최소 3회 조회 |

### 5.2 우리 시스템에 적용 우선순위

즉시 적용 가능한 것(인프라 변경 없음) vs 중기(스키마 변경) vs 장기(아키텍처 변경):

**즉시 (코드 5줄 이하)**
- MiroFish 최소 증거 게이트: `if query_count < 3: continue_querying()`
- Context Hub 세션 annotation: 각 연구 세션 종료 시 발견 인사이트를 annotation 테이블에 저장
- Hyperspace 피드백 주입: fitness > 0.7인 논문을 다음 루프 프롬프트 앞에 주입

**중기 (스키마 변경)**
- OpenViking L0/L1/L2: papers 테이블에 l0_summary, l1_summary 컬럼 추가
- Wrkr 콘텐츠 해시 ID: UUID → `SHA-256(content[:500])[:16]` 변경
- Wrkr 감사 체인: audit_chain 테이블 추가 (append-only)

**장기 (아키텍처 변경)**
- SkillNet 스킬 조합 그래프: depend_on / compose_with 엣지 타입 추가
- OpenViking URI 주소 체계: `research://papers/`, `research://experiments/` 네임스페이스
- Hyperspace CRDT 분산: Loro CRDT로 멀티 인스턴스 수렴 (필요 시)

### 5.3 v1 스키마 → v2 마이그레이션

v1 스키마에서 v2로 마이그레이션하는 최소 SQL:

```sql
-- 1단계: L0/L1 요약 필드 추가
ALTER TABLE papers ADD COLUMN l0_summary TEXT;
ALTER TABLE papers ADD COLUMN l1_summary TEXT;
ALTER TABLE papers ADD COLUMN expires_at TEXT;
ALTER TABLE papers ADD COLUMN source_uri TEXT;

-- 기존 content에서 L0 자동 생성 (첫 200자)
UPDATE papers SET l0_summary = SUBSTR(content, 1, 200) WHERE l0_summary IS NULL;
UPDATE papers SET l1_summary = SUBSTR(content, 1, 2000) WHERE l1_summary IS NULL;

-- 2단계: 세션 annotation 테이블
CREATE TABLE IF NOT EXISTS annotations (
    id         TEXT PRIMARY KEY,
    paper_id   TEXT REFERENCES papers(id),
    session_id TEXT,
    content    TEXT NOT NULL,
    tags       TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- 3단계: 감사 체인 (append-only)
CREATE TABLE IF NOT EXISTS audit_chain (
    id             TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    paper_id       TEXT,
    event_type     TEXT NOT NULL,
    previous_state TEXT,
    new_state      TEXT,
    agent_id       TEXT,
    created_at     TEXT DEFAULT (datetime('now'))
);
-- 삭제/업데이트 방지 트리거
CREATE TRIGGER IF NOT EXISTS audit_chain_immutable
    BEFORE UPDATE ON audit_chain BEGIN SELECT RAISE(ABORT,'audit_chain is immutable'); END;
CREATE TRIGGER IF NOT EXISTS audit_chain_nodelete
    BEFORE DELETE ON audit_chain BEGIN SELECT RAISE(ABORT,'audit_chain cannot be deleted'); END;

-- 4단계: 스킬 의존성 엣지 (SkillNet 방식)
-- 기존 edges 테이블의 relation 컬럼에 'depend_on', 'compose_with' 값 추가만 하면 됨
-- 스키마 변경 없이 새 relation 타입으로 즉시 사용 가능
```

### 5.4 세션 시작 시 메모리 주입 패턴

Context Hub의 annotation 자동 주입을 auto_research 시스템에 적용하는 구체적 구현:

```python
def build_session_context(db: str, topic: str, session_id: str, max_tokens: int = 4000) -> str:
    """
    세션 시작 시 에이전트 프롬프트에 주입할 컨텍스트를 구성한다.
    - L0로 관련성 필터링 (전체 스캔)
    - L1을 토큰 예산 내에서 로드
    - Annotation을 최신순으로 앞에 주입
    """
    conn = sqlite3.connect(db)

    # 1. 이전 세션 annotation 로드 (가장 최근 5개, 토큰 효율)
    annotations = conn.execute("""
        SELECT a.content, a.tags, a.created_at
        FROM annotations a
        JOIN papers p ON a.paper_id = p.id
        WHERE p.topic_tag = ?
        ORDER BY a.created_at DESC LIMIT 5
    """, (topic,)).fetchall()

    # 2. L0로 관련 논문 필터 (전체 목록, 빠름)
    all_l0 = conn.execute(
        "SELECT id, l0_summary, fitness FROM papers WHERE status='active' AND topic_tag=?",
        (topic,)
    ).fetchall()

    # 3. L1 선택적 로드 (fitness 상위 + 토큰 예산 내)
    top_papers = sorted(all_l0, key=lambda x: x[2], reverse=True)[:10]
    budget, context_parts = max_tokens, []

    for pid, l0, fitness in top_papers:
        l1 = conn.execute("SELECT l1_summary FROM papers WHERE id=?", (pid,)).fetchone()[0]
        tokens_needed = len((l1 or "").split())
        if budget - tokens_needed > 0:
            context_parts.append(l1)
            budget -= tokens_needed

    # annotation → L1 순서로 주입 (최신 인사이트 먼저)
    annotation_text = "\n".join([f"[이전 발견] {a[0]}" for a in annotations])
    return annotation_text + "\n\n" + "\n\n".join(context_parts)
```

---

## 결론

v1이 "최소 무엇이 필요한가"를 답했다면, v2는 "현장에서 작동하는 시스템이 어떤 추가 패턴을 쓰는가"를 답한다.

7개 레포에서 공통으로 나타나는 패턴:
1. **메모리 계층화** (L0/L1/L2) — 토큰 효율의 핵심
2. **콘텐츠 해시 ID** — 세션 간 연속성의 기반
3. **실시간 write-back** — 분산 환경에서의 생존
4. **최소 증거 게이트** — 품질 보장의 구조화
5. **불변 감사 체인** — 신뢰와 디버깅의 기반

v1의 SQLite+WAL + LLM-as-Judge + MAP-Elites 설계는 여전히 유효하다. v2는 이 위에 **L0/L1/L2 분리, SHA-256 콘텐츠 ID, 3중 파일 영속성, 비동기 write-back, 최소 증거 게이트** 5가지를 추가한다.

여전히 오컴의 면도날은 유효하다: **평가압력 + 다양성 보존 + 상태 명시성**. 단지 각각의 구현이 1년간의 오픈소스 현장 경험으로 한 층 더 성숙해졌다.

---

## 참고 자료

### 분석한 레포지토리 (v2 신규)
- Hyperspace AGI: [github.com/hyperspaceai/agi](https://github.com/hyperspaceai/agi)
- CodeGraphContext: [github.com/CodeGraphContext/CodeGraphContext](https://github.com/CodeGraphContext/CodeGraphContext)
- Wrkr: [github.com/Clyra-AI/wrkr](https://github.com/Clyra-AI/wrkr)
- SkillNet: [skillnet.openkg.cn](http://skillnet.openkg.cn/) · [arXiv:2603.04448](https://arxiv.org/abs/2603.04448)
- Context Hub: [github.com/andrewyng/context-hub](https://github.com/andrewyng/context-hub)
- OpenViking: [github.com/volcengine/OpenViking](https://github.com/volcengine/OpenViking)
- MiroFish: [github.com/666ghj/MiroFish](https://github.com/666ghj/MiroFish)

### v1 기반 참고 문헌 (선별)
- MemGPT: [arXiv:2310.08560](https://arxiv.org/abs/2310.08560)
- A-MEM: [arXiv:2502.12110](https://arxiv.org/abs/2502.12110)
- Zep/Graphiti: [arXiv:2501.13956](https://arxiv.org/abs/2501.13956)
- LLM-as-Judge: [arXiv:2306.05685](https://arxiv.org/abs/2306.05685)
- MAP-Elites: [arXiv:1504.04909](https://arxiv.org/abs/1504.04909)
