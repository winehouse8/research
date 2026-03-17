# autoresearch 장기기억 구현 제안서 v2
> 수정 근거: Architect 합성 제안 + Critic ITERATE 판정 4개 항목 반영

---

## Part A: 현시점 최선의 방법

### A.1 토큰 절감 현실적 추정 (수정됨)

기존 보고서의 **"-90% 토큰 절감"** 주장은 과장. 정확한 수치:

| 항목 | 토큰 수 (100회 실험 시점) | 비고 |
|------|--------------------------|------|
| program.md | ~1,800 토큰 | 고정 (114줄, 7KB) |
| train.py (현재) | **~6,900 토큰** | **고정 (630줄, 26KB) — 매 이터레이션 반드시 읽힘** |
| results.tsv 전체 | ~3,000 토큰 | O(N) 성장 |
| system prompt 등 | ~500 토큰 | 고정 |
| **총합** | **~12,200 토큰** | |

SUMMARY.md 방식 적용 시:
- results.tsv → SUMMARY.md (~300 토큰): results.tsv 부분 **-90%** 절감 (3,000 → 300)
- 전체 컨텍스트 기준: 절감량 2,700 토큰 / 총 12,200 = **전체 ~22% 절감**
- **올바른 표현**: "results.tsv 읽기 비용 -90% 절감, 전체 이터레이션 컨텍스트 ~22% 절감"

> ⚠️ 기존 보고서(Section 4.5)의 "-90%" 수치는 results.tsv 부분에만 해당. 전체 컨텍스트의 가장 큰 구성요소는 train.py(~6,900 토큰)이며 이는 절감 불가.

**그러나 핵심 가치는 토큰 절감이 아니다.** 실질적 이점:
1. **중복 실험 방지**: HARD/SOFT BLOCK으로 이미 실패한 방향 재시도 방지 (5분 실험 1회 = GPU + API 비용)
2. **탐색-활용 균형**: 탐색 공간 지도로 exploitation 편향 억제
3. **누적 지식**: 이전 실험에서 검증된 패턴을 다음 이터레이션에 활용
4. **~22% 토큰 절감**: 부수적 이점

---

### A.2 SUMMARY.md — 탐색 공간 지도 (Architect 합성 반영)

**핵심 재정의**: SUMMARY.md를 "현재 상태 요약"이 아닌 **"탐색 공간 지도(Exploration Space Map)"**로 설계

기존 설계(문제 있음):
```markdown
# 유망한 방향
- LR warmup 연장 효과 있음 (+0.008)
- GQA 미탐색
```
→ exploitation 편향: 유망 방향만 반복 탐색

**개정 설계 (탐색 공간 지도)**:
```markdown
# 탐색 공간 지도 | 총 실험: 47회 | 최고 val_bpb: 0.9712 (a3f8c2d) | 베이스라인: 0.9979

## 시도된 방향
- LR 조정 (8회): 최적점 ~0.04 확인. 0.05 이상은 발산.
- GeLU 활성화 (1회): SiLU 대비 -0.008 악화. [SOFT BLOCK]
- 모델 width 2배 (1회): OOM. [HARD BLOCK]
- RMSNorm 전환 (2회): +0.003 안정 개선.

## 미탐색 방향 (후보)
- GQA (Grouped Query Attention)
- Muon β2 파라미터 조정
- Dynamic batch size
- ALiBi positional encoding
```

**장점**:
- 같은 방향 중복 탐색 방지 (exploitation 억제)
- 미탐색 영역 명시 (exploration 촉진)
- 컨텍스트 고정 (~300 토큰 목표)

---

### A.3 FAILED.md — 2계층 블로킹 (Critic 반영)

**단일 영구 블록 → 2계층으로 분리** (simplicity criterion과 충돌 해소)

```markdown
# 실패 방향

## [HARD BLOCK] — 하드웨어/구조적 한계, 재시도 금지
현재 플랫폼 조건이 근본적으로 변하지 않는 한 무의미한 방향.
- model width 2배 → OOM (d4e5f6g): H100 45GB 초과. 구조적 VRAM 한계.
- depth ≥ 16 → OOM (h5i6j7k): 동일 이유.

## [SOFT BLOCK] — 조건부 재시도 가능
현재 설정 기준으로 비효과적. `[조건: ...]` 태그에 명시된 변화 시 재검토 가능.
- GeLU activation: SiLU 대비 악화 (실험 c3d4e5f, depth=8 기준). [조건: depth 변경 시]
- weight decay 0.1: LR=0.04 조합에서 악화 (5회). [조건: LR 재설정 시]
- attention dropout: baseline 설정에서 일관 악화. [조건: 대형 아키텍처 전환 시]
```

