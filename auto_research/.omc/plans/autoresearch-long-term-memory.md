# 계획: autoresearch Ralph 루프 장기기억 구현

> 작성일: 2026-03-16
> 목적: Ralph 루프의 토큰 낭비를 줄이고, 실험 지식을 누적하는 장기기억 시스템 설계

---

## Context

**현재 구조의 핵심 문제:**

- `results.tsv` 전체 읽기 = O(N) 토큰. 100회 실험 후 매 이터레이션마다 ~3,000 토큰 낭비.
- 에이전트가 종료/재시작 시 "이미 실패한 방향"을 재탐색하는 반복 낭비.
- "왜 실패했는가"에 대한 추론이 기록되지 않아 같은 실수 반복.
- (멀티 에이전트 시) 여러 에이전트가 동시에 동일한 아이디어를 실험하는 중복 낭비.

**설계 원칙:**
- 오컴의 면도날: 가장 단순한 해결책 우선.
- 5분 실험 사이클에 맞는 오버헤드 (메모리 읽기/쓰기 <30초).
- 새 의존성 없음 — 파일 시스템만 사용 (Phase 1).

---

## Work Objectives

1. **토큰 절감**: 이터레이션당 메모리 로딩 비용 ~3,000 토큰 → ~300 토큰 (-90%).
2. **지식 누적**: 검증된 발견과 실패 방향을 영구 보존하여 반복 실험 방지.
3. **program.md 업데이트**: 에이전트가 메모리를 자율적으로 읽고 쓰도록 지침 추가.

---

## Guardrails

**Must Have:**
- `results.tsv`는 절대 수정하지 않음 (기존 append-only 원칙 유지).
- 메모리 파일은 에이전트가 직접 생성/편집 (외부 스크립트 의존 없음).
- SUMMARY.md는 항상 300 토큰 이하로 유지.

**Must NOT Have:**
- 새 Python 패키지 설치 금지 (pyproject.toml 변경 없음).
- 메모리 읽기/쓰기가 5분 실험 사이클의 병목이 되어서는 안 됨.
- INSIGHTS.md에 검증되지 않은 가설을 "사실"로 기록 금지.

---

## Part A: 지금 당장 쓸 수 있는 최선의 방법

### 설계 근거

기존 연구 중 autoresearch에 가장 실용적인 조합은:

**OpenClaw 2계층 메모리 패턴 + FAILED.md 추가**

이유:
1. OpenClaw(Claude Code 자체)가 이미 이 패턴으로 동작 중 — 에이전트가 이 구조에 이미 익숙함.
2. Synapse(-95% 토큰)나 A-MEM(Zettelkasten)은 벡터 DB, 임베딩 모델 등 인프라가 필요 → autoresearch의 "0 의존성" 원칙 위반.
3. `memory/SUMMARY.md` 하나로 -90% 토큰 절감 달성 가능 — 80%의 효과를 20%의 복잡도로.

### Task 1: 메모리 디렉토리 구조 생성

```
autoresearch/
├── train.py
├── prepare.py
├── program.md          ← 수정 대상
├── ralph.sh
├── results.tsv
└── memory/
    ├── SUMMARY.md      ★ 항상 로딩 (목표 ≤300 토큰)
    ├── INSIGHTS.md     검증된 발견 (영구 보존)
    └── FAILED.md       실패 방향 목록 (반복 방지)
```

**각 파일 명세:**

`memory/SUMMARY.md` — 항상 로딩되는 압축 요약:
```markdown
# 현재 상태
- 총 실험: {N}회 (keep: {k}, discard: {d}, crash: {c})
- 현재 최고 val_bpb: {best} (커밋 {hash}, {description})
- 베이스라인 val_bpb: {baseline}
- 개선율: {pct}%

# 유망한 미탐색 방향
- {idea_1}
- {idea_2}

# 주의: FAILED.md 참조 (이미 시도한 방향들)
```

`memory/INSIGHTS.md` — 2회 이상 재현된 발견만 기록:
```markdown
# [검증됨] {제목}
- 실험: {commit_hash_1}, {commit_hash_2}
- val_bpb 평균 개선: {delta}
- 조건: {hyperparam context}
```

