# 에이전트 기반 과학 공동체 시뮬레이션 설계 보고서

**날짜**: 2026-03-17
**목적**: 학문 공동체의 지식 진화 메커니즘을 에이전트로 시뮬레이션하기 위한 게임 룰 설계
**범위**: 평가 시스템 이론, 논문 생태계 설계, 구현 로드맵

---

## 목차

1. 왜 이것을 만드는가 — 문제 프레이밍
2. 학계의 지식 진화 메커니즘 분석
3. 알고리즘 선택: 피드백 비판적 수용
4. 논문(Paper) 객체 및 생애주기 설계
5. 게임 룰: 사이클 구조
6. 창의적 확장 아이디어
7. 구현 로드맵
8. 한계와 열린 질문들

---

## 1. 왜 이것을 만드는가 — 문제 프레이밍

### 1.1 두 종류의 진실 탐색

지식 탐색에는 두 가지 근본적으로 다른 유형이 있다.

**유형 A: 정답이 있는 탐색**
- 딥러닝 모델의 val_bpb 최소화
- 수학 증명의 정확성
- 알고리즘의 시간복잡도

이 유형에서는 평가 함수가 명확하다. 숫자 하나로 "이 실험이 지난 실험보다 낫다"를 즉시 판단할 수 있다. 기존의 `ralph.sh` 기반 autoresearch는 여기에 최적화되어 있다.

**유형 B: 진실에 수렴하는 탐색**
- "유가 급등 우려의 근거와 반론은 무엇인가?"
- "온프레미스 24GB GPU에 최적인 LLM은 무엇인가?"
- "다크 에너지는 무엇인가?"

이 유형에서는 정답이 없다. 더 정확히는, **진실은 존재하지만 우리가 접근할 수 없다**. 우리가 할 수 있는 최선은 "진실에 가까운 가설의 집합"을 점진적으로 정제하는 것이다.

이 보고서는 유형 B를 위한 에이전트 시스템을 설계한다.

### 1.1.1 머신러닝 벤치마크와 인문·비정형 지식 평가의 구조적 차이

머신러닝 벤치마크는 평가 자체가 수렴적이다. MMLU 점수, val_loss, pass@k 같은 지표는 동일한 테스트셋에 대해 누가 측정하든 같은 숫자가 나온다. 평가자가 개입할 여지가 없고, 결과는 재현 가능하며, 두 모델 중 어느 쪽이 낫다는 판단에 이견이 없다. 이것이 autoresearch의 기존 접근 — `results.tsv`에 val_bpb를 기록하고 낮은 값을 추구하는 방식 — 이 잘 작동하는 이유다.

인문·비정형 지식 평가는 본질적으로 발산적이다. "유가 급등 우려가 얼마나 타당한가"에는 동일한 데이터를 보고도 경제학자, 지정학 전문가, 환경운동가가 각각 다른 답을 낸다. 이것은 그들 중 누군가가 틀렸다는 뜻이 아니라, **평가 기준 자체가 복수이고 문맥에 의존**하기 때문이다. 역사 해석에서는 어떤 사료를 더 신뢰하느냐는 학파에 따라 다르고, 정책 분석에서는 가치 판단(성장 우선 vs 형평성 우선)이 결론을 바꾼다. 따라서 이 영역에서 "정답"을 수렴하는 단일 점수를 만들려는 시도는 근본적으로 잘못된 질문을 하는 것이다. 대신 "현재 가장 많은 반론을 버텨낸 가설"을 추적하는 것이 올바른 목표다.

### 1.2 핵심 통찰: 진화 생태계 vs 랭킹 시스템

처음에는 "논문들을 랭킹하면 되겠다"는 직관이 자연스럽다. 하지만 이것은 근본적으로 잘못된 프레이밍이다.

**랭킹 시스템의 문제**:
- 단일 스칼라 값으로 논문의 가치를 표현 불가
- 각 논문 간의 *관계*를 무시
- 새로운 혁명적 이론이 초기에 낮은 랭킹을 받아 도태되는 구조
- "좋다/나쁘다"는 문맥에 의존 — 무엇을 위해 좋은가?

**진화 생태계의 특성**:
- 논문은 독립 개체가 아니라 *관계망 속의 노드*
- 가치는 타 논문과의 지지/반박 상호작용에서 창발
- "진실에 가까움"은 생존 압력(반박 내성)으로 구현
- 소수설은 보호되어야 한다 — 다음 패러다임 전환이 여기서 시작되므로

