# hyperspaceai/agi 분석 보고서
> 분석일: 2026-03-17 | 대상: https://github.com/hyperspaceai/agi

---

## 1. 한 줄 요약

> **"단일 에이전트의 메모리가 아니라, 네트워크 전체가 하나의 기억 기관이다."**

Hyperspace AGI는 수십~수백 개의 자율 에이전트가 P2P로 실험을 수행하고, 그 결과를 GossipSub + CRDT로 즉시 공유하며, 집단 기억(collective memory)이 점진적으로 진화하는 분산 연구 시스템이다. 기존 에이전틱 메모리 연구가 "한 에이전트가 무엇을 기억하는가"를 다뤘다면, Hyperspace는 "에이전트 군집이 어떻게 집단 지식을 수렴·유지하는가"를 실제로 구현했다.

---

## 2. 핵심 기여 (What's New)

### 2.1 3계층 메모리 스택 — 속도×내구성 분리

```
계층          기술            지연      특성
─────────────────────────────────────────────────
L1 (워킹)    GossipSub       ~1초     휘발성, 브로드캐스트
L2 (집단)    CRDT (Loro)     ~2분     수렴적, 충돌 없는 병합
L3 (영구)    GitHub branch   ~5분     인간-가독, 감사 가능
```

- **GossipSub**: 에이전트가 실험 하나를 마치면 즉시 전체 피어에 브로드캐스트. 중앙 서버 없이 리얼타임 공유.
- **CRDT (Loro)**: Conflict-free Replicated Data Type. 어떤 두 노드가 동일한 데이터를 가지면 항상 같은 상태로 수렴. 네트워크 분할 후 재연결해도 자동 병합.
- **GitHub branch**: 각 에이전트마다 독립 브랜치. 영구 기록, 인간도 열람 가능.

**핵심 속성**: 새 노드가 네트워크에 참여하면 즉시 전체 CRDT 리더보드를 수신한다. **콜드 스타트 문제가 없다.** 어제 합류한 에이전트도 오늘 합류한 에이전트도 같은 집단 기억에서 출발한다.

### 2.2 "영감(Inspiration)" 메커니즘 — 집단 기억이 다음 가설을 생성

```
실험 완료
    ↓
GossipSub으로 피어에게 즉시 전파
    ↓
피어들이 "영감(inspiration)" 피드 업데이트
    ↓
다음 가설 생성 시 피어의 발견을 읽어서 반영
    ↓
더 나은 가설 생성 (크로스 폴리네이션)
```

실제 사례: 한 에이전트가 Kaiming 초기화가 성능을 높인다는 것을 발견 → GossipSub 전파 → 23개 에이전트가 수 시간 내에 같은 전략을 채택. **집단 기억 → 행동 변화**의 루프가 완성된다.

### 2.3 에이전트별 인지 저널 (JOURNAL.md)

각 에이전트는 고유한 libp2p peerId로 식별되며, 자신의 실험 공간에 다음을 기록한다:

```
projects/<project>/agents/<peerId>/
  run-0001.json    ← 기계 판독 결과 (val_loss, 하이퍼파라미터 등)
  run-0001.md      ← 인간 판독 실험 보고서
  best.json        ← 현재 개인 최고 기록
  JOURNAL.md       ← 에이전트의 인지 저널
```

`JOURNAL.md`는 단순 로그가 아니라 에이전트가 자신의 탐색 경험을 서술적으로 기록하는 공간이다. 이는 에이전트 고유의 **에피소딕 메모리(episodic memory)** 역할을 한다.

### 2.4 CRDT 리더보드 — 5개 도메인 동시 운용

5개 CRDT 문서가 독립 운용된다:

| 도메인 | 메트릭 | 방향 |
|--------|--------|------|
| Machine Learning | val_loss | 낮을수록 좋음 |
| Search Engine | NDCG@10 | 높을수록 좋음 |
| Financial Analysis | Sharpe ratio | 높을수록 좋음 |
| Skills & Tools | test_pass_rate | 높을수록 좋음 |
| Causes | per-cause metric | 도메인별 상이 |

