# GEPA 프롬프트 최적화 기술 분석 보고서

> **저장소**: https://github.com/gepa-ai/gepa
> **논문**: arXiv:2507.19457 — "Reflective Prompt Evolution Can Outperform Reinforcement Learning" (ICLR 2026 Oral)
> **작성일**: 2026-03-12

---

## 목차

1. [GEPA란 무엇인가](#1-gepa란-무엇인가)
2. [해결하려는 문제](#2-해결하려는-문제)
3. [핵심 알고리즘: 반성적 진화 (Reflective Evolution)](#3-핵심-알고리즘-반성적-진화)
4. [5단계 최적화 프로세스](#4-5단계-최적화-프로세스)
5. [파레토 기반 후보 선택 (핵심 차별점)](#5-파레토-기반-후보-선택-핵심-차별점)
6. [시스템 인식 병합 (Crossover)](#6-시스템-인식-병합-crossover)
7. [입력/출력 구조](#7-입력출력-구조)
8. [다른 기법과의 비교](#8-다른-기법과의-비교)
9. [성능 벤치마크 결과](#9-성능-벤치마크-결과)
10. [코드 구조 및 확장성](#10-코드-구조-및-확장성)
11. [핵심 요약](#11-핵심-요약)

---

## 1. GEPA란 무엇인가

**GEPA** (Genetic-Pareto Prompt Optimization)는 LLM의 프롬프트를 자동으로 최적화하는 시스템이다. 사람이 직접 프롬프트를 튜닝하는 대신, GEPA가 수십~수백 번의 실험을 통해 스스로 더 좋은 프롬프트를 찾아낸다.

핵심 아이디어는 단 하나다:

> **"LLM이 실패할 때 나오는 자연어 실행 로그(트레이스)는 숫자 스코어보다 훨씬 풍부한 학습 신호다"**

실패한 LLM 실행에는 오류 메시지, 추론 과정, 잘못된 답변의 이유가 모두 담겨 있다. GEPA는 이 텍스트를 그대로 "왜 틀렸는가"의 근거로 활용해 다음 프롬프트를 작성한다.

---

## 2. 해결하려는 문제

### 기존 방식의 한계

| 방식 | 문제점 |
|------|--------|
| **강화학습 (GRPO 등)** | 24,000~250,000회 롤아웃 필요. 비용이 너무 크다 |
| **MIPROv2 (DSPy)** | 스코어만 보고 최적화 → 로컬 옵티마에 빠짐. 프롬프트가 예시 묶음처럼 길어짐 |
| **TextGrad / APE** | 현재 최고 후보 1개에서만 탐색 → 다양성 없음 |
| **수동 튜닝** | 시간 비용 큼, 재현성 없음 |

### GEPA의 해결 방향

- 롤아웃 수를 **35배 줄이면서** GRPO보다 높은 성능 달성
- 단순 스코어가 아닌 **전체 실행 트레이스(ASI)**를 학습 신호로 사용
- **파레토 프론티어** 기반 다양성 유지로 로컬 옵티마 탈출

---

## 3. 핵심 알고리즘: 반성적 진화

GEPA의 알고리즘 이름은 **Reflective Evolutionary Prompt Optimizer**다. 세 개의 개념이 합쳐진 것이다:

```
유전 알고리즘 (Genetic)
  + 파레토 최적화 (Pareto)
  + LLM 자기반성 (Reflection)
= GEPA
```

### 알고리즘 전체 흐름 (의사코드)

```
입력: 초기 프롬프트 Φ, 학습데이터 D_train, 검증데이터 D_val, 예산 B

1. 후보 풀 초기화: P = [Φ_seed]
2. 씨앗 프롬프트를 D_val 전체에서 평가

반복 (예산 B 소진까지):
   a. 파레토 프론티어에서 후보 k 선택
   b. 컴포넌트 j 선택 (멀티모듈인 경우 라운드로빈)
   c. 미니배치 M을 D_train에서 추출
   d. 후보 k를 M에서 실행 → 실행 트레이스 + 피드백 수집
   e. LLM에게 트레이스를 보여주고 "더 나은 프롬프트"를 작성하게 함
   f. 새 후보 Φ' 생성 (j번째 컴포넌트만 교체)
   g. M에서 재평가: 개선되면 P에 추가, 아니면 폐기
   h. 파레토 프론티어 업데이트

결과: 검증셋에서 최고 점수 후보 반환
```

---

## 4. 5단계 최적화 프로세스

README에서 설명하는 GEPA의 실제 작동 5단계:

### Step 1: SELECT — 후보 선택

단순히 "가장 점수 높은 것"을 선택하지 않는다. **파레토 프론티어**에서 다양성을 고려해 확률적으로 샘플링한다 (자세한 내용은 5장 참조).

### Step 2: EXECUTE — 실행 + 트레이스 수집

```python
evaluation_batch = adapter.evaluate(
    batch=minibatch,
    candidate=current_prompt,
    capture_traces=True  ← 트레이스 수집 활성화
)
# 결과: outputs, scores, trajectories (실행 로그), objective_scores
```

각 실행 결과는 단순 점수가 아니라:
- 모델이 생성한 텍스트
- 성공/실패 여부
- **왜 실패했는지 설명 (피드백 텍스트)**
- 전체 추론 체인

### Step 3: REFLECT — LLM 반성

GEPA의 핵심 단계. 수집된 트레이스를 **Actionable Side Information (ASI)**로 변환한다:

```python
reflective_dataset = {
    "Inputs":             "수학 문제: 3x + 5 = 20에서 x는?",
    "Generated Outputs":  "x = 4 (계산 과정 생략)",
    "Feedback":           "답은 맞지만 단계별 설명이 없어 채점 불가"
}
```

이 데이터를 반성 LLM (예: GPT-5, gpt-4.1)에게 전달하는 메타-프롬프트:

```
나는 어시스턴트에게 다음 지시를 제공했습니다:
```{현재 프롬프트}```

다음은 다양한 입력에 대한 어시스턴트의 응답과 개선 피드백입니다:
```{ASI 데이터셋}```

이제 어시스턴트를 위한 새로운 지시를 작성하세요...
```

반성 LLM은 이것을 읽고 **왜 실패했는지 이해한 후** 개선된 프롬프트를 작성한다.

### Step 4: MUTATE — 프롬프트 교체

```python
new_candidate = current_candidate.copy()
new_candidate[component_name] = improved_prompt_text
# 멀티컴포넌트 시스템: 1개 컴포넌트만 교체, 나머지는 그대로
```

이를 통해 **외과적 수정**이 가능하다. DSPy 파이프라인처럼 여러 프롬프트가 있는 경우, 한 번에 하나씩 순서대로 개선한다.

### Step 5: ACCEPT/REJECT — 검증 게이트

```python
new_scores = adapter.evaluate(minibatch, new_candidate)
if sum(new_scores) > sum(old_scores):
    # 후보 풀에 추가 + 파레토 프론티어 업데이트
else:
    # 폐기 (풀을 오염시키지 않음)
```

---

## 5. 파레토 기반 후보 선택 (핵심 차별점)

이것이 GEPA가 MIPROv2/TextGrad를 크게 앞서는 이유다.

### 문제: 단순 "최고 후보" 선택의 함정

기존 방법들은 "현재까지 가장 점수 높은 프롬프트"에서만 탐색한다. 이러면 어떻게 될까?

```
검증 문제 10개가 있다고 가정:

프롬프트 A: 문제 1~7 모두 정답, 문제 8~10 틀림  → 평균 70점
프롬프트 B: 문제 1~5 정답, 문제 6~10 정답        → 평균 70점

단순 선택: A와 B 중 랜덤 선택 → 놓치는 게 있음
파레토:   문제 8,9,10에선 B가 최고, 다른 문제에선 A가 최고
          → 두 프롬프트 모두 유지, 서로 다른 "전문성" 활용
```

### GEPA의 파레토 프론티어 알고리즘 (Algorithm 2)

```python
# 검증셋의 각 예제 i마다:
#   s*[i] = 어떤 후보라도 달성한 최고 점수
#   P*[i] = 예제 i에서 최고점 달성한 후보들의 집합

# 모든 P*[i]의 합집합 = 파레토 프론티어 C
# 지배당한(dominated) 후보 제거

# 선택 확률 = 해당 후보가 "최고인 예제" 수에 비례
```

**4가지 프론티어 모드**:
| 모드 | 설명 |
|------|------|
| `instance` | 검증 예제별 (기본값) |
| `objective` | 메트릭 목표별 |
| `hybrid` | 예제 + 목표 모두 |
| `cartesian` | (예제, 목표) 쌍별 |

### 실험 결과 비교 (Qwen3-8B 기준)

| 선택 전략 | HotpotQA | IFBench | HoVer | PUPA | 평균 향상 |
|-----------|----------|---------|-------|------|-----------|
| 기준선 | 42.33 | 36.90 | 35.33 | 80.82 | — |
| TextGrad 방식 (최고 후보만) | 58.33 | 30.44 | 45.33 | 85.45 | +6.05% |
| APO 방식 (빔서치) | 57.33 | 36.39 | 41.00 | 81.08 | +5.11% |
| **GEPA (파레토)** | **62.33** | **38.61** | **52.33** | **91.85** | **+12.44%** |

---

## 6. 시스템 인식 병합 (Crossover)

`use_merge=True` 옵션 사용 시, 두 파레토 최적 후보를 **지능적으로 결합**한다.

### 병합 로직

```
공통 조상 Ancestor를 가진 두 후보 id1, id2에 대해:

각 컴포넌트마다:
  - id1, id2 모두 Ancestor와 동일 → 그대로 유지
  - id1만 진화됨 → id1 버전 채택 (새로운 변화를 보존)
  - id2만 진화됨 → id2 버전 채택
  - 둘 다 진화됨 → 점수 높은 쪽 채택
```

**직관**: id1이 쿼리 생성 프롬프트를 개선하고, id2가 추론 프롬프트를 개선했다면, 병합 후보는 두 개선을 모두 가져간다.

**효과**: 평균 +2%, 개별 태스크 최대 +5% 추가 향상.

---

## 7. 입력/출력 구조

### API 사용법

```python
import gepa

result = gepa.optimize(
    seed_candidate={"system_prompt": "수학 문제를 풀어주세요."},
    trainset=[
        {"input": "3x + 5 = 20", "answer": "x = 5"},
        ...
    ],
    valset=[...],
    reflection_lm="openai/gpt-5",        # 반성용 LLM
    task_lm="openai/gpt-4.1-mini",        # 태스크 실행 LLM
    max_metric_calls=500,                  # 평가 예산
)

# 결과
print(result.best_candidate)
# {"system_prompt": "수학 문제를 단계별로 풀어주세요. 먼저 변수를 격리하고..."}
```

### 커스텀 평가자 (피드백 포함)

```python
def my_evaluator(inputs, outputs, gold):
    if correct(outputs, gold):
        return 1.0, "정확한 답변입니다."
    else:
        return 0.0, f"오답: '{outputs}'. 기대값: '{gold}'. 단계별 풀이가 필요합니다."
    # ↑ 이 피드백 문자열이 ASI가 됨
```

### `optimize_anything` 범용 API

프롬프트 외에도 **임의의 텍스트 아티팩트** (코드, CUDA 커널, 3D 모델 코드 등) 최적화 가능:

```python
from gepa import optimize_anything

# 코딩 문제 최적화
result = optimize_anything(
    seed_candidate="def pack_circles(): ...",
    evaluator=lambda code: run_and_score(code),
    objective="단위 정사각형 내 원들의 반지름 합 최대화",
    config=GEPAConfig(max_metric_calls=500),
)

# 씨앗 없이 시작 (LLM이 초안 생성)
result = optimize_anything(
    seed_candidate=None,
    evaluator=evaluate_render,
    objective="Python으로 3D 유니콘 생성",
    background="build123d 라이브러리 사용",
)
```

---

## 8. 다른 기법과의 비교

| 비교 항목 | **GEPA** | MIPROv2 | TextGrad | APE/OPRO | GRPO (RL) |
|-----------|---------|---------|----------|----------|-----------|
| **학습 신호** | 자연어 실행 트레이스 (ASI) | 스코어 기반 | 텍스트 그래디언트 | 스코어 기반 | 스칼라 보상 → 정책 그래디언트 |
| **후보 선택** | 파레토 프론티어 | 단일 최고 | 단일 최고 | 빔서치 | N/A (가중치 업데이트) |
| **멀티모듈** | ✅ 라운드로빈 | ✅ DSPy만 | ⚠️ 제한적 | ❌ | ❌ |
| **최적화 대상** | 프롬프트 (가중치 고정) | 프롬프트+예시 | 프롬프트 | 프롬프트 | 모델 가중치 |
| **필요 평가 횟수** | **100~500회** | 500~2,000회 | 100~500회 | 100~500회 | **5,000~25,000+회** |
| **결과 프롬프트 길이** | 짧고 선언적 | 길고 예시 의존적 | 짧은 재작성 | 짧은 재작성 | N/A |
| **타 모델 전이** | ✅ (+9% 제로샷) | ❌ | ❌ | 미검증 | ❌ |
| **코드/아키텍처 최적화** | ✅ optimize_anything | ❌ | ❌ | ❌ | ❌ |
| **다목적 최적화** | ✅ 파레토 프론트 | ❌ | ❌ | ❌ | ❌ |

### MIPROv2와의 본질적 차이

MIPROv2는 지시문과 예시(few-shot demonstrations)를 함께 최적화해 프롬프트가 **예시 묶음처럼** 길어진다. GEPA는 **선언적 지시문**만 최적화해 최대 9.2배 짧으면서도 더 잘 일반화된다.

### GRPO와의 본질적 차이

GRPO는 롤아웃 트레이스를 스칼라로 **압축**한 뒤 정책 그래디언트를 계산한다. GEPA는 **전체 트레이스를 그대로** 반성 LLM에게 전달해 신용 배분(credit assignment)을 자연어로 수행한다. 이것이 35배 적은 롤아웃으로 같거나 더 높은 성능을 내는 이유다.

---

## 9. 성능 벤치마크 결과

### Qwen3-8B (오픈소스 모델)

| 방법 | HotpotQA | IFBench | HoVer | PUPA | AIME-2025 | LiveBench-Math | **종합** |
|------|----------|---------|-------|------|-----------|----------------|---------|
| 기준선 | 42.33 | 36.90 | 35.33 | 80.82 | 27.33 | 48.70 | 45.23 |
| GRPO (24k 롤아웃) | 43.33 | 35.88 | 38.67 | 86.66 | 38.00 | 51.26 | 48.91 (+3.68%) |
| MIPROv2 | 55.33 | 36.22 | 47.33 | 81.55 | 20.00 | 46.60 | 47.84 (+2.61%) |
| **GEPA** | **62.33** | **38.61** | **52.33** | **91.85** | **32.00** | **51.95** | **54.85 (+9.62%)** |
| GEPA+Merge | 64.33 | 28.23 | 51.67 | 86.26 | 32.00 | 51.95 | 52.40 |

> GEPA 사용 롤아웃: 1,839~7,051회 (GRPO 대비 **35배 이하**)

### GPT-4.1 Mini (API 모델)

| 방법 | HotpotQA | IFBench | HoVer | PUPA | AIME-2025 | LiveBench-Math | **종합** |
|------|----------|---------|-------|------|-----------|----------------|---------|
| 기준선 | 38.00 | 47.79 | 46.33 | 78.57 | 49.33 | 58.20 | 53.03 |
| TextGrad | 62.33 | 48.64 | 47.67 | 85.68 | 46.67 | 63.84 | 59.14 (+6.11%) |
| MIPROv2 | 58.00 | 49.15 | 48.33 | 83.37 | 51.33 | 61.84 | 58.67 (+5.64%) |
| **GEPA** | **69.00** | **52.72** | **51.67** | **94.47** | **59.33** | **64.13** | **65.22 (+12.19%)** |
| GEPA+Merge | 65.67 | 55.95 | 56.67 | 96.46 | 59.33 | 64.13 | 66.36 (+13.33%) |

### 크로스모델 전이 (놀라운 결과)

| 실험 | 결과 |
|------|------|
| Qwen3-8B로 최적화 → GPT-4.1 Mini에 적용 (제로샷) | **+9.00%** 향상 |

→ GEPA가 만든 프롬프트는 최적화 대상 모델이 아닌 다른 모델에서도 효과적이다.

### 기타 태스크 결과

| 태스크 | 시작 | GEPA 후 |
|--------|------|---------|
| AIME 2025 (GPT-4.1 Mini) | 46.6% | **56.6%** |
| MATH 벤치마크 (DSPy 전체 프로그램 진화) | 67% | **93%** |
| ARC-AGI (아키텍처 발견) | 32% | **89%** |
| Jinja 코딩 | 55% | **82%** |
| NPU 커널 최적화 (NPUEval) | 4.25% | **30.52%** |
| 클라우드 스케줄링 비용 절감 | — | **40.2%** 절감 |

---

## 10. 코드 구조 및 확장성

### 디렉토리 구조

```
src/gepa/
├── api.py                          # gepa.optimize() 메인 API
├── optimize_anything.py            # 범용 최적화 API
├── core/
│   ├── engine.py                   # 메인 최적화 루프
│   ├── adapter.py                  # GEPAAdapter 프로토콜
│   ├── state.py                    # 파레토 프론티어 + 후보 풀
│   └── result.py                   # 결과 반환 구조
├── proposer/
│   ├── merge.py                    # 크로스오버 로직
│   └── reflective_mutation/
│       └── reflective_mutation.py  # 반성적 변이 프로포저
├── strategies/
│   ├── candidate_selector.py       # 파레토/최고후보/엡실론-그리디
│   ├── instruction_proposal.py     # 반성 메타-프롬프트
│   └── component_selector.py      # 라운드로빈/전체
└── adapters/
    ├── default_adapter/            # 단일 턴 LLM 최적화
    ├── dspy_adapter/               # DSPy 시그니처 최적화
    ├── dspy_full_program_adapter/  # DSPy 전체 프로그램 진화
    ├── generic_rag_adapter/        # RAG 파이프라인 최적화
    ├── mcp_adapter/                # MCP 툴 설명 최적화
    └── terminal_bench_adapter/    # 터미널 에이전트 최적화
```

### GEPAAdapter 프로토콜 (통합 포인트)

```python
class GEPAAdapter(Protocol):
    def evaluate(
        self,
        batch: list[DataInst],
        candidate: dict[str, str],
        capture_traces: bool
    ) -> EvaluationBatch:
        """시스템 실행 → 출력 + 점수 + 트레이스 반환"""
        ...

    def make_reflective_dataset(
        self,
        candidate,
        eval_batch,
        components_to_update: list[str]
    ) -> dict[str, list[dict]]:
        """트레이스 → {"Inputs", "Generated Outputs", "Feedback"} 변환"""
        ...
```

이 두 메서드만 구현하면 어떤 시스템에도 GEPA를 적용할 수 있다.

---

## 11. 핵심 요약

### GEPA가 프롬프트를 최적화하는 방법 (한 문단 요약)

> GEPA는 "실패 로그를 읽고 반성하는 AI"를 반복 실행해 프롬프트를 개선한다. 매 이터레이션마다 파레토 프론티어에서 후보를 선택하고, 미니배치에서 실행해 전체 실행 트레이스(오류, 추론 과정, 피드백)를 수집한다. 이 트레이스를 반성 LLM에게 주어 "이전 프롬프트가 왜 실패했고 어떻게 고쳐야 하는가"를 자연어로 추론하게 한다. 개선된 프롬프트는 같은 미니배치에서 검증되어 통과하면 후보 풀에 추가된다. 핵심 차별점은 파레토 선택 전략: 단일 "최고 후보"가 아니라 "예제별 최고 후보들"의 집합을 유지해 로컬 옵티마를 탈출하고, 롤아웃 35배 절감으로 GRPO를 능가한다.

### 핵심 3가지

1. **반성 (Reflection)**: 스코어 대신 자연어 트레이스를 학습 신호로 → 더 풍부한 개선 방향
2. **파레토 선택**: "어떤 예제에서도 최고인 프롬프트"를 유지 → 로컬 옵티마 탈출
3. **진화 + 병합**: 조상 계보를 추적해 다른 방향으로 진화한 후보들을 결합 → 시너지

### 실용적 시사점

- **비용**: 롤아웃 200~500회로 GRPO급 성능 달성 (API 비용 대폭 절감)
- **이식성**: 최적화된 프롬프트가 타 모델에서도 +9% 제로샷 전이
- **범용성**: 단일 API 호출부터 DSPy 전체 프로그램, CUDA 커널까지 동일 프레임워크
- **적용 분야**: 에이전트 LLM, RAG, MCP 도구, 코딩 어시스턴트, 수학 추론 등

---

## 참고 자료

- [GitHub Repository](https://github.com/gepa-ai/gepa)
- [arXiv Paper](https://arxiv.org/abs/2507.19457) — ICLR 2026 Oral
- [공식 문서](https://gepa-ai.github.io/gepa)
- 통합 지원: MLflow, DSPy, HuggingFace, Google ADK
- 도입 사례: Shopify, Databricks, Dropbox