> 규칙: SOFT BLOCK 항목은 반드시 `[조건: ...]` 태그를 포함할 것. 조건 불분명 → HARD BLOCK으로 보수적 분류.

**선택 기준**:
- HARD BLOCK: OOM, timeout, 수학적으로 불가능한 조합
- SOFT BLOCK: 특정 하이퍼파라미터 조합 의존적 실패, 가역적 실패

---

### A.4 git reset → 메모리 일관성 규칙 (Critic 신규 요구사항)

**핵심 통찰**: `memory/` 디렉토리는 git 미추적 파일 → git reset이 일어나도 영향 없음.
따라서 **reset 이전에 메모리를 업데이트해야** 일관성 보장.

**규칙: 메모리 업데이트 → git reset (이 순서 절대 준수)**

프로그램 스텝에 명시:
```
7. crash 발생 시:
   ① FAILED.md 업데이트 (HARD/SOFT 분류 후 기록)
   ② SUMMARY.md 시도된 방향에 추가
   ③ git reset --hard HEAD~1

9. discard 결정 시:
   ① FAILED.md 업데이트 (SOFT BLOCK으로 기록)
   ② SUMMARY.md 시도된 방향에 추가
   ③ git reset --hard HEAD~1

   ⚠️ 역순 금지: git reset을 먼저 하면 어떤 변경을 시도했는지 train.py에서 볼 수 없음
```

**왜 이 순서인가?**
- git reset은 즉시 완료, 이후 Claude가 메모리 업데이트를 잊을 수 있음
- 메모리를 먼저 기록하면 이후 과정 실패해도 실험 결과는 보존됨
- `results.tsv`에 기록(Step 8)과 동일 패턴으로 일관성 유지

**비정상 종료 복구 (Step 1에 추가)**:

```
1. 메모리 로딩 전, 이전 이터레이션 미정리 확인:
   - git log --oneline -1 로 마지막 커밋 확인
   - 해당 커밋 해시가 results.tsv에 없으면 → 이전 이터레이션이 비정상 종료된 것
   - git reset --hard HEAD~1 로 정리 후 계속
```

> **메모리는 캐시다**: `memory/`는 results.tsv의 파생 데이터. 불일치 발생 시 results.tsv가 진실의 원천. 메모리 파일이 없거나 손상되었으면 results.tsv에서 재생성 가능 → graceful degradation.

---

### A.5 program.md 수정 스텝 (Critic: 스텝 번호 충돌 해소)

**현재 program.md 실험 루프 (Steps 1-10)**:
```
1. results.tsv 읽기
2. 첫 실험이면 baseline 실행
3. 아이디어 선택, train.py 수정
4. git commit
5. uv run train.py
6. 결과 읽기
7. crash 처리 → git reset
8. results.tsv에 기록
9. keep/discard 결정 → git reset
10. 종료
```

**제안 수정 (메모리 스텝 삽입, 순서 조정)**:
```
1. [수정] 메모리 로딩:
   - memory/SUMMARY.md 읽기 (탐색 공간 지도 확인)
   - memory/FAILED.md 읽기 (HARD/SOFT 블록 확인)
   - results.tsv는 필요 시만 읽기 (세부 실험 데이터 필요할 때)

2. 첫 실험이면 baseline 실행 (기존 유지)

3. [수정] HARD BLOCK에 없는 방향 선택, train.py 수정
   (SUMMARY.md 미탐색 방향에서 우선 선택)

4. git commit (기존 유지)

5. uv run train.py > run.log 2>&1 (기존 유지)

6. 결과 읽기 (기존 유지)

7. [수정] crash 처리:
   - ① FAILED.md 업데이트 (HARD/SOFT 판단) ← 메모리 먼저
   - ② SUMMARY.md 시도된 방향에 추가
   - ③ git reset --hard HEAD~1

8. results.tsv에 기록 (기존 유지, git 미추적)

9. [수정] keep/discard 결정:
   - keep: SUMMARY.md 최고 val_bpb 갱신, 시도된 방향 업데이트
   - discard:
     - ① FAILED.md 업데이트 (SOFT BLOCK) ← 메모리 먼저
     - ② SUMMARY.md 시도된 방향에 추가
     - ③ git reset --hard HEAD~1

10. [신규] 메모리 최종 업데이트:
    - SUMMARY.md 미탐색 방향 업데이트 (방금 시도한 방향 제거)
    - 중요한 패턴 발견 시 INSIGHTS.md 추가

11. 종료 (기존 Step 10)
```

