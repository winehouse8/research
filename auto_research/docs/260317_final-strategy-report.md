# 장기기억과 평가압을 가진 자율 연구 에이전트 — 최종 전략 보고서

**작성일**: 2026-03-17
**기반 문서**: `260317_research-ecosystem-design.md`, `260317_autoresearch-agent-sdk.md`, `260317_agent-science-community.md`, `260317_agent-ecosystem-minimal.md`, `260317_agent-ecosystem-minimal-v2.md`
**목적**: 지금까지의 모든 연구를 통합하여 "장기기억 + 평가압을 가진 연구 에이전트"의 최종 구현 전략을 정리

---

## 요약 (두괄식 핵심)

**우리는 무엇을 만드는가**: 단발성 `claude -p` 루프를 넘어, **지식이 축적되고 경쟁하고 진화하는** 자율 연구 생태계.

**왜 지금 만들 수 있는가**:
1. **장기기억**: L0/L1/L2 계층화 + SHA-256 콘텐츠 ID + 세션 간 annotation으로 에이전트가 재시작 후에도 이전 발견을 이어받는다
2. **평가압**: `comparisons(winner, loser)` 테이블 하나로 충분 — pairwise LLM 판단이 자연선택압이 된다
3. **진화**: MAP-Elites 다양성 + PageRank 중요도 + archived 상태로 도태와 보존이 동시에 일어난다

**핵심 설계 결정 요약**:

| 결정 | 선택 | 이유 |
|---|---|---|
| 저장소 | SQLite + WAL | 의존성 0, 동시 쓰기 가능, 에이전트 친화적 |
| 평가 | LLM-as-Judge pairwise | 가장 단순하고 검증된 방법 |
| 다양성 | MAP-Elites (topic × perspective) | 국소 셀 경쟁으로 소수설 보호 |
| 중요도 | PageRank (comparisons 그래프) | "많이 반박받는 논문 = 중요한 논문" |
| 메모리 로딩 | L0(필터) → L1(추론) → L2(전문) | 토큰 91% 절감 (OpenViking 검증) |
| 에이전트 구조 | Planner-Executor-Reflector | 역할 분리 + 모델별 비용 최적화 |
| 실행 기반 | Claude Agent SDK (Python) | claude -p 한계 극복, 서브에이전트 지원 |

**풀린 이슈**: 14개 (핵심 아키텍처 전부 확정)
**안 풀린 이슈**: 10개 (구현 세부사항 + 철학적 한계)
**즉시 시작 가능한 첫 단계**: Q6(에이전틱 메모리) 주제로 papers 10개 시드 → 루프 10회 파일럿

---

## 1. 연구 배경 — 무엇을 해결하려 하는가

### 1.1 기존 autoresearch의 한계

```
ralph.sh (기존):
  while true:
    claude -p "$(cat program.md)" → 단일 에이전트 → 결과
    sleep 5
```

이 방식의 근본 문제:
- **학습 없음**: 각 이터레이션이 이전 이터레이션을 기억하지 못한다
- **평가 없음**: 좋은 결과와 나쁜 결과가 동등하게 취급된다
- **진화 없음**: 생산만 있고 도태와 선택이 없다

`results.tsv`는 선형 로그일 뿐이다. 에이전트는 "지금 무엇을 알고 있는가"가 아니라 "지금까지 무엇을 했는가"만 볼 수 있다.

### 1.2 두 종류의 연구 문제

| 유형 | 예시 | 평가 방법 |
|---|---|---|
| **A형: 정답 있음** | val_bpb 최소화, 알고리즘 증명 | 수치 메트릭으로 즉시 판단 |
| **B형: 진실 수렴** | 유가 예측, 에이전틱 메모리 설계 | 반론 내성으로 간접 판단 |

기존 autoresearch는 A형에 최적화되어 있다. 이 보고서가 설계하는 시스템은 **B형을 위한 것**이다.

B형에서의 "진실"은 접근 불가능하다. 우리가 할 수 있는 최선은 **"현재 증거 기준으로 가장 반박하기 어려운 가설의 집합"** 을 점진적으로 정제하는 것이다.

