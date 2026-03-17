# 과학철학 통합 — 포퍼, 베이즈, 라카토슈

## 개요

세 철학자의 원리가 평가 파이프라인의 각 단계를 담당합니다.

```
포퍼  → 진입 게이트    (반증 불가능한 주장 차단)
베이즈 → 주 엔진       (증거 기반 신뢰도 갱신)
라카토슈 → 판정 기준    (진보 vs 퇴행 연구 프로그램 구별)
```

---

## 포퍼 (Karl Popper) — 반증 가능성 게이트

### 원리

과학적 주장은 반증이 가능해야 합니다. "모든 것에 적용되는" 주장은 과학적 주장이 아닙니다.

### 구현

research_agent의 시스템 프롬프트가 `assumptions` 필드를 필수로 요구합니다.

```
4. Include assumptions that could be challenged
```

`assumptions` 필드: claim이 성립하는 조건. 이 조건이 틀렸을 때 claim도 틀렸다고 볼 수 있어야 합니다.

```python
# _parse_paper_json() 폴백
paper.setdefault("assumptions", "None stated")
```

`"None stated"`가 들어온 논문은 반박 가능성이 낮은 약한 논문으로, judge 프롬프트에서 불리하게 평가될 수 있습니다.

### Popper 경고

`assumptions`가 없거나 너무 약한 논문이 감지되면 로그에 경고를 남깁니다. 현재 구현은 파싱 단계에서 폴백 값을 삽입하고, judge 프롬프트가 assumptions를 직접 LLM에게 전달하여 평가에 반영합니다.

---

## 베이즈 (Thomas Bayes) — 증거 기반 신뢰도 갱신

### 원리

새로운 증거가 나타날 때마다 기존 믿음을 업데이트합니다. 사전 확률 × 우도 = 사후 확률.

### 구현

비교 결과가 fitness를 업데이트합니다.

```
초기 fitness = 0.5  (사전 확률: 중립)

비교 결과 → comparisons 테이블 누적
→ PageRank 재계산
→ fitness 갱신 (사후 확률)
```

매 사이클마다 `calculate_fitness(conn, topic)`이 전체 `comparisons` 그래프를 기반으로 모든 논문의 fitness를 재계산합니다. 새 비교가 추가될 때마다 전체 분포가 재조정됩니다.

사이클이 누적될수록 비교 데이터가 많아지고 fitness 추정이 정밀해집니다. 초기에는 분산이 크고 나중에는 수렴합니다.

---

## 라카토슈 (Imre Lakatos) — 진보 vs 퇴행 연구 프로그램

### 원리

- **진보적 연구 프로그램**: 새로운 예측을 만들고 그 예측이 확인됨
- **퇴행적 연구 프로그램**: 반례가 나올 때마다 ad hoc 수정(땜질)으로 대응

진보적 프로그램이 퇴행적 프로그램보다 과학적으로 우월합니다.

### 구현 1 — Judge 프롬프트

opposing 비교 시 라카토슈 기준이 `JUDGE_OPPOSING_PROMPT`의 4단계 평가 기준 중 4번째로 명시됩니다.

```
4. LAKATOS PROGRESSIVENESS: Which claim makes NEW testable predictions
   beyond its evidence? A claim that only explains known facts is weaker
   than one that predicts something new and verifiable.
```

LLM judge가 두 논문을 비교할 때 새 예측을 제시하는 논문에 가산점을 줍니다. 다만 RELEVANCE(research question 관련성)와 EVIDENCE QUALITY(증거 품질), FALSIFIABILITY(반증 가능성)이 더 높은 우선순위를 가집니다.

### 구현 2 — REBUTTAL 논문

챔피언에 대한 반박 논문 생성 시 라카토슈 원리를 직접 지시합니다.

```
(Lakatos: require new predictions, not patches).
```

단순히 "챔피언이 틀렸다"고 주장하는 것이 아니라 새로운 예측을 제시하는 반박을 생성하도록 유도합니다.

---

## 3종 조합 요약

| 역할 | 철학자 | 질문 | 구현 위치 |
|------|--------|------|-----------|
| 진입 게이트 | 포퍼 | "반증 가능한가?" | `assumptions` 필드 필수화 |
| 신뢰도 갱신 | 베이즈 | "증거가 어떻게 분포하는가?" | comparisons → PageRank → fitness |
| 진보 판정 | 라카토슈 | "새 예측인가, 땜질인가?" | `JUDGE_OPPOSING_PROMPT` + `REBUTTAL_ADDITION` |

세 원리가 파이프라인의 서로 다른 단계를 담당하므로 충돌하지 않습니다. 포퍼가 약한 주장을 걸러내고, 베이즈가 남은 주장들의 상대적 신뢰도를 축적하고, 라카토슈가 대결 상황에서 최종 승자를 결정합니다.