**스텝 수 증가 최소화**: 실질적 변화는 Step 1(메모리 로딩), Step 7/9(메모리→reset 순서), Step 10(신규 업데이트), Step 11(종료) 4개. 기존 Steps 2-6, 8은 그대로.

---

### A.6 최소 파일 구조

```
autoresearch/
├── train.py, prepare.py, program.md, ralph.sh  ← 기존 파일
├── results.tsv                                  ← 기존, git 미추적
└── memory/                                      ← 신규, git 미추적
    ├── SUMMARY.md    ← 탐색 공간 지도 (~300 토큰 목표)
    ├── FAILED.md     ← HARD/SOFT 2계층 블로킹
    ├── INSIGHTS.md   ← 검증된 패턴 (여러 실험 재현 시)
    └── QUEUE.md      ← 다음 실험 후보 큐 (선택적)
```

`.gitignore`에 추가:
```
memory/
results.tsv
run.log
```

---

## Part B: 창의적 사고실험

*현재 연구 문헌에 없거나 초기 단계인 아이디어들.*

---

### B.1 실험 그래디언트 메모리

**아이디어**: 실험을 성공/실패 이진이 아닌, **개선 벡터의 그래디언트**로 기록

기존: "LR 0.04 효과 있음 / 없음"
제안: "LR 방향 ↑ → Δval_bpb 음수 (개선), 최적점 추정 ~0.04"

```markdown
# 그래디언트 지도
- LR: ↑ 방향 개선 (-) → 최적 ~0.04 (0.05 이상 발산)
- Depth: ↑ plateau (8이상 한계수익 감소)
- Warmup steps: ↑ 개선 중 (아직 최솟값 미발견)
- Batch size: 미탐색
```

**실험 선택 로직**: 그래디언트가 아직 0에 수렴하지 않은 방향 우선 탐색. SGD가 기울기 방향으로 파라미터를 업데이트하듯, 에이전트가 개선 방향으로 실험 공간을 탐색.

**연구 연결**: Bayesian Optimization의 acquisition function 개념 — 어느 방향의 불확실성이 가장 높은가?를 암묵적으로 추론.

**현황**: 현재 autoresearch에 존재하지 않음. HPO(Hyperparameter Optimization) 분야의 sequential model-based optimization 원리를 메모리 형식으로 경량화한 아이디어.

---

### B.2 실패 분류학 메모리 (Failure Taxonomy)

**아이디어**: FAILED.md를 단순 목록이 아닌 **원인 트리**로 구조화

```markdown
# 실패 분류 트리
├── 하드웨어 한계
│   ├── VRAM 초과 (OOM): depth≥12, width×2
│   └── 시간 초과: 아직 없음
├── 최적화 실패
│   ├── 발산 (NaN/Inf): LR≥0.05
│   └── 정체: LR≤0.01
└── 아키텍처 부적합
    ├── GeLU (표현력 문제 아닌 학습 동역학)
    └── attention dropout (5분 예산에서 regularization 과잉)
```

**장점**: 새 실패 발생 시 "같은 트리 브랜치에 속하는가?" 판단 → 새로운 분기이면 탐색 가치 있음, 같은 분기면 건너뜀.

**연구 연결**: A-MEM의 Zettelkasten 원칙 — 새 노트(실패)가 기존 노트(실패 분류)를 동적 업데이트. 지금까지 실패 메모리에 적용한 사례 없음.

---

### B.3 메타 루프 에이전트 (30 이터레이션마다 전략 재조정)