### 1.3 설계 철학

> **"에이전트가 좋은 논문을 쓰도록 하는 것이 아니라, 나쁜 논문이 자연스럽게 도태되는 생태계를 설계하는 것."**

AlphaGo 원리: "이기면 좋다"만 정의하면 전략은 에이전트가 찾는다.
우리 원리: "살아남으면 좋다"만 정의하면 좋은 지식 생산 방법은 에이전트가 발견한다.

---

## 2. 확정된 최종 아키텍처

### 2.1 3원칙 (오컴의 면도날 적용)

7개 최신 오픈소스 레포지토리 분석 결과, 3가지 원칙이 모든 성공적인 에이전트 지식 시스템에서 공통으로 나타났다:

**① 평가압력 (Selection Pressure)**
생성된 지식이 비교 경쟁에서 도태되는 메커니즘. 기준은 "좋은가/나쁜가"가 아니라 "지금 이 셀에서 상대보다 나은가"로 충분하다.

구현: `comparisons(winner, loser, created_at)` — **3컬럼이 전부**.

```sql
fitness = wins / total_matches  -- comparisons 테이블에서 파생
```

**② 다양성 보존 (Diversity Maintenance)**
MAP-Elites 원리: `topic × perspective` 2차원 격자에서 각 셀에 최소 1개 생존자 보장. 전역 순위에서 지면 도태되지만, 자신의 셀에서 이기면 살아남는다.

구현: `topic_tag + perspective` 필드로 셀 주소 지정, `archived` 상태(삭제 없음).

**③ 상태 명시성 (Explicit State)**
에이전트는 상태를 기억하지 못한다. 모든 지식의 현재 상태(fitness, 관계, 나이)는 외부 저장소에 명시적으로 기록되어야 한다.

구현: SQLite + WAL + 불변 감사 체인(audit_chain).

### 2.2 장기기억 아키텍처 — v2 스키마

5개 문서와 7개 오픈소스 분석을 통해 수렴한 **최종 스키마**:

```sql
-- 논문/보고서 노드 (L0/L1/L2 계층화, OpenViking 패턴)
CREATE TABLE papers (
    id              TEXT PRIMARY KEY,   -- SHA-256(content[:500])[:16] — 결정론적 ID
    claim           TEXT NOT NULL,      -- 핵심 주장 한 문장
    l0_summary      TEXT,               -- ~50 토큰: 관련성 필터용
    l1_summary      TEXT,               -- ~2000 토큰: 계획·추론용
    l2_content      TEXT,               -- 전문: on-demand 로드
    evidence_sources TEXT,              -- JSON: [{title, url, citation_count, excerpt}]
    assumptions     TEXT,               -- 성립 조건 (반박 가능성 게이트)
    fitness         REAL DEFAULT 0.5,   -- PageRank 기반 중요도
    status          TEXT DEFAULT 'active',  -- active|contested|foundational|archived
    topic_tag       TEXT,               -- MAP-Elites 셀 주소
    perspective     TEXT,               -- empirical|theoretical|applied|critical
    expires_at      TEXT,               -- TTL 기반 재검토 기준 시각
    created_at      TEXT,
    source_uri      TEXT                -- 검색 경로 감사 (OpenViking DRR 방식)
);

-- pairwise 비교 결과 (평가압력의 핵심)
CREATE TABLE comparisons (
    winner      TEXT REFERENCES papers(id),
    loser       TEXT REFERENCES papers(id),
    created_at  TEXT
);
-- 전부. agent_id, judge_score, relation_type 없음 — fitness는 여기서 파생.

-- 지식 관계 그래프 (Zep 시간축 방식)
CREATE TABLE edges (
    id          TEXT PRIMARY KEY,
    src         TEXT REFERENCES papers(id),
    dst         TEXT REFERENCES papers(id),
    relation    TEXT,   -- supports|contradicts|extends|derived_from|depend_on
    strength    REAL DEFAULT 1.0,
    created_at  TEXT,
    valid_until TEXT    -- NULL = 여전히 유효. 만료 시 삭제 대신 만료 처리.
);

-- 세션 간 annotation (Context Hub 패턴: 에이전트의 개인 장기 메모리)
CREATE TABLE annotations (
    id          TEXT PRIMARY KEY,
    paper_id    TEXT REFERENCES papers(id),
    session_id  TEXT,
    content     TEXT NOT NULL,  -- "이 논문은 X 조건에서만 유효함"
    tags        TEXT,           -- JSON 배열
    created_at  TEXT
);

-- 불변 감사 체인 (Wrkr 패턴: append-only, 삭제/수정 불가)
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

**핵심 패턴 5가지** (7개 오픈소스에서 수렴):

| 패턴 | 출처 | 효과 |
|---|---|---|
| L0/L1/L2 계층 로딩 | OpenViking (ByteDance 2026) | 토큰 비용 91% 절감 |
| SHA-256 콘텐츠 ID | Wrkr | 세션 간 동일 노드 재연결 |
| Zep 시간축 엣지 | Zep/Graphiti (arXiv:2501.13956) | "언제 반박됐는가" 감사 추적 |
| 세션 annotation | Context Hub (Andrew Ng) | 이전 세션 발견 자동 주입 |
| 실시간 write-back | MiroFish/Hyperspace | 중단 시에도 발견 보존 |

### 2.3 평가압력 시스템

**판단 기준 (단순화)**:

```
기본 judge 프롬프트:
  "제시된 근거가 결론을 실제로 지지하는가?"

