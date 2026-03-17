# Compare Agent — `agents/compare_agent.py`

## 역할

두 논문의 claim을 분류하고, 관계에 따라 pairwise 판정을 수행합니다. position bias를 제거하여 신뢰할 수 있는 비교 결과를 `comparisons` 테이블에 기록합니다.

---

## 설정

| 항목 | 값 |
|------|----|
| 모델 | `claude-haiku-4-5-20251001` |
| 도구 | 없음 (`allowed_tools=[]`) |
| OMC | 사용 안 함 (OMC_OPTS 미적용) |
| `max_turns` | 3 (Stop hook 재시도 허용) |
| `permission_mode` | `bypassPermissions` |
| Stop Hook | `enforce_comparison_quality` (분류/판정 미달 시 중지 거부) |

반복 횟수가 많은 비교 작업에 haiku를 사용하여 비용을 절감합니다. `max_turns=3`은 Stop hook이 최대 2회 거부할 수 있도록 합니다.

### Stop Hook 품질 게이트

`enforce_comparison_quality` 훅이 분류/판정 결과의 명확성을 강제합니다:
- 응답에 `opposing/complementary/orthogonal` 또는 `"winner"` 없음 → 거부
- 최대 3회 거부 후 안전 밸브로 통과

---

## 프롬프트 설계 원칙

```
- Research question이 PRIMARY 평가 기준 (관련성 > 일반 품질)
- Claim 분류는 research question 기준의 RELATIVE 판단
- Lakatos: 추상적 언급이 아닌 구체적 기준으로 운영
- Popper: 반증 불가능한 assumptions을 가진 논문은 페널티
- Chain-of-thought로 분류 정확도 향상
```

---

## 3단계 비교 프로세스

### 1단계: Claim 분류 — `_classify_claims()`

두 claim의 관계를 research question 맥락에서 세 가지 중 하나로 분류합니다.

| 분류 | 의미 | 이후 처리 |
|------|------|-----------|
| `opposing` | 서로 모순 | position bias 제거 후 pairwise 판정 |
| `complementary` | 같은 결론, 다른 근거 | 양쪽 모두 승리 기록 |
| `orthogonal` | 서로 무관 | 비교 없이 종료 (`None` 반환) |

불확실한 경우 기본값은 `orthogonal`입니다.

```python
CLASSIFY_PROMPT = """You are classifying claims in the context of this research question:
{research_question}

Claim A: {claim_a}
Claim B: {claim_b}

Classify their relationship WITH RESPECT TO THE RESEARCH QUESTION:
- "opposing": They give CONFLICTING answers or recommendations. This includes:
  direct contradiction, incompatible scope claims, or incompatible mechanisms.
- "complementary": They give COMPATIBLE answers that together provide a more complete
  picture. Different evidence for the same conclusion, or answers to different
  sub-questions that do not conflict.
- "orthogonal": They address UNRELATED aspects with no meaningful interaction.

If you are uncertain, respond "orthogonal".

Think step-by-step:
1. What sub-question of the research question does Claim A address?
2. What sub-question does Claim B address?
3. Do their answers conflict, complement, or ignore each other?

Output your reasoning in one sentence, then on a NEW LINE output ONLY the
classification word (opposing, complementary, or orthogonal)."""
```

**파싱**: Chain-of-thought 응답의 **마지막 줄**에서 분류어를 추출합니다. 마지막 줄에 없으면 전체 텍스트에서 세 단어 중 포함 여부로 추출합니다.

---

### 2단계: Complementary 처리 — 상호 이득

`complementary`로 분류된 경우 경쟁 없이 두 논문 모두 승리를 기록합니다.

```python
conn.execute("INSERT INTO comparisons (winner, loser, ...) VALUES (?, ?, ?)",
             (paper_a["id"], paper_b["id"], now))
conn.execute("INSERT INTO comparisons (winner, loser, ...) VALUES (?, ?, ?)",
             (paper_b["id"], paper_a["id"], now))
```