각 도메인은 독립적인 GossipSub 토픽을 가진다:
- `research/rounds`, `search/experiments`, `finance/experiments`, `cause/skills`, `cause/inspiration`

### 2.5 연구 파이프라인 — 5단계 논문 생태계

```
Stage 1: Hypothesis     "LayerNorm 대신 RMSNorm은 어떨까?"
    ↓
Stage 2: Training       실제 실험 수행 (브라우저 탭~H100)
    ↓
Stage 3: Paper          충분한 실험 누적 후 논문 자동 합성
    ↓
Stage 4: Peer Critique  다른 에이전트들이 1-10점으로 평가
    ↓
Stage 5: Discovery      8+ 논문 → "돌파구" 플래그 → Stage 1 영감 피드에 주입
```

이 파이프라인은 우리가 논의했던 **평가압력 → 도태 → 다양성 유지** 사이클과 동일한 구조다. 점수 8+ 논문만 다음 세대의 영감으로 흡수된다.

### 2.6 분산 훈련 (DiLoCo) — 메모리로서의 가중치 델타

여러 에이전트가 같은 모델을 협력 훈련할 때 DiLoCo 방식을 사용:
- 각 에이전트가 H 스텝씩 로컬 훈련
- 압축된 가중치 델타만 공유
- 피어가 없으면 솔로 훈련으로 자동 폴백

압축된 가중치 델타는 일종의 **암묵적 지식(tacit knowledge) 전달** 메커니즘이다.

### 2.7 자동 스냅샷 — 집단 기억의 주기적 고정화

매 시간 하나의 노드가 전체 네트워크 상태를 `snapshots/latest.json`으로 GitHub에 푸시:

```json
{
  "version": 2,
  "timestamp": "2026-03-11T05:00:00.000Z",
  "generatedBy": "12D3KooW...",
  "summary": "67 agents, 1,369 experiments, 5 domains active",
  "leaderboards": {
    "machineLearning": { "top10": [...], "globalBest": {...} },
    "searchEngine":    { "top10": [...], "globalBest": {...} }
  },
  "disclaimer": "Raw CRDT leaderboard state. No statistical significance testing."
}
```

이 스냅샷은 "지금 이 순간 집단 지성이 어디까지 왔는가"의 타임스탬프된 사진이다. 어떤 LLM이든 이 URL을 가리키면 현재 네트워크 상태를 분석할 수 있다.

---

## 3. 메모리 아키텍처 심층 분석

### 3.1 CRDT가 에이전틱 메모리로서 갖는 의미

전통적 분산 시스템에서 CRDT는 "최종 일관성(eventual consistency)"을 보장하기 위해 쓰인다. Hyperspace는 이를 **집단 기억의 자동 병합 메커니즘**으로 활용했다.

```
에이전트 A의 관점:     best_val_loss = 2.5 (자신이 달성)
에이전트 B의 관점:     best_val_loss = 2.3 (자신이 달성)
CRDT 병합 결과:        global_best_val_loss = 2.3 (B의 결과)
                       A도 자동으로 2.3을 인식
```

충돌 없이 병합된다는 의미는: **누가 먼저 발견했는지 경쟁할 필요가 없다.** 더 좋은 결과는 자동으로 전파되고 채택된다. 이는 학계의 "선점(priority)" 경쟁과 정반대의 협력 구조다.

### 3.2 메모리 계층별 역할 비교

| 계층 | 아날로그 | 역할 | 휘발성 |
|------|----------|------|--------|
| GossipSub | 구두 발표 | 즉각 전파 | 매우 높음 |
| CRDT Leaderboard | 학과 게시판 | 최신 현황 유지 | 낮음 (수렴) |
| GitHub branch | 논문 아카이브 | 재현 가능한 기록 | 없음 |
| JOURNAL.md | 연구노트 | 에피소딕 기억 | 없음 |
| best.json | 개인 최고기록 | 현재 상태 | 없음 |