대립인 경우:
  "A와 B 중 어느 주장이 제시된 근거에 의해 더 잘 지지되는가?
   단, 반박에 새로운 예측으로 응답한 쪽(라카토슈 진보)을 더 높이 평가한다."

보완인 경우:
  "A와 B가 같은 결론인데, 어느 쪽 근거가 더 강한가?"
```

**Position bias 제거**: A→B, B→A 순서로 두 번 평가, 두 번 모두 일치한 경우만 확정.

**과학철학 3종 조합**:

| 역할 | 철학 | 구현 |
|---|---|---|
| 게이트키퍼 (진입 필터) | **포퍼**: 반증 불가능 주장 제외 | assumptions 필드 필수 |
| 주 엔진 (신뢰도 갱신) | **베이즈**: evidence 기반 fitness 업데이트 | comparisons → fitness |
| 평가 기준 (진보/퇴행) | **라카토슈**: 새 예측 제시 vs 땜질 | judge 프롬프트 보너스 |

### 2.4 에이전트 구조 — Planner-Executor-Reflector

**실행 기반**: Claude Agent SDK (Python). `claude -p`는 one-shot이라 스킬/훅/서브에이전트가 작동하지 않는다. SDK는 Python이 루프를 완전 제어하며 비용 최적화(역할별 모델 선택)가 가능하다.

```
research_agent (연구 루프):
  입력: topic_tag, 상위 fitness 3개(L1) + 랜덤 2개(L1) + 이전 세션 annotations
  도구: WebSearch, WebFetch, (Bash — Q4~Q7용)
  출력: papers 테이블에 새 논문 추가

pair_compare_agent (평가 루프):
  입력: 같은 topic_tag의 두 논문 (claim 분류 후)
  도구: 없음 (읽기만)
  출력: comparisons 테이블에 (winner, loser) 기록

reflector_agent (메모리 갱신):
  입력: 비교 결과, 현재 상태
  도구: Read, Write, Edit
  출력: annotations 갱신, audit_chain 기록, PageRank 재계산 트리거
