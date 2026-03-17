# ReAct + Deferred Validation: 복잡한 DB Search Agent 설계

> 작성일: 2026-03-09
> 목적: tree/link 혼합 구조의 DB를 자유롭게 탐색하고, 탐색 완료 후 독립 검증자에게 검증을 맡기는 agent 아키텍처 설계 및 구현 가이드

---

## 1. 왜 이 패턴이 필요한가

### 기존 Plan-Execute-Validate의 한계

```
Planner → Searcher → Validator
```

처음부터 완벽한 계획을 세울 수 없는 경우가 있다:
- DB tree 구조는 특정 `node_id`를 타고 가봐야만 알 수 있음
- 예상한 노드가 없을 수도, 예상 못한 연결이 있을 수도 있음
- 탐색 중 발견한 정보가 계획 자체를 바꿔야 할 수 있음

### 해결책: ReAct + Deferred Validation

```
[Explorer — ReAct 루프]
  think → search → observe → think → search → ...
  (탐색하면서 실시간으로 방향 수정)
       ↓
  "찾은 것 같다" 싶을 때
  submit_for_validation() 호출
       ↓
[Validator — 독립 실행, as_tool]
  탐색 히스토리 없이 (질문 + 결과)만 봄
       ↓
  pass → 최종 답변
  fail → 피드백 → Explorer 계속 탐색
```

**ReAct**: Reasoning + Acting. 생각(think)과 행동(tool 호출)이 번갈아 반복되는 패턴
**Deferred Validation**: 탐색이 끝났다고 판단할 때 독립적 검증자에게 위임

---

## 2. 핵심 설계 원칙

### Validator의 독립성 — `as_tool()` 사용 이유

handoff를 쓰면 대화 히스토리 전체가 넘어간다:

```
handoff → Validator가 Planner/Searcher의 사고 과정을 봄
         → "Planner가 이렇게 했으니 맞겠지" 앵커링 편향 발생
         → 독립적 반례 탐색이 어려워짐 ❌
```

`as_tool()`을 쓰면 격리된 컨텍스트에서 실행:

```
as_tool → Validator는 딱 두 가지만 봄: 원본 질문 + 제출된 결과
          → 탐색 과정 모름 → 독립적 판단 가능 ✅
```

### `handoff` vs `as_tool` 비교

| | handoff | as_tool |
|---|---|---|
| 컨텍스트 | 전체 히스토리 넘어감 | 격리된 새 컨텍스트 |
| 제어권 | Orchestrator에서 완전히 넘어감 | Orchestrator가 결과 받고 계속 제어 |
| 적합한 경우 | 전문가 agent로 위임 | 독립적 판단이 필요한 검증 |

---

## 3. 전체 아키텍처

```
사용자 질문
    ↓
Runner.run(explorer, query, context=ExplorerContext(...))
    │
    ├── think(): "satellite 노드부터 찾아볼까"
    ├── get_children("satellite/"): → 결과 관찰
    ├── think(): "sensor_group 하위에 뭔가 있을 것 같음"
    ├── get_linked_nodes("sensor_group/A", "communicates_with"): → 관찰
    ├── think(): "답을 찾은 것 같다. 검증 요청해야겠다"
    └── submit_for_validation(answer, evidence)
                ↓ (as_tool — 독립 컨텍스트)
          Validator
            ├── pass → Explorer가 최종 답변 반환
            └── fail → "satellite_id 확인 안 됨" 피드백
                            ↓
                  Explorer가 피드백 보고 계속 탐색
```

---

## 4. 구현 코드

### 4-1. Context 정의

```python
from dataclasses import dataclass, field
from typing import Any

@dataclass
class ExplorerContext:
    db: Any
    domain_knowledge: dict
    original_query: str

    # 루프 종료 조건 (단 두 개)
    is_validated: bool = False   # True = 검증 통과 or 포기 → while 루프 탈출
    gave_up: bool = False        # True = give_up() 호출됨

    # iteration 간 메모리 (Reflexion 패턴)
    failed_approaches: list[str] = field(default_factory=list)
    iteration: int = 0
    max_iterations: int = 3
    validation_feedback: str | None = None

    # 탐색 누적
    visited_nodes: set[str] = field(default_factory=set)
    found_evidence: list[str] = field(default_factory=list)
```