`memory/FAILED.md` — 간결한 실패 목록 (이유 포함):
```markdown
# 시도했으나 효과 없음 (재시도 금지)

- {실험 설명} → {실패 이유 한 줄} (커밋 {hash})
- {실험 설명} → OOM (커밋 {hash})
```

**수용 기준**: `memory/` 디렉토리가 존재하고, 세 파일 모두 초기 템플릿으로 생성됨.

---

### Task 2: program.md에 메모리 지침 추가

현재 `program.md`의 "The experiment loop" 섹션 Step 1과 Step 8을 다음으로 교체:

```markdown
## The experiment loop

**You are called once per experiment.** An external loop (ralph.sh) will restart
you for the next experiment. Your job: run exactly ONE experiment, then exit.

1. **메모리 로딩** (항상):
   - `memory/SUMMARY.md` 읽기 → 현재 상태와 유망한 방향 파악
   - `memory/FAILED.md` 읽기 → 이미 실패한 방향 파악 후 재탐색 금지
   - (필요한 경우만) `results.tsv` 전체 읽기

2. If `results.tsv` has only the header row, this is the first run — run `train.py`
   unmodified to establish the baseline.

3. Otherwise, choose ONE new idea based on memory files. Modify `train.py`.

4. `git commit` the change.

5. Run: `uv run train.py > run.log 2>&1`

6. Read results: `grep "^val_bpb:\|^peak_vram_mb:" run.log`

7. If output is empty (crash): run `tail -n 50 run.log`. If trivially fixable,
   fix and re-run once. Otherwise log as `crash` and `git reset --hard HEAD~1`.

8. Record in `results.tsv` (do NOT commit this file — leave it untracked).

9. If val_bpb improved → keep commit. If equal or worse → `git reset --hard HEAD~1`.

10. **메모리 업데이트** (항상 실행):
    - `memory/SUMMARY.md` 업데이트: 총 실험 수, 새 최고값, 유망 미탐색 방향.
    - 실패한 방향이면 `memory/FAILED.md`에 한 줄 추가 (실패 이유 포함).
    - 2회 이상 재현된 발견이면 `memory/INSIGHTS.md`에 추가.

11. Exit cleanly. The external loop will call you again.

**Timeout**: If a run exceeds 10 minutes, kill it and treat as failure.
**Do NOT loop. Do NOT ask the human. Run one experiment and exit.**
```

**수용 기준**: program.md의 실험 루프 섹션이 위 지침을 포함하고, 에이전트가 Step 1에서 results.tsv 대신 SUMMARY.md를 먼저 읽고, Step 10에서 메모리를 업데이트함.

---

### Task 3: 토큰 비용 검증

| 방식 | 100회 시점 이터레이션당 토큰 |
|------|------------------------------|
| 기존 (results.tsv 전체) | ~3,000 토큰 |
| 제안 (SUMMARY.md + FAILED.md) | ~300 토큰 |
| 절감률 | -90% |

검증 방법: 10회 실험 후 SUMMARY.md 크기를 확인하여 300 토큰(~1,200자) 이하인지 체크.

**수용 기준**: `wc -c memory/SUMMARY.md` 출력이 1,200 바이트 미만.

---

## Part B: 창의적 사고실험 (5개 이상)

아래 아이디어들은 기존 연구에 직접 구현된 사례는 없으나, 논리적으로 autoresearch에 유망한 접근들이다.

---

### 사고실험 1: val_bpb 변화율 기반 탐색 방향 자동 결정 (Gradient of Experiments)

**아이디어**: 단순히 "val_bpb가 좋아졌는가"를 기록하는 것을 넘어, 탐색 방향의 "기울기(gradient)"를 추적.

**구체적 메커니즘**:
```
# SUMMARY.md에 추가되는 메타 정보
## 탐색 기울기 (최근 10회 실험)
- learning_rate 방향: +0.0012/실험 (상승 중, 계속 탐색 가치 있음)
- model_depth 방향: -0.0003/실험 (수렴, 추가 탐색 가치 낮음)
- attention_variant 방향: 데이터 부족 (2회만 시도, 불확실)
```