이 시스템을 만드는 것은 결국 **인공 자연선택압**을 설계하는 일이다.

### 1.3 에이전트 시뮬레이션의 한계 (솔직하게)

이 시스템이 *실제 학계와 다른 점*도 명확히 해야 한다:

- **에이전트는 실험을 수행하지 못한다**: 유가 분석에서 실제 유가 데이터를 수집하거나 천문 관측을 할 수 없다. 기존 공개 정보를 재조합하는 수준.
- **새로운 데이터 생성 불가**: 실험 과학에서 진짜 검증은 새 데이터로 한다. 에이전트는 기존 문헌에 의존.
- **전문가 암묵지 없음**: 수십 년 분야 경험에서 나오는 직관을 에이전트는 가지지 못한다.
- **합의 형성의 사회적 차원 없음**: 학계에서 정설 형성에는 학회, 교과서 저자, 기관 권위가 관여한다.

따라서 이 시스템의 목표는 "학계를 대체"가 아니라, **"빠른 문헌 탐색 + 가설 구조화 + 반론 자동 발굴"** 의 자동화다.

---

## 2. 학계의 지식 진화 메커니즘 분석

### 2.1 3계층 구조

실제 학문 공동체는 동시에 작동하는 3개의 메커니즘 레이어가 있다.

```
Layer 1: 생산 (Exploration)
  연구자 → 가설 → 실험/논증 → 논문
  특징: noisy, 다양, 틀린 것 많이 포함

Layer 2: 필터링 (Gatekeeping)
  피어리뷰 → accept/reject/revise
  특징: 최소 품질 기준, 하지만 불완전

Layer 3: 진화 (Selection)
  인용, 재현, 반박, 시간
  특징: 가장 강력한 필터, 느리지만 robust
```

**핵심**: 피어리뷰(Layer 2)는 과대평가되고 있다. 진짜 지식 선별은 Layer 3에서 일어난다.

토마스 쿤의 패러다임 전환이 이를 증명한다: 코페르니쿠스, 다윈, 아인슈타인의 이론은 모두 초기에 Layer 2를 통과하기 어려웠다. 그러나 Layer 3 (시간 + 누적 검증)이 결국 이들을 정설로 만들었다.

### 2.2 평가 메커니즘 분류 및 에이전트 매핑

| 학계 메커니즘 | 역할 | 에이전트 구현 | 비고 |
|---|---|---|---|
| **Peer Review** | 초기 품질 필터 | `reviewer_agent` (4축 평가) | 보수적 bias 주의 |
| **Citation** | 영향력 측정 | `support_graph` (논문 간 링크) | PageRank 유사 |
| **Replication** | 주장 검증 | `replicator_agent` (증거 검색) | 가장 강한 검증 |
| **Adversarial** | 반박 생성 | `adversarial_critic` (반례 발굴) | 핵심 필터 |
| **Meta-analysis** | 통합 분석 | `synthesizer_agent` (상위 논문 통합) | 정설 형성 |
| **Prediction Markets** | 칼리브레이션 | `uncertainty` (σ 값) | TrueSkill |
| **Registered Reports** | 방법론 사전등록 | `methodology_precheck` | optional |

### 2.3 무엇이 정설을 만드는가?

학계에서 "정설"이 되는 조건:

1. **반박에 살아남기**: 다수의 독립적 반론을 견뎌낸 이론
2. **재현 성공**: 독립적 그룹이 같은 결론에 도달
3. **설명력 확장**: 예측하지 못했던 현상도 설명
4. **단순성**: 같은 설명력이면 더 간단한 이론 (Occam)
5. **네트워크 효과**: 다른 강한 이론들이 이 이론을 기반으로 구축됨

에이전트 시스템에서는 이를 **Fitness 함수**로 구현한다 (섹션 4에서 상세 설명).

---

## 3. 알고리즘 선택: 피드백 비판적 수용

### 3.1 피드백 요약 및 수용

외부 피드백에서 제시된 핵심 비판:

> "평균 랭킹만 쓰면 self-reinforcement, cold-start, bias 누적이 생긴다. Bradley-Terry + TrueSkill + 4종 샘플링 + 4축 평가가 더 낫다."

**수용하는 부분** (이유 포함):

✓ **Pairwise > 전체 순위**: LLM이 6개를 동시에 순위 매기는 것은 불안정. 1:1 비교가 일관적이고 Bradley-Terry에 직접 입력 가능.