**설계 원칙:**
- `is_validated`: 루프 종료의 유일한 신호. 검증 통과 또는 포기 시 `True`
- `gave_up`: 최종 답변이 "모릅니다"인지 구분
- `failed_approaches`: iteration 간 메모리 — 이전 실패 접근법을 다음 시도에 주입
- Phase enum / confidence_flag 없음 — 외부 while 루프가 흐름을 제어

### 4-2. Validator Agent

```python
from pydantic import BaseModel
from typing import Literal
from agents import Agent, Runner

class ValidationResult(BaseModel):
    verdict: Literal["pass", "fail"]
    issues: list[str]               # 발견된 문제들
    follow_up_hints: list[str]      # 더 탐색해볼 방향 힌트

validator_agent = Agent(
    name="Validator",
    instructions="""
    당신은 독립적인 검증자입니다.
    탐색 과정은 전혀 모릅니다. 오직 아래만 봅니다:
    - 원본 질문
    - 제출된 답변
    - 답변의 근거 목록

    ## 검증 체크리스트 (순서대로)
    1. **반례 탐색**: 이 답변이 틀릴 수 있는 경우를 3개 이상 생각하세요
    2. **근거 추적**: 각 답변 항목이 근거에서 실제로 도출되는가? 추론으로 채운 부분은 없는가?
    3. **논리적 비약**: 근거에서 답변까지 비약이 있는가?
    4. **질문 충족**: 답변이 원본 질문에 실제로 답하는가?
    5. **과신 탐지**: 확신 표현의 근거가 충분한가?

    판정:
    - pass: 위 체크리스트를 통과
    - fail: 하나라도 문제 발견 시 → issues와 follow_up_hints 상세히 기록
    """,
    output_type=ValidationResult,
    model="gpt-4.1",
    model_settings=ModelSettings(temperature=0.0),
)
```

### 4-3. Explorer Tools

```python
from agents import function_tool, RunContextWrapper

# think — 명시적 추론 (loop 계속 돌게 하는 역할)
@function_tool
async def think(wrapper: RunContextWrapper[ExplorerContext], thought: str) -> str:
    """
    탐색 중 생각을 정리할 때 사용하세요.
    - 다음에 어디를 탐색할지 결정
    - 수집한 증거를 정리
    - 현재 가설을 세우거나 수정
    반드시 tool 호출 전에 think로 계획을 세우세요.
    """
    wrapper.context.found_evidence.append(f"[추론] {thought}")
    return f"생각 완료: {thought}"

# 방향 수정 — 탐색 중 계획 변경
@function_tool
async def replan(
    wrapper: RunContextWrapper[ExplorerContext],
    reason: str,
    new_direction: str,
) -> str:
    """
    탐색 방향을 수정할 때 호출하세요.
    예: 예상한 노드가 없거나, 더 유망한 경로를 발견했을 때.
    """
    wrapper.context.found_evidence.append(
        f"[재계획] 이유: {reason} → 새 방향: {new_direction}"
    )
    return f"방향 변경: {new_direction}"

# 8개 검색 tool (LLM 친화적 설계 — SWE-agent 원칙)
@function_tool
async def get_children(
    wrapper: RunContextWrapper[ExplorerContext],
    node_id: str,
    max_results: int = 10,
) -> str:
    """
    특정 노드의 직접 자식 노드 목록 반환.
    언제 사용: 하위에 어떤 항목들이 있는지 탐색할 때.
    주의: 깊이 1만 반환. 더 깊이 탐색하려면 반환된 자식에 재호출.
    결과가 많으면 max_results 조정하거나 filter 사용.
    """
    wrapper.context.visited_nodes.add(node_id)
    children = await wrapper.context.db.get_children(node_id)
    if len(children) > max_results:
        return (
            f"총 {len(children)}개 (처음 {max_results}개만 표시): "
            f"{children[:max_results]}\n더 보려면 max_results를 늘리세요."
        )
    return str(children)

@function_tool
async def get_parent(wrapper: RunContextWrapper[ExplorerContext], node_id: str) -> str:
    """
    특정 노드의 부모 노드 반환.
    언제 사용: 현재 노드가 어디에 속하는지 확인할 때.
    """
    wrapper.context.visited_nodes.add(node_id)
    return str(await wrapper.context.db.get_parent(node_id))

@function_tool
async def get_attributes(wrapper: RunContextWrapper[ExplorerContext], node_id: str) -> str:
    """
    특정 노드의 속성(property) 전체 반환.
    언제 사용: 노드의 세부 정보가 필요할 때.
    """
    wrapper.context.visited_nodes.add(node_id)
    return str(await wrapper.context.db.get_attributes(node_id))

@function_tool
async def get_linked_nodes(
    wrapper: RunContextWrapper[ExplorerContext],
    node_id: str,
    link_type: str,
) -> str:
    """
    특정 노드와 연결된 노드를 link 타입별로 반환.
    언제 사용: tree 구조가 아닌 횡적 연결(참조, 의존, 통신 등) 탐색 시.
    link_type 예시: "depends_on", "communicates_with", "shares_resource"
    """
    wrapper.context.visited_nodes.add(node_id)
    return str(await wrapper.context.db.get_linked_nodes(node_id, link_type))

@function_tool
async def search_by_id(wrapper: RunContextWrapper[ExplorerContext], node_id: str) -> str:
    """특정 ID로 노드 직접 접근."""
    wrapper.context.visited_nodes.add(node_id)
    return str(await wrapper.context.db.get_node(node_id))

@function_tool
async def search_by_property(
    wrapper: RunContextWrapper[ExplorerContext],
    property_name: str,
    value: str,
) -> str:
    """속성값으로 노드 검색. 언제 사용: ID를 모를 때."""
    return str(await wrapper.context.db.search_by_property(property_name, value))

@function_tool
async def get_node_type(wrapper: RunContextWrapper[ExplorerContext], node_id: str) -> str:
    """노드의 타입 확인. 언제 사용: 이 노드가 무엇인지 파악할 때."""
    return str(await wrapper.context.db.get_node_type(node_id))

@function_tool
async def list_link_types(wrapper: RunContextWrapper[ExplorerContext], node_id: str) -> str:
    """이 노드에서 나가는/들어오는 link 타입 목록. 언제 사용: 어떤 연결이 있는지 전체 파악."""
    return str(await wrapper.context.db.list_link_types(node_id))
```