```

**모델별 역할 분배 (비용 최적화)**:

```
Planner (컨텍스트 읽기, 전략 수립)    → claude-haiku-4-5  (저비용)
Researcher (검색, 논문 작성)           → claude-sonnet-4-6 (실행력)
Comparator (pairwise 판단)             → claude-haiku-4-5  (저비용, 반복 많음)
Reflector (메모리 갱신, 상태 관리)     → claude-haiku-4-5  (저비용)
```

### 2.5 메인 루프

```python
async def research_loop(topic: str, max_cycles: int = 100):
    """
    메인 진화 루프 — 3원칙 구현
    """
    for cycle in range(max_cycles):
        # ── 세션 컨텍스트 구성 (L0 필터 → L1 로드 → annotation 주입) ──
        context = build_session_context(db, topic, session_id)
        # OpenViking: L0 전체 스캔 → 관련성 0.7 이상만 L1 로드
        # Context Hub: 이전 세션 annotations를 프롬프트 앞에 주입

        # ── Phase 1: 최소 증거 게이트 ──
        # MiroFish: 출력 전 최소 3회 메모리 조회 강제
        evidence = []
        for _ in range(3):
            q = llm_generate_query(topic, context)
            evidence.append(search_papers(db, q))

        # ── Phase 2: 새 논문 생성 (30% 확률로 반박 논문) ──
        if random.random() < 0.3:
            champion = get_champion(db, topic)
            new_paper = research_agent(topic, context, instruction="반박 논문 작성")
        else:
            new_paper = research_agent(topic, context)

        pid = sha256_id(new_paper["content"])
        asyncio.create_task(db_save_paper(db, pid, new_paper))  # 비동기 write-back

        # ── Phase 3: claim 분류 후 비교 ──
        rival = select_rival(db, topic)  # 70% 챔피언, 30% 랜덤
        relation = classify_claims(new_paper["claim"], rival["claim"])

        if relation != "직교":
            # Position bias 제거: A→B, B→A 두 번 평가
            r1 = llm_judge(new_paper, rival, JUDGE_PROMPT, relation)
            r2 = llm_judge(rival, new_paper, JUDGE_PROMPT, relation)
            if r1.winner == r2.winner:
                db.save_comparison(r1.winner, r1.loser)
                db.update_fitness_pagerank(topic)

        # ── Phase 4: 상태 갱신 ──
        update_lifecycle_states(db, topic)    # active→contested→foundational→archived
        update_map_elites_grid(db, topic)     # 셀별 최강자 갱신
        reconcile_and_annotate(db, session_id)  # Wrkr Reconcile + annotation 추출

        await asyncio.sleep(5)