**논리적 근거**:
- 인간 연구자가 암묵적으로 하는 것 — "이 방향이 계속 좋아지고 있어, 더 파보자" — 을 명시화.
- 에이전트가 매 실험마다 SUMMARY.md의 기울기를 보고 "수렴한 방향 재탐색 금지, 상승 중인 방향 우선"을 결정.
- 실질적으로 bandit algorithm의 파일 기반 구현.

**구현 복잡도**: 낮음. SUMMARY.md에 텍스트 섹션 추가, 에이전트가 서술적으로 기울기를 업데이트.

---

### 사고실험 2: 실패 원인 분류 분류기 (Failure Taxonomy)

**아이디어**: FAILED.md를 단순 목록이 아닌 구조화된 실패 분류표로.

**현재**:
```
- GeLU activation → 효과 없음
- weight decay 0.1 → 악화
```

**제안**:
```markdown
## 실패 분류

### [카테고리: activation] 비선형함수 변경 시도 → 대부분 효과 없음
- SiLU가 이 데이터셋/아키텍처에서 이미 최적인 것으로 보임
- GeLU, ReLU, Swish 모두 시도됨 → 추가 시도 불필요

### [카테고리: regularization] 정규화 강화 → 일관되게 악화
- 5분 학습에서는 언더피팅이 문제이지 오버피팅이 아님
- 가설: 5분 예산에서 모델이 수렴하기 전에 정규화가 학습을 방해

### [카테고리: scale-up] 모델 크기 증가 → OOM 또는 처리량 감소
- 5분 예산에서는 더 큰 모델 = 더 적은 스텝 = 나쁜 결과
```

**논리적 근거**:
- 에이전트가 "왜 이 카테고리가 실패했는가"의 가설을 기록하면, 새 아이디어를 제안할 때 "이 아이디어가 이미 실패한 카테고리와 같은 이유로 실패할 것인가"를 사전에 추론 가능.
- 인간 연구자의 직관("5분 예산에서 정규화는 의미 없다")을 에이전트가 스스로 유도하고 보존.

**구현 복잡도**: 낮음. FAILED.md 구조를 카테고리별로 재편성.

---

### 사고실험 3: 메타 루프 — 에이전트가 자신의 research strategy를 검토하는 주기적 리뷰

**아이디어**: 10번 실험에 한 번씩 "일반 실험" 대신 "전략 검토 실험"을 수행.

**구체적 메커니즘**:
```
# program.md에 추가될 조건
10의 배수 실험 번호(10, 20, 30...)이면:
  일반 실험 대신 다음을 수행:
  1. INSIGHTS.md, FAILED.md, results.tsv 전체 읽기
  2. "지금까지 가장 효과적인 변경 유형은 무엇인가?" 분석
  3. "아직 시도하지 않은 가장 유망한 방향 5개" 목록 생성
  4. SUMMARY.md의 "유망한 미탐색 방향" 섹션 대규모 업데이트
  5. 실험 없이 종료 (이 이터레이션은 "전략 업데이트" 역할)
```

**논리적 근거**:
- 에이전트가 100회 중 90번은 개별 실험에 집중하고, 10번은 "올라와서 지도를 보는" 역할.
- 현재 구조에서 아이디어가 고갈되면 에이전트가 랜덤 변경을 시작하는 문제(autoresearch-overnight-guide.md에서 언급)를 완화.
- 인간 연구자의 주간 리뷰 미팅과 동일한 역할을 자동화.

**구현 복잡도**: 낮음. program.md에 조건 분기 추가.

---

### 사고실험 4: 압축률 동적 조절 — SUMMARY.md의 self-compaction

**아이디어**: SUMMARY.md가 300 토큰을 초과하면, 에이전트가 스스로 오래된 내용을 INSIGHTS.md로 이동시키고 SUMMARY를 재압축.