### 4-4. submit_for_validation + give_up Tool

```python
@function_tool
async def submit_for_validation(
    wrapper: RunContextWrapper[ExplorerContext],
    answer: str,
    evidence: list[str],
) -> str:
    """
    답을 찾았다는 확신이 들 때 독립 검증자에게 제출합니다.
    근거 목록을 반드시 포함하세요.
    검증 실패 시 피드백을 받아 탐색을 계속하세요.
    """
    ctx = wrapper.context

    # Validator 독립 실행 (context 안 넘김 — 완전 격리)
    result = await Runner.run(
        validator_agent,
        f"원본 질문: {ctx.original_query}\n\n답변: {answer}\n\n근거:\n" +
        "\n".join(f"- {e}" for e in evidence),
        # context 파라미터 없음 → Validator는 탐색 히스토리 모름
    )

    verdict = result.final_output

    if verdict.verdict == "pass":
        ctx.is_validated = True   # ← while 루프 탈출 신호
        return f"PASS: 검증 통과. 최종 답변: {answer}"
    else:
        feedback = (
            "실패 이유: " + ", ".join(verdict.issues) +
            " | 힌트: " + ", ".join(verdict.follow_up_hints)
        )
        ctx.failed_approaches.append(f"시도 {ctx.iteration + 1}: {answer[:80]}... → {feedback}")
        ctx.validation_feedback = feedback
        return f"FAIL: {feedback}\n계속 탐색하세요."


@function_tool
async def give_up(
    wrapper: RunContextWrapper[ExplorerContext],
    reason: str,
) -> str:
    """
    충분히 탐색했지만 DB에서 답을 찾을 수 없을 때 호출합니다.
    최소 3번 시도 후에만 호출 가능합니다.
    이 tool을 쓰면 '모릅니다'로 정직하게 답변할 수 있습니다.
    """
    ctx = wrapper.context
    if ctx.iteration < 3:
        return (
            f"❌ 아직 {ctx.iteration}번 시도했습니다. "
            f"최소 3번 후 포기 가능합니다. 계속 탐색하세요."
        )
    ctx.is_validated = True   # ← while 루프 탈출 신호
    ctx.gave_up = True
    return f"포기 선언. 이유: {reason}\n'찾을 수 없습니다'로 답변하세요."
```

### 4-5. Explorer Agent