```

---

## 3. 풀린 이슈 (해결됨)

### ✅ 아키텍처 핵심

**이슈 A: 그래프 DB 역할 혼동**
- 해결: 그래프 = "발견된 관계의 정리장". 검색/발견은 SQL 필터 + LLM 판단이 담당.
- 결론: `edges(src, dst, relation, valid_until)` 테이블 + SQL 쿼리로 충분.

**이슈 B: 벡터 임베딩의 필요성**
- 해결: 불필요. L0 요약 + SQL 필터 + LLM 일괄 판단이 더 정확하다는 사용자 경험 + 오픈소스 현장 검증.
- 결론: FAISS/sqlite-vss 없이 L0/L1/L2 계층화로 충분.

**이슈 C: 평가 시스템 설계**
- 해결: `comparisons(winner, loser, created_at)` 3컬럼이 전부. `fitness = wins/total_matches`.
- 근거: "누가 평가했나"는 의미 없다. 결과 사실만 기록한다.

**이슈 D: 피어리뷰 vs 반박 논문 구분**
- 해결: 인프라 관점에서 동일. 생성 프롬프트만 다를 뿐, 평가 메커니즘은 같다.

### ✅ 메모리 아키텍처

**이슈 E: 토큰 폭발 문제**
- 해결: L0(50토큰) → L1(2000토큰) → L2(전문) 계층화 로딩. 수백 개 논문이 쌓여도 토큰 예산 내 작동.
- 근거: OpenViking이 실제 91% 토큰 절감 검증.

**이슈 F: 세션 간 메모리 손실**
- 해결: SHA-256 콘텐츠 해시 ID (재시작 후 동일 노드 재연결) + `annotations` 테이블 (세션 발견 지속).
- 근거: Wrkr의 결정론적 ID 패턴, Context Hub의 annotation 자동 주입.

**이슈 G: 중단 시 발견 손실**
- 해결: 비동기 write-back. 에이전트가 작업 중에도 메모리 실시간 갱신.
- 근거: MiroFish, Hyperspace AGI 실증.

**이슈 H: 상태 추적 신뢰성**
- 해결: `audit_chain` 불변 감사 체인 (append-only). "왜 archived됐는가"를 항상 추적 가능.
- 근거: Wrkr의 proof chain 패턴.

### ✅ 평가압력 설계

**이슈 I: LLM 평가 편향**
- 해결 (부분): Position bias → A→B, B→A 두 번 평가. Verbosity bias → 라카토슈 보정 (새 예측 보너스, 땜질 패널티).
- 한계: LLM이 특정 스타일 선호는 완전 제거 불가.

**이슈 J: 소스 신뢰도 평가**
- 해결: URL 기반 자의적 점수 없음. `citation_count` (Semantic Scholar API) + 원문 발췌를 judge에게 직접 전달. judge가 스스로 판단.

**이슈 K: 비교 불가능한 논문 처리**
- 해결: claim 분류 → 대립(pairwise 대결) / 보완(근거 대결) / 직교(비교 없음, 공존).
- 보완 논문은 둘 다 fitness 상승. 실제 학계처럼 독립 복제가 강화.

### ✅ 다양성 보존

**이슈 L: 조기 수렴 방지**
- 해결: MAP-Elites `topic × perspective` 격자. 전역 경쟁이 아닌 셀 내 경쟁.
- 추가: 소수설 보호 (최소 15% 정설 반론 논문 유지 강제).

**이슈 M: 챔피언 과적합**
- 해결: rival 선택 = 70% 챔피언 + 30% 랜덤. SGD-inspired 탐색.

### ✅ 구현 기반

**이슈 N: claude -p의 한계**
- 해결: Claude Agent SDK 전환. Python이 루프를 완전 제어. 서브에이전트, 역할 분리, asyncio 병렬화 모두 가능.
- 근거: `claude -p`에서 스킬/훅 비활성화는 공식 문서 명시 사항.

---

## 4. 안 풀린 이슈 (미해결)

### 🔴 구현 필요 (설계 확정 안 됨)

**이슈 1: claim 분류의 신뢰성**

두 논문의 claim이 "대립/보완/직교"인지 자동 분류하는 것 자체가 LLM에 의존한다. 이 분류가 틀리면 잘못된 비교가 발생한다.

- **현재 상태**: 후보 해결만 존재 (claim 분류 전용 경량 LLM + 불확실할 때 "직교" 기본값)
- **왜 어려운가**: LLM이 claim 관계를 과잉 해석하거나 미해석할 수 있다. 정확도 측정 방법도 없다.
- **권장 접근**: 먼저 "직교" 기본값으로 구현 → 비교 결과를 인간이 샘플링하여 분류 정확도 측정 → 이후 정제

---

**이슈 2: topic_tag 자동 할당**

새 논문이 생성될 때 어떤 `topic_tag`를 붙이는가? 자동 할당 방법이 없으면 MAP-Elites 셀이 의미없어진다.

- **현재 상태**: "사전 정의된 분류 체계 + LLM 분류" 방향만 제시됨
- **왜 어려운가**: 분류 체계를 사전에 정의해야 하는데, 연구가 진행되면서 새 카테고리가 생긴다
- **권장 접근**: 초기 topic_tag를 5~10개로 고정 + 논문이 일정 수 이상 쌓이면 LLM으로 클러스터링 재조정

---

**이슈 3: 콜드 스타트**

시스템 시작 시 papers가 0개다. 초기 시드 논문을 어떻게 확보하나?

- **현재 상태**: "arXiv 자동 수집" 제안만 있음
- **왜 중요한가**: 첫 비교가 이루어지려면 최소 2개 논문이 필요하다. 5~10개 이하면 MAP-Elites 셀이 거의 비어있다
- **권장 접근**: Phase 1에서 수동으로 10개 시드 논문 작성 + arXiv/Semantic Scholar API로 관련 논문 3~5개 자동 수집

---

**이슈 4: 코드 실행 환경 격리**

Q4(LLM 성능), Q5(행렬 알고리즘), Q6(에이전틱 메모리), Q7(로컬 챗봇)에서 에이전트가 직접 코드를 실행한다. 악성 코드, 무한 루프, OOM 방지 필요.

- **현재 상태**: "Docker 격리 + 타임아웃 + 자원 제한" 방향만 제시됨
- **왜 어려운가**: Docker 컨테이너 내에서 Claude Agent SDK가 작동하도록 환경 구성이 복잡하다
- **권장 접근**: 우선 타임아웃 + ulimit으로 시작. Docker 격리는 Phase 3에서 추가.

---

**이슈 5: 수렴 판단 기준**

시스템이 언제 "충분히 탐색했다"고 판단하나?

- **현재 상태**: "fitness 분포의 분산이 임계값 이하" 후보 해결
- **왜 어려운가**: 수렴 ≠ 정답 도달. 수렴은 "현재 탐색 전략으로 더 개선이 없다"는 뜻일 수 있다
- **권장 접근**: 수렴 감지는 알림(emit event)만 하고 루프를 멈추지 않는다. 인간이 수렴 여부를 최종 판단.

---

### 🟡 부분 해결 (구현 불확실)

**이슈 6: 인터넷 검색 품질 (Q1 유가, Q3 역사)**

실제 에이전트가 수행 불가능한 실험을 대체할 수 있는 인터넷 정보의 품질이 들쑥날쑥하다.

- **현재 최선**: `citation_count` (Semantic Scholar) + 원문 발췌를 judge에게 직접 전달
- **한계**: 오래된 정보, 상충되는 출처, 저품질 블로그 등을 LLM이 완벽히 필터링하지 못한다
- **영향**: Q1, Q3 주제는 신뢰도가 Q4~Q7(코드 실험) 대비 낮을 수밖에 없음. 이 한계를 명시하고 운영.

---

**이슈 7: perspective 축 정의**

MAP-Elites의 `perspective` 차원을 어떻게 정의하나?

- **후보**: empirical / theoretical / applied / critical (4개 고정)
- **미결**: 이 4개가 모든 연구 주제에 적합한가? 연구 주제에 따라 perspective 분류가 달라야 하는가?

---

**이슈 8: Research Direction Drift**

품질 기반 진화만 하면 시스템이 원래 연구 질문에서 벗어나 "쓰기 쉬운 방향"으로 수렴한다.

- **현재 최선**: 매 5 사이클마다 research_question 커버리지 계산. 0.6 이하면 novelty 가중치 증가.
- **한계**: "커버리지"를 어떻게 계산하는가 자체가 LLM 의존적이고 측정 방법이 미확정.

---

**이슈 9: 다중 주제 병렬 운영**

여러 topic을 동시에 진화시킬 때 Cross-Field Pollination(타 분야 오염)이 어떻게 작동하는가?

- **현재 상태**: 설계 아이디어만 존재 (매 N사이클마다 다른 topic 논문 1개 삽입)
- **미결**: 어떤 주제 조합이 유익한 cross-pollination을 만드는가?

---

### 🟢 철학적 미해결 (수용하고 진행)

**이슈 10: 규범적 질문 (Q2 과학철학)**

순수 철학적 질문은 이 시스템으로 잘 다루기 어렵다. pairwise 비교가 "더 정교하게 들리는 쪽"을 선택하는 경향이 있다.

→ **수용 결정**: Q2형 질문은 시스템 범위 밖으로 설정. 이 한계는 알고 있고, 경험적 반증이 가능한 질문에만 시스템을 적용한다.

**이슈 11: 진리 vs 합리성**

이 시스템은 "진리"가 아닌 "현재 증거 기준으로 가장 반박하기 어려운 가설"을 찾는다.

→ **수용 결정**: 시스템 출력물에 항상 이 한계를 명시. 인간 판단의 보조 도구로 포지셔닝.

---

## 5. 구현 로드맵

### Phase 1: MVP (1~2주) — 즉시 시작 가능

**목표**: 동작하는 최소 진화 루프 확인

**핵심 파일 구조**:
```
auto_research/
  db/
    knowledge.db        ← SQLite (papers + comparisons + edges + annotations + audit_chain)
  agents/
    research_agent.py   ← 새 논문 생성
    compare_agent.py    ← pairwise 비교
    reflector_agent.py  ← 메모리 갱신
  core/
    schema.sql          ← 최종 스키마
    memory.py           ← L0/L1/L2 로딩 + annotation 주입
    fitness.py          ← PageRank + MAP-Elites
  autoresearch_v2.py    ← 메인 루프