**구체적 메커니즘**:
```
# Step 10 업데이트 후 추가 조건
SUMMARY.md가 1,500자 초과이면:
  - 10회 이상 된 항목 중 "유망 방향"으로 표시된 것이 아직 시도 안 된 것 → 유지
  - 이미 시도되어 FAILED.md 또는 INSIGHTS.md에 기록된 항목 → SUMMARY에서 삭제
  - 전체 통계(총 실험 수, 최고값)는 항상 유지
  - 압축 후 SUMMARY.md ≤ 800자 목표
```

**논리적 근거**:
- OpenClaw의 "auto-flush before compaction" 패턴을 autoresearch에 이식.
- SUMMARY.md도 시간이 지나면 커진다는 미해결 문제(보고서에서 언급)를 에이전트 자체 루틴으로 해결.
- "메모리를 관리하는 것도 에이전트의 책임"이라는 Agentic Memory 패러다임.

**구현 복잡도**: 낮음. Step 10에 조건 추가.

---

### 사고실험 5: 실험 쌍 비교 기반 인과 추론 (Counterfactual Logging)

**아이디어**: 단순히 "A보다 B가 좋았다"가 아니라, "A에서 하나만 바꾼 B와 비교했을 때 그 차이의 원인"을 기록.

**구체적 메커니즘**:
```markdown
# INSIGHTS.md 확장 형식

## [인과 추론] LR warmup 연장 효과
- 베이스 실험: a1b2c3d (depth=8, lr=0.03, warmup=100)
- 변경 실험: b2c3d4e (depth=8, lr=0.03, warmup=200) ← warmup만 변경
- val_bpb 차이: +0.008 (warmup 연장 단독 효과로 추정)
- 신뢰도: 높음 (단일 변수 변경)
- 반증 가능 예측: warmup=400으로 추가 실험 시 +0.004 예상
```

**논리적 근거**:
- 현재 에이전트는 여러 변경을 한 번에 시도하거나, 단일 변경이어도 이전 실험의 누적 상태를 고려하지 않아 인과관계 추론이 불명확.
- 인과 추론을 명시적으로 기록하면: (a) 검증된 인과 지식 누적, (b) "이미 인과관계가 밝혀진 것을 재탐색하지 않음", (c) 예측을 기록하고 나중에 검증 — 에이전트가 과학적 방법론을 명시적으로 따름.
- Synapse의 "에피소딕-시맨틱 그래프 연결"을 파일 기반으로 경량 구현한 것.

**구현 복잡도**: 낮음~중간. INSIGHTS.md 형식 확장 + 에이전트에게 "단일 변수 원칙" 권고.

---

### 사고실험 6 (보너스): 아이디어 예약 큐 (Idea Buffer)

**아이디어**: 에이전트가 실험 중 "이 아이디어도 좋아 보이는데 지금은 하나만 해야 하니까..."라고 버리는 아이디어를 QUEUE.md에 저장.

**구체적 메커니즘**:
```markdown
# memory/QUEUE.md — 시도할 아이디어 목록 (우선순위 순)

1. [우선순위 높음] GQA (Grouped Query Attention) — KV 헤드 수 줄이기
   근거: attention 효율 논문 기반, 아직 미탐색

2. [우선순위 중간] cosine LR schedule 대신 linear decay 시도
   근거: step 수가 적어 cosine의 tail이 의미 없을 수 있음

3. [우선순위 낮음] flash attention pattern 변경
   근거: WINDOW_PATTERN="L"로 단순화 시도, 현재 "SSSL"
```

**Step 10 추가 동작**:
- QUEUE.md에서 방금 시도한 아이디어 삭제.
- 실험 중 떠오른 새 아이디어는 QUEUE.md에 추가.
- 다음 이터레이션의 Step 1에서 QUEUE.md도 읽기.

**논리적 근거**:
- 에이전트가 "하나의 실험만" 원칙을 지키면서도 아이디어를 잃지 않음.
- 메타 루프(사고실험 3)의 전략 검토 시 QUEUE.md를 재정렬 가능.
- 멀티 에이전트로 확장 시, 두 에이전트가 QUEUE.md에서 서로 다른 아이디어를 꺼내면 자연스럽게 중복 방지.