### 3.3 리더보드 빌드 메커니즘 (`build-leaderboard.js`)

GitHub Actions가 15분마다 모든 에이전트 브랜치를 스캔해 `best.json`을 읽고 `LEADERBOARD.md`를 재생성한다:

```javascript
// 각 프로젝트마다 메트릭 정의가 다름
const PROJECT_METRICS = {
  'astrophysics':       { field: 'valLoss',     dir: 'asc',  ... },
  'financial-analysis': { field: 'sharpeRatio', dir: 'desc', ... },
  'search-engine':      { field: 'ndcg10',      dir: 'desc', ... },
};

// 각 에이전트 브랜치에서 best.json 읽기
const content = execSync(`git show ${branch}:${bestPath}`);
```

이 설계의 핵심: **브랜치 = 에이전트 메모리의 네임스페이스.** 에이전트 충돌이 없고, main에 머지도 없다. 각자의 탐색 공간을 독립 유지하면서 리더보드라는 공유 인터페이스로만 만난다.

---

## 4. 우리 연구 생태계와의 비교 및 인사이트

### 4.1 공통점

| 개념 | Hyperspace | 우리 시스템 (설계중) |
|------|-----------|---------------------|
| 평가압력 | Peer critique 1-10점 + 8점 이상만 생존 | pairwise comparison → fitness |
| 다양성 보존 | 에이전트별 독립 브랜치 + 각자 탐색 | MAP-Elites (topic×perspective) |
| 상태 명시성 | best.json + JOURNAL.md | papers 테이블 + l0/l1/l2 |
| 집단 기억 진화 | CRDT leaderboard | comparisons → fitness 재계산 |

### 4.2 결정적 차이: 메모리의 주체

- **Hyperspace**: 메모리 주체 = **네트워크 전체**. 개별 에이전트 메모리는 부차적.
- **우리 설계**: 메모리 주체 = **SQLite DB (papers + comparisons)**. 에이전트는 읽고 쓰는 클라이언트.

Hyperspace는 에이전트가 네트워크의 노드로서 메모리를 **분산 소유**한다. 우리는 중앙 DB가 메모리를 **단일 소유**한다. 우리 설계가 더 단순하고 오컴의 면도날에 더 가깝다.

### 4.3 채택할 수 있는 패턴

**① "영감 피드" 패턴**

Hyperspace의 핵심: 에이전트가 다음 가설을 생성하기 전에 피어의 최근 발견을 읽는다.
우리 시스템에서 동일 패턴:

```python
def research_agent(topic):
    # 현재 fitness 상위 논문을 읽어서 영감으로 사용
    top_papers = db.query("""
        SELECT l0_summary, claim, fitness
        FROM papers
        WHERE topic_tag = ?
        ORDER BY fitness DESC
        LIMIT 5
    """, topic)

    new_paper = llm.generate(
        prompt=f"다음 발견들을 참고해서 새 논문을 써라: {top_papers}"
    )
    return new_paper
```

이미 우리가 설계한 내용이지만, Hyperspace가 실제로 동작함을 확인했다.

**② 스냅샷 패턴 — 주기적 전체 상태 고정화**

Hyperspace는 매 시간 `snapshots/latest.json`을 만든다. 우리도:

```sql
-- 매일 00:00에 전체 상태 스냅샷
CREATE TABLE snapshots (
    snapshot_at  TEXT,
    paper_count  INTEGER,
    top_paper_id TEXT,
    top_fitness  REAL,
    avg_fitness  REAL,
    topic_stats  TEXT  -- JSON
);
```

이렇게 하면 "이 에코시스템이 시간에 따라 어떻게 진화했는가"를 추적할 수 있다. 현재 설계에서 빠진 부분이다.

**③ 도메인별 독립 메트릭 설계**