```

**구현 순서**:
1. `schema.sql`: v2 스키마 확정 + audit_chain 트리거
2. `memory.py`: L0 필터링, L1 로딩, annotation 주입
3. `compare_agent.py`: pairwise judge (A→B, B→A 두 번)
4. `fitness.py`: comparisons → PageRank → fitness 업데이트
5. `research_agent.py`: L1 컨텍스트 + 새 논문 생성
6. `autoresearch_v2.py`: 메인 루프 (최소 증거 게이트 포함)

**첫 파일럿 조건**:
- **주제**: Q6 (에이전틱 메모리) — 코드 실험 가능, 현재 연구 중인 주제
- **시드**: 수동 10개 논문 (기존 5개 문서에서 핵심 주장 추출)
- **목표**: 10 iteration 후 비교 로그 확인 + fitness 분포 관찰

**성공 기준**:
- `comparisons`에 30+ 항목
- 최소 1개 논문 `archived` 상태 전환
- 최소 1개 논문 `fitness > 0.7` (챔피언 형성)
- 비용: cycle당 $0.5 이하

---

### Phase 2: 안정화 (2~4주)

**목표**: 생태계 메타데이터 완성 + 세션 간 연속성 검증

1. annotation 자동 추출 → 다음 세션 자동 주입 확인
2. Reconcile 상태 머신 + 드리프트 감지
3. `foundational` 상태 추가 + PageRank 기반 자동 승격
4. claim 분류 로직 구현 (직교 기본값으로 시작)
5. topic_tag 자동 할당 프로토타입

**성공 기준**:
- 50 cycle 후 `foundational` 논문 1개 이상 존재
- 세션 재시작 후 이전 발견이 annotation으로 자동 주입됨 확인
- audit_chain으로 "논문 X가 언제 왜 archived됐는가" 추적 가능

---

### Phase 3: 확장 (1개월+)

**목표**: 코드 실험 + 인터넷 검색 품질 개선

1. Docker 격리 코드 실행 환경 (Q4, Q5, Q6, Q7용)
2. Semantic Scholar API 통합 (citation_count 자동 수집)
3. Cross-Field Pollination (매 10 cycle 타 주제 논문 1개 삽입)
4. 수렴 감지 + 알림 시스템
5. 인간 피어리뷰 주입 인터페이스

---

## 6. 적용 주제별 예상 효과

| 주제 | 에이전트 실험 | 기대 강도 | 풀린 이슈 | 남은 장벽 |
|---|---|---|---|---|
| **Q6. 에이전틱 메모리** | ✅ 구현+테스트 | **최강** | 거의 없음 | 코드 실행 격리 |
| **Q4. LLM 성능** | ✅ 벤치마크 실행 | **최강** | 거의 없음 | 코드 실행 격리 |
| **Q5. 행렬 알고리즘** | ✅ 증명+코드 | **최강** | 거의 없음 | 코드 실행 격리 |
| **Q7. 로컬 LLM 챗봇** | ✅ GPU 벤치마크 | **최강** | 거의 없음 | 코드 실행 격리 |
| **Q1. 유가 예측** | ❌ 검색만 | **중간** | 이슈 6 부분 해결 | 검색 품질 |
| **Q3. 역사 연구** | ❌ 검색만 | **중간** | 이슈 6 부분 해결 | 1차 사료 접근성 |
| **Q2. 과학철학** | ❌ | **약함** | 이슈 10 수용됨 | 구조적 한계 |

**권장 순서**: Q6 → Q4/Q5/Q7 → Q1/Q3 → Q2(범위 제외)

---

## 7. 핵심 기술 스택 최종 선택

```
언어:          Python 3.10+
에이전트:       Claude Agent SDK (pip install claude-agent-sdk)
모델:           Haiku 4.5 (계획/평가), Sonnet 4.6 (연구 실행)
저장소:         SQLite 3 (Python 내장, 의존성 0) + WAL 모드
그래프:         networkx (PageRank, 5줄)
해시:           hashlib SHA-256 (Python 내장)
비동기:         asyncio (Python 내장)
스케줄러:       tmux + nohup (간단한 백그라운드 실행)