**구현 복잡도**: 매우 낮음. 파일 하나 추가 + program.md 두 줄 추가.

---

## Task Flow

### Step 1: 파일 구조 생성
```bash
mkdir -p autoresearch/memory
touch autoresearch/memory/SUMMARY.md
touch autoresearch/memory/INSIGHTS.md
touch autoresearch/memory/FAILED.md
touch autoresearch/memory/QUEUE.md   # 사고실험 6 적용 시
```
수용 기준: `ls autoresearch/memory/` 에 네 파일 존재.

### Step 2: SUMMARY.md 초기 템플릿 작성
기존 results.tsv를 한 번 읽고 현재 상태를 SUMMARY.md 형식으로 압축.
수용 기준: SUMMARY.md가 300 토큰(~1,200자) 이하이고 현재 최고 val_bpb와 총 실험 수가 정확히 기재됨.

### Step 3: program.md 실험 루프 섹션 수정
"The experiment loop" 섹션의 Step 1과 Step 8 사이에 메모리 지침 삽입.
수용 기준: program.md에 "memory/SUMMARY.md 읽기"와 "memory/FAILED.md 업데이트" 지침이 명시됨.

### Step 4: 첫 메모리 루프 실험 실행 및 검증
다음 ralph 이터레이션에서 에이전트가 실제로 SUMMARY.md를 먼저 읽는지 확인.
수용 기준: run.log 또는 에이전트 출력에서 "memory/SUMMARY.md" 읽기 도구 호출이 results.tsv 읽기 이전에 나타남.

---

## 도입 우선순위 권고

| 우선순위 | 항목 | 이유 |
|----------|------|------|
| 1 (즉시) | SUMMARY.md + FAILED.md + program.md 수정 | -90% 토큰, 30분 구현 |
| 2 (즉시) | QUEUE.md 아이디어 예약 큐 (사고실험 6) | 추가 5분, 매우 낮은 복잡도 |
| 3 (1주 내) | 실패 분류 분류기 (사고실험 2) | FAILED.md 형식만 변경 |
| 4 (1주 내) | val_bpb 기울기 추적 (사고실험 1) | SUMMARY.md 섹션 추가 |
| 5 (2주 내) | 메타 루프 전략 검토 (사고실험 3) | program.md 조건 분기 추가 |
| 6 (2주 내) | 인과 추론 기록 (사고실험 5) | INSIGHTS.md 형식 확장 |
| 7 (선택) | self-compaction (사고실험 4) | SUMMARY.md 안정화 후 |

---

## Success Criteria

- [ ] `memory/SUMMARY.md` 크기가 100회 실험 시점에서도 1,200자 미만으로 유지됨.
- [ ] 에이전트가 이미 FAILED.md에 기록된 방향을 재시도하지 않음 (10회 이상 연속 실험에서 중복 없음).
- [ ] 각 이터레이션의 메모리 읽기 토큰 비용이 results.tsv 전체 읽기 대비 -80% 이상.
- [ ] QUEUE.md에 항상 최소 2개 이상의 미탐색 아이디어가 유지됨 (아이디어 고갈 방지).

---

## Open Questions

1. SUMMARY.md의 "유망한 미탐색 방향"은 에이전트가 자유롭게 판단해서 쓰는가, 아니면 명시적 포맷(JSON-like)을 강제하는가? — 자유 텍스트가 에이전트 자율성에 유리하나, 파싱 오류 위험.
2. 멀티 에이전트(여러 GPU 동시) 전환 시 파일 잠금 전략: `flock` vs SQLite WAL. 현재 단일 에이전트 가정이지만 이 결정이 파일 구조에 영향을 줌.
3. 메타 루프(사고실험 3)의 "10번에 1번" 주기가 적절한가? 초기(1-20회)에는 너무 잦고, 후기(80-100회)에는 너무 드물 수 있음.

→ 위 질문들은 `.omc/plans/open-questions.md`에도 기록됨.