✓ **TrueSkill의 `(μ, σ)` 이중 추적**: 불확실성이 핵심이다. "현재 1위지만 σ가 크다" = 논쟁 중인 이론. 학계의 "controversial but promising" 상태 표현 가능.

✓ **4종 샘플링 혼합**: champion + boundary + high-σ + novelty. 단순 top-3/random-3보다 정보 획득 효율이 높다.

✓ **4축 평가 rubric**: goal_fit / evidence_quality / reasoning_robustness / novel_contribution.

### 3.2 내 추가 비판 (피드백에 없던 것)

**비판 1: 평가 비용을 과소평가**

피드백대로 하면 4축 × C(6,2)=15쌍 = 최소 60 LLM calls/cycle. Claude API 기준 1 cycle에 $3~5. 하루 연속 실행 시 $150+.

**해결안**: 계층적 평가(Coarse-to-Fine)

```
Layer 1 Quick Filter: 1 call/paper × 6 = 6 calls
  "이 논문이 research question에 관련 있나?" → pass/skip

Layer 2 Core Pairwise: 2축 × 6쌍 = 12 calls
  goal_fit + evidence 축만 → 가장 중요한 두 축

Layer 3 Deep Eval: 4축 × 2쌍 = 8 calls
  경계선 논문만 full evaluation

총: ~26 calls/cycle (피드백 안의 60 → 43% 절감)
```

**비판 2: Critic Reliability 추정의 메타 문제**

피드백: "critic마다 reliability `r_c`를 추정하라."

문제: evaluator를 evaluate하려면 또 다른 evaluator가 필요 → 무한 회귀.

**해결안**: reliability 추정 대신 **역할 분리**

```python
critics = {
    "evidence_critic":     "출처, 데이터, 통계 오류만 집중",
    "logic_critic":        "논리 비약, 모순, 과잉 일반화만",
    "adversarial_critic":  "반례, 대안 가설 발굴에 특화",
    "novelty_critic":      "기존 문헌 대비 새로운 기여 평가"
}
```

역할이 고정되면 각 critic의 판단을 그 역할의 맥락에서만 해석 → reliability 추정 불필요.

**비판 3: 논문 간 관계(Citation Graph)를 무시**

피드백은 논문을 독립 개체로 취급하지만, 실제 가치는 관계에서 나온다.

논문 A가 논문 B를 "support"하고, B가 C를 "refute"하면:
- A의 폐기는 B의 신뢰도를 낮춘다
- C가 강해지면 B와 A가 함께 약해진다

**이 연쇄 효과가 없으면 패러다임 전환을 모델링할 수 없다.**

**비판 4: Research Direction Drift (피드백 미언급)**

품질 기반 진화만 하면 시스템이 가장 쓰기 쉬운 방향으로 수렴한다.

예: "유가 급등 분석"으로 시작했는데 50 cycle 후 "시계열 통계 방법론 논쟁"만 남는 현상.

**해결안**: Research Question Anchor를 매 N cycle마다 재점검.

```python
def check_research_drift(papers, research_question, threshold=0.6):
    """현재 활성 논문들이 research_question을 얼마나 다루는가"""
    coverage = compute_semantic_coverage(papers, research_question)
    if coverage < threshold:
        adjust_sampling_weights(novelty_weight=+0.5)
        emit("RESEARCH_DRIFT_DETECTED", coverage)
```

### 3.3 알고리즘 비교표 (최종 선택)

| 알고리즘 | 장점 | 단점 | 추천 용도 |
|---|---|---|---|
| **평균 순위 (Borda)** | 간단 | self-reinforcement, cold-start | Baseline only |
| **Bradley-Terry** | pairwise 기반, 해석 쉬움 | 불확실성 추적 없음 | MVP 핵심 엔진 |
| **TrueSkill** | `(μ,σ)` 불확실성 포함 | 구현 복잡 | Phase 2 이후 |
| **Plackett-Luce** | 전체 순위 직접 모델링 | 평가 비용 높음 | 선택사항 |
| **Kemeny/Condorcet** | pairwise 일관성 보장 | NP-hard | 주기적 감사용만 |

**채택**: MVP는 Bradley-Terry, Phase 2는 TrueSkill로 업그레이드.

---

## 4. 논문(Paper) 객체 및 생애주기 설계

### 4.1 Paper 객체 스키마