```python
from agents import Agent, ModelSettings

def explorer_instructions(wrapper: RunContextWrapper[ExplorerContext], agent: Agent) -> str:
    ctx = wrapper.context

    knowledge_text = "\n".join(
        f"- {k}: {v}" for k, v in ctx.domain_knowledge.items()
    )
    failed_text = "\n".join(
        f"  {a}" for a in ctx.failed_approaches
    )
    last_warning = "\n⚠️ 마지막 시도입니다. give_up()도 고려하세요.\n" \
        if ctx.iteration >= ctx.max_iterations - 1 else ""

    return f"""
    당신은 복잡한 DB 탐색 전문가입니다.
    tree와 link가 혼합된 구조를 자유롭게 탐색합니다.

    ## 도메인 지식
    {knowledge_text}

    ## 탐색 원칙
    1. 행동 전 반드시 think()로 먼저 생각하세요
    2. 막힌 경로는 다른 경로로 우회
    3. 답을 찾았다는 확신이 들면 submit_for_validation() 호출
    4. 검증 실패 피드백을 받으면 그 힌트대로 다른 방향 탐색
    5. 3번 이상 실패 후 정말 모르겠으면 give_up() 호출

    ## 이전에 실패한 접근법 (반복 금지)
    {failed_text if failed_text else "없음 — 첫 시도입니다."}

    ## 검증 피드백
    {ctx.validation_feedback or "없음"}

    ## 현재 시도: {ctx.iteration}/{ctx.max_iterations}
    {last_warning}
    """

explorer = Agent(
    name="Explorer",
    instructions=explorer_instructions,
    tools=[
        think,
        get_parent,
        get_children,
        get_attributes,
        get_linked_nodes,
        search_by_id,
        search_by_property,
        get_node_type,
        list_link_types,
        submit_for_validation,
        give_up,              # 3회 후 포기 가능
    ],
    model="gpt-4.1",
    model_settings=ModelSettings(
        temperature=0.3,
        parallel_tool_calls=False,
    ),
)
```

### 4-6. 실행 진입점 — Ralph 스타일 외부 루프

루프 제어를 Python 코드에 둔다. 모델이 실수로 루프를 탈출할 수 없다.

```python
async def run_db_search(query: str) -> str:
    relevant_knowledge = domain_store.retrieve(query, top_k=5)

    ctx = ExplorerContext(
        db=db_connection,
        domain_knowledge=relevant_knowledge,
        original_query=query,
        max_iterations=3,
    )

    # Ralph 스타일: is_validated가 True가 될 때까지 반복
    while not ctx.is_validated:
        result = await Runner.run(
            explorer,
            query,
            context=ctx,
            max_turns=50,
        )

        ctx.iteration += 1

        # 모델이 submit/give_up 없이 끝낸 경우 (안전망)
        if not ctx.is_validated and ctx.iteration >= ctx.max_iterations:
            break

    if ctx.gave_up:
        return "해당 정보를 DB에서 찾을 수 없습니다."

    if ctx.is_validated:
        return result.final_output

    return "최대 시도 횟수 초과. 답을 찾지 못했습니다."
```

---

## 5. 루프 종료 조건 (3중 안전망)

| 레이어 | 위치 | 방법 | 설명 |
|---|---|---|---|
| 1 | Python while | `ctx.is_validated == True` | 정상 종료 (검증 통과 or 포기) |
| 2 | Python while | `ctx.iteration >= max_iterations` | 최대 반복 초과 강제 종료 |
| 3 | Runner | `max_turns=50` | 단일 탐색 내 무한 루프 방지 |

```
is_validated = True 설정 주체:
  submit_for_validation() → Validator pass 시
  give_up()              → 3회 이상 실패 후 포기 시
```

---

## 6. 관련 SOTA 패턴 비교

### ReAct (Yao et al., 2022) — 이 아키텍처의 기반

```
Think → Act → Observe → Think → Act → ...
```
생각과 행동의 교대. OpenAI Agents SDK에서는 `think` tool + 검색 tool로 자연스럽게 구현.

### Reflexion (Shinn et al., 2023)

실패 이유를 언어로 서술하여 에피소딕 메모리에 **누적**. 다음 시도 때 모든 이전 실패를 참고.

```python
# 이 아키텍처에 적용: validation_feedback을 누적하도록 수정
ctx.feedback_history.append(verdict.issues)  # 누적
# instructions에서: "모든 이전 실패:\n" + "\n".join(ctx.feedback_history)
```

### RAISE (2024)

ReAct + 작업 메모리(스크래치패드). 탐색이 길어지면 앞 내용을 잊는 문제 해결.
→ `found_evidence` 리스트가 이 역할.

### ReWOO (Xu et al., 2023)