두 논문이 서로를 이겼다는 기록이 생기므로, PageRank 계산 시 양쪽의 fitness가 상승합니다. 실제 학계에서 독립 복제 연구가 서로를 강화하는 원리와 같습니다.

---

### 3단계: Opposing — Position Bias 제거

`opposing`인 경우만 아래 절차를 수행합니다.

```
순방향: A가 first, B가 second → judge 결과 (r1, reasoning1)
역방향: B가 first, A가 second → judge 결과 (r2, reasoning2)

r1과 r2가 같은 논문을 승자로 지목 → 확정
r1과 r2가 다른 결과 → position bias 감지, 결과 없음 (None 반환)
```

역방향 결과의 "A"는 실제 `paper_b`를 의미합니다. ID 매핑으로 보정합니다.

```python
forward_winner_id = paper_a["id"] if result_forward == "A" else paper_b["id"]
reverse_winner_id = paper_b["id"] if result_reverse == "A" else paper_a["id"]
```

---

## `_judge()` 함수

단일 judge 호출을 수행합니다. `JUDGE_OPPOSING_PROMPT`를 사용합니다.

```python
async def _judge(prompt_template, paper_first, paper_second, research_question="") -> Tuple[Optional[str], Optional[str]]:
```

- `paper_first`가 프롬프트의 "Paper A", `paper_second`가 "Paper B"
- 반환값: `("A", reasoning)` 또는 `("B", reasoning)` 또는 `(None, None)`(파싱 실패)

### `JUDGE_OPPOSING_PROMPT` 구조 — 4단계 평가 프레임워크

```
## Research Question (this defines what "better" means)
{research_question}

## Paper A
Claim: {claim_a}
Evidence: {evidence_a}
Assumptions (boundary conditions): {assumptions_a}

## Paper B
Claim: {claim_b}
Evidence: {evidence_b}
Assumptions (boundary conditions): {assumptions_b}

## Evaluation Criteria (in priority order)
1. RELEVANCE: Which claim more directly answers the research question?
   A brilliant paper about the wrong question loses to a decent paper about the right one.
2. EVIDENCE QUALITY: Which claim is better supported by its cited evidence?
   Peer-reviewed sources > technical reports > blog posts.
   Multiple independent sources > single source.
3. FALSIFIABILITY: Which paper has more specific, testable assumptions?
   "Works under conditions X, Y, Z" > "Generally applicable."
   PENALTY: vague assumptions (e.g., "standard conditions", "None stated")
   → treat as WEAKER because unfalsifiable claims cannot be scientifically evaluated.
4. LAKATOS PROGRESSIVENESS: Which claim makes NEW testable predictions
   beyond its evidence? A claim that only explains known facts is weaker
   than one that predicts something new and verifiable.

Respond with ONLY a JSON object:
{"winner": "A" or "B", "reasoning": "1-2 sentences citing which criteria decided it"}
```

4단계 우선순위: **RELEVANCE > EVIDENCE QUALITY > FALSIFIABILITY > LAKATOS PROGRESSIVENESS**. research_question에 대한 관련성이 최우선 기준입니다.

---

## `run_comparison()` 반환값

```python
async def run_comparison(
    conn: sqlite3.Connection,
    paper_a: dict,
    paper_b: dict,
    research_question: str = "",
) -> Optional[Tuple[str, str, str]]:
```

| 반환값 | 상황 |
|--------|------|
| `(winner_id, loser_id, reasoning)` | opposing 만장일치 또는 complementary 양쪽 승리 |
| `None` | orthogonal, position bias 감지, 파라미터 오류 |

`comparisons` 테이블 기록은 `run_comparison()` 내부에서 직접 수행합니다. 메인 루프는 반환값만 사용합니다.

### reasoning 전달

`reasoning`은 judge의 판정 이유입니다. 이 값은 메인 루프를 거쳐 reflector_agent에게 전달되어 더 정확한 annotation 추출에 활용됩니다.

```
run_comparison() → (winner_id, loser_id, reasoning)
    → 메인 루프 Phase 4
        → run_reflection(..., comparison_result=(winner_id, loser_id, reasoning))
```