```json
{
  "id": "p_0042",
  "research_question": "유가 급등 우려의 근거와 반론",
  "title": "중국 수요 회복과 OPEC+ 감산이 유가에 미치는 복합 효과",

  "content_path": "papers/active/p_0042.md",

  "claims": [
    "2026년 중국 GDP 회복이 원유 수요를 5% 증가시킬 것",
    "OPEC+ 감산 준수율이 85% 이상이면 공급 압박 지속"
  ],
  "evidence_sources": [
    {"type": "report", "ref": "IEA World Energy Outlook 2025"},
    {"type": "data", "ref": "EIA Petroleum Status Report 2026-Q1"}
  ],
  "methodology": "문헌 분석 + 통계 추론",

  "axes": {
    "goal_fit": null,
    "evidence_quality": null,
    "reasoning_robustness": null,
    "novel_contribution": null
  },

  "trueskill": {
    "mu": 25.0,
    "sigma": 8.33,
    "conservative_score": 0.0
  },

  "graph": {
    "supports": ["p_0039", "p_0041"],
    "refutes": ["p_0033"],
    "refuted_by": [],
    "cited_by": []
  },

  "lifecycle": {
    "state": "active",
    "generation": 3,
    "created_at": "2026-03-17T10:00:00Z",
    "matches": 0,
    "survived_attacks": 0,
    "last_compared_at": null
  }
}
```

### 4.2 Fitness 함수

단일 랭킹 점수 대신 **복합 생존 압력**으로 계산:

```python
def compute_fitness(paper, all_papers):
    # 1. 독자적 품질 (TrueSkill 보수적 추정)
    standalone = paper.mu - 3 * paper.sigma  # μ - 3σ

    # 2. 지지 네트워크 강도
    supporting_papers = [p for p in all_papers if paper.id in p.graph.supported_by]
    support_strength = sum(p.fitness for p in supporting_papers) * 0.3

    # 3. 반박 생존율
    attack_survival = paper.survived_attacks / max(1, paper.total_attacks)

    # 4. 시간 감쇠 (오래된 논문은 자연 감소)
    age_days = (now() - paper.created_at).days
    decay = exp(-age_days / 90)  # 90일 반감기

    return (
        0.40 * standalone +
        0.30 * support_strength +
        0.20 * attack_survival * 100 +
        0.10 * decay * 100
    )
```

### 4.3 생애주기 상태 전환

```
        [생성]
          │
          ▼
       [active]
          │
    ┌─────┴─────┐
    │           │
    ▼           ▼
[contested] [growing]
    │    ╲         │
    │     ╲  sigma < 3 AND
    │      ╲ matches > 10
    │       ╲       │
    ▼        ▼      ▼
[refuted] [foundational]
    │
    ▼
[archived]
```

**상태 전환 조건**:
- `active → contested`: total_attacks > 3 AND survived_attacks/total_attacks < 0.6
- `active → growing`: matches > 5 AND mu 지속 상승
- `growing → foundational`: sigma < 3 AND mu > 30 AND survived_attacks > 5
- `contested → foundational`: survived_attacks/total_attacks > 0.8 AND matches > 20 AND mu > 30 AND sigma < 4
  - 의미: 강한 반박을 받았지만 80% 이상 살아남은 이론 — 이것이 가장 강한 정설 후보
- `contested → refuted`: survived_attacks/total_attacks < 0.3 AND matches > 10
- `refuted → archived`: 30일 이상 refuted 상태 유지

**foundational** 논문은 아카이브되지 않으며, 이후 모든 사이클의 baseline으로 사용된다.

---

## 5. 게임 룰: 사이클 구조

### 5.1 한 사이클 (Ralph 루프 1회) 개요

```
PHASE 1: SAMPLE     (논문 6개 선택)
    │
    ▼
PHASE 2: EVALUATE   (계층적 pairwise 평가)
    │
    ▼
PHASE 3: ADVERSARIAL (반론 생성 + 새 논문 작성)
    │
    ▼
PHASE 4: LIFECYCLE   (상태 전환 + 정리)
```

### 5.2 PHASE 1: SAMPLE — 4종 샘플링