탐색 경로가 예측 가능할 때: 전체 tool 호출 계획을 한 번에 작성하고 기계적으로 실행.
→ 토큰 절약. 하지만 동적 탐색에는 부적합.

### SWE-agent (2024) — tool 설계 원칙

LLM이 헷갈리지 않도록 tool을 설계하는 원칙:
- 결과가 많으면 **페이지네이션/요약** 제공
- tool description에 **언제 쓰는지** 명시
- **재호출 방법** 안내 포함

### Tree of Thoughts (Yao et al., 2023)

여러 탐색 경로를 **병렬**로 탐색 후 유망한 경로 선택. 탐색 비용이 크지만 복잡한 tree에 유리.

```python
# 병렬 탐색 예시 (비용 높음)
results = await asyncio.gather(
    Runner.run(explorer, query + " 경로A"),
    Runner.run(explorer, query + " 경로B"),
)
best = await Runner.run(path_evaluator, results)
```

### AlphaCodium 원칙 (코딩 에이전트)

LLM 평가 대신 **실제 실행 결과**로 검증. DB search에 적용:

```python
# Validator가 실제로 DB 재조회해서 검증
# → "이 답이 맞다면 이 쿼리 결과가 일치해야 한다"
expected = derive_verification_query(answer)
actual = await db.query(expected)
verdict = "pass" if matches(answer, actual) else "fail"
```

---

## 7. 적용 시 주의사항

1. **`parallel_tool_calls=False`**: 순차 탐색을 강제. 병렬 호출하면 context 상태 충돌 가능성
2. **`think` tool 필수**: 없으면 LLM이 "한 번만 생각하고 바로 검색" 패턴으로 수렴
3. **tool description 품질**: LLM이 언제 어떤 tool을 쓸지는 description에 달려 있음
4. **Validator 격리**: `Runner.run(validator, ..., context=None)` — context 절대 넘기지 않기
5. **max_turns 설정**: `think` + `search` 교대이므로 `max_turns`는 여유 있게 (50~100)

---

## 8. 약한 모델을 위한 신뢰성 설계 요약 (오컴의 면도날)

> 약한 모델일수록 프롬프트 지시를 무시하고 단계를 건너뛴다.
> 구조적 강제로 보완한다. **단, 최소한의 것만.**

### 핵심 원칙

```
프롬프트     = 모델에게 부탁 (무시 가능)
구조적 강제  = 코드 레벨 강제 (무시 불가)

약한 모델일수록 구조적 강제의 효과가 커진다.
```

### 최종 Context 필드 — 5개만

| 필드 | 타입 | 역할 |
|---|---|---|
| `is_validated` | bool | 루프 종료 신호 (검증 통과 or 포기) |
| `gave_up` | bool | "모릅니다" 답변 구분 |
| `failed_approaches` | list | iteration 간 메모리 — 반복 실패 방지 |
| `iteration` | int | give_up 게이트 + 안전망 |
| `validation_feedback` | str\|None | 다음 탐색에 힌트 주입 |

### 약한 모델의 주요 실패 패턴과 대응

| 실패 패턴 | 대응 |
|---|---|
| 검증 없이 아무 답변이나 출력 | while 루프: `is_validated=True` 아니면 재시도 |
| 같은 접근법 반복 | `failed_approaches` → instructions에 "반복 금지" 주입 |
| 무한 탐색 | `max_iterations` + `max_turns` 이중 안전망 |
| "모른다"는 말 못 함 | `give_up()` tool (3회 후에만 호출 가능) |

### 구조적 강제 vs 프롬프트 역할 분담

```
구조적 강제 (코드):
  - while 루프: is_validated=True 아니면 계속
  - give_up() 게이트: iteration < 3 이면 차단
  - submit_for_validation(): Validator 통과해야 is_validated=True

프롬프트 (instructions):
  - failed_approaches 보여주기 → "이 방향은 이미 실패했음"
  - validation_feedback 보여주기 → "이런 힌트로 재탐색"
  - 탐색 원칙 안내
```

### `give_up()` — "모르면 모른다" 신뢰성 핵심

```
왜 중요한가:
  약한 모델 → 확신 없어도 그럴듯한 답 생성 (hallucination)
  give_up() → "진짜 모를 때" 명시적으로 표현하는 출구

왜 3회 후에만:
  너무 일찍 포기하면 탐색을 충분히 안 한 것
  3회 = 충분히 시도했다는 최소 기준
```