Hyperspace는 도메인마다 다른 메트릭을 쓴다 (val_loss vs NDCG@10 vs Sharpe). 우리도 research_type(Q1~Q7)별로 평가 기준을 달리할 수 있다:

```python
DOMAIN_METRICS = {
    'Q1_hypothesis':   '합리성 (근거 → 결론)',
    'Q3_survey':       '포괄성 + 정확성',
    'Q5_methodology':  '재현 가능성',
    'Q7_prediction':   '캘리브레이션 (예측 vs 실제)',
}
```

### 4.4 채택하지 않을 패턴

**CRDT 기반 분산 메모리**: 우리는 멀티노드 P2P가 아닌 단일 SQLite이므로 불필요. 복잡성만 증가.

**DiLoCo 분산 훈련**: 우리는 모델 가중치를 공유하지 않고 논문(텍스트 지식)을 공유하므로 해당 없음.

---

## 5. 한계 및 미해결 문제

### 5.1 페어 리뷰의 신뢰성 문제

Peer critique 1-10점 평가에서 **누가 평가하는지**가 중요하다. 동일한 에이전트 집단이 서로를 평가하면 집단적 맹점(collective blind spot)이 생길 수 있다. README에도 `"No statistical significance testing. Interpret the numbers yourself."` 경고가 있다.

우리 pairwise comparison이 이 문제를 더 잘 해결한다: 두 논문 중 어느 쪽의 "근거가 결론을 더 잘 지지하는가"는 점수가 아니라 비교이므로 앵커링(anchoring) 문제가 없다.

### 5.2 하드웨어 이질성이 결과 편향을 만든다

H100 에이전트 vs CPU 에이전트는 동일한 실험을 해도 다른 결과를 낸다. 리더보드 1위(`4offfUdWnAYX`, H100)가 2위(`6ZQm6LcgRqkd`, CPU)보다 val_loss가 0.9966 vs 2.5086으로 압도적이다. 하드웨어 차이가 지식 기여도를 왜곡한다.

우리 시스템은 하드웨어 이질성 문제가 없다 (논문 품질은 compute 비례가 아님).

### 5.3 탐색 vs 착취 균형 미해결

Hyperspace는 "mutation" 전략으로 다양성을 유지하지만, 이것이 충분한지 불명확하다. 상위 발견에 23개 에이전트가 몰리는 현상은 다양성 손실의 위험이다 (Kaiming init 채택 사례).

우리 MAP-Elites 방식이 이를 더 체계적으로 다룬다.

---

## 6. 결론: Hyperspace가 보여준 것

Hyperspace AGI의 핵심 기여를 한 문장으로: **"에이전트는 소모품이고, 집단 CRDT 상태가 유일한 진실(single source of truth)이다."**

이는 에이전틱 메모리 설계의 패러다임 전환이다:

| 전통적 접근 | Hyperspace 접근 |
|------------|-----------------|
| 에이전트 = 상태 보유자 | 에이전트 = 상태 없는 워커 |
| 메모리 = 에이전트 내부 | 메모리 = 네트워크 CRDT |
| 에이전트 죽으면 기억 손실 | 에이전트 죽어도 CRDT 살아있음 |
| 콜드 스타트 = 빈 메모리 | 콜드 스타트 = 전체 집단 기억 상속 |

우리 연구 생태계 설계에서 직접 대응하는 원칙:
- **에이전트는 상태를 갖지 않는다.** 상태는 SQLite에만 있다.
- **콜드 스타트는 없다.** 새 실행이라도 papers 테이블에서 전체 지식을 읽는다.
- **개별 실행의 실패는 괜찮다.** DB가 살아있으면 전체 지식은 보존된다.

이것이 Hyperspace가 우리에게 확인해준 가장 중요한 메모리 원칙이다.

---

*분석 기반: `/tmp/agi` (depth=1 clone), README.md, projects/*/README.md, .github/scripts/build-leaderboard.js, .github/workflows/leaderboard.yml, baseline configs*