```python
def sample_papers(paper_store, n=6):
    active = [p for p in paper_store if p.state in ("active", "contested", "growing")]

    # 1. Champion (1개): 현재 conservative score 최고
    champion = max(active, key=lambda p: p.mu - 3*p.sigma)

    # 2. Boundary (2개): champion과 σ 범위가 겹치는 논문
    boundary = select_boundary(active, champion, n=2)

    # 3. High-σ (2개): 아직 평가가 적어 불확실한 논문
    high_sigma = sorted(active, key=lambda p: p.sigma, reverse=True)[:2]

    # 4. Novelty (1개): research_question 커버리지 약한 영역
    novelty = select_least_covered_area(active, research_question)

    return deduplicate([champion] + boundary + high_sigma + [novelty])

def select_boundary(active, champion, n):
    """champion의 μ±2σ 범위와 겹치는 논문"""
    champion_range = (champion.mu - 2*champion.sigma, champion.mu + 2*champion.sigma)
    return [p for p in active
            if p.mu - 2*p.sigma < champion_range[1]
            and p.mu + 2*p.sigma > champion_range[0]
            and p.id != champion.id][:n]
```

**선택 점수 수식**:
```
selection_score(i) = α × quality_i + β × uncertainty_i + γ × novelty_i
```
기본값: α=0.4, β=0.35, γ=0.25 (exploration 중 γ 증가)

### 5.3 PHASE 2: EVALUATE — 계층적 평가

```python
# Layer 1: Quick Filter (6 calls)
relevant = []
for paper in sampled_6:
    result = quick_filter_agent(paper, research_question)
    if result == "relevant":
        relevant.append(paper)

# Layer 2: Core Pairwise (goal_fit + evidence, 최대 6쌍)
pairs_l2 = select_informative_pairs(relevant, n=6)
for (a, b) in pairs_l2:
    result = pairwise_agent(a, b, axes=["goal_fit", "evidence_quality"])
    update_bradley_terry(a, b, result)

# Layer 3: Deep Eval (4축 full, 경계선 2쌍만)
boundary_pairs = select_boundary_pairs(relevant, n=2)
for (a, b) in boundary_pairs:
    result = full_eval_agent(a, b, axes=ALL_AXES)
    update_trueskill(a, b, result)  # Phase 2에서 TrueSkill로 전환
```

**Pairwise 비교 프롬프트 핵심 원칙**:
- 논문 ID/제목 숨기기 (blind comparison)
- 이전 랭킹 숨기기
- 축별로 분리하여 질문 ("A와 B 중 어느 쪽이 더 나은 근거를 제시하는가?")
- 승자만 아니라 "왜 이겼는가"도 기록

### 5.4 PHASE 3: ADVERSARIAL — 반론 + 신규 논문

```python
# Step 1: 현재 champion 논문에 adversarial 공격
top_paper = get_current_champion(paper_store)
attack_results = adversarial_critic_agent(top_paper)

# attack_results = {
#     "weak_points": ["중국 수요 예측이 코로나 이전 트렌드 가정",
#                     "OPEC+ 이탈 국가 시나리오 미고려"],
#     "counterexamples": ["2023년 OPEC+ 감산 실패 사례"],
#     "alternative_hypotheses": ["수요 측면보다 달러 강세가 더 큰 변수"]
# }

# Step 2: 가장 강한 반론을 기반으로 새 논문 작성
most_critical_gap = select_most_impactful_gap(attack_results)
new_paper = actor_agent(
    research_question=research_question,
    inspiration=most_critical_gap,
    foundational_papers=get_foundational_papers(paper_store),
    top_current_papers=top_paper
)

# Step 3: 신규 논문 등록 (초기 TrueSkill: μ=25, σ=8.33)
paper_store.add(new_paper)
```

### 5.5 PHASE 4: LIFECYCLE — 상태 전환

```python
for paper in paper_store:
    new_state = compute_lifecycle_state(paper)
    if new_state != paper.state:
        log_transition(paper, paper.state, new_state)
        paper.state = new_state

# Research Direction 점검 (매 5 cycle)
if cycle_count % 5 == 0:
    coverage = compute_research_coverage(
        active_papers=paper_store.active,
        research_question=research_question
    )
    if coverage < 0.6:
        log_warning("RESEARCH_DRIFT", coverage)
        sampling_weights["novelty"] *= 1.5

# 수렴 감지
elo_variance = stdev([p.mu for p in paper_store.active])
if elo_variance < 3.0 and len(paper_store.foundational) >= 2:
    emit("CONVERGENCE_CANDIDATE", {
        "top_papers": get_top_n(paper_store, 3),
        "variance": elo_variance
    })
```

### 5.6 메타데이터 스토어 구조