**아이디어**: 실험 에이전트(매 5분)와 별개로, **메타 에이전트**(매 30 이터레이션)가 전략 수준에서 SUMMARY.md를 재작성

```bash
# ralph.sh 수정안
if (( LOOP_COUNT % 30 == 0 )); then
    echo "=== 메타 분석 실행 (이터레이션 #${LOOP_COUNT}) ==="
    claude -p --allowedTools "Read,Write" \
        "results.tsv 전체를 분석하라. 탐색 공간 편향이 있는가?
         특정 방향(LR 등)만 과도하게 시도되었는가?
         memory/SUMMARY.md를 전략적 수준에서 재작성하라."
fi
```

**메타 에이전트의 질문들**:
- "지금까지 LR을 20회 변경했는데, 아키텍처 변경은 3회뿐이다. 탐색이 편향되었는가?"
- "개선률이 마지막 10회 동안 0.001 이하다. 지역 최솟값에 갇혔는가? 큰 변화가 필요한가?"
- "HARD BLOCK에 없는데 아직 시도하지 않은 방향은 무엇인가?"

**연구 연결**: Synapse의 spreading activation — 메타 에이전트가 의미 그래프에서 활성화를 퍼뜨려 관련 실험들을 연결하고 패턴을 추출하는 방식.

---

### B.4 자기 압축 메모리 (Self-Compacting Memory)

**아이디어**: SUMMARY.md가 500토큰 초과 시 **스스로 압축**

문제: SUMMARY.md도 쌓이면 커짐 → 원래 문제(O(N) 토큰) 재발

해결 메커니즘:
```markdown
## SUMMARY.md 자기 압축 규칙 (program.md에 추가)
- 파일이 500토큰 초과하면: 오래된 "시도된 방향" 항목을 카테고리로 압축
  예: "LR 관련 실험 15회 → 최적 LR≈0.04로 수렴, 세부 기록은 results.tsv 참조"
- 압축 전 원본은 memory/ARCHIVE_YYYY-MM-DD.md에 보존
- 미탐색 방향과 HARD BLOCK은 압축 대상 제외
```

**MIRIX 연결**: Episodic Memory(세부 실험 기록) → Semantic Memory(압축된 패턴)로 자동 승격하는 메커니즘을 파일 시스템에서 구현.

**OpenClaw 연결**: "auto-flush before compaction" 패턴과 동일 원리 — 컨텍스트 압축 전에 중요 정보를 디스크에 내보내 메모리 손실 방지.

---

### B.5 반사실적 기록 (Counterfactual Memory)

**아이디어**: "시도한 것" 외에 **"시도하려다 포기한 것"**도 기록

현재 누락: 에이전트가 어떤 아이디어를 떠올렸다가 이유 없이 포기했는지 추적 불가.

```markdown
# 포기한 아이디어 (미실험)
## 현재 불가 (외부 제약)
- Flash Attention 3 커널: CUDA 버전 불일치, 현재 환경 미지원
- FP8 훈련: transformer-engine 미설치, pyproject.toml 제약

## simplicity criterion 위반
- Mixture of Experts: 구현 복잡도 과다 (예상 +150 LOC)
- Custom CUDA 커널: 의존성 추가 불가

## 나중에 재검토
- Flash Attention 3: CUDA 업그레이드 후 재검토
```

**장점**: 에이전트가 같은 아이디어를 생각했을 때 "왜 포기했는가"를 확인 → **조건이 변한 경우**만 재검토 (e.g., 플랫폼 업그레이드 후).

**현황**: 에이전트 메모리 연구에 이 개념을 명시적으로 다룬 논문 없음. 인지심리학의 반사실적 사고(counterfactual thinking) 연구에서 영감. 새로운 제안.

---

### B.6 탐색 큐 (QUEUE.md)

**아이디어**: 미탐색 방향을 **우선순위 큐**로 명시적 관리

```markdown
# QUEUE.md — 다음 실험 후보 (상단 우선)
## [HIGH] 즉시 시도
1. GQA (Grouped Query Attention): LM 논문에서 일관 개선, 미시도
2. Muon β2=0.98: 현재 0.95, 미세 조정 여지

## [MEDIUM] 조건부 시도
3. 배치 사이즈 2배: VRAM 허용 시 (현재 ~44GB, 여유 1GB)
4. Cosine LR decay 주기 절반: 5분 예산에서 더 빠른 스케줄링

## [LOW] 위험 감수 시도
5. ALiBi positional encoding: RoPE 대체, 구현 복잡도 중간
6. Lion 옵티마이저: Muon 대체 실험
```