선택하지 않은 것:
  ❌ FAISS/sqlite-vss (벡터 임베딩) — L0 + LLM이 더 정확
  ❌ Neo4j/ArangoDB    — SQLite WAL로 충분
  ❌ CrewAI/AutoGen   — 오버헤드 높음, 루프 제어 약함
  ❌ LangGraph         — Claude Agent SDK가 더 통합적 (claude 전용)
```

---

## 8. 결론

이 보고서가 정리하는 최종 답은 간단하다:

**장기기억**: `L0/L1/L2 계층화 + SHA-256 ID + annotations 테이블` — 에이전트가 재시작 후에도 이전 발견을 이어받는다.

**평가압**: `comparisons(winner, loser)` 테이블 — 2컬럼이 자연선택압 전체를 구현한다.

**진화**: `MAP-Elites 격자 + PageRank + archived 상태` — 도태와 보존이 동시에 일어난다.

이 세 가지가 합쳐지면 "단순한 저장 + 반복 루프"에서 "생성 + 평가 + 도태 + 보존 루프"로 진화한다.

인간 학계 2000년이 학술지, 학회, 동료 심사, 저자 명성을 통해 구현한 것을, 에이전트 환경에서는 **while 루프 하나 + SQLite DB 하나 + LLM 판사 하나**로 구현한다.

설계자가 할 일은 최초 주제를 주입하고, 루프를 시작하는 것뿐이다.

---

## 부록: 핵심 설계 결정 요약표

| 결정 | 초기 혼동 | 최종 결론 | 근거 |
|---|---|---|---|
| 그래프 DB 역할 | 검색 + 관계 동시 | 관계 기록만. 검색은 SQL + LLM | 그래프는 완전성 불필요 |
| 임베딩 | FAISS 필수 | 불필요 | L0 + LLM이 더 정확 |
| 평가 테이블 | agent_id, rubric, score | winner, loser, created_at | "누가 평가했나" 의미 없음 |
| 피어리뷰/반박 구분 | 별도 처리 | 동일 인프라 | 프롬프트만 다름 |
| claim 분류 | 복잡한 온톨로지 | 대립/보완/직교 3분류 | 단순함이 실용적 |
| 평가 rubric | 6개 축 | "근거가 결론을 지지하는가?" | 알파고 원리 |
| 소스 신뢰도 | URL 기반 점수 | citation_count + 원문 발췌 | 객관적 데이터만 |
| 메모리 로딩 | 전체 로딩 | L0 → L1 → L2 | 토큰 91% 절감 |
| 에이전트 ID | UUID | SHA-256(content) | 세션 간 재연결 |
| 실행 기반 | claude -p | Claude Agent SDK | 스킬/서브에이전트 필요 |

---

*참고 문서:*
- `260317_research-ecosystem-design.md`: 핵심 설계 결정 기록
- `260317_autoresearch-agent-sdk.md`: Agent SDK 기반 아키텍처
- `260317_agent-science-community.md`: 과학 공동체 시뮬레이션 설계
- `260317_agent-ecosystem-minimal.md`: 오컴의 면도날 단순화 (v1)
- `260317_agent-ecosystem-minimal-v2.md`: 오픈소스 7개 분석 업데이트 (v2)