```
papers/
  active/
    p_0042.md
    p_0043.md
  contested/
    p_0038.md
  foundational/
    p_0001.md         ← 정설로 승격, 삭제 불가
  archived/
    p_0010.md         ← 도태됨

comparison_log.jsonl  ← 모든 pairwise 결과 누적
  {"ts":"...", "a":"p_0042", "b":"p_0038", "winner":"a",
   "axes":{"goal_fit":"a","evidence":"b",...}, "reason":"..."}

cycle_log.jsonl       ← 사이클별 이벤트
  {"cycle":12, "new_papers":["p_0043"], "state_changes":[...], "drift_score":0.82}

trueskill_log.jsonl   ← μ,σ 이력
  {"ts":"...", "paper_id":"p_0042", "mu":27.3, "sigma":6.1}

consensus_map.json    ← 현재 지식 상태 스냅샷
  {
    "foundational": ["p_0001", "p_0005"],
    "contested": ["p_0038"],
    "minority_views": ["p_0043"],
    "research_frontier": "달러 강세 vs 수요 측면 논쟁"
  }
```

---

## 6. 창의적 확장 아이디어

### 6.1 Generational Pressure — 세대 개념 도입

**아이디어**: 논문에 "세대" 개념을 도입하여 세대 내 경쟁을 강화한다.

```
Generation 1 (cycle 1~10):  기초 가설들
Generation 2 (cycle 11~20): G1 가설을 기반으로 발전한 가설들
Generation 3 (cycle 21~30): G2의 반론을 흡수한 통합 이론
```

**메커니즘**: 같은 세대 논문끼리는 pairwise 비교 가중치를 높인다. 다른 세대 논문은 "역사적 참조"로만 사용. 이렇게 하면:
- 각 세대에서 가장 강한 논문이 살아남아 다음 세대의 foundational이 됨
- 진화의 세대적 구조가 명시적으로 구현됨
- 실현 가능성: 높음 (generation 필드 추가만 필요)
- 리스크: 세대 경계 설정이 임의적 → 사이클 수 기반으로 자동화

### 6.2 Paradigm Shift Detector — 패러다임 전환 감지

**아이디어**: 현재 foundational 논문들의 집단적 가정을 추출하고, 새 논문이 이 가정들을 얼마나 뒤집는지 측정한다.

```python
def detect_paradigm_challenge(new_paper, foundational_papers):
    """새 논문이 현재 정설의 몇 %를 뒤집는가"""
    current_assumptions = extract_assumptions(foundational_papers)
    challenged = [a for a in current_assumptions
                  if new_paper.contradicts(a)]

    challenge_ratio = len(challenged) / len(current_assumptions)

    if challenge_ratio > 0.5:
        # 패러다임 도전자 — 특별 보호 모드
        new_paper.sampling_weight_bonus = 3.0
        emit("PARADIGM_CHALLENGER", new_paper.id)
```

패러다임 도전 논문은 일반 논문보다 3배 자주 샘플링 → 조기 도태 방지.

이것이 없으면 "안전한 증분 기여" 논문만 살아남아 시스템이 혁신을 죽인다.
- 실현 가능성: 중간 (가정 추출이 LLM 의존적)
- 리스크: LLM이 "패러다임 전환"을 과도하게 라벨링할 수 있음

### 6.3 Socratic Catalyst — 소크라테스 에이전트

**아이디어**: Actor/Critic과 별도로, **질문만 하는 전용 에이전트**를 추가한다.

```
Socratic Agent의 역할:
- 논문을 읽고 "이 논문이 답하지 못한 가장 중요한 질문은 무엇인가?"를 생성
- 직접 논문을 쓰지 않고 질문만 남김
- 이 질문들은 다음 Actor의 "inspiration" 풀에 추가됨
```

학계에서 가장 중요한 논문은 종종 "정답을 제시"하는 논문이 아니라 "올바른 질문을 처음 던진" 논문이다 (예: Turing의 "Can machines think?").

Actor가 직접 답을 만들 때보다 **질문에서 시작할 때 더 novel한 논문이 나온다**는 가설.
- 실현 가능성: 높음 (별도 프롬프트로 구현)
- 리스크: 질문 풀이 빠르게 포화될 수 있음 → 질문에도 TrueSkill 적용 가능

### 6.4 Minority View Protection — 소수설 보호 메커니즘

**아이디어**: 시스템이 "현재 승리 이론에 모순되는 주장을 적어도 1개 이상 항상 유지"하도록 강제한다.