에이전트 행동: QUEUE.md 최상단에서 하나 선택 → 실험 후 큐에서 제거 → 결과에서 새 아이디어 추가.

**연구 연결**: RL의 replay buffer 개념. exploration policy를 명시적 큐로 구현. Synapse의 "미탐색 활성화 노드 우선 방문" 원칙의 경량 파일 기반 구현.

**단순성**: QUEUE.md는 SUMMARY.md의 "미탐색 방향"을 별도 파일로 분리한 것. 필요 없으면 SUMMARY.md에 통합 가능 (선택적).

---

## 최종 권장 요약

### 즉시 적용 (Phase 1, 구현 30분)

```bash
mkdir -p memory
cat > memory/SUMMARY.md << 'EOF'
# 탐색 공간 지도 | 총 실험: 0회 | 최고 val_bpb: (베이스라인 후 기록)
## 시도된 방향
(실험 후 채워질 예정)
## 미탐색 방향
- GQA, Muon 변형, Dynamic batch size, ALiBi, ...
EOF
touch memory/FAILED.md memory/INSIGHTS.md
echo "memory/" >> .gitignore
```

program.md 수정: Steps 1 (메모리 로딩), 7/9 (메모리→reset 순서), 10 (신규 업데이트).

### 효과 추정

| 지표 | 현재 | 제안 후 |
|------|------|---------|
| results.tsv 읽기 토큰 (100회 시점) | ~3,000 | ~300 (-90%) |
| 전체 이터레이션 컨텍스트 | ~12,200 | ~9,500 |
| **전체 컨텍스트 절감** | 기준 | **~22% 절감** |
| 중복 실험 방지 | 없음 | HARD/SOFT BLOCK |
| 탐색 편향 방지 | 없음 | 탐색 공간 지도 |
| 지식 누적 | 없음 | INSIGHTS.md |

> **결론**: 숫자보다 질적 이점이 더 크다. GPU 5분 + API 비용 = 실험 1회 비용. 중복 실험 5회만 방지해도 memory 시스템의 ROI를 초과한다.

### 단순성 반론 (steelman)에 대한 답변

*"results.tsv는 100회 시점에서도 전체 컨텍스트의 25%뿐이다. stateless 단순성을 포기할 만한 이익인가?"*

이 반론은 타당하다. 그래서 다음 원칙을 제안한다:

**메모리는 결과의 캐시이지, 진실의 원천이 아니다.**

- `results.tsv` = 진실의 원천 (항상 유지, git 미추적)
- `memory/SUMMARY.md` = 캐시 (results.tsv에서 언제든 재생성 가능)
- 불일치 발생 시: results.tsv로 fallback → stateless 모드로 graceful degradation
- 50회 미만 실험: memory 시스템 없이 기존 방식으로 충분
- **100회 이상**: 중복 실험 비용 > memory 관리 복잡도

실험 횟수에 따라 도입 시점을 조절하면 단순성을 최대한 보존하면서 장기 이점을 취할 수 있다.

### 선택적 적용 (Phase 2, 필요에 따라)

| 사고실험 | 구현 난이도 | 기대 효과 | 독창성 |
|---------|-----------|----------|--------|
| 그래디언트 메모리 | 낮음 | 탐색 방향 최적화 | 중간 (BO 기반) |
| 실패 분류학 | 낮음 | 중복 실패 방지 | 중간 (A-MEM 응용) |
| 메타 루프 에이전트 | 중간 | 전략적 탐색 재조정 | 높음 |
| 자기 압축 메모리 | 낮음 | 장기 토큰 안정 | 중간 |
| 반사실적 기록 | 낮음 | 포기한 아이디어 추적 | **높음 (신규)** |
| 탐색 큐 | 낮음 | 탐색 우선순위 명시 | 중간 |

---

*이 제안은 autoresearch의 단순성 원칙(오컴의 면도날)을 최대한 준수하면서, 최소한의 변경으로 최대 메모리 효율을 달성하는 것을 목표로 합니다.*
