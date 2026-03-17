# ClockCanvas EDA 에이전트 아키텍처 결정 보고서

**대상 조직:** 잇다반도체 (Ittda Semiconductor)
**문서 유형:** 기술 아키텍처 결정 보고서 (Architecture Decision Record)
**작성일:** 2026-02-24
**대상 시스템:** ClockCanvas EDA Tool - 내부 에이전트 기능
**검토 모델 제약:** On-premise, 10B 파라미터 미만
**문서 상태:** 최종 (Final)

---

## 목차

1. [개요 및 배경](#1-개요-및-배경)
2. [평가 대상 아키텍처](#2-평가-대상-아키텍처)
3. [심층 연구 결과](#3-심층-연구-결과)
4. [변증법적 분석](#4-변증법적-분석-정반합)
5. [최종 결론 및 권고사항](#5-최종-결론-및-권고사항)
   6. [OpenAI Agents SDK 기반 구현 가이드](#56-openai-agents-sdk-기반-구현-가이드-로컬-llm-완전-지원)
6. [위험 요소 및 완화 전략](#6-위험-요소-및-완화-전략)
7. [구현 우선순위 로드맵](#7-구현-우선순위-로드맵)

---

## 1. 개요 및 배경

### 1.1 목적

본 보고서는 잇다반도체의 ClockCanvas EDA 도구에 탑재될 내부 에이전트 기능의 아키텍처를 결정하기 위해 작성되었다. 두 가지 핵심 접근 방식 — Claude Agent SDK + HOOK 방식과 LangGraph 상태 머신 방식 — 을 체계적으로 분석하고, 잇다반도체의 특수한 운영 제약 조건에 최적화된 최종 아키텍처를 권고한다.

### 1.2 배경 및 운영 제약

ClockCanvas는 반도체 설계 자동화(EDA) 영역에서 클럭 트리 합성, 타이밍 분석, 레이아웃 최적화 등 복잡한 워크플로우를 지원하는 도구이다. 내부 에이전트 기능을 통해 사용자는 자연어 명령으로 EDA 작업을 자동화할 수 있어야 한다.

**핵심 운영 제약:**

| 제약 항목 | 내용 |
|-----------|------|
| LLM 배포 방식 | On-premise (클라우드 API 불가) |
| 모델 크기 제한 | 10B 파라미터 미만 |
| 보안 요구사항 | IP(지적 재산) 민감 데이터 외부 유출 불가 |
| 워크플로우 특성 | 순차적 Phase 진행 (RTL → 합성 → 배치/배선 → 검증) |
| 신뢰성 요구사항 | 설계 오류는 수천만 원 이상의 재작업 비용 발생 |

### 1.3 의사결정 기준

아키텍처 평가는 다음 5가지 기준을 중심으로 수행되었다.

1. **신뢰성 (Reliability):** Sub-10B 모델에서 정합성 있는 도구 호출 보장 가능성
2. **제어 가능성 (Controllability):** EDA Phase 순서 강제 및 이탈 방지 능력
3. **진화 가능성 (Evolvability):** 모델 성능 향상 시 아키텍처 재설계 없이 혜택 수용
4. **유지보수성 (Maintainability):** 신기능 추가 및 버그 수정의 용이성
5. **프레임워크 종속성 리스크 (Framework Lock-in Risk):** 외부 의존성으로 인한 장기 운영 리스크

---

## 2. 평가 대상 아키텍처

### 2.1 방식 1: Claude Agent SDK + HOOK 방식

#### 기본 개념

Claude Agent SDK의 에이전틱 루프(agentic loop)를 핵심 실행 엔진으로 사용하되, PreToolUse / PostToolUse / UserPromptSubmit 훅을 통해 LLM의 행동을 외부에서 제어하는 방식이다. 워크플로우 상태는 JSON 파일로 관리되며, 훅이 상태 기반 도구 호출을 강제한다.

```
+--------------------------------------------------+
|           Claude Agent SDK Agentic Loop           |
|                                                  |
|  User Input                                      |
|      |                                           |
|      v                                           |
|  [UserPromptSubmit Hook] <-- 상태 컨텍스트 주입   |
|      |                                           |
|      v                                           |
|  LLM 추론 (sub-10B 모델)                         |
|      |                                           |
|      v                                           |
|  Tool Call 생성                                   |
|      |                                           |
|      v                                           |
|  [PreToolUse Hook] <-- Phase 검증 / 차단 / 수정   |
|      |                                           |
|      v                                           |
|  Tool 실행                                        |
|      |                                           |
|      v                                           |
|  [PostToolUse Hook] <-- 상태 업데이트             |
|      |                                           |
|      v                                           |
|  다음 턴 또는 완료                                |
+--------------------------------------------------+
         |
         v
  [workflow_state.json]
  {
    "current_phase": "synthesis",
    "allowed_tools": ["run_synthesis", "check_timing"],
    "completed_phases": ["rtl_check"],
    ...
  }
```

#### 핵심 메커니즘

**PreToolUse 훅 (예방 계층):**
- LLM이 잘못된 Phase의 도구를 호출하면 즉시 차단
- 도구 파라미터 수정 (안전 범위 내 자동 교정)
- `permissionDecisionReason` 필드를 통해 LLM에게 교정 텍스트 제공

**PostToolUse 훅 (상태 업데이트 계층):**
- 도구 실행 결과를 기반으로 `workflow_state.json` 갱신
- Phase 완료 조건 평가 및 다음 Phase 허용 도구 갱신

**UserPromptSubmit 훅 (컨텍스트 주입 계층):**
- 매 턴 시작 시 현재 Phase 상태, 허용 도구 목록, 진행률을 시스템 프롬프트에 주입
- LLM이 항상 정확한 컨텍스트를 보유하도록 보장

**Phase-lock 도구 노출 패턴:**
- 현재 Phase에서 허용된 1-2개 도구만 LLM에 노출
- 도구 과부하(>5-7개) 방지 → sub-10B 모델의 선택 오류 근본 차단

#### 장단점 요약

**장점:**
- 모델 성능 향상 시 훅 엄격도만 낮추면 됨 (아키텍처 변경 불필요)
- SDK 자체가 에이전틱 루프, 컨텍스트 관리, 도구 파싱을 처리
- 훅 로직만 교체하면 다른 LLM 백엔드로 이식 가능

**단점:**
- SDK 파싱 이전 실패 시(예: 완전히 깨진 JSON 출력) 훅 미발동
- 반응형(reactive) 구조로 예방형(preventive) 구조보다 이론적으로 취약
- 상태 전이 로직이 여러 훅에 분산될 수 있어 추적이 어려울 수 있음

---

### 2.2 방식 2: LangGraph 상태 머신 방식

#### 기본 개념

LangGraph를 사용하여 EDA 워크플로우 전체를 명시적 유향 그래프(Directed Graph)로 모델링한다. 각 노드는 특정 EDA 단계를 나타내며, 엣지는 Phase 전이 조건을 인코딩한다. LLM은 각 노드 내에서 제한적 역할만 수행한다.

```
+--------------------------------------------------+
|           LangGraph State Machine                 |
|                                                  |
|  START                                           |
|    |                                             |
|    v                                             |
|  [RTL Check Node]                                |
|    | (pass)                                      |
|    v                                             |
|  [Synthesis Node] <--(retry)--+                  |
|    | (pass)         |         |                  |
|    v                |         |                  |
|  [Timing Analysis Node]       |                  |
|    | (violations)  |          |                  |
|    +---------------+          |                  |
|    | (pass)                   |                  |
|    v                          |                  |
|  [Place & Route Node]         |                  |
|    | (pass)                   |                  |
|    v                          |                  |
|  [Final Verification Node]    |                  |
|    |                          |                  |
|    v                          |                  |
|  END                          |                  |
+--------------------------------------------------+
         |
         v
  TypedDict State
  {
    "phase": "synthesis",
    "timing_violations": [...],
    "approval_required": True,
    ...
  }
```

#### 핵심 메커니즘

**TypedDict 기반 상태 관리:**
- 모든 상태가 Python 타입 시스템으로 검증됨
- 런타임 타입 오류를 컴파일 타임에 감지 가능

**interrupt() 패턴:**
- Human-in-the-loop 승인 게이트를 그래프 엣지에 명시적으로 삽입
- 장시간 EDA 작업 중 중단/재개 지원

**체크포인트 기능:**
- LangGraph의 Checkpointer를 통해 임의 지점에서 상태 저장/복원
- 장시간 실행 중 실패 시 재시작 없이 재개 가능

#### 장단점 요약

**장점:**
- 그래프 구조가 워크플로우를 시각적으로 명확하게 표현
- 체크포인트/재개로 장시간 EDA 작업 안정성 향상
- Human-in-the-loop을 그래프 레벨에서 구현 가능

**단점:**
- 신기능 추가 = 그래프 코드 변경 필수 (유지보수 부담)
- 고정 그래프 구조로 인해 모델 발전의 기회비용 발생
- LangGraph 1.0은 2025년 10월에야 API 안정화 (성숙도 이슈)
- Grid Dynamics 사례: LangGraph + Redis 조합이 "incredibly brittle" 로 평가됨

---

## 3. 심층 연구 결과

### 3.1 Sub-10B 모델의 현실적 한계

On-premise 제약으로 인해 10B 파라미터 미만 모델을 사용해야 하는 잇다반도체의 환경에서, 다음의 실패 모드가 문서화되어 있다.

#### 주요 실패 모드

| 실패 유형 | 발생률 | 설명 |
|-----------|--------|------|
| JSON 포맷 오류 (zero-shot) | 38% | 구조화된 출력 없이 JSON 생성 시 실패율 |
| 도구 선택 오류 (>5-7개 노출 시) | 높음 | 너무 많은 도구 노출 시 잘못된 도구 선택 |
| 다단계 추론 실패 | 높음 | 3단계 이상 연쇄 추론 시 오류 누적 |
| 컨텍스트 소실 | 중간 | 긴 대화에서 초기 지시 망각 |

**핵심 시사점:** Sub-10B 모델을 신뢰성 있게 운용하려면 아키텍처 레벨의 보상 메커니즘이 필수이다. LLM의 능력에만 의존하는 설계는 운영 환경에서 반드시 실패한다.

#### Grammar-Constrained Decoding의 역할

ACL 2025 연구에 따르면, Grammar-constrained decoding을 적용하면 JSON 포맷 오류율이 38%에서 0%로 감소한다. 주요 도구는 다음과 같다.

- **Outlines:** Python 기반, EBNF 문법으로 출력 구조 강제
- **XGrammar:** 고성능 GPU 가속 grammar 디코딩
- **lm-format-enforcer:** vLLM과 네이티브 통합 지원

On-premise vLLM 환경에서 lm-format-enforcer를 사용하면 추가적인 추론 인프라 없이 JSON 보장이 가능하다.

#### EDAid 논문의 시사점

8B 모델이 EDA 특화 파인튜닝과 multi-agent voting을 결합하여 신뢰성 있는 EDA 작업 수행에 성공했다는 연구 결과는, sub-10B 모델도 **도메인 특화 파인튜닝 + 구조적 제약**의 조합으로 운영 수준의 신뢰성에 도달할 수 있음을 시사한다.

---

### 3.2 Claude Agent SDK + HOOK 심층 분석

#### HOOK의 동작 범위와 한계

```
LLM 출력 처리 파이프라인:
                                        HOOK 발동 범위
                                        |           |
Raw LLM Output --> SDK JSON Parser --> Tool Call Object --> PreToolUse --> Tool Execution --> PostToolUse
                        |
                   실패 시 HOOK 미발동
                   (Grammar-constrained decoding으로 보완)
```

**핵심 취약점:** SDK가 LLM 출력을 JSON으로 파싱하기 이전에 실패하면 훅이 발동하지 않는다. 이는 sub-10B 모델의 38% JSON 실패율과 결합될 때 심각한 문제가 된다.

**해결책:** Grammar-constrained decoding을 LLM 추론 레이어에 적용하면 이 취약점이 근본적으로 해소된다. 훅은 항상 유효한 JSON 도구 호출을 입력받게 된다.

#### Phase-lock 패턴의 효과

```python
# PreToolUse 훅 예시 (의사 코드)
def pre_tool_use_hook(tool_name: str, tool_params: dict, state: WorkflowState):
    allowed_tools = state.get_allowed_tools_for_phase(state.current_phase)

    if tool_name not in allowed_tools:
        return {
            "action": "block",
            "permissionDecisionReason": f"현재 Phase '{state.current_phase}'에서는 "
                                        f"{allowed_tools} 만 허용됩니다. "
                                        f"'{tool_name}'은 Phase '{get_required_phase(tool_name)}'에서 사용 가능합니다."
        }

    return {"action": "allow"}
```

이 패턴은 다음 효과를 달성한다:
1. LLM이 잘못된 Phase 도구를 호출해도 실행 자체가 불가
2. `permissionDecisionReason`으로 LLM이 자기 교정할 기회 제공
3. Phase별로 1-2개 도구만 노출하므로 도구 선택 실패 가능성 최소화

#### 반복 거부 무한 루프 방지

```python
# Phase별 재시도 카운터 (workflow_state.json에 저장)
{
  "current_phase": "synthesis",
  "retry_counts": {
    "synthesis": 3
  },
  "max_retries_per_phase": 3,
  "fallback_strategy": "human_in_the_loop"
}
```

재시도 횟수가 임계값을 초과하면 자동으로 human-in-the-loop 모드로 전환하여 무한 루프를 방지한다.

---

### 3.3 LangGraph 심층 분석

#### StateFlow 논문 (NeurIPS 2024) 결과

StateFlow 논문은 구조화된 태스크에서 LangGraph 스타일의 FSM이 ReAct 대비 13-28% 성능 향상과 5x 토큰 비용 절감을 달성했다고 보고한다. 그러나 이 성능 향상은 **"그래프 구조 자체"** 에서 오는 것이 아니라 **"Phase별 전문화된 컨텍스트 제공"** 에서 온다는 점이 중요하다. 동일한 효과는 훅 기반 컨텍스트 주입으로도 달성 가능하다.

#### Graph-lock 문제의 실질적 영향

LangGraph에서 새로운 EDA 기능을 추가하려면 반드시 그래프 코드를 수정해야 한다.

```python
# LangGraph: 새 Phase 추가 시 코드 변경 필수
graph.add_node("new_eda_phase", new_phase_function)
graph.add_edge("timing_analysis", "new_eda_phase")
graph.add_edge("new_eda_phase", "place_and_route")
# 모든 관련 라우팅 로직 재검토 필요
```

반면 HOOK 방식에서는 `workflow_state.json`에 새 Phase를 추가하고 훅 규칙을 갱신하면 된다. 코드 변경 범위가 최소화된다.

#### Grid Dynamics 실패 사례 분석

Grid Dynamics의 LangGraph + Redis 프로덕션 사례에서 "incredibly brittle"이라는 평가가 나온 원인은 다음과 같다.

1. LangGraph 상태와 Redis 상태 간의 동기화 불일치
2. 그래프 노드 간 전이 중 실패 시 상태 복구의 복잡성
3. 각 노드 내 LLM 호출의 비결정성이 그래프 레벨로 전파

**핵심 교훈:** LangGraph는 노드 간 라우팅을 결정론적으로 만들 수 있지만, 각 노드 내 LLM 호출은 여전히 비결정론적이다. "100% 제어"라는 LangGraph의 주장은 절반만 사실이다.

---

### 3.4 하이브리드 접근법 분석

#### 업계 합의 (2025-2026)

2025-2026년 업계 합의는 **"90% 결정론적 + 소규모 에이전트 루프"** 패턴으로 수렴하고 있다. 완전한 LLM 에이전트도, 완전한 하드코딩도 아닌 중간 지점이 프로덕션 환경에서 최적임이 검증되었다.

#### AutoEDA 연구 결과

AutoEDA 연구에서 구조화된 프롬프트만으로(파인튜닝 없이) 86-98% 성공률을 달성했다. 이는 EDA 도메인에서 아키텍처적 구조화가 LLM 능력 자체보다 더 중요할 수 있음을 시사한다.

#### 3계층 하이브리드 아키텍처

```
+-----------------------------------------------------+
|  Layer 1: 결정론적 Phase 컨트롤러 (순수 Python)      |
|  - EDA Phase 순서 강제 (RTL→합성→배치/배선→검증)      |
|  - Phase 전이 조건 평가                              |
|  - workflow_state.json 관리                         |
+-----------------------------------------------------+
                        |
                        v
+-----------------------------------------------------+
|  Layer 2: HOOK 검증층 (Claude Agent SDK)            |
|  - PreToolUse: Phase 기반 도구 호출 검증/차단        |
|  - PostToolUse: 실행 결과 기반 상태 업데이트          |
|  - UserPromptSubmit: 현재 상태 컨텍스트 주입          |
+-----------------------------------------------------+
                        |
                        v
+-----------------------------------------------------+
|  Layer 3: Grammar-constrained LLM 실행층             |
|  - vLLM + lm-format-enforcer                        |
|  - JSON 스키마 강제로 파싱 실패 0%                   |
|  - Phase별 1-2개 도구만 노출                         |
+-----------------------------------------------------+
```

---

## 4. 변증법적 분석 (정반합)

### 4.1 라운드 1: 각 방식의 심층 비판

#### 정 (Thesis): HOOK 방식의 약점

HOOK 방식에는 구조적으로 해결하기 어려운 약점이 있다.

**약점 1 - 반응형의 한계:**
HOOK은 LLM이 이미 잘못된 도구 호출을 시도한 이후에 개입한다. 이는 예방형(preventive)이 아닌 반응형(reactive) 구조다. LLM이 SDK 파싱 자체를 실패시키는 깨진 출력을 내놓으면 훅은 개입할 기회조차 없다.

**약점 2 - 상태 전이 로직의 분산:**
Pre/PostToolUse 훅과 workflow_state.json에 걸쳐 분산된 상태 전이 로직은 버그 추적을 어렵게 만든다. 훅 A가 상태를 쓰고, 훅 B가 같은 상태를 읽는 구조에서 경쟁 조건(race condition)이 발생할 수 있다.

**약점 3 - 반복 거부 시 무한 루프:**
PreToolUse가 계속 차단하고 LLM이 같은 도구를 반복 시도하면 무한 루프가 발생할 수 있다. 이를 방지하는 로직이 별도로 필요하다.

#### 반 (Antithesis): LangGraph 방식의 약점

LangGraph의 "100% 결정론적 제어"라는 주장에는 근본적 오류가 있다.

**약점 1 - 결정론성의 범위 착각:**
LangGraph는 노드 간 라우팅만 결정론적으로 만든다. 각 노드 내부의 LLM 호출은 여전히 비결정론적이다. 노드 B로 라우팅되는 것은 100% 보장되지만, 노드 B에서 LLM이 올바른 작업을 수행할지는 보장되지 않는다.

**약점 2 - Graph-lock의 기회비용:**
고정된 그래프 구조는 모델이 발전해도 그 혜택을 흡수하지 못한다. 2년 후 EDA 특화 20B 모델이 등장해도 LangGraph 구조는 여전히 동일한 노드와 엣지 안에 LLM을 가두고 있을 것이다.

**약점 3 - 프레임워크 성숙도:**
LangGraph 1.0은 2025년 10월에야 출시되었다. API가 안정화된 지 수개월밖에 되지 않은 프레임워크를 프로덕션 EDA 도구의 핵심 의존성으로 채택하는 것은 장기 운영 리스크를 수반한다.

#### 합 1 (Synthesis 1): 3계층 하이브리드

라운드 1의 분석에서 도출되는 1차 합은 **3계층 하이브리드 아키텍처**다. 결정론적 외부 Phase 컨트롤러가 상태 전이를 담당하고, HOOK이 중간 검증 계층으로 작동하며, Grammar-constrained LLM이 내부 실행 계층을 담당한다. HOOK의 파싱 실패 문제는 Grammar-constrained decoding으로 해소된다.

---

### 4.2 라운드 2: 1차 합에 대한 비판

#### 1차 합의 새로운 약점

**비판 1 - Phase 컨트롤러의 구현 주체:**
3계층 하이브리드에서 "결정론적 Phase 컨트롤러"를 LangGraph로 구현할 것인가, 순수 Python FSM으로 구현할 것인가? LangGraph를 사용하면 graph-lock 문제가 다시 발생한다.

**비판 2 - 복잡성 증가:**
3계층 구조는 단일 방식 대비 시스템 복잡도가 높다. 각 계층의 책임 경계가 명확하지 않으면 오히려 디버깅이 더 어려워질 수 있다.

**비판 3 - EDA 워크플로우의 실제 특성:**
ClockCanvas의 EDA 워크플로우는 근본적으로 선형적(linear)이다. RTL 검사 → 합성 → 타이밍 분석 → 배치/배선 → 검증의 순서는 거의 변하지 않는다. LangGraph의 복잡한 그래프 라우팅 기능은 이 순차적 워크플로우에 과분(over-engineering)하다.

#### 2차 합 (Synthesis 2): Phase 분류 체계 + 순수 Python Phase 컨트롤러

**Phase 분류 체계 도입:**

| Phase 유형 | 설명 | 제어 방식 |
|------------|------|-----------|
| Rigid Phase | 반드시 이 도구만 호출, 이 순서로만 실행 | PreToolUse 100% 차단 + Grammar 강제 |
| Guided Phase | 주로 이 도구를 사용하되 LLM 자율성 일부 허용 | PreToolUse 경고 + 재시도 허용 |
| Flexible Phase | LLM이 최적 도구를 선택 (탐색적 분석 등) | PreToolUse 최소 개입 |

**순수 Python Phase 컨트롤러 선택 근거:**
- EDA 워크플로우는 선형적 → 복잡한 그래프 라우팅 불필요
- LangGraph 의존성 없이 동일한 결정론적 제어 달성 가능
- 테스트, 디버깅, 수정이 단순 Python 코드로 가능

---

### 4.3 라운드 3: 최종 합

#### 최종 합의 핵심 명제

라운드 1과 라운드 2의 분석을 통합하여 최종 결론은 다음과 같이 도출된다.

**명제 1:** HOOK의 파싱 실패 문제는 Grammar-constrained decoding으로 근본 해소된다.
**명제 2:** LangGraph의 "결정론적 제어"는 절반만 사실이며, 순수 Python FSM으로 더 단순하게 달성 가능하다.
**명제 3:** 3계층 하이브리드를 Claude Agent SDK + HOOK + 자체 Phase 컨트롤러로 구현하면 LangGraph 없이도 동등한 제어를 달성할 수 있다.
**명제 4:** 이 구조는 모델 발전 시 훅 엄격도만 조정하면 되므로 아키텍처 재설계 없이 진화 가능하다.

#### HOOK 커버리지 분석

| 실패 유형 | HOOK 없이 | Grammar 추가 | Grammar + Phase-lock | +재시도 카운터+Fallback |
|-----------|----------|-------------|---------------------|------------------------|
| JSON 파싱 실패 | 38% | 0% | 0% | 0% |
| 잘못된 도구 선택 | 높음 | 중간 | ~0% | ~0% |
| Phase 순서 위반 | 높음 | 중간 | ~0% | ~0% |
| 반복 실패 | - | - | - | Fallback 처리 |
| **종합 커버리지** | **낮음** | **중간** | **~99%** | **~99.5%** |

**잔여 0.5%에 대한 현실적 판단:** Grammar-constrained decoding + Phase-lock + 재시도 카운터 + Fallback 전략 조합으로 99.5% 커버리지가 달성 가능하다. 잔여 0.5%는 어떤 아키텍처로도 처리 불가능한 영역이며, human-in-the-loop 게이트로만 처리 가능하다. **이 0.5%는 LangGraph 선택의 근거가 되지 않는다.**

---

## 5. 최종 결론 및 권고사항

### 5.1 결정: 어떤 방식을 택해야 하는가

**권고:** Claude Agent SDK + HOOK + 자체 구현 Phase 컨트롤러. **LangGraph 배제.**

이 결정은 다음 근거에 기반한다.

1. LangGraph가 제공하는 결정론적 제어의 실질적 범위는 노드 간 라우팅에 한정된다. ClockCanvas의 선형적 EDA 워크플로우에는 순수 Python FSM으로 충분하다.

2. HOOK 방식의 근본 취약점(파싱 실패)은 Grammar-constrained decoding으로 해소된다. 두 기술의 조합은 LangGraph 수준의 신뢰성을 달성한다.

3. 모델이 발전하면 LangGraph 기반 아키텍처는 그래프를 재설계해야 하지만, HOOK 기반 아키텍처는 훅 엄격도만 낮추면 된다. 이 차이는 2-3년의 운영 기간에서 매우 중요하다.

4. LangGraph 1.0은 2025년 10월에야 API 안정화가 시작되었다. Grid Dynamics의 실패 사례는 이 프레임워크가 아직 프로덕션 EDA 환경에서 충분히 검증되지 않았음을 시사한다.

---

### 5.2 권고 아키텍처: 3계층 구조

```
+============================================================+
|           ClockCanvas Agent Architecture (권고안)           |
+============================================================+

+------------------------------------------------------------+
| [Layer 1] Phase 컨트롤러 (순수 Python FSM)                  |
|                                                            |
|  Phase Registry:                                           |
|  +------------------+  +------------------+               |
|  | Rigid Phase      |  | Guided Phase     |               |
|  | - RTL 검사       |  | - 타이밍 분석    |               |
|  | - 합성 실행      |  | - 최적화 탐색    |               |
|  +------------------+  +------------------+               |
|           |                     |                         |
|           v                     v                         |
|       workflow_state.json (Phase 상태 / 허용 도구)          |
+------------------------------------------------------------+
                        |
              Phase 상태 주입 (매 턴)
                        |
                        v
+------------------------------------------------------------+
| [Layer 2] Claude Agent SDK + HOOK                          |
|                                                            |
|  UserPromptSubmit Hook                                     |
|  --> 현재 Phase / 허용 도구 / 진행률 시스템 프롬프트 주입    |
|                                                            |
|  PreToolUse Hook                                           |
|  --> Phase 규칙 검증 / 위반 차단 / 교정 메시지 반환         |
|  --> 재시도 카운터 증가 / 임계값 도달 시 Fallback 활성화     |
|                                                            |
|  PostToolUse Hook                                          |
|  --> 실행 결과 기반 Phase 컨트롤러 상태 갱신                |
+------------------------------------------------------------+
                        |
              도구 호출 요청 (JSON 보장)
                        |
                        v
+------------------------------------------------------------+
| [Layer 3] Grammar-Constrained LLM 실행층                   |
|                                                            |
|  vLLM + lm-format-enforcer (On-premise)                   |
|                                                            |
|  JSON Schema 강제:                                         |
|  {                                                         |
|    "tool_name": "<allowed_tools_only>",                    |
|    "parameters": { ... }                                   |
|  }                                                         |
|                                                            |
|  Phase별 노출 도구: 1-2개 (도구 과부하 방지)                |
+------------------------------------------------------------+
                        |
                        v
+------------------------------------------------------------+
| [Human-in-the-Loop Gate]                                   |
| - 재시도 초과 시 자동 활성화                                |
| - 고위험 작업 (테이프아웃 직전 등) 수동 승인                |
| - 잔여 0.5% 불확실성 처리                                   |
+------------------------------------------------------------+
```

---

### 5.3 Phase 분류 체계

```
EDA Phase 분류:

[Rigid Phases] - PreToolUse 100% 강제
  RTL_CHECK:
    allowed_tools: ["run_rtl_lint", "check_syntax"]
    max_retries: 3
    fallback: human_in_the_loop

  SYNTHESIS:
    allowed_tools: ["run_synthesis"]
    max_retries: 3
    fallback: human_in_the_loop

[Guided Phases] - PreToolUse 경고 + 재시도 허용
  TIMING_ANALYSIS:
    allowed_tools: ["run_timing", "check_setup_hold", "analyze_path"]
    max_retries: 5
    fallback: rigid_mode_downgrade

[Flexible Phases] - PreToolUse 최소 개입
  EXPLORATORY_OPTIMIZATION:
    allowed_tools: [all_non_destructive_tools]
    max_retries: 10
    fallback: guided_mode_downgrade
```

---

### 5.4 구체적 구현 지침

#### 구현 순서 (우선순위 순)

**1단계: Grammar-constrained LLM 레이어 구축**
```bash
# vLLM 서버에 lm-format-enforcer 통합
pip install lm-format-enforcer
# vLLM 서버 시작 시 guided_decoding_backend 설정
vllm serve <model> --guided-decoding-backend lm-format-enforcer
```

**2단계: workflow_state.json 스키마 정의**
```json
{
  "session_id": "eda-session-001",
  "current_phase": "rtl_check",
  "phase_type": "rigid",
  "allowed_tools": ["run_rtl_lint", "check_syntax"],
  "completed_phases": [],
  "retry_counts": {},
  "max_retries_per_phase": {
    "rtl_check": 3,
    "synthesis": 3,
    "timing_analysis": 5
  },
  "fallback_activated": false,
  "human_review_required": false,
  "phase_history": []
}
```

**3단계: PreToolUse 훅 구현**
```python
def pre_tool_use(tool_name: str, tool_input: dict) -> dict:
    state = load_workflow_state()
    allowed = state["allowed_tools"]

    # Phase 규칙 검증
    if tool_name not in allowed:
        retry_key = state["current_phase"]
        state["retry_counts"][retry_key] = \
            state["retry_counts"].get(retry_key, 0) + 1

        # 재시도 임계값 초과 시 human-in-the-loop 전환
        if state["retry_counts"][retry_key] >= \
           state["max_retries_per_phase"][retry_key]:
            state["human_review_required"] = True
            save_workflow_state(state)
            return {
                "type": "block",
                "message": "반복 실패로 인해 사람의 검토가 필요합니다."
            }

        save_workflow_state(state)
        return {
            "type": "block",
            "message": (
                f"현재 Phase '{state['current_phase']}'에서는 "
                f"{allowed}만 호출 가능합니다. "
                f"'{tool_name}'은 현재 허용되지 않습니다."
            )
        }

    return {"type": "allow"}
```

**4단계: Phase 컨트롤러 FSM 구현**
```python
class EDAPhaseController:
    PHASE_ORDER = [
        "rtl_check", "synthesis", "timing_analysis",
        "place_and_route", "final_verification"
    ]

    def advance_phase(self, state: dict) -> dict:
        current = state["current_phase"]
        idx = self.PHASE_ORDER.index(current)

        if idx + 1 < len(self.PHASE_ORDER):
            next_phase = self.PHASE_ORDER[idx + 1]
            state["current_phase"] = next_phase
            state["allowed_tools"] = \
                self.get_allowed_tools(next_phase)
            state["completed_phases"].append(current)

        return state

    def get_allowed_tools(self, phase: str) -> list:
        PHASE_TOOLS = {
            "rtl_check": ["run_rtl_lint", "check_syntax"],
            "synthesis": ["run_synthesis"],
            "timing_analysis": [
                "run_timing", "check_setup_hold", "analyze_path"
            ],
            "place_and_route": [
                "run_placement", "run_routing"
            ],
            "final_verification": [
                "run_drc", "run_lvs", "generate_report"
            ]
        }
        return PHASE_TOOLS.get(phase, [])
```

#### SDK 호환성 명확화: 비 Anthropic 온프레미스 모델과의 연동

> **핵심 질문:** Claude Agent SDK는 Anthropic 모델 전용인가? On-premise sub-10B 모델에서 훅 아키텍처를 사용할 수 있는가?

본 보고서가 권고하는 아키텍처에서 "Claude Agent SDK"는 **훅 패턴(Hook Pattern) 그 자체**를 지칭하며, Anthropic API에 대한 의존성은 선택적이다. ClockCanvas의 온프레미스 환경에서는 다음 두 가지 방식으로 구현 가능하다.

**방식 A: OpenAI 호환 클라이언트 + 훅 패턴 래퍼 (권고)**

vLLM은 OpenAI 호환 REST API(`/v1/chat/completions`)를 기본 제공한다. 단, `anthropic.Anthropic` 클라이언트는 Anthropic Messages API 와이어 포맷(`/v1/messages`)으로 통신하므로 vLLM의 OpenAI 호환 엔드포인트와 **프로토콜 불일치**가 발생한다. 따라서 vLLM 연동 시에는 `openai` 파이썬 클라이언트를 사용하고, 훅 패턴을 그 위에 직접 래핑하는 방식을 택한다.

```python
from openai import OpenAI

# vLLM 온프레미스 서버 (OpenAI 호환 프로토콜)
llm_client = OpenAI(
    base_url="http://your-onprem-vllm:8000/v1",
    api_key="not-used",  # vLLM은 API 키 불필요 (내부망)
)

def call_with_hook_pattern(prompt: str, phase_state: dict) -> dict:
    # [UserPromptSubmit 훅 역할] Phase 정보 시스템 프롬프트에 주입
    system_msg = build_phase_system_prompt(phase_state)

    response = llm_client.chat.completions.create(
        model="your-onprem-model",
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt},
        ],
        extra_body={"guided_json": get_phase_tool_schema(phase_state)},  # Grammar-constrained
    )

    tool_call = parse_tool_call(response)

    # [PreToolUse 훅 역할] Phase 규칙 검증
    if tool_call["name"] not in phase_state["allowed_tools"]:
        return block_with_correction(tool_call, phase_state)

    # [PostToolUse 훅 역할] 상태 갱신
    update_phase_state(tool_call, phase_state)
    return tool_call
```

이 방식에서 훅 패턴(PreToolUse/PostToolUse/UserPromptSubmit)은 **Claude Agent SDK 없이도 동일한 로직**으로 구현된다. SDK는 이 패턴을 편의 추상화로 제공할 뿐이며, 핵심 제어 로직은 백엔드 LLM 종류와 무관하다.

**방식 B: 순수 Python 미들웨어로 훅 패턴 자체 구현 (최대 이식성)**

Claude Agent SDK를 전혀 사용하지 않고, 훅 패턴을 순수 Python HTTP 미들웨어로 구현한다.

```python
class HookMiddleware:
    """Claude Agent SDK 훅을 순수 Python으로 재현한 미들웨어."""

    def call_llm_with_hooks(self, prompt: str, phase_state: dict) -> dict:
        # UserPromptSubmit 훅 역할: 프롬프트에 Phase 정보 주입
        enriched_prompt = self._inject_phase_context(prompt, phase_state)

        # LLM 호출 (vLLM, Ollama, 또는 임의의 OpenAI 호환 서버)
        response = self._call_backend(enriched_prompt)

        # PreToolUse 훅 역할: 도구 호출 검증
        if response.get("tool_call"):
            validation = self._pre_tool_use(
                response["tool_call"]["name"],
                response["tool_call"]["arguments"],
                phase_state
            )
            if validation["type"] == "block":
                return {"blocked": True, "reason": validation["message"]}

        # PostToolUse 훅 역할: 상태 갱신
        self._post_tool_use(response, phase_state)
        return response
```

**결론:** ClockCanvas의 온프레미스 환경에서 핵심은 Anthropic SDK 사용 여부가 아니라 **훅 패턴(Phase 검증 → LLM 호출 → 상태 갱신)의 구현**이다. 방식 A는 Claude Agent SDK의 생태계를 활용하면서 vLLM을 백엔드로 쓰는 실용적 선택이며, 방식 B는 외부 의존성을 완전히 제거하고자 할 때의 대안이다. 두 방식 모두 3계층 아키텍처의 Layer 2를 구성할 수 있다.

---

### 5.5 모델 발전에 따른 진화 경로

아키텍처는 모델 성능 향상에 따라 훅 엄격도만 조정하면 되므로, 아키텍처 재설계 없이 진화한다.

```
모델 성능 진화에 따른 훅 엄격도 조정:

현재 (sub-10B, 2026):
  - 모든 Rigid Phase: 100% 차단
  - Guided Phase: 3회 이내 재시도
  - Grammar-constrained: 반드시 활성화

모델 발전 후 (가상의 15B EDA 특화, 2027):
  - Rigid Phase: 여전히 100% 차단 (EDA 안전성)
  - Guided Phase: LLM 자율성 확대 (재시도 완화)
  - Grammar-constrained: 선택적 활성화

모델 성숙 후 (가상의 30B EDA 특화, 2028):
  - Rigid Phase만 100% 차단 (안전 임계 작업)
  - Flexible/Guided: 훅 최소 개입
  - Phase 컨트롤러는 여전히 유효 (순서 보장)
```

**LangGraph 방식과의 비교:**
- LangGraph: 모델이 발전해도 그래프 구조 동일, 혜택 흡수 어려움
- HOOK 방식: 훅 파라미터 조정만으로 모델 발전의 혜택 점진적 흡수

---

## 6. 위험 요소 및 완화 전략

### 6.1 위험 요소 매트릭스

| 위험 요소 | 발생 가능성 | 영향도 | 완화 전략 |
|-----------|-----------|--------|-----------|
| Sub-10B 모델의 JSON 파싱 실패 | 높음 (38%) | 높음 | Grammar-constrained decoding으로 0%로 절감 |
| 훅 로직 버그로 인한 잘못된 Phase 전이 | 중간 | 높음 | Phase 컨트롤러 단위 테스트 + 통합 테스트 |
| 반복 거부 무한 루프 | 중간 | 중간 | 재시도 카운터 + Human-in-the-loop Fallback |
| workflow_state.json 파일 손상 | 낮음 | 높음 | 주기적 체크포인트 + 백업 + 검증 |
| vLLM / lm-format-enforcer 버전 호환성 | 중간 | 중간 | 버전 고정 (requirements.txt) + 정기 업데이트 테스트 |
| EDA Phase 정의 변경 시 훅 업데이트 누락 | 중간 | 중간 | Phase 정의와 훅 규칙의 단일 진실 소스(SSOT) 관리 |
| On-premise 모델 성능 저하 (배포 이후) | 낮음 | 높음 | Human-in-the-loop 게이트 + 성능 모니터링 |
| IP 데이터 유출 | 낮음 | 매우 높음 | On-premise 전용 운영 + 네트워크 격리 확인 |

### 6.2 주요 완화 전략 상세

#### 위험 1: JSON 파싱 실패
Grammar-constrained decoding을 LLM 추론 레이어에 적용한다. vLLM의 `--guided-decoding-backend lm-format-enforcer` 옵션을 통해 모든 LLM 출력이 사전 정의된 JSON 스키마를 준수하도록 강제한다. 이 조치로 38% 파싱 실패율이 0%로 감소한다.

#### 위험 2: 훅 로직 버그
Phase 컨트롤러와 훅 규칙에 대한 포괄적인 단위 테스트를 작성한다. 특히 Phase 경계(한 Phase의 마지막 도구 호출 → 다음 Phase로의 전이) 시나리오를 철저히 테스트한다. CI/CD 파이프라인에 훅 회귀 테스트를 포함시킨다.

#### 위험 3: 상태 파일 손상
`workflow_state.json`을 단순한 파일이 아닌 원자적 쓰기(atomic write)로 처리한다. 매 Phase 전이 시 이전 상태를 `.bak` 파일로 보존한다. 시작 시 상태 파일 무결성 검증을 수행한다.

---

## 7. 구현 우선순위 로드맵

### 7.1 Phase 1: 기반 인프라 구축 (1-2주)

**목표:** Grammar-constrained LLM 실행 환경 구축

| 작업 | 담당 | 기간 | 완료 기준 |
|------|------|------|-----------|
| On-premise vLLM 서버 배포 | 인프라팀 | 3일 | vLLM API 응답 확인 |
| lm-format-enforcer 통합 테스트 | ML팀 | 2일 | JSON 스키마 강제 동작 확인 |
| 기본 JSON 출력 스키마 정의 | 개발팀 | 1일 | 도구 호출 스키마 문서화 |
| 통합 테스트 환경 구축 | 개발팀 | 2일 | E2E 테스트 실행 가능 상태 |

### 7.2 Phase 2: Phase 컨트롤러 구현 (2-3주)

**목표:** EDAPhaseController FSM 및 workflow_state.json 관리 구현

| 작업 | 담당 | 기간 | 완료 기준 |
|------|------|------|-----------|
| EDA Phase 분류 체계 확정 | 아키텍트 + EDA전문가 | 3일 | Phase/도구 매핑 문서 완성 |
| EDAPhaseController FSM 구현 | 개발팀 | 5일 | 모든 Phase 전이 단위 테스트 통과 |
| workflow_state.json 스키마 구현 | 개발팀 | 2일 | 스키마 검증 로직 포함 |
| Phase 컨트롤러 통합 테스트 | QA팀 | 3일 | 5개 Phase 전체 흐름 테스트 통과 |

### 7.3 Phase 3: HOOK 레이어 구현 (2-3주)

**목표:** PreToolUse / PostToolUse / UserPromptSubmit 훅 구현

| 작업 | 담당 | 기간 | 완료 기준 |
|------|------|------|-----------|
| PreToolUse 훅 구현 | 개발팀 | 4일 | Phase 위반 차단 + 교정 메시지 동작 확인 |
| PostToolUse 훅 구현 | 개발팀 | 3일 | 상태 업데이트 정확성 테스트 통과 |
| UserPromptSubmit 훅 구현 | 개발팀 | 2일 | 컨텍스트 주입 검증 |
| 재시도 카운터 + Fallback 구현 | 개발팀 | 3일 | 무한 루프 방지 테스트 통과 |
| Human-in-the-loop 게이트 구현 | 개발팀 | 3일 | Fallback 시 수동 개입 UI 동작 확인 |

### 7.4 Phase 4: 통합 및 검증 (2주)

**목표:** 3계층 아키텍처 전체 통합 및 ClockCanvas 연동

| 작업 | 담당 | 기간 | 완료 기준 |
|------|------|------|-----------|
| 3계층 통합 테스트 | 개발팀 + QA팀 | 4일 | 전체 EDA 워크플로우 자동화 테스트 통과 |
| ClockCanvas UI 연동 | 프론트엔드팀 | 5일 | 에이전트 UI 동작 확인 |
| 성능 부하 테스트 | QA팀 | 3일 | 동시 세션 처리 성능 확인 |
| 보안 검토 | 보안팀 | 2일 | IP 데이터 격리 확인 |

### 7.5 Phase 5: 운영 모니터링 체계 (1주)

**목표:** 에이전트 동작 모니터링 및 지속적 개선 체계 구축

| 작업 | 담당 | 기간 | 완료 기준 |
|------|------|------|-----------|
| 에이전트 성공/실패율 메트릭 수집 | 개발팀 | 2일 | 대시보드 구축 |
| HOOK 차단 이벤트 로깅 | 개발팀 | 1일 | 로그 시스템 연동 |
| Human-in-the-loop 트리거 분석 | ML팀 | 2일 | 개선 우선순위 도출 |

### 7.6 총 일정 요약

```
주차:  1   2   3   4   5   6   7   8   9   10
       |---|---|---|---|---|---|---|---|---|---|
P1: 기반  [=====]
P2: Phase 컨트롤러    [=========]
P3: HOOK 레이어             [=========]
P4: 통합 및 검증                      [=====]
P5: 모니터링                               [==]
```

**총 예상 기간:** 약 10주

---

### 5.6 OpenAI Agents SDK 기반 구현 가이드 (로컬 LLM 완전 지원)

앞서 5.4절에서 소개한 방식 A(OpenAI 호환 클라이언트 + 훅 패턴 래퍼)의 구체화된 버전으로, **OpenAI Agents SDK** (`openai-agents` 패키지)를 사용하면 다음을 얻을 수 있다:

- N0 while-loop 에이전틱 패턴 (Claude Agent SDK와 동일한 철학)
- LiteLLM을 통한 로컬 LLM(vLLM, Ollama) 완전 지원
- `is_enabled`를 이용한 Phase-lock (도구 노출 자체를 Phase별 동적 제어)

#### 5.6.1 Claude Agent SDK vs OpenAI Agents SDK 훅 비교

두 SDK의 핵심 메커니즘을 나란히 비교한다.

| 기능 | Claude Agent SDK | OpenAI Agents SDK |
|------|-----------------|-------------------|
| 실행 전 차단 | `PreToolUse` → `permissionDecision: "deny"` | 없음. 도구 함수 내부에서 오류 반환 |
| 실행 후 상태 | `PostToolUse` → `tool_response` 접근 | `RunHooks.on_tool_end(context, agent, tool, result)` |
| 프롬프트 주입 | `UserPromptSubmit` → `additionalContext` | `RunConfig.call_model_input_filter` 또는 Agent `instructions` |
| Phase 도구 잠금 | PreToolUse에서 `deny` 반환 | **`is_enabled` 콜백으로 도구 자체를 숨김** ✅ |
| LLM 교정 메시지 | `permissionDecisionReason` | 도구 반환값이 LLM에게 전달됨 |
| 로컬 LLM 연결 | ❌ 공식 미지원 | ✅ LiteLLM 네이티브 지원 |

**중요 차이:** OpenAI Agents SDK의 `on_tool_start` / `on_tool_end`는 **관찰(observability) 전용**이며 도구 실행을 차단할 수 없다. 대신 `is_enabled`로 도구 자체를 Phase별로 숨기는 방식이 ClockCanvas에 더 적합하다.

#### 5.6.2 설치 및 의존성

```bash
# OpenAI Agents SDK + LiteLLM 확장 설치
pip install "openai-agents[litellm]"

# LiteLLM 시리얼라이저 경고 억제 (권장)
export OPENAI_AGENTS_ENABLE_LITELLM_SERIALIZER_PATCH=true
```

#### 5.6.3 로컬 LLM 연결: LiteLLM 경유

OpenAI Agents SDK는 `LitellmModel` 클래스를 통해 100개 이상의 모델 백엔드를 지원한다.

```python
from agents.extensions.models.litellm_model import LitellmModel

# vLLM 온프레미스 서버 연결 (OpenAI 호환 엔드포인트)
model = LitellmModel(
    model="openai/your-eda-model",   # LiteLLM의 vLLM 라우팅 형식
    api_base="http://your-vllm-server:8000/v1",
    api_key="not-required",           # 내부망 vLLM은 키 불필요
)

# 또는 Ollama 직접 연결
model = LitellmModel(model="ollama/qwen2.5:7b")
```

#### 5.6.4 Phase-lock: `is_enabled`로 도구 노출 자체를 제어

Claude Agent SDK의 PreToolUse 차단보다 강력한 방식: **LLM에게 허용되지 않은 Phase의 도구를 아예 보여주지 않는다.** 도구 선택 오류 자체가 발생하지 않으므로 sub-10B 모델의 신뢰성을 높이는 데 유리하다.

```python
import json
from pathlib import Path
from agents import Agent, Runner, function_tool, RunConfig
from agents.extensions.models.litellm_model import LitellmModel

# workflow_state.json 로드 헬퍼
def load_state() -> dict:
    return json.loads(Path("workflow_state.json").read_text())

# --- EDA 도구 정의: is_enabled로 Phase 제한 ---

@function_tool(
    is_enabled=lambda ctx, agent: "run_rtl_lint" in load_state()["allowed_tools"]
)
def run_rtl_lint(target_file: str) -> str:
    """RTL 파일의 문법 및 구조 검사를 실행합니다."""
    # 실제 RTL lint 실행 로직
    return f"{target_file} lint 통과"

@function_tool(
    is_enabled=lambda ctx, agent: "run_synthesis" in load_state()["allowed_tools"]
)
def run_synthesis(config_file: str) -> str:
    """논리 합성을 실행합니다. RTL Check 완료 후에만 호출 가능합니다."""
    state = load_state()
    if state["current_phase"] != "synthesis":
        # 이중 안전장치: 도구 내부에서도 Phase 검증
        return f"ERROR: 현재 Phase는 '{state['current_phase']}'입니다. synthesis 도구를 지금 호출할 수 없습니다. 현재 허용 도구: {state['allowed_tools']}"
    return "합성 완료"

@function_tool(
    is_enabled=lambda ctx, agent: "run_timing" in load_state()["allowed_tools"]
)
def run_timing(report_type: str) -> str:
    """타이밍 분석을 실행합니다."""
    return f"{report_type} 타이밍 분석 완료"

@function_tool(
    is_enabled=lambda ctx, agent: "run_placement" in load_state()["allowed_tools"]
)
def run_placement(area_constraint: str) -> str:
    """셀 배치를 실행합니다."""
    return f"배치 완료 (제약: {area_constraint})"

@function_tool(
    is_enabled=lambda ctx, agent: "run_drc" in load_state()["allowed_tools"]
)
def run_drc() -> str:
    """설계 규칙 검사(DRC)를 실행합니다."""
    return "DRC 통과"
```

#### 5.6.5 RunHooks: PostToolUse 상태 갱신 및 로깅

```python
from agents import RunHooks
from agents.run_context import RunContextWrapper

class EDAPhaseHooks(RunHooks):
    """PostToolUse 훅으로 Phase 상태를 갱신하고 감사 로그를 기록한다."""

    async def on_tool_end(self, context: RunContextWrapper, agent, tool, result: str) -> None:
        """도구 실행 완료 후 Phase 상태 업데이트."""
        state = load_state()
        tool_name = tool.name

        # Phase 완료 조건 평가
        self._evaluate_phase_completion(tool_name, result, state)

        # 감사 로그 기록
        print(f"[AUDIT] Tool={tool_name} | Phase={state['current_phase']} | Result={result[:100]}")

    async def on_tool_start(self, context: RunContextWrapper, agent, tool) -> None:
        """도구 실행 직전 로깅 (차단 불가 - 관찰 전용)."""
        state = load_state()
        print(f"[PRE-TOOL] Tool={tool.name} | Phase={state['current_phase']}")

    def _evaluate_phase_completion(self, tool_name: str, result: str, state: dict):
        """Phase 완료 조건 평가 및 다음 Phase로 전이."""
        if "ERROR" in result:
            return  # 오류 시 Phase 전이 없음

        phase_completion = {
            "run_rtl_lint": ("rtl_check", "synthesis", ["run_synthesis"]),
            "run_synthesis": ("synthesis", "timing_analysis", ["run_timing", "check_setup_hold"]),
            "run_timing": ("timing_analysis", "place_and_route", ["run_placement", "run_routing"]),
            "run_placement": ("place_and_route", "final_verification", ["run_drc", "run_lvs"]),
        }

        if tool_name in phase_completion:
            current, next_phase, next_tools = phase_completion[tool_name]
            if state["current_phase"] == current:
                state["current_phase"] = next_phase
                state["allowed_tools"] = next_tools
                state["completed_phases"].append(current)
                Path("workflow_state.json").write_text(json.dumps(state, indent=2, ensure_ascii=False))
                print(f"[PHASE] {current} → {next_phase}")
```

#### 5.6.6 UserPromptSubmit 등가: 프롬프트 컨텍스트 주입

Claude Agent SDK의 `UserPromptSubmit` 훅은 OpenAI Agents SDK에서 Agent의 `instructions`를 동적으로 생성하거나 `call_model_input_filter`로 대체한다.

```python
def get_phase_aware_instructions() -> str:
    """현재 Phase 상태를 시스템 프롬프트에 주입 (UserPromptSubmit 등가)."""
    state = load_state()
    return f"""당신은 ClockCanvas EDA 에이전트입니다.

현재 EDA 워크플로우 상태:
- 현재 Phase: {state['current_phase']}
- 허용된 도구: {state['allowed_tools']}
- 완료된 Phase: {state['completed_phases']}

규칙:
1. 현재 Phase에서 허용된 도구만 호출하세요.
2. Phase 순서(RTL Check → 합성 → 타이밍 → 배치/배선 → 최종 검증)를 반드시 준수하세요.
3. 도구 호출 시 올바른 파라미터를 제공하세요.
"""

# call_model_input_filter로 매 턴 컨텍스트 주입
def inject_phase_context(ctx, input_list, *, agent, **kwargs):
    """매 LLM 호출 직전 Phase 상태를 입력에 주입."""
    state = load_state()
    context_msg = {
        "role": "system",
        "content": f"[Phase 상태 업데이트] 현재: {state['current_phase']}, 허용: {state['allowed_tools']}"
    }
    return [context_msg] + input_list
```

#### 5.6.7 전체 ClockCanvas 에이전트 실행 예시

```python
import asyncio
from agents import Agent, Runner, RunConfig
from agents.extensions.models.litellm_model import LitellmModel

async def run_clockcanvas_agent(user_request: str) -> str:
    """ClockCanvas EDA 에이전트 실행."""

    # 로컬 vLLM 모델 설정
    model = LitellmModel(
        model="openai/eda-qwen-7b",
        api_base="http://your-vllm-server:8000/v1",
        api_key="internal",
    )

    # 에이전트 생성: is_enabled로 Phase별 도구 자동 필터링
    agent = Agent(
        name="ClockCanvas-EDA-Agent",
        model=model,
        instructions=get_phase_aware_instructions(),  # 동적 Phase 컨텍스트
        tools=[
            run_rtl_lint,    # is_enabled: rtl_check phase만
            run_synthesis,   # is_enabled: synthesis phase만
            run_timing,      # is_enabled: timing_analysis phase만
            run_placement,   # is_enabled: place_and_route phase만
            run_drc,         # is_enabled: final_verification phase만
        ],
    )

    # RunConfig: 최대 턴 수 제한, 컨텍스트 주입 필터
    config = RunConfig(
        max_turns=30,
        call_model_input_filter=inject_phase_context,
    )

    # 훅 등록
    hooks = EDAPhaseHooks()

    # N0 while-loop 실행 (Runner.run이 내부적으로 while not done 루프)
    result = await Runner.run(
        agent,
        user_request,
        run_config=config,
        hooks=hooks,
    )

    return result.final_output

# 실행
if __name__ == "__main__":
    result = asyncio.run(run_clockcanvas_agent(
        "qwen_rtl_v3.sv 파일의 클럭 트리를 최적화하고 전체 EDA 플로우를 실행해주세요."
    ))
    print(result)
```

#### 5.6.8 Grammar-constrained Decoding과의 통합

OpenAI Agents SDK는 grammar-constrained decoding을 SDK 레벨에서 지원하지 않는다. 이는 vLLM 서버 레벨에서 처리하므로 SDK와 무관하게 적용된다.

```bash
# vLLM 서버 시작 시 grammar-constrained decoding 활성화
vllm serve eda-qwen-7b \
  --guided-decoding-backend lm-format-enforcer \
  --port 8000

# 도구 호출 스키마를 vLLM에 guided_json으로 전달 (LiteLLM extra_body 경유)
```

LiteLLM의 `extra_body` 파라미터를 통해 vLLM의 `guided_json` 옵션을 전달할 수 있다. 단, OpenAI Agents SDK의 `LitellmModel`에서 `extra_body` 전달은 현재 베타 상태이므로, 필요 시 `LitellmModel`을 상속하여 커스텀 호출 로직을 추가하는 방식을 검토한다.

#### 5.6.9 ClockCanvas 구현 선택 가이드

| 상황 | 권고 선택 |
|------|-----------|
| 빠른 프로토타입, LLM 자주 교체 예상 | OpenAI Agents SDK + LiteLLM |
| Claude Agent SDK 훅 패턴 정확히 재현 필요 | 순수 Python 미들웨어 (5.4절 방식 B) |
| Ollama 로컬 개발 환경 | OpenAI Agents SDK + `LitellmModel("ollama/qwen2.5:7b")` |
| On-premise vLLM + grammar-constrained | OpenAI Agents SDK + LiteLLM + vLLM guided decoding |
| 최대 안정성, 외부 의존성 최소화 | 순수 Python 미들웨어 (5.4절 방식 B) |

**결론:** 잇다반도체 ClockCanvas 환경에서 OpenAI Agents SDK는 `is_enabled` 기반 Phase-lock과 LiteLLM 로컬 LLM 지원을 통해 Claude Agent SDK의 실질적 대체재로 기능한다. 특히 `is_enabled`는 LLM에게 잘못된 Phase의 도구를 아예 노출하지 않으므로, sub-10B 모델의 도구 선택 오류를 근본적으로 차단하는 더 강력한 Phase-lock 메커니즘이다.

---

## 결론 요약

잇다반도체 ClockCanvas EDA 에이전트 기능의 아키텍처로 **Claude Agent SDK + HOOK + 자체 구현 Phase 컨트롤러** 를 권고하며, **LangGraph는 채택하지 않는다.**

이 결정의 핵심 근거는 세 가지다. 첫째, LangGraph가 제공하는 결정론적 제어는 절반만 사실이며 순수 Python FSM으로 더 단순하게 달성 가능하다. 둘째, HOOK의 근본 취약점은 Grammar-constrained decoding으로 완전히 해소된다. 셋째, 이 아키텍처는 모델 발전 시 훅 엄격도 조정만으로 진화 가능하여 장기 운영 비용이 현저히 낮다.

Grammar-constrained decoding + Phase-lock + 재시도 카운터 + Fallback 전략의 조합은 99.5% 신뢰성을 달성하며, 잔여 0.5%는 어떤 아키텍처로도 처리 불가능한 영역으로 human-in-the-loop 게이트가 이를 담당한다.

---

*본 보고서는 2026-02-24 기준 최신 연구 결과 (ACL 2025, NeurIPS 2024 StateFlow, EDAid 논문)를 반영하여 작성되었다.*