```python
def enforce_minority_protection(paper_store, min_minority_ratio=0.15):
    """전체 활성 논문 중 최소 15%는 현재 정설에 반하는 논문 유지"""
    total = len(paper_store.active)
    foundational_claims = extract_claims(paper_store.foundational)

    opposing = [p for p in paper_store.active
                if contradicts_foundational(p, foundational_claims)]

    if len(opposing) / total < min_minority_ratio:
        # 강제로 minority view 생성 주문
        actor_agent(
            instruction="현재 정설을 정면으로 반박하는 논문을 작성하라",
            target_ratio=min_minority_ratio
        )
```

토마스 쿤의 교훈: 정설은 반드시 소수에서 시작된다. 소수가 없으면 패러다임 전환도 없다.
- 실현 가능성: 높음
- 리스크: 없음. 이것은 오히려 시스템 건강성 지표.

### 6.5 Cross-Field Pollination — 타 분야 무작위 오염

**아이디어**: 매 N 사이클마다 **완전히 다른 research question에서 생성된 논문 1개**를 삽입한다.

```
주제 A: 유가 분석 사이클 중
  → cycle 15: 천체물리 논문 1개 삽입
  → Critic: "이 논문의 방법론이 유가 분석에 적용 가능한가?"
```

실제 학계에서 가장 혁신적인 발견은 종종 다른 분야의 방법론 이식에서 온다:
- 물리학 → 금융 (블랙숄즈)
- 진화생물학 → 컴퓨터 과학 (유전 알고리즘)
- 언어학 → AI (트랜스포머 어텐션)

"타 분야 논문이 현재 주제에 어떤 새로운 관점을 줄 수 있는가"를 탐색하는 특수 critic 추가.
- 실현 가능성: 높음 (별도 paper pool 유지)
- 리스크: 관련성 낮은 noise가 증가할 수 있음 → 빈도 조절로 해결

### 6.6 Temporal Horizon Forcing — 시간 지평선 강제

**아이디어**: 에이전트에게 명시적으로 다른 시간 지평선에서 생각하도록 강제한다.

```
매 사이클 논문 작성 시:
- 논문 A: "6개월 내 유가 방향" (단기 예측)
- 논문 B: "5년 내 에너지 전환이 유가에 미치는 영향" (중기)
- 논문 C: "탄소중립 시나리오에서 2040년 석유 수요" (장기)
```

동일 주제라도 시간 지평선이 다르면 완전히 다른 논리 구조와 증거가 필요하다. 이를 통해 "같은 이야기를 다른 방식으로 말하는" 중복 논문 생성을 방지한다.
- 실현 가능성: 높음
- 리스크: 시간 지평선 분류가 모호할 수 있음

---

## 7. 구현 로드맵

### Phase 1: MVP (1~2주)

**목표**: 동작하는 최소한의 진화 루프

```python
# 핵심 파일 구조
autoresearch/
  papers/
    active/
    archived/
  comparison_log.jsonl
  cycle_log.jsonl
  consensus_map.json
  program_v2.md          ← 새 게임 룰 포함 program
  ralph_v2.sh            ← 기존 ralph.sh 업그레이드
```

**구현 우선순위**:
1. Paper 객체 JSON 스키마 구현
2. Bradley-Terry pairwise update 함수
3. 4종 샘플링 정책 (단순화: champion-2 + boundary-2 + novelty-1 + random-1)
4. adversarial_critic 프롬프트
5. lifecycle state machine (active/archived만 먼저)

**성공 기준**:
- 사이클 10회 실행 후 비교 로그가 50+ entries
- 적어도 1개 논문이 archived 상태로 전환
- 비용: cycle당 $1 이하 (계층적 평가 적용)

### Phase 2: 안정화 (2~4주)

**목표**: 생태계 메타데이터 완성

1. TrueSkill로 Bradley-Terry 대체
2. Citation graph (supports/refutes 관계)
3. Fitness 함수 전체 구현
4. `foundational` 상태 추가
5. Research Direction Drift 감지

**성공 기준**:
- cycle 50회 후 foundational paper가 1개 이상 존재
- consensus_map.json이 coherent한 지식 구조를 반영
- 소수설 보호 메커니즘 동작 확인

### Phase 3: "학계화" (1개월+)

**목표**: 창의적 확장 기능 추가

1. Paradigm Shift Detector
2. Socratic Catalyst 에이전트
3. Cross-Field Pollination
4. Temporal Horizon Forcing
5. 주기적 Kemeny/Condorcet audit (top-10 논문 대상)

**성공 기준**:
- 인간이 보기에 "정설 → 반론 → 통합" 구조가 보이는 cycle 50+ 이력
- Paradigm Shift가 한 번 이상 감지됨

### Agent SDK 통합

```python
# 핵심 아키텍처
from claude_agent_sdk import query, ClaudeAgentOptions

async def run_research_cycle(research_question: str, cycle_num: int):
    """한 사이클 실행"""

    # 공통 옵션: oh-my-claude 하네스 포함
    base_options = ClaudeAgentOptions(
        setting_sources=["user", "project"],  # oh-my-claude 스킬 로드
        allowed_tools=["Skill", "Read", "Write", "Bash", "WebSearch"]
    )

    papers = load_paper_store()
    sampled = sample_papers(papers, research_question)

    # PHASE 2: Critic agents (병렬 실행)
    evidence_task = query(
        prompt=build_evidence_eval_prompt(sampled),
        options=ClaudeAgentOptions(**base_options, system_prompt=EVIDENCE_CRITIC_PROMPT)
    )
    logic_task = query(
        prompt=build_logic_eval_prompt(sampled),
        options=ClaudeAgentOptions(**base_options, system_prompt=LOGIC_CRITIC_PROMPT)
    )

    # 병렬 실행 (asyncio.gather)
    evidence_result, logic_result = await asyncio.gather(
        collect_result(evidence_task),
        collect_result(logic_task)
    )

    # PHASE 3: Actor (새 논문 작성)
    champion = get_current_champion(papers)
    adversarial_result = await collect_result(query(
        prompt=build_adversarial_prompt(champion),
        options=ClaudeAgentOptions(**base_options, system_prompt=ADVERSARIAL_CRITIC_PROMPT)
    ))

    new_paper = await collect_result(query(
        prompt=build_actor_prompt(research_question, adversarial_result),
        options=base_options  # oh-my-claude /ralph 사용 가능
    ))

    # PHASE 4: Lifecycle update
    update_trueskill(papers, evidence_result, logic_result)
    update_lifecycle_states(papers)
    save_paper_store(papers)
    log_cycle(cycle_num, papers)

# 메인 루프
async def main():
    research_question = load_research_question()
    cycle = 0
    while True:
        await run_research_cycle(research_question, cycle)
        cycle += 1
        await asyncio.sleep(5)
```

---

## 8. 한계와 열린 질문들

### 8.1 알려진 한계

**LLM 평가의 한계**: pairwise 비교도 결국 LLM의 판단에 의존한다. LLM이 특정 스타일의 글쓰기를 선호한다면 편향이 누적된다. (해결 방향: 다양한 critic 모델 사용)

**새 데이터 없음**: 실제 과학에서 진짜 검증은 새 실험 데이터로 이루어진다. 이 시스템은 기존 공개 정보를 재조합하는 수준.

**합의 기준 모호**: "언제 정설이 되는가"의 threshold (sigma < 3, matches > 10 등)는 임의적이다. 조정 가능하지만 정답이 없다.

### 8.2 열린 질문들

1. **자기참조 문제**: 에이전트 시스템 자체를 이 시스템으로 평가할 수 있는가?

2. **진짜 패러다임 전환**: 에이전트가 학습 데이터에 없는 완전히 새로운 이론을 만들 수 있는가? 아니면 기존 이론의 재조합만 가능한가?

3. **인간 피어리뷰 통합**: 이 시스템의 출력물을 인간이 주기적으로 평가하여 TrueSkill 업데이트에 반영하면 어떨까?

4. **다중 research question**: 여러 주제를 병렬로 진화시킬 때 Cross-Field Pollination이 어떻게 일어나는가?

---

## 결론

이 시스템의 핵심 아이디어는 하나다:

> **에이전트가 좋은 논문을 쓰도록 하는 것이 아니라, 나쁜 논문이 자연스럽게 도태되는 생태계를 설계하는 것.**

자연선택에서 진화의 방향을 직접 지정하지 않는다. 환경(평가 압력)을 설계하면 적자생존이 원하는 방향을 향한다.

마찬가지로, 에이전트에게 "좋은 연구를 하라"고 명령하는 것보다 반박, 생존, 재검증의 압력을 만들어내는 것이 더 강력하다.

이것이 인간 학계 2000년이 만들어낸 지혜다.

---

*이 보고서는 다음 문서들을 기반으로 작성됨:*
- `docs/260317_autoresearch-agent-sdk.md`: Agent SDK 기반 autoresearch 설계
- `docs/memory-proposal-v2.md`: 장기기억 설계 제안
- 대화 중 외부 피드백 (랭킹 알고리즘 비판)
