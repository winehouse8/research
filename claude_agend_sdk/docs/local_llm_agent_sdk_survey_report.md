# 로컬 LLM 호환 Agent SDK/프레임워크 비교 분석 보고서
## 잇다반도체 ClockCanvas EDA 에이전트 — 프레임워크 선택 가이드

**대상 조직:** 잇다반도체 (Ittda Semiconductor)
**문서 유형:** 기술 조사 보고서 (Technology Survey Report)
**작성일:** 2026-02-24
**연관 문서:** clockcanvas_agent_architecture_report.md
**문서 상태:** 최종 (Final)

---

## 목차

1. [개요 및 조사 배경](#1-개요-및-조사-배경)
2. [평가 기준 및 방법론](#2-평가-기준-및-방법론)
3. [프레임워크 개별 분석](#3-프레임워크-개별-분석)
4. [종합 비교 매트릭스](#4-종합-비교-매트릭스)
5. [변증법적 분석](#5-변증법적-분석-정반합-2라운드)
6. [최종 권고 및 ClockCanvas v2 아키텍처](#6-최종-권고-및-clockcanvas-v2-아키텍처)
7. [구현 전략 및 단계적 도입 로드맵](#7-구현-전략-및-단계적-도입-로드맵)
8. [위험 요소 및 완화 전략](#8-위험-요소-및-완화-전략)

---

## 1. 개요 및 조사 배경

### 1.1 기존 보고서 결론 요약

`clockcanvas_agent_architecture_report.md` (이하 "기존 보고서")는 잇다반도체 ClockCanvas EDA 에이전트의 아키텍처 결정을 위해 두 가지 방식 — Claude Agent SDK + HOOK 방식 대 LangGraph 상태 머신 방식 — 을 비교 분석한 문서이다. 기존 보고서의 핵심 결론은 다음과 같다.

- **채택:** Claude Agent SDK + HOOK + 자체 구현 Phase 컨트롤러 (순수 Python FSM)
- **배제:** LangGraph (결정론성이 절반만 사실이며, API 안정화 시점이 늦고, Graph-lock 문제가 존재)
- **3계층 아키텍처 권고:**
  - Layer 1: 결정론적 Phase 컨트롤러 (순수 Python)
  - Layer 2: HOOK 검증층 (PreToolUse / PostToolUse / UserPromptSubmit)
  - Layer 3: Grammar-Constrained LLM (vLLM + lm-format-enforcer)
- **핵심 근거:** Grammar-constrained decoding이 HOOK의 파싱 실패 취약점을 해소하며, 두 기법의 조합으로 99.5% 신뢰성 달성

기존 보고서는 또한 두 가지 온프레미스 구현 경로를 제시하였다. 방식 A는 OpenAI 호환 클라이언트 + HOOK 패턴 래퍼이고, 방식 B는 순수 Python 미들웨어로 훅 패턴을 자체 구현하는 것이다.

### 1.2 이번 조사의 계기: Claude Agent SDK 온프레미스 불가 확인

기존 보고서 작성 이후 중요한 제약 사항이 추가로 확인되었다. **Claude Agent SDK는 공식적으로 온프레미스 배포를 지원하지 않는다.**

GitHub 이슈 #7178 (claude-code 리포지토리)은 Claude Agent SDK의 온프레미스/로컬 LLM 지원 요청이었으나, 2025년 말 기준 `CLOSED / NOT_PLANNED` 상태로 종료되었다. 이는 Anthropic이 Claude Agent SDK를 Anthropic 클라우드 API 전용으로 유지할 계획임을 의미한다.

이 확인 사항은 기존 보고서의 구현 경로에 직접적 영향을 미친다. "방식 A (OpenAI 호환 클라이언트 + HOOK 패턴 래퍼)"는 Claude Agent SDK 없이 훅 패턴만 차용하는 것이므로 여전히 유효하나, SDK 자체의 에이전틱 루프(agentic loop), 컨텍스트 관리, 도구 파싱 기능을 활용할 수 없다는 점이 명확해졌다.

### 1.3 이번 조사 목적

기존 보고서의 "처음부터 코딩하지 않고 기존 구현체 위에서 개발"하는 옵션이 충분히 탐색되지 않았다. Claude Agent SDK를 사용할 수 없다면, 다음 질문이 부상한다.

> **"동등한 훅 패턴 + 온프레미스 LLM 지원을 제공하는 기존 프레임워크가 있는가? 있다면 처음부터 코딩하는 것보다 나은가?"**

이번 조사는 이 질문에 답하기 위해 10개의 로컬 LLM 호환 Agent SDK/프레임워크를 체계적으로 분석한다.

### 1.4 조사 범위

다음 10개 프레임워크가 조사 대상이다.

| # | 프레임워크 | 개발 주체 | 주요 특성 |
|---|------------|-----------|-----------|
| 1 | PraisonAI | 단일 메인테이너 ("p1") | Ollama 공식 지원, 간편 설정 |
| 2 | Pydantic AI | Pydantic 팀 | Grammar-constrained 유일 지원 |
| 3 | Smolagents | HuggingFace | CodeAgent 방식, 강력한 HF 생태계 |
| 4 | LlamaIndex | LlamaIndex 팀 | 이벤트 기반 Workflow, 최고 성숙도 |
| 5 | OpenAI Agents SDK | OpenAI 공식 | RunHooks/AgentHooks 이중 계층 |
| 6 | CrewAI | CrewAI Inc. | @before_tool_call/@after_tool_call |
| 7 | AutoGen | Microsoft | 유지보수 모드 전환 (탈락) |
| 8 | Haystack | deepset | RAG-first 파이프라인 |
| 9 | DSPy | Stanford NLP | 프롬프트 컴파일러 (에이전트 SDK 아님) |
| 10 | Agno (구 Phidata) | Agno 팀 | 2025 신규, run_hooks + middleware |

### 1.5 조사 방법론 개요

각 프레임워크에 대해 공식 문서, GitHub 이슈 트래커, 커뮤니티 포럼, 실증 사례 보고서를 분석하였다. 6개 평가 기준을 각 5점 만점으로 채점하여 최대 30점의 종합 점수를 산출하였다. ClockCanvas 특수 조건(온프레미스, sub-10B 모델, EDA 도메인, Phase 순서 강제)을 주요 필터로 적용하였다.

---

## 2. 평가 기준 및 방법론

### 2.1 6개 평가 기준

#### 기준 1: 로컬/온프레미스 LLM 공식 지원 (5점 만점)

온프레미스 환경에서 vLLM, Ollama, LM Studio 등 로컬 LLM 서버와의 통합을 공식적으로 지원하는지 평가한다. 단순한 OpenAI 호환 URL 변경(base_url 교체)만 지원하는 경우는 2점, 전용 패키지 또는 공식 통합이 존재하는 경우 4-5점을 부여한다.

#### 기준 2: Hook/미들웨어 패턴 (5점 만점)

기존 보고서의 PreToolUse / PostToolUse / UserPromptSubmit에 상응하는 훅 또는 미들웨어 기능을 공식 API로 제공하는지 평가한다. 도구 실행 전후에 커스텀 로직을 삽입할 수 있는 공식 인터페이스가 있는 경우 높은 점수를 부여한다.

#### 기준 3: Sub-10B 모델 호환성 (5점 만점)

10B 파라미터 미만 모델과의 실증된 호환성을 평가한다. 공식 문서의 지원 명시, 커뮤니티 성공 사례, 알려진 버그(특히 tool calling 관련)의 유무를 종합적으로 고려한다.

#### 기준 4: Grammar-Constrained Decoding 통합 (5점 만점)

Outlines, XGrammar, lm-format-enforcer 등 grammar-constrained decoding 도구와의 네이티브 통합 또는 공식 지원을 평가한다. 기존 보고서에서 JSON 파싱 실패율을 38%에서 0%로 감소시키는 핵심 기술로 확인된 사항이다.

#### 기준 5: 프로덕션 성숙도 (5점 만점)

GitHub 릴리스 이력, 버전 안정성, 실제 프로덕션 배포 사례, 기업 채택 현황, API 안정성을 평가한다. 2025년 이후 유지보수 모드 전환 또는 API 변경이 잦은 프레임워크는 낮은 점수를 부여한다.

#### 기준 6: 커뮤니티/생태계 (5점 만점)

GitHub stars, 활성 기여자 수, 문서화 품질, 커뮤니티 포럼 활성도, 서드파티 통합의 풍부함을 평가한다.

### 2.2 ClockCanvas 필수 요건 (Knock-out 기준)

다음 두 가지 요건 중 하나라도 충족하지 못하면 추천 후보에서 제외된다.

- **KO-1:** 로컬/온프레미스 LLM 지원 (기준 1) 점수 2점 미만
- **KO-2:** 2025년 이후 유지보수 모드 전환 또는 아카이브

### 2.3 점수 척도 정의

| 점수 | 의미 |
|------|------|
| 5 | 완전 지원, 문서화, 실증 사례 다수 |
| 4 | 공식 지원, 일부 제약 존재 |
| 3 | 부분 지원 또는 우회 방법 필요 |
| 2 | 비공식 지원 또는 커뮤니티 해결책만 존재 |
| 1 | 지원 계획 없음 또는 알려진 심각한 버그 |

---

## 3. 프레임워크 개별 분석

### 3.1 PraisonAI

#### 기본 정보

| 항목 | 내용 |
|------|------|
| GitHub Stars | ~5,600 |
| 최신 버전 | 2.x |
| 라이선스 | MIT |
| 개발 주체 | 단일 메인테이너 ("p1", Mervin Praison) |
| 주요 목적 | 간편한 멀티 에이전트 구성 |

#### 6개 기준 점수표

| 평가 기준 | 점수 | 근거 |
|-----------|------|------|
| 로컬/온프레미스 LLM 지원 | 4/5 | Ollama 공식 지원, LiteLLM 통합 |
| Hook/미들웨어 패턴 | 1/5 | PreToolUse/PostToolUse 상당 기능 없음 |
| Sub-10B 모델 호환성 | 3/5 | Ollama를 통해 동작, 실증 사례 제한적 |
| Grammar-Constrained Decoding | 1/5 | 미지원 |
| 프로덕션 성숙도 | 2/5 | 단일 메인테이너, 릴리스 주기 불안정 |
| 커뮤니티/생태계 | 3/5 | YouTube 튜토리얼 다수, 문서 품질 보통 |
| **총점** | **14/30** | |

#### "p1"의 정체와 단일 메인테이너 리스크

PraisonAI의 주요 메인테이너인 "p1"(Mervin Praison)은 개인 개발자이다. GitHub 커밋 이력을 보면 기여자의 90% 이상이 단일 인물에 집중되어 있다. 이는 다음과 같은 구체적 리스크를 수반한다.

- 메인테이너 이탈 시 프로젝트 사실상 종료
- 버그 수정 우선순위가 단일 인물의 판단에 의존
- 기업 SLA(서비스 수준 협약) 불가능
- API 호환성 보장 체계 없음

#### 핵심 강점

- Ollama와의 통합이 간단하여 빠른 프로토타이핑에 적합
- YAML 기반 에이전트 구성으로 코드 없이 멀티 에이전트 설정 가능
- 다양한 LLM 프로바이더를 LiteLLM 통해 통합

#### 핵심 약점

- Hook/미들웨어 패턴 실질적 부재: PreToolUse/PostToolUse에 해당하는 공식 API 없음
- Grammar-constrained decoding 미지원
- 단일 메인테이너 리스크가 프로덕션 채택의 근본적 장벽

#### ClockCanvas 적합성 판단

**부적합.** Hook 패턴의 부재와 단일 메인테이너 리스크는 EDA 프로덕션 환경의 요구사항을 충족하지 못한다. Grammar-constrained decoding 미지원은 sub-10B 모델 환경에서 치명적 약점이다.

---

### 3.2 Pydantic AI

#### 기본 정보

| 항목 | 내용 |
|------|------|
| GitHub Stars | ~15,000 |
| 최신 버전 | v1.0 (2025-09 출시) |
| 라이선스 | MIT |
| 개발 주체 | Pydantic 팀 (Samuel Colvin 외) |
| 주요 목적 | 타입 안전 에이전트, 구조화 출력 |

#### 6개 기준 점수표

| 평가 기준 | 점수 | 근거 |
|-----------|------|------|
| 로컬/온프레미스 LLM 지원 | 4/5 | Ollama 공식 모델, OpenAI 호환 엔드포인트 |
| Hook/미들웨어 패턴 | 4/5 | instrument() API, 이벤트 후크 |
| Sub-10B 모델 호환성 | 4/5 | Ollama 통해 실증, tools와 동시 사용 제약 있음 |
| Grammar-Constrained Decoding | 5/5 | Outlines 통합 (10개 프레임워크 중 유일) |
| 프로덕션 성숙도 | 4/5 | v1.0 출시, Pydantic 팀의 신뢰도 |
| 커뮤니티/생태계 | 3/5 | 빠른 성장 중, 생태계 아직 초기 |
| **총점** | **24/30** | |

#### Outlines 통합: 유일한 Grammar-Constrained 지원

Pydantic AI는 10개 조사 대상 프레임워크 중 **유일하게** grammar-constrained decoding을 공식 통합하는 프레임워크이다. Outlines 라이브러리와의 통합을 통해 다음이 가능하다.

```python
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel

# vLLM 온프레미스 서버 + Outlines grammar-constrained decoding
model = OpenAIModel(
    model_name="qwen2.5-7b-instruct",
    base_url="http://localhost:8000/v1",
    api_key="not-required",
)

class EDAToolCall(BaseModel):
    tool_name: str
    parameters: dict
    phase: str

agent = Agent(
    model=model,
    result_type=EDAToolCall,  # Pydantic 모델로 출력 구조 강제
)

result = await agent.run("현재 합성 Phase에서 타이밍 분석을 실행하라.")
# result.data는 항상 EDAToolCall 인스턴스 (파싱 실패 없음)
print(result.data.tool_name)   # "run_synthesis" (예시)
```

#### tools와 동시 사용 불가 제약

Pydantic AI의 결정적 제약사항: **`result_type` (구조화 출력)과 `tools` (도구 호출)를 동시에 사용할 수 없다.** 구조화 출력 모드에서는 LLM이 직접 도구를 호출하는 agentic loop가 비활성화된다. 이는 다음을 의미한다.

- Grammar-constrained decoding → 도구 호출 에이전트 루프 불가
- 에이전트 루프 → grammar-constrained decoding 불가

ClockCanvas의 경우 이 제약으로 인해 Pydantic AI를 에이전트 메인 프레임워크로 사용하는 것이 어렵다. 다만 **구조화 출력 전용 레이어** (예: LLM 출력 파싱, 결과 검증)로는 이상적이다.

#### ClockCanvas 적합성 판단

**부분 적합 (구조화 출력 레이어 전용).** 메인 에이전트 프레임워크로는 tools 동시 사용 불가 제약으로 부적합하나, 구조화 출력 검증 계층 또는 DSPy와의 조합에서 강력한 보완재로 활용 가능하다.

---

### 3.3 Smolagents

#### 기본 정보

| 항목 | 내용 |
|------|------|
| GitHub Stars | ~15,000 |
| 최신 버전 | 1.x |
| 라이선스 | Apache 2.0 |
| 개발 주체 | HuggingFace |
| 주요 목적 | 경량 에이전트, CodeAgent |

#### 6개 기준 점수표

| 평가 기준 | 점수 | 근거 |
|-----------|------|------|
| 로컬/온프레미스 LLM 지원 | 5/5 | VLLMModel, LiteLLMModel(Ollama), TransformersModel 3가지 경로 |
| Hook/미들웨어 패턴 | 3/5 | 커스텀 에이전트 클래스 확장 가능, 공식 훅 API 없음 |
| Sub-10B 모델 호환성 | 4/5 | CodeAgent 방식이 JSON tool calling 실패를 근본 우회 |
| Grammar-Constrained Decoding | 2/5 | TransformersModel 통해 간접 지원 |
| 프로덕션 성숙도 | 3/5 | HuggingFace 지원, API 변경 빈번 |
| 커뮤니티/생태계 | 2/5 | HuggingFace Hub 연동 강점, 독립 생태계 작음 |
| **총점** | **19/30** | |

#### CodeAgent 방식: JSON Tool Calling 실패의 근본적 우회

Smolagents의 가장 혁신적인 특성은 **CodeAgent** 방식이다. 전통적인 JSON tool calling 대신, LLM이 Python 코드를 직접 생성하고 실행한다.

```python
from smolagents import CodeAgent, HfApiModel, VLLMModel

# vLLM 온프레미스 모델 연결
model = VLLMModel(
    model_id="Qwen/Qwen2.5-7B-Instruct",
    server_url="http://localhost:8000/v1",
)

agent = CodeAgent(
    tools=[run_synthesis_tool, check_timing_tool],
    model=model,
)

# LLM이 JSON이 아닌 Python 코드로 응답:
# ```python
# result = run_synthesis_tool(design_file="top.v", target_freq=500)
# if result.timing_violations > 0:
#     check_timing_tool(result.netlist)
# ```
result = agent.run("top.v 파일로 합성을 실행하고 타이밍을 확인하라.")
```

이 방식의 핵심 이점은 **JSON 파싱 실패 문제가 발생 자체가 불가능**하다는 점이다. LLM이 Python 코드를 생성하면 Python 인터프리터가 문법 오류를 즉시 감지하고 재시도를 요청할 수 있다. 하지만 동시에 Python 코드 실행은 보안 샌드박싱이 필수적이며, EDA 도구에 대한 임의 코드 실행은 심각한 보안 위험을 수반한다.

#### 3가지 로컬 LLM 통합 경로

| 경로 | 클래스 | 특성 |
|------|--------|------|
| vLLM | `VLLMModel` | GPU 가속, 고성능, lm-format-enforcer 통합 가능 |
| Ollama | `LiteLLMModel(model_id="ollama/...")` | 간편 설정, CPU 지원 |
| Transformers | `TransformersModel` | HuggingFace 모델 직접 로드, Grammar 통합 가능 |

#### ClockCanvas 적합성 판단

**조건부 적합.** CodeAgent 방식이 JSON 실패를 우회하는 혁신적 접근이지만, EDA 도구에 대한 임의 Python 코드 실행의 보안 위험이 허용 가능한 수준인지 별도 검토가 필요하다. 훅 패턴의 부재는 Phase 순서 강제를 코드 레벨에서 직접 구현해야 함을 의미한다.

---

### 3.4 LlamaIndex

#### 기본 정보

| 항목 | 내용 |
|------|------|
| GitHub Stars | 42,000+ |
| 최신 버전 | 0.12.x |
| 라이선스 | MIT |
| 개발 주체 | LlamaIndex 팀 (Jerry Liu 외) |
| 주요 목적 | RAG, 이벤트 기반 Workflow |

#### 6개 기준 점수표

| 평가 기준 | 점수 | 근거 |
|-----------|------|------|
| 로컬/온프레미스 LLM 지원 | 5/5 | llama-index-llms-vllm, llama-index-llms-ollama 전용 패키지 |
| Hook/미들웨어 패턴 | 5/5 | 이벤트 기반 Workflow에서 PreToolUse/PostToolUse 등가 구현 |
| Sub-10B 모델 호환성 | 4/5 | 실증 사례 다수, vLLM 통해 최적화 가능 |
| Grammar-Constrained Decoding | 3/5 | vLLM 통해 간접 지원 (네이티브 아님) |
| 프로덕션 성숙도 | 5/5 | 3년+ 운영, 기업 채택 다수, API 안정 |
| 커뮤니티/생태계 | 3/5 | RAG 중심 생태계, 에이전트 부분은 성장 중 |
| **총점** | **25/30** | |

#### 이벤트 기반 Workflow: PreToolUse/PostToolUse 등가 구현

LlamaIndex의 Workflow 시스템은 이벤트 기반 아키텍처로 PreToolUse/PostToolUse에 정확히 대응하는 구조를 제공한다.

```python
from llama_index.core.workflow import Workflow, step, Event
from llama_index.llms.vllm import Vllm

class ToolValidationEvent(Event):
    tool_name: str
    tool_params: dict
    phase: str

class ToolResultEvent(Event):
    result: dict
    success: bool

class ClockCanvasWorkflow(Workflow):
    def __init__(self, phase_controller):
        super().__init__(timeout=300)
        self.phase_controller = phase_controller
        self.llm = Vllm(
            model="Qwen/Qwen2.5-7B-Instruct",
            vllm_kwargs={"gpu_memory_utilization": 0.85},
        )

    @step
    async def pre_tool_use(self, ev: ToolValidationEvent) -> ToolResultEvent:
        """PreToolUse 훅 역할: Phase 기반 도구 호출 검증."""
        allowed = self.phase_controller.get_allowed_tools(ev.phase)
        if ev.tool_name not in allowed:
            return ToolResultEvent(
                result={"error": f"{ev.tool_name}은 {ev.phase}에서 허용되지 않음"},
                success=False,
            )
        # 실제 도구 실행
        result = await self.execute_tool(ev.tool_name, ev.tool_params)
        return ToolResultEvent(result=result, success=True)

    @step
    async def post_tool_use(self, ev: ToolResultEvent) -> None:
        """PostToolUse 훅 역할: 결과 기반 Phase 상태 업데이트."""
        if ev.success:
            self.phase_controller.advance_if_complete(ev.result)
```

#### 전용 vLLM 패키지의 의미

```bash
pip install llama-index-llms-vllm  # vLLM 전용 패키지
pip install llama-index-llms-ollama  # Ollama 전용 패키지
```

이 전용 패키지의 존재는 단순한 URL 교체 수준을 넘어, LlamaIndex 팀이 로컬 LLM 통합을 1급(first-class) 기능으로 지원함을 의미한다. vLLM 특화 최적화(배치 처리, 스트리밍, 모델 로딩)가 패키지에 포함되어 있다.

#### ClockCanvas 적합성 판단

**높은 적합성 (RAG 레이어 + Workflow 구조화 용도).** 성숙도, 로컬 LLM 지원, 이벤트 기반 훅 시스템이 ClockCanvas 요구사항과 잘 일치한다. 특히 EDA 문서, 설계 규칙 데이터베이스에 대한 RAG 파이프라인 구축에 이상적이다.

---

### 3.5 OpenAI Agents SDK

#### 기본 정보

| 항목 | 내용 |
|------|------|
| GitHub Stars | ~12,000 |
| 최신 버전 | 0.x (빠른 발전 중) |
| 라이선스 | MIT |
| 개발 주체 | OpenAI 공식 |
| 주요 목적 | OpenAI 중심 에이전트 |

#### 6개 기준 점수표

| 평가 기준 | 점수 | 근거 |
|-----------|------|------|
| 로컬/온프레미스 LLM 지원 | 3/5 | LiteLLM 통합 beta, 비-OpenAI 환경 기능 제약 |
| Hook/미들웨어 패턴 | 4/5 | RunHooks/AgentHooks 이중 계층, on_tool_start/on_tool_end |
| Sub-10B 모델 호환성 | 3/5 | 공식 지원이 OpenAI 모델 중심, 로컬 모델 호환성 검증 부족 |
| Grammar-Constrained Decoding | 2/5 | 직접 지원 없음, vLLM 서버 레벨에서 우회 가능 |
| 프로덕션 성숙도 | 3/5 | OpenAI 공식이지만 API 변경 빈번 |
| 커뮤니티/생태계 | 3/5 | OpenAI 생태계 의존, 독립 커뮤니티 작음 |
| **총점** | **18/30** | |

#### RunHooks/AgentHooks 이중 계층

OpenAI Agents SDK는 두 계층의 훅 시스템을 제공한다.

- **RunHooks:** 실행 전체 수준의 훅 (on_agent_start, on_agent_end)
- **AgentHooks:** 개별 에이전트 수준의 훅 (on_tool_start, on_tool_end)

이 이중 계층은 기존 보고서의 PreToolUse(on_tool_start), PostToolUse(on_tool_end)와 개념적으로 일치한다. 그러나 LiteLLM 통합이 beta 상태이며, 비-OpenAI 환경에서의 기능 제약(트레이싱, 병렬 도구 호출 등)이 문서화되어 있다.

#### ClockCanvas 적합성 판단

**조건부 적합.** 훅 시스템은 우수하나, OpenAI API 중심 설계로 인해 온프레미스 vLLM 환경에서 완전한 기능 활용이 어렵다. LiteLLM beta 의존성은 추가 리스크다.

---

### 3.6 CrewAI

#### 기본 정보

| 항목 | 내용 |
|------|------|
| GitHub Stars | 20,000+ |
| 최신 버전 | 0.80.x |
| 라이선스 | MIT |
| 개발 주체 | CrewAI Inc. |
| 주요 목적 | 역할 기반 멀티 에이전트 |

#### 6개 기준 점수표

| 평가 기준 | 점수 | 근거 |
|-----------|------|------|
| 로컬/온프레미스 LLM 지원 | 4/5 | Ollama 공식 지원, LiteLLM 통해 다양한 로컬 모델 |
| Hook/미들웨어 패턴 | 5/5 | @before_tool_call/@after_tool_call, ToolCallHookContext |
| Sub-10B 모델 호환성 | 3/5 | Issue #4036: sub-10B 모델 tool_calls 포맷 불일치 버그 |
| Grammar-Constrained Decoding | 2/5 | 직접 미지원, 서버 레벨 우회 가능 |
| 프로덕션 성숙도 | 4/5 | 100k+ 개발자, 기업 채택 사례 다수 |
| 커뮤니티/생태계 | 4/5 | 활발한 커뮤니티, 풍부한 통합 |
| **총점** | **22/30** | |

#### @before_tool_call/@after_tool_call: 가장 완성도 높은 훅 API

CrewAI의 훅 시스템은 10개 프레임워크 중 **훅 API 완성도가 가장 높다.** `ToolCallHookContext`를 통해 도구 호출의 전후 컨텍스트를 풍부하게 접근할 수 있다.

```python
from crewai import Agent, Task, Crew
from crewai.tools import BaseTool
from crewai.tools.tool_types import ToolCallHookContext

class EDAPhaseValidatorTool(BaseTool):
    name: str = "run_synthesis"
    description: str = "반도체 설계 합성을 실행합니다."

    def before_tool_call(self, context: ToolCallHookContext) -> None:
        """PreToolUse 역할: Phase 검증."""
        current_phase = context.agent.memory.get("current_phase")
        allowed_tools = context.agent.memory.get("allowed_tools", [])

        if self.name not in allowed_tools:
            raise PermissionError(
                f"현재 Phase '{current_phase}'에서 '{self.name}'은 허용되지 않습니다. "
                f"허용 도구: {allowed_tools}"
            )

    def after_tool_call(self, context: ToolCallHookContext, result: str) -> str:
        """PostToolUse 역할: 상태 업데이트 및 결과 후처리."""
        if "synthesis complete" in result.lower():
            context.agent.memory.set("synthesis_done", True)
            context.agent.memory.set("current_phase", "timing_analysis")
        return result

    def _run(self, design_file: str, target_freq: float) -> str:
        # 실제 합성 실행 로직
        return f"합성 완료: {design_file}, 목표 주파수: {target_freq}MHz"
```

#### Sub-10B 버그: Issue #4036

GitHub Issue #4036은 CrewAI에서 sub-10B 모델 사용 시 `tool_calls` 포맷 불일치 문제를 보고한다. 구체적으로, 일부 소형 모델이 CrewAI가 기대하는 OpenAI tool_calls 포맷이 아닌 자체 포맷으로 응답할 때 파싱 오류가 발생한다. 이 버그는 grammar-constrained decoding으로 완화 가능하나, 프레임워크 수준의 공식 패치가 아직 적용되지 않았다.

#### ClockCanvas 적합성 판단

**높은 적합성 (훅 시스템 측면).** `@before_tool_call/@after_tool_call`은 기존 보고서의 PreToolUse/PostToolUse와 가장 직접적으로 대응하는 기성품 구현이다. Sub-10B 버그는 grammar-constrained decoding과 병행 사용으로 완화 가능하다.

---

### 3.7 AutoGen

#### 기본 정보

| 항목 | 내용 |
|------|------|
| GitHub Stars | 54,400+ |
| 라이선스 | MIT |
| 개발 주체 | Microsoft |
| 주요 목적 | 멀티 에이전트 대화 |

#### 6개 기준 점수표

| 평가 기준 | 점수 | 근거 |
|-----------|------|------|
| 로컬/온프레미스 LLM 지원 | 3/5 | OpenAI 호환 엔드포인트 지원 |
| Hook/미들웨어 패턴 | 3/5 | 메시지 인터셉터 패턴 |
| Sub-10B 모델 호환성 | 3/5 | 동작하나 최적화 미흡 |
| Grammar-Constrained Decoding | 2/5 | 미지원 |
| 프로덕션 성숙도 | 1/5 | **2025년 10월 유지보수 모드 전환** |
| 커뮤니티/생태계 | 5/5 | 가장 큰 커뮤니티, 但 신규 개발 중단 |
| **총점** | **17/30** | |

#### 2025년 10월 유지보수 모드 전환: 탈락 결정

**AutoGen은 이번 조사에서 유일하게 KO-2 기준(유지보수 모드 전환)으로 탈락한 프레임워크이다.**

Microsoft는 2025년 10월 AutoGen을 유지보수 모드로 전환하고, 신규 개발을 "Microsoft Agent Framework"(내부 프로젝트)로 이전하였다. 이는 다음을 의미한다.

- 신규 기능 추가 없음
- 보안 패치만 제한적으로 유지
- 생태계 의존성 업데이트 불명확

GitHub stars 54,400+이라는 수치는 과거의 유산이며, 현재 진행 중인 프로젝트로서의 가치와 무관하다. 잇다반도체와 같이 수년간 운영해야 하는 프로덕션 환경에서 유지보수 모드 프레임워크 채택은 허용 불가한 장기 리스크이다.

#### ClockCanvas 적합성 판단

**탈락 (KO-2 기준 적용).** 유지보수 모드 전환으로 후보에서 제외한다.

---

### 3.8 Haystack

#### 기본 정보

| 항목 | 내용 |
|------|------|
| GitHub Stars | 18,000+ |
| 최신 버전 | 2.x |
| 라이선스 | Apache 2.0 |
| 개발 주체 | deepset |
| 주요 목적 | RAG 파이프라인, 프로덕션 NLP |

#### 6개 기준 점수표

| 평가 기준 | 점수 | 근거 |
|-----------|------|------|
| 로컬/온프레미스 LLM 지원 | 5/5 | vLLM 공식 통합, Ollama 컴포넌트 |
| Hook/미들웨어 패턴 | 3/5 | 파이프라인 컴포넌트 방식, 미들웨어 유사 구조 |
| Sub-10B 모델 호환성 | 3/5 | Ollama tool calling "not fully refined" 경고 |
| Grammar-Constrained Decoding | 2/5 | vLLM 통해 간접 지원 |
| 프로덕션 성숙도 | 5/5 | deepset 기업 지원, 엔터프라이즈 배포 다수 |
| 커뮤니티/생태계 | 3/5 | RAG 특화 강점, 에이전트 영역은 제한적 |
| **총점** | **21/30** | |

#### RAG-First 설계와 Ollama Tool Calling 주의사항

Haystack은 RAG 파이프라인에서 가장 성숙한 프레임워크이다. vLLM 전용 컴포넌트(`HuggingFaceAPIGenerator`, `vLLMChatGenerator`)를 통해 온프레미스 통합이 우수하다.

그러나 Haystack 공식 문서에는 다음 경고가 명시되어 있다.

> "Ollama을 통한 tool calling은 아직 완전히 정제되지 않았습니다(not fully refined). 모델과 Ollama 버전에 따라 동작이 다를 수 있습니다."

이 경고는 sub-10B 모델과의 조합에서 ClockCanvas의 핵심 기능(도구 호출 기반 EDA 작업)이 불안정할 수 있음을 시사한다. vLLM을 사용하면 이 문제를 우회할 수 있으나, Ollama 경로가 막히면 선택지가 제한된다.

#### ClockCanvas 적합성 판단

**부분 적합 (RAG 레이어 전용).** RAG 파이프라인 구축에는 LlamaIndex와 함께 최고 수준이나, 에이전트 훅 시스템이 Phase 순서 강제에 적합하지 않다. EDA 문서 검색, 설계 규칙 조회에 보조 레이어로 활용 권고.

---

### 3.9 DSPy

#### 기본 정보

| 항목 | 내용 |
|------|------|
| GitHub Stars | 22,000+ |
| 최신 버전 | 2.x |
| 라이선스 | MIT |
| 개발 주체 | Stanford NLP (Omar Khattab 외) |
| 주요 목적 | 프롬프트 컴파일러, 자동 최적화 |

#### 6개 기준 점수표

| 평가 기준 | 점수 | 근거 |
|-----------|------|------|
| 로컬/온프레미스 LLM 지원 | 4/5 | Ollama, vLLM, LM Studio 공식 지원 |
| Hook/미들웨어 패턴 | 2/5 | 에이전트 SDK가 아님, 훅 개념 없음 |
| Sub-10B 모델 호환성 | 5/5 | Sub-10B 최적화 핵심 강점 (770M T5 → GPT-3.5 수준) |
| Grammar-Constrained Decoding | 3/5 | Typed Predictors 통해 구조화 출력 강제 |
| 프로덕션 성숙도 | 4/5 | Stanford 연구 기반, 실증 사례 증가 |
| 커뮤니티/생태계 | 3/5 | 학술+산업 커뮤니티, 독특한 포지션 |
| **총점** | **21/30** | |

#### DSPy의 정체: 에이전트 SDK가 아닌 프롬프트 컴파일러

DSPy는 이번 조사 대상 10개 중 **유일하게 에이전트 SDK가 아닌 프레임워크**이다. DSPy는 "프롬프트 컴파일러" 또는 "자동 프롬프트 최적화 엔진"으로, 주어진 데이터셋과 메트릭을 기반으로 LLM 프롬프트를 자동으로 최적화한다.

DSPy가 총점 21/30을 받았음에도 에이전트 메인 프레임워크 후보에서 제외되는 이유는 이 근본적 역할 차이에 있다. DSPy는 "어떻게 LLM에게 물어볼 것인가"를 최적화하는 도구이지, "어떻게 에이전트 루프를 제어할 것인가"를 담당하지 않는다.

#### Sub-10B 최적화: 실증된 강점

DSPy의 가장 강력한 실증 사례는 770M 파라미터 T5 모델을 DSPy로 최적화하여 GPT-3.5 수준의 성능을 달성한 것이다. 이는 sub-10B 모델 환경에서 프롬프트 최적화의 중요성을 극명하게 보여준다.

ClockCanvas 관점에서 DSPy는 다음 역할에 적합하다.

- EDA 특화 프롬프트 자동 최적화 (Phase별 프롬프트 최적화)
- Sub-10B 모델의 도구 호출 정확도 향상
- 훈련 데이터 없이 few-shot 예제 자동 생성

#### ClockCanvas 적합성 판단

**부분 적합 (프롬프트 최적화 레이어 전용).** 에이전트 메인 프레임워크가 아니나, Phase별 프롬프트 최적화와 sub-10B 모델 성능 향상을 위한 보조 레이어로 이상적이다.

---

### 3.10 Agno (구 Phidata)

#### 기본 정보

| 항목 | 내용 |
|------|------|
| GitHub Stars | 추정 8,000+ (2025 신규, 급성장 중) |
| 최신 버전 | 1.x |
| 라이선스 | Mozilla Public License 2.0 |
| 개발 주체 | Agno 팀 (구 Phidata) |
| 주요 목적 | 모델 불가지론적 에이전트 |

#### 6개 기준 점수표

| 평가 기준 | 점수 | 근거 |
|-----------|------|------|
| 로컬/온프레미스 LLM 지원 | 5/5 | Ollama first-class (20+ 프로바이더), vLLM 지원 |
| Hook/미들웨어 패턴 | 5/5 | run_hooks + middleware 클래스 공식 지원 |
| Sub-10B 모델 호환성 | 4/5 | Ollama 통해 실증, EDA 사례 전무 |
| Grammar-Constrained Decoding | 2/5 | 직접 미지원, 서버 레벨 우회 가능 |
| 프로덕션 성숙도 | 3/5 | 2025 신규, EDA 사례 전무, 성숙도 검증 부족 |
| 커뮤니티/생태계 | 5/5 | 모델 불가지론적 설계, 빠른 생태계 성장 |
| **총점** | **~24/30** | |

#### run_hooks + middleware: 기존 보고서 방식 B의 기성품 버전

Agno의 `run_hooks`와 `middleware` 시스템은 기존 보고서의 "방식 B (순수 Python 미들웨어 자체 구현)"를 기성품으로 제공하는 것과 같다.

```python
from agno.agent import Agent
from agno.models.ollama import Ollama
from agno.run.response import RunResponse

class EDAPhaseHook:
    """Agno run_hooks를 사용한 PreToolUse/PostToolUse 구현."""

    def __init__(self, phase_controller):
        self.phase_controller = phase_controller

    def before_tool_call(self, agent: Agent, tool_name: str, **kwargs) -> bool:
        """PreToolUse 역할."""
        state = self.phase_controller.get_state()
        if tool_name not in state["allowed_tools"]:
            agent.add_message(
                role="system",
                content=f"'{tool_name}'은 현재 Phase에서 허용되지 않습니다."
            )
            return False  # 도구 실행 중단
        return True

    def after_tool_call(self, agent: Agent, tool_name: str, result: str) -> None:
        """PostToolUse 역할."""
        self.phase_controller.update_state(tool_name, result)

agent = Agent(
    model=Ollama(id="qwen2.5:7b"),
    run_hooks=EDAPhaseHook(phase_controller),
    tools=[run_synthesis, check_timing, run_placement],
    markdown=True,
)
```

#### Ollama first-class 지원과 20+ 프로바이더

Agno는 Ollama를 1급(first-class) 지원 프로바이더로 다룬다. OpenAI 호환 URL 교체가 아닌, Ollama 전용 클라이언트 클래스(`Ollama(id="...")`)를 제공한다. 20개 이상의 LLM 프로바이더를 단일 API로 추상화하며, 프로바이더 교체가 단 한 줄 코드 변경으로 가능하다.

#### 성숙도 3점의 의미

Agno는 2025년 신규 프레임워크로, 다음 성숙도 관련 위험이 존재한다.

- EDA 도메인 사례 전무: EDA 특화 도구와의 호환성 미검증
- API 안정성 불확실: 신규 프레임워크 특성상 API 변경 가능성
- 장기 지원 불명확: 기업 SLA 체계 미확립

#### ClockCanvas 적합성 판단

**높은 잠재 적합성, 성숙도 검증 필요.** run_hooks + middleware 시스템이 기존 보고서 방식 B의 기성품 버전이며, Ollama first-class 지원이 우수하다. 성숙도 부족이 유일한 주요 약점으로, 2026년 하반기 이후 재평가 권고.

---

## 4. 종합 비교 매트릭스

### 4.1 전체 비교표

| 프레임워크 | 로컬LLM | Hook | Sub-10B | Grammar | 성숙도 | 커뮤니티 | **총점** | 상태 |
|-----------|---------|------|---------|---------|--------|----------|---------|------|
| LlamaIndex | 5 | 5 | 4 | 3 | 5 | 3 | **25** | 추천 후보 |
| Pydantic AI | 4 | 4 | 4 | 5 | 4 | 3 | **24** | 추천 후보 |
| Agno | 5 | 5 | 4 | 2 | 3 | 5 | **~24** | 추천 후보 |
| CrewAI | 4 | 5 | 3 | 2 | 4 | 4 | **22** | 추천 후보 |
| Haystack | 5 | 3 | 3 | 2 | 5 | 3 | **21** | 부분 적합 |
| DSPy | 4 | 2 | 5 | 3 | 4 | 3 | **21** | 부분 적합 |
| Smolagents | 5 | 3 | 4 | 2 | 3 | 2 | **19** | 조건부 |
| OpenAI Agents SDK | 3 | 4 | 3 | 2 | 3 | 3 | **18** | 조건부 |
| AutoGen | 3 | 3 | 3 | 2 | 1 | 5 | **17** | **탈락** |
| PraisonAI | 4 | 1 | 3 | 1 | 2 | 3 | **14** | 부적합 |

### 4.2 상위 5개 집중 비교

| 비교 항목 | LlamaIndex | Pydantic AI | Agno | CrewAI | (순수 Python) |
|-----------|-----------|-------------|------|--------|--------------|
| 훅 API 방식 | 이벤트 기반 | instrument() | run_hooks | @decorator | 직접 구현 |
| vLLM 통합 | 전용 패키지 | OpenAI 호환 | 직접 지원 | LiteLLM | 직접 연결 |
| Grammar 지원 | vLLM 경유 | Outlines 네이티브 | vLLM 경유 | vLLM 경유 | vLLM 직접 |
| Phase FSM | 외부 구현 필요 | 외부 구현 필요 | 외부 구현 필요 | 외부 구현 필요 | 직접 구현 |
| Sub-10B 버그 | 없음 | 없음 | 없음 | Issue #4036 | N/A |
| EDA 사례 | 없음 | 없음 | 없음 | 없음 | N/A |
| 성숙도 | 최고 (5/5) | 높음 (4/5) | 낮음 (3/5) | 높음 (4/5) | 완전 통제 |

### 4.3 ClockCanvas 특화 평가

ClockCanvas의 특수 요구사항(EDA Phase 순서 강제, 온프레미스, sub-10B)을 기준으로 한 추가 평가.

| 요구사항 | LlamaIndex | Pydantic AI | Agno | CrewAI |
|---------|-----------|-------------|------|--------|
| EDA Phase FSM | 외부 구현 | 외부 구현 | 외부 구현 | 외부 구현 |
| 온프레미스 vLLM | 전용 패키지 ✓ | OpenAI 호환 ✓ | 직접 지원 ✓ | LiteLLM ✓ |
| Grammar-constrained | vLLM 경유 ✓ | Outlines ✓✓ | vLLM 경유 ✓ | vLLM 경유 ✓ |
| IP 데이터 보호 | 온프레미스 ✓ | 온프레미스 ✓ | 온프레미스 ✓ | 온프레미스 ✓ |
| 장기 안정성 | 매우 높음 | 높음 | 미검증 | 높음 |

**핵심 발견:** 모든 프레임워크에서 **EDA Phase FSM은 외부에서 별도 구현해야 한다.** 이는 기존 보고서의 Layer 1(Phase 컨트롤러)이 어떤 프레임워크를 선택해도 필수 자체 구현 컴포넌트임을 확인한다.

---

## 5. 변증법적 분석 (정반합 2라운드)

### 5.1 Round 1: 기존 보고서 결론 vs. 프레임워크 채택

#### 정(正): "기존 보고서 결론(순수 Python 미들웨어)이 여전히 최선"

기존 보고서의 최종 결론은 순수 Python 미들웨어로 Hook 패턴을 자체 구현하는 "방식 B"를 권고하였다. 이 입장을 지지하는 근거는 다음과 같다.

**근거 1: Grammar-Constrained Decoding은 어떤 프레임워크도 온전히 해결하지 못한다**

10개 프레임워크 중 grammar-constrained decoding을 네이티브로 통합하는 것은 Pydantic AI 단 하나이며, 그마저도 tools와 동시 사용이 불가능하다. 나머지 9개 프레임워크는 vLLM 서버 레벨에서 grammar-constrained decoding을 적용해야 하며, 이는 프레임워크 선택과 무관하다. 즉, grammar-constrained decoding 측면에서 프레임워크가 제공하는 실질적 가치는 미미하다.

**근거 2: 추상화 레이어가 복잡도를 증가시킨다**

CrewAI의 `@before_tool_call`이 편리해 보이지만, ClockCanvas의 Phase FSM 로직을 CrewAI의 추상화 위에 구현하면 두 가지 상태 관리 시스템(CrewAI 내부 상태 + Phase FSM)이 공존하게 된다. 이 이중 상태 관리는 디버깅을 복잡하게 만든다.

**근거 3: 프레임워크 수명주기 리스크**

AutoGen(Microsoft)이 2025년 10월 유지보수 모드로 전환된 사례는, 대형 조직이 지원하는 프레임워크도 갑작스러운 방향 전환이 가능함을 보여준다. 순수 Python 구현은 이 리스크가 원천 존재하지 않는다.

**근거 4: EDA Phase FSM은 어차피 자체 구현 필수**

4.3에서 확인했듯, 10개 프레임워크 모두 EDA Phase FSM을 외부에서 자체 구현해야 한다. 프레임워크가 제공하지 않는 가장 핵심적인 컴포넌트를 어차피 직접 만들어야 한다면, 그 위의 훅 레이어도 직접 구현하는 것과 총 개발 비용 차이가 크지 않다.

#### 반(反): "상위 프레임워크가 기존 결론보다 낫다"

반대 입장에서는 다음 근거로 기존 보고서 결론을 비판한다.

**근거 1: Agno의 run_hooks는 기존 보고서 방식 B의 기성품 버전**

Agno의 `run_hooks` + `middleware` 조합은 기존 보고서가 권고한 순수 Python 미들웨어를 기성품으로 제공한다. 이미 검증된 구현체를 사용하면 초기 개발 속도가 빠르고, 커뮤니티에서 발견된 버그가 이미 수정된 상태로 사용할 수 있다.

**근거 2: LlamaIndex 이벤트 Workflow는 EDA 파이프라인 구조화에 우월**

LlamaIndex의 이벤트 기반 Workflow는 EDA 파이프라인의 이벤트 구조(Phase 시작, 도구 호출, Phase 완료)를 자연스럽게 표현한다. RAG(EDA 문서 검색)와 에이전트 워크플로우를 단일 프레임워크로 통합할 수 있다.

**근거 3: "처음부터 코딩하지 않는다"는 사용자 요구 미충족**

조사 요청 자체가 "처음부터 코딩하지 않고 기존 구현체 위에서 개발"하는 옵션 탐색이었다. 기존 보고서 결론을 그대로 유지하면 이 요구사항이 충족되지 않는다.

**근거 4: CrewAI @before_tool_call은 즉시 활용 가능**

CrewAI의 `@before_tool_call`/`@after_tool_call`은 Pre/PostToolUse 훅의 완성도 높은 기성품이다. 100k+ 개발자 커뮤니티에서 검증된 구현체를 사용하면 엣지 케이스에 대한 처리가 이미 내장되어 있다.

#### 합(合) 1: Layer별 프레임워크 적합성이 다르다

Round 1의 정반 분석을 통해 도출되는 1차 합은 다음과 같다.

**"단일 프레임워크로 모든 레이어를 대체하려는 시도는 실패한다. 각 레이어의 역할에 따라 프레임워크 채택 여부를 독립적으로 결정해야 한다."**

구체적으로:
- **Layer 1 (Phase FSM):** 어떤 프레임워크도 이를 제공하지 않는다 → 자체 구현 필수
- **Layer 2 (Hook 검증층):** Agno 또는 CrewAI가 좋은 후보이나, 자체 구현도 충분히 작다
- **Layer 3 (Grammar LLM):** vLLM + lm-format-enforcer는 프레임워크 선택과 무관
- **부가 기능 (RAG, 구조화 출력, 프롬프트 최적화):** LlamaIndex, Pydantic AI, DSPy가 각 역할에 특화

---

### 5.2 Round 2: Agno 단독 채택 vs. 기존 아키텍처 유지

#### 정(正): "Agno가 ClockCanvas에 가장 적합"

Round 1의 1차 합에서 Agno가 Layer 2 후보로 부상하였다. Agno 채택을 강하게 지지하는 입장의 근거는 다음과 같다.

**근거 1: run_hooks + middleware = PreToolUse/PostToolUse 기성품**

Agno의 `run_hooks` 시스템은 기존 보고서가 방식 B로 자체 구현하도록 권고한 미들웨어를 공개 API로 제공한다. 구현 비용이 절감되고, 커뮤니티 검증이 이미 되어 있다.

**근거 2: 모델 불가지론적 설계 = 진화 전략과 일치**

Agno는 모델 프로바이더를 단 한 줄로 교체할 수 있도록 설계되었다. 이는 기존 보고서의 "모델 발전에 따른 훅 엄격도 조정" 진화 전략과 완벽하게 일치한다. Ollama에서 시작하여 vLLM으로, 나아가 미래의 로컬 모델로 교체가 용이하다.

**근거 3: Ollama first-class 지원**

Agno는 OpenAI 호환 URL 교체 방식이 아닌, Ollama 전용 클라이언트를 제공한다. 이는 Ollama의 모델 관리, 컨텍스트 최적화 기능을 프레임워크 수준에서 활용할 수 있음을 의미한다.

#### 반(反): "Agno 성숙도 부족, 기존 아키텍처가 더 안전"

Agno 채택에 반대하는 입장의 근거는 다음과 같다.

**근거 1: 성숙도 3점, EDA 사례 전무**

Agno는 2025년 신규 프레임워크로, EDA 도메인에서의 활용 사례가 전혀 없다. ClockCanvas가 Agno를 채택하면 사실상 EDA 분야 최초 사례가 된다. 이는 예상치 못한 버그와 엣지 케이스에 직면할 가능성이 높음을 의미한다.

**근거 2: Grammar 우회 필요 시 추상화 파괴**

Agno는 grammar-constrained decoding을 네이티브로 지원하지 않는다. vLLM 서버 레벨에서 grammar를 적용하면, Agno의 추상화(모델 불가지론적 API)가 vLLM 특화 파라미터(`extra_body={"guided_json": ...}`)를 직접 전달해야 하는 순간 깨진다.

**근거 3: Phase Controller FSM은 어차피 자체 구현 필수**

Agno를 채택해도 Layer 1(Phase FSM)은 순수 Python으로 직접 구현해야 한다. Agno가 제공하는 것은 Layer 2(훅 레이어)뿐이다. Layer 2 단독 구현 비용은 Agno 학습 곡선과 의존성 관리 비용 대비 실질적으로 크지 않다.

**근거 4: Mozilla Public License 2.0의 카피레프트 조항**

Agno는 MIT 또는 Apache 2.0이 아닌 Mozilla Public License 2.0(MPL 2.0)을 사용한다. MPL 2.0은 수정된 파일을 동일 라이선스로 공개해야 하는 약한 카피레프트 조항이 있다. 잇다반도체의 법무팀이 이를 별도 검토해야 한다.

#### 합(合) 2: "핵심 자체 구현 + 외곽 프레임워크" 하이브리드

Round 2의 분석에서 도출되는 최종 합은 다음과 같다.

**"Phase FSM과 Hook 검증층이라는 핵심 제어 로직은 순수 Python으로 자체 구현하고, RAG/구조화 출력/프롬프트 최적화라는 부가 기능 레이어에서 특화 프레임워크를 도입하는 하이브리드 전략이 최적이다."**

이 합은 다음 원칙에 기반한다.

1. **핵심 제어 = 자체 구현:** Phase FSM과 Hook 패턴은 ClockCanvas의 핵심 차별화 요소이며, 외부 의존성 없이 완전한 통제가 필요하다
2. **부가 기능 = 프레임워크 활용:** RAG, 구조화 출력, 프롬프트 최적화는 범용적이며, 성숙한 프레임워크의 활용이 효율적이다
3. **교체 가능 인터페이스 설계:** Layer 2 Hook 레이어를 인터페이스 기반으로 설계하면, 순수 Python 구현을 Agno/CrewAI로 나중에 교체할 수 있다

---

## 6. 최종 권고 및 ClockCanvas v2 아키텍처

### 6.1 최종 권고 요약

기존 보고서의 3계층 아키텍처를 유지하되, 다음 사항을 추가한다.

| 레이어 | 구현 방식 | 변경 여부 |
|--------|-----------|-----------|
| Layer 1: Phase FSM | 순수 Python (EDAPhaseController) | 변경 없음 |
| Layer 2: Hook 검증층 | 인터페이스 기반 순수 Python | 교체 가능 설계로 강화 |
| Layer 3: Grammar LLM | vLLM + lm-format-enforcer | 변경 없음 |
| 부가: RAG | LlamaIndex + llama-index-llms-vllm | 신규 추가 |
| 부가: 구조화 출력 | Pydantic AI (도구 없는 검증 용도) | 신규 추가 |
| 부가: 프롬프트 최적화 | DSPy (성능 병목 발생 시) | 선택적 추가 |

### 6.2 ClockCanvas v2 아키텍처 다이어그램

```
+===========================================================================+
|                  ClockCanvas v2 Agent Architecture                        |
|                  (기존 보고서 3계층 + 부가 기능 레이어)                    |
+===========================================================================+

+-------------------------------------------------------------------------+
| [LAYER 1] Phase Controller FSM (순수 Python — 변경 없음)                 |
|                                                                         |
|  +----------------+    +----------------+    +----------------+         |
|  | RTL Check      | -> | Synthesis      | -> | Timing Analysis|         |
|  | (Rigid Phase)  |    | (Rigid Phase)  |    | (Guided Phase) |         |
|  +----------------+    +----------------+    +----------------+         |
|          |                     |                     |                  |
|          v                     v                     v                  |
|  +----------------+    +----------------+                               |
|  | Place & Route  | -> | Final Verify   |                               |
|  | (Rigid Phase)  |    | (Rigid Phase)  |                               |
|  +----------------+    +----------------+                               |
|                                                                         |
|  workflow_state.json: { phase, allowed_tools, retry_counts, ... }       |
+-------------------------------------------------------------------------+
                                  |
                    Phase 상태 주입 (매 LLM 호출 전)
                                  |
                                  v
+-------------------------------------------------------------------------+
| [LAYER 2] Hook 검증층 (인터페이스 기반 — PurePython/Agno 교체 가능)       |
|                                                                         |
|  <<interface>> HookProvider                                             |
|  +------------------------------------------+                          |
|  | + on_prompt_submit(state) -> str          |  UserPromptSubmit 역할   |
|  | + pre_tool_use(tool, params) -> Decision  |  PreToolUse 역할         |
|  | + post_tool_use(tool, result) -> None     |  PostToolUse 역할        |
|  +------------------------------------------+                          |
|           |                          |                                  |
|           v                          v                                  |
|  PurePythonHookProvider     [AgnoHookAdapter] (선택적 교체)             |
|  (현재 기본 구현)            (Agno 성숙 후 교체 가능)                    |
+-------------------------------------------------------------------------+
                                  |
                    검증된 도구 호출 (JSON 보장)
                                  |
                                  v
+-------------------------------------------------------------------------+
| [LAYER 3] Grammar-Constrained LLM (vLLM + lm-format-enforcer — 변경 없음)|
|                                                                         |
|  On-premise vLLM Server                                                 |
|  +---------------------------------------+                              |
|  | Model: Qwen2.5-7B / Llama-3.1-8B ... |                              |
|  | guided_decoding_backend: lm-format-enforcer                          |
|  | Phase별 JSON Schema 강제              |                              |
|  | 노출 도구: Phase당 1-2개              |                              |
|  +---------------------------------------+                              |
+-------------------------------------------------------------------------+
                                  |
                    +--------------+--------------+
                    |              |              |
                    v              v              v
+-------------------+ +-------------------+ +-------------------+
| [부가] LlamaIndex  | | [부가] Pydantic AI | | [부가] DSPy       |
| RAG 파이프라인     | | 구조화 출력 검증   | | 프롬프트 최적화   |
|                   | |                   | |                   |
| llama-index-llms  | | result_type=      | | Phase별 프롬프트  |
| -vllm 전용 패키지  | | EDAToolCallResult | | 자동 최적화       |
|                   | | (tools 없는 모드) | |                   |
| EDA 문서 검색     | | 출력 유효성 검증  | | Sub-10B 성능향상  |
| 설계 규칙 조회    | |                   | |                   |
+-------------------+ +-------------------+ +-------------------+
                                  |
                                  v
+-------------------------------------------------------------------------+
| [Human-in-the-Loop Gate]                                                |
| - 재시도 임계값 초과 시 자동 활성화                                       |
| - 타임아웃 직전 고위험 작업 수동 승인                                     |
| - 잔여 불확실성(~0.5%) 처리                                              |
+-------------------------------------------------------------------------+
```

### 6.3 코드 예제 1: LlamaIndex + vLLM 통합

```python
# 예제 1: LlamaIndex vLLM 통합 — EDA 문서 RAG 파이프라인
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader
from llama_index.llms.vllm import Vllm
from llama_index.core import Settings

# vLLM 온프레미스 서버 연결 (전용 패키지 사용)
Settings.llm = Vllm(
    model="Qwen/Qwen2.5-7B-Instruct",
    vllm_kwargs={
        "gpu_memory_utilization": 0.85,
        "max_model_len": 8192,
    },
    temperature=0.1,
    max_new_tokens=512,
)

# EDA 문서 (설계 규칙, 타이밍 제약) 인덱싱
documents = SimpleDirectoryReader("./eda_docs/").load_data()
index = VectorStoreIndex.from_documents(documents)
query_engine = index.as_query_engine()

def query_eda_rules(question: str) -> str:
    """EDA 설계 규칙 및 타이밍 제약 조회."""
    response = query_engine.query(question)
    return str(response)

# 사용 예시
result = query_eda_rules(
    "TSMC 7nm 공정에서 클럭 주파수 500MHz 달성을 위한 최소 셀 간격은?"
)
print(result)
```

### 6.4 코드 예제 2: Pydantic AI + 구조화 출력 검증

```python
# 예제 2: Pydantic AI — EDA 도구 호출 결과 구조화 검증
# (tools 없는 모드: 구조화 출력 검증 레이어 전용)
from pydantic import BaseModel, field_validator
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from typing import Optional

class SynthesisResult(BaseModel):
    """합성 결과 구조화 출력 스키마."""
    success: bool
    timing_slack_ps: float
    area_um2: float
    power_mw: float
    violations: list[str] = []
    recommended_next_phase: str

    @field_validator("recommended_next_phase")
    @classmethod
    def validate_phase(cls, v: str) -> str:
        valid_phases = ["timing_analysis", "place_and_route", "retry_synthesis"]
        if v not in valid_phases:
            raise ValueError(f"유효하지 않은 Phase: {v}. 허용값: {valid_phases}")
        return v

# vLLM 온프레미스 서버 (OpenAI 호환 엔드포인트)
model = OpenAIModel(
    model_name="Qwen/Qwen2.5-7B-Instruct",
    base_url="http://localhost:8000/v1",
    api_key="not-required",
)

# tools 없이 구조화 출력만 사용 (Pydantic AI 제약 활용)
validator_agent = Agent(
    model=model,
    result_type=SynthesisResult,
    system_prompt=(
        "합성 로그를 분석하여 구조화된 결과를 반환하라. "
        "timing_slack이 음수이면 violations에 포함하라."
    ),
)

async def validate_synthesis_output(synthesis_log: str) -> SynthesisResult:
    """합성 출력 로그를 파싱하여 구조화된 결과 반환."""
    result = await validator_agent.run(synthesis_log)
    return result.data  # 항상 SynthesisResult 인스턴스

# 사용 예시 (Phase FSM에서 PostToolUse 역할로 호출)
import asyncio
result = asyncio.run(validate_synthesis_output("""
Synthesis completed for top_clock.v
Timing slack: -23ps (VIOLATION)
Area: 15420 um2
Power: 8.3 mW
"""))
print(f"다음 Phase: {result.recommended_next_phase}")
print(f"위반 사항: {result.violations}")
```

### 6.5 코드 예제 3: CrewAI @before_tool_call 훅

```python
# 예제 3: CrewAI @before_tool_call/@after_tool_call — Phase 검증 훅
from crewai.tools import BaseTool
from crewai.tools.tool_types import ToolCallHookContext
from pydantic import BaseModel

class SynthesisInput(BaseModel):
    design_file: str
    target_freq_mhz: float
    output_dir: str

class RunSynthesisTool(BaseTool):
    name: str = "run_synthesis"
    description: str = "반도체 설계 합성을 실행합니다. Synthesis Phase에서만 사용 가능."
    args_schema: type[BaseModel] = SynthesisInput

    # Phase 컨트롤러 주입 (의존성 주입)
    _phase_controller: object = None

    def before_tool_call(self, context: ToolCallHookContext) -> None:
        """PreToolUse 역할: Phase 기반 허용 여부 검증."""
        state = self._phase_controller.get_state()
        current_phase = state["current_phase"]
        allowed_tools = state["allowed_tools"]

        if self.name not in allowed_tools:
            raise PermissionError(
                f"[Phase 위반] '{self.name}'은 "
                f"'{current_phase}' Phase에서 허용되지 않습니다. "
                f"이 도구는 'synthesis' Phase에서만 사용 가능합니다. "
                f"현재 허용 도구: {allowed_tools}"
            )

        # 재시도 카운터 초기화 (정상 호출)
        self._phase_controller.reset_retry_count(current_phase)

    def after_tool_call(self, context: ToolCallHookContext, result: str) -> str:
        """PostToolUse 역할: 결과 기반 Phase 상태 업데이트."""
        if "SUCCESS" in result.upper():
            self._phase_controller.mark_phase_complete("synthesis")
            self._phase_controller.advance_phase()  # -> timing_analysis
            return result + "\n[시스템: 합성 완료. 타이밍 분석 Phase로 진입합니다.]"

        # 실패 시 재시도 카운터 증가
        retry_count = self._phase_controller.increment_retry("synthesis")
        if retry_count >= 3:
            self._phase_controller.activate_human_in_the_loop()
            return result + "\n[시스템: 재시도 한도 초과. 사람의 검토가 필요합니다.]"

        return result

    def _run(self, design_file: str, target_freq_mhz: float, output_dir: str) -> str:
        # 실제 합성 도구 호출 로직 (외부 EDA 도구 연동)
        return f"합성 실행 중: {design_file} → {output_dir} (목표: {target_freq_mhz}MHz)"
```

### 6.6 코드 예제 4: Agno run_hooks 미들웨어

```python
# 예제 4: Agno run_hooks — Phase 검증 미들웨어 구현
from agno.agent import Agent
from agno.models.ollama import Ollama
from agno.tools import tool
from typing import Optional
import json

class ClockCanvasAgnoHook:
    """
    Agno run_hooks 인터페이스를 사용한 ClockCanvas Phase 검증 훅.
    기존 보고서 방식 B(순수 Python 미들웨어)의 Agno 기반 구현체.
    """

    def __init__(self, phase_controller):
        self.phase_controller = phase_controller

    def before_run(self, agent: Agent, message: str, **kwargs) -> Optional[str]:
        """UserPromptSubmit 역할: 매 호출 전 Phase 컨텍스트 주입."""
        state = self.phase_controller.get_state()
        context_injection = (
            f"\n[시스템 컨텍스트]\n"
            f"현재 Phase: {state['current_phase']}\n"
            f"허용 도구: {', '.join(state['allowed_tools'])}\n"
            f"완료된 Phase: {', '.join(state['completed_phases'])}\n"
        )
        return message + context_injection

    def before_tool_call(
        self, agent: Agent, tool_name: str, tool_args: dict, **kwargs
    ) -> bool:
        """PreToolUse 역할: 도구 호출 전 Phase 검증."""
        state = self.phase_controller.get_state()
        allowed = state["allowed_tools"]

        if tool_name not in allowed:
            # Agno는 False 반환 시 도구 실행 취소
            agent.add_message(
                role="tool",
                content=json.dumps({
                    "error": f"Phase 위반: '{tool_name}'은 현재 허용되지 않음",
                    "allowed_tools": allowed,
                    "current_phase": state["current_phase"],
                }),
            )
            return False

        return True

    def after_tool_call(
        self, agent: Agent, tool_name: str, tool_args: dict, result: str, **kwargs
    ) -> None:
        """PostToolUse 역할: 도구 결과 기반 Phase 상태 갱신."""
        self.phase_controller.update_after_tool(tool_name, result)


# Agno 에이전트 구성
phase_controller = EDAPhaseController()  # 자체 구현 FSM
hook = ClockCanvasAgnoHook(phase_controller)

agent = Agent(
    model=Ollama(id="qwen2.5:7b"),  # Ollama first-class 지원
    run_hooks=hook,
    tools=[run_rtl_lint, run_synthesis, check_timing, run_placement, run_drc],
    instructions=(
        "당신은 EDA 워크플로우 에이전트입니다. "
        "시스템 컨텍스트에 명시된 허용 도구만 사용하십시오."
    ),
    markdown=True,
)
```

### 6.7 코드 예제 5: HookProvider 인터페이스 (교체 가능 설계)

```python
# 예제 5: HookProvider 인터페이스 — 순수 Python/Agno/CrewAI 교체 가능 설계
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any

class HookDecision(Enum):
    ALLOW = "allow"
    BLOCK = "block"
    MODIFY = "modify"

@dataclass
class HookResult:
    decision: HookDecision
    reason: str = ""
    modified_params: dict | None = None

class HookProvider(ABC):
    """
    Layer 2 Hook 검증층의 추상 인터페이스.
    이 인터페이스를 구현하면 PurePython, Agno, CrewAI 간 교체 가능.
    """

    @abstractmethod
    def on_prompt_submit(self, user_prompt: str, state: dict) -> str:
        """UserPromptSubmit 역할: Phase 컨텍스트 주입."""
        ...

    @abstractmethod
    def pre_tool_use(
        self, tool_name: str, tool_params: dict, state: dict
    ) -> HookResult:
        """PreToolUse 역할: Phase 기반 도구 호출 검증."""
        ...

    @abstractmethod
    def post_tool_use(
        self, tool_name: str, tool_params: dict, result: Any, state: dict
    ) -> None:
        """PostToolUse 역할: 결과 기반 상태 갱신."""
        ...


class PurePythonHookProvider(HookProvider):
    """
    기본 구현체: 순수 Python 미들웨어.
    외부 프레임워크 의존성 없음.
    """

    def __init__(self, phase_controller):
        self.phase_controller = phase_controller

    def on_prompt_submit(self, user_prompt: str, state: dict) -> str:
        phase_info = (
            f"\n현재 Phase: {state['current_phase']}\n"
            f"허용 도구: {state['allowed_tools']}\n"
        )
        return user_prompt + phase_info

    def pre_tool_use(
        self, tool_name: str, tool_params: dict, state: dict
    ) -> HookResult:
        if tool_name not in state["allowed_tools"]:
            retry = self.phase_controller.increment_retry(state["current_phase"])
            if retry >= state.get("max_retries", 3):
                self.phase_controller.activate_human_review()
                return HookResult(
                    decision=HookDecision.BLOCK,
                    reason="재시도 한도 초과. 사람의 검토가 필요합니다.",
                )
            return HookResult(
                decision=HookDecision.BLOCK,
                reason=(
                    f"'{tool_name}'은 '{state['current_phase']}' Phase에서 "
                    f"허용되지 않습니다. 허용 도구: {state['allowed_tools']}"
                ),
            )
        return HookResult(decision=HookDecision.ALLOW)

    def post_tool_use(
        self, tool_name: str, tool_params: dict, result: Any, state: dict
    ) -> None:
        self.phase_controller.update_state(tool_name, result)


class AgnoHookAdapter(HookProvider):
    """
    Agno run_hooks를 HookProvider 인터페이스로 래핑.
    Agno 성숙 후 PurePythonHookProvider를 교체할 때 사용.
    """
    # (Agno 성숙 후 구현)
    ...


# 사용 예시: 단 한 줄로 구현체 교체 가능
hook_provider: HookProvider = PurePythonHookProvider(phase_controller)
# hook_provider: HookProvider = AgnoHookAdapter(phase_controller)  # 나중에 교체
```

---

## 7. 구현 전략 및 단계적 도입 로드맵

### 7.1 도입 원칙

1. **핵심 제어 우선:** Layer 1 (Phase FSM)과 Layer 2 (Hook 검증층)은 반드시 먼저 구현한다. 부가 기능 레이어는 핵심 제어가 안정화된 이후 단계적으로 도입한다.
2. **낮은 위험 우선:** 각 단계에서 위험도가 낮은 항목부터 도입하여 실패 가능성을 최소화한다.
3. **교체 가능성 보장:** HookProvider 인터페이스를 통해 구현체를 나중에 교체할 수 있도록 설계한다.
4. **검증 후 다음 단계 진입:** 각 단계의 통합 테스트가 통과된 후에만 다음 단계로 진행한다.

### 7.2 5단계 점진적 도입 계획

| 단계 | 도입 항목 | 시점 | 위험도 | 비고 |
|------|-----------|------|--------|------|
| **1단계** | 순수 Python 3계층 (Phase FSM + PurePythonHookProvider + vLLM) | 즉시 (1-10주) | 낮음 | 기존 보고서 로드맵과 동일 |
| **2단계** | Pydantic AI (구조화 출력 검증 레이어) | Phase 2 (11-14주) | 낮음 | tools 없는 모드, 안전 |
| **3단계** | LlamaIndex (EDA 문서 RAG 파이프라인) | RAG 필요 시 | 낮음 | 핵심 제어와 독립적 |
| **4단계** | DSPy (Phase별 프롬프트 최적화) | 성능 병목 시 | 중간 | 프롬프트 컴파일 시간 필요 |
| **5단계** | Agno 평가 및 교체 결정 | 2026 하반기 | 중간 | HookProvider 인터페이스로 위험 관리 |

### 7.3 단계별 상세 설명

#### 1단계: 순수 Python 3계층 (즉시 시작, 10주)

기존 보고서의 구현 로드맵(Phase 1-5)을 그대로 실행한다. 이 단계의 산출물은 다음과 같다.

- `EDAPhaseController`: 순수 Python FSM
- `PurePythonHookProvider`: HookProvider 인터페이스 구현체
- `workflow_state.json` 스키마 및 원자적 쓰기 구현
- vLLM + lm-format-enforcer 온프레미스 서버
- 전체 EDA 워크플로우 통합 테스트

이 단계가 완료되면 프로덕션 배포 가능한 최소 기능 에이전트(MVP)가 완성된다.

#### 2단계: Pydantic AI 구조화 출력 (11-14주)

합성, 타이밍 분석, DRC 등 각 EDA 도구의 출력 로그를 구조화된 Pydantic 모델로 파싱하는 레이어를 추가한다.

```
EDA 도구 실행 -> 원시 출력 로그 -> Pydantic AI 구조화 검증 -> SynthesisResult/TimingResult/...
```

이 레이어는 PostToolUse 훅 내에서 호출되며, 도구 결과를 타입 안전하게 처리한다. Pydantic AI의 `result_type` 기능이 tools 없는 모드에서 완전히 안전하게 동작한다.

#### 3단계: LlamaIndex RAG (RAG 기능 요구 발생 시)

EDA 설계 규칙 문서, 공정 PDK 문서, 내부 설계 노트를 벡터 데이터베이스에 인덱싱하여 에이전트가 참조할 수 있도록 한다.

```
UserPromptSubmit 훅 -> LlamaIndex 관련 문서 검색 -> 컨텍스트에 추가 -> LLM 호출
```

LlamaIndex의 `llama-index-llms-vllm` 전용 패키지를 사용하여 RAG 검색 엔진도 동일한 온프레미스 vLLM 서버를 활용한다.

#### 4단계: DSPy 프롬프트 최적화 (성능 병목 발생 시)

1단계 배포 후 실제 운영 데이터에서 에이전트 실패율이 높은 Phase를 모니터링한다. 특정 Phase에서 지속적 실패가 관측되면 DSPy를 사용하여 해당 Phase의 프롬프트를 자동 최적화한다.

```
수집된 실패 사례 -> DSPy 최적화 파이프라인 -> 최적화된 Phase 프롬프트 -> 배포
```

DSPy는 오프라인 최적화 도구로, 런타임 에이전트 루프에 직접 통합하지 않는다.

#### 5단계: Agno 평가 (2026 하반기)

2026년 하반기에 Agno의 성숙도(EDA 사례, API 안정성, MPL 2.0 라이선스 검토)를 재평가한다. HookProvider 인터페이스가 설계되어 있으므로, Agno 채택 결정 시 `AgnoHookAdapter`를 구현하여 핵심 로직 변경 없이 교체 가능하다.

### 7.4 전체 로드맵 타임라인

```
주차:   1    5    10   14   18   22   26   30+
        |----|----|----|----|----|----|----|--->
1단계:  [====================] (10주)
        순수 Python 3계층 구현 + 프로덕션 배포

2단계:            [========] (4주)
                  Pydantic AI 구조화 출력 레이어

3단계:                       [.........] (필요 시)
                              LlamaIndex RAG 파이프라인

4단계:                                [.......] (성능 병목 시)
                                       DSPy 프롬프트 최적화

5단계:                                          [평가]
                                                2026 하반기 Agno 재평가

모니터링:         [==================================>] (지속)
                  에이전트 성공률, HOOK 차단 이벤트, 재시도 분포
```

---

## 8. 위험 요소 및 완화 전략

### 8.1 위험 매트릭스

| # | 위험 요소 | 발생 가능성 | 영향도 | 위험 수준 | 완화 전략 |
|---|-----------|------------|--------|-----------|-----------|
| R1 | Agno MPL 2.0 라이선스 위반 | 낮음 | 높음 | 중간 | 5단계 전 법무팀 검토 의무화; 미채택 시 순수 Python 유지 |
| R2 | LlamaIndex/Pydantic AI API 변경 | 중간 | 중간 | 중간 | 버전 고정(requirements.txt); 테스트 커버리지로 회귀 감지 |
| R3 | Sub-10B 모델 + 다중 프레임워크 통합 시 성능 저하 | 중간 | 높음 | 높음 | 각 레이어 독립 성능 테스트; vLLM 배치 최적화 적용 |
| R4 | CrewAI Issue #4036 (tool_calls 포맷 불일치) 재현 | 중간 | 높음 | 높음 | grammar-constrained decoding 병행 적용; 프레임워크 패치 추적 |
| R5 | DSPy 오프라인 최적화 결과가 온라인 성능에 미전이 | 중간 | 중간 | 중간 | 최적화 전후 A/B 테스트; 소규모 배포 후 확장 |
| R6 | LlamaIndex RAG 검색 레이턴시가 EDA 작업 지연 유발 | 중간 | 중간 | 중간 | 비동기 검색; 결과 캐싱; 검색 타임아웃 설정 |
| R7 | 다중 프레임워크 의존성 충돌 (Python 패키지) | 높음 | 중간 | 높음 | 가상 환경 격리; 의존성 감사 자동화; Docker 컨테이너화 |
| R8 | 프레임워크 메인테이너 이탈 또는 유지보수 모드 전환 | 낮음 | 높음 | 중간 | HookProvider 인터페이스로 교체 가능성 보장; 핵심 로직 자체 구현 유지 |

### 8.2 주요 위험 상세 분석

#### R3: 다중 프레임워크 통합 시 성능 저하

ClockCanvas v2에서 LlamaIndex(RAG) + Pydantic AI(검증) + 순수 Python(FSM) + vLLM(LLM)이 동시 운영될 때, 각 컴포넌트의 레이턴시가 합산되면 전체 응답 시간이 허용 수준을 초과할 수 있다.

완화 전략:
- LlamaIndex RAG 검색을 UserPromptSubmit 훅에서 비동기로 실행
- Pydantic AI 검증을 PostToolUse 훅에서 경량 스키마만 적용
- 레이턴시 임계값(예: 5초) 초과 시 비상 경량 모드 전환

#### R7: 다중 프레임워크 의존성 충돌

Python 생태계에서 다중 대형 ML 프레임워크가 공존할 때 패키지 의존성 충돌은 빈번하게 발생한다. 특히 `torch`, `transformers`, `pydantic` 버전이 프레임워크 간에 다른 버전을 요구할 경우 환경 구성이 어려워진다.

완화 전략:
```
레이어별 격리 원칙:
- Core Agent (Layer 1-2): 독립 venv, 최소 의존성
- LlamaIndex RAG: 별도 마이크로서비스 또는 독립 venv
- Pydantic AI: Core와 공유 가능 (경량 의존성)
- DSPy: 오프라인 최적화 전용 환경 (온라인 런타임 미포함)
```

### 8.3 리스크 모니터링 지표

| 지표 | 측정 방법 | 임계값 | 조치 |
|------|-----------|--------|------|
| 에이전트 성공률 | PostToolUse 훅 성공/실패 로그 | <95% | 프레임워크 버그 조사 |
| Hook 차단율 | PreToolUse 차단 이벤트 수 | >10% | Phase 컨트롤러 로직 검토 |
| RAG 검색 레이턴시 | LlamaIndex 응답 시간 분포 | >2초 | 인덱스 최적화 또는 캐싱 |
| Grammar 실패율 | vLLM JSON 파싱 오류 수 | >0% | lm-format-enforcer 설정 점검 |
| 의존성 취약점 | 자동화된 패키지 감사 | 높음/위험 | 즉시 업데이트 |

---

## 결론 요약

본 보고서는 10개 로컬 LLM 호환 Agent SDK/프레임워크를 6개 기준으로 분석하여 다음 결론을 도출하였다.

### 핵심 발견

1. **AutoGen 탈락:** 2025년 10월 유지보수 모드 전환으로 즉시 제외
2. **EDA Phase FSM은 모든 프레임워크에서 자체 구현 필수:** 이 사실이 프레임워크 선택의 실질적 영향을 제한한다
3. **Grammar-Constrained Decoding은 Pydantic AI만 네이티브 지원:** 단, tools와 동시 사용 불가 제약으로 에이전트 메인 프레임워크 역할 불가
4. **Agno의 run_hooks는 기존 보고서 방식 B의 기성품:** 성숙도 부족이 현재 시점 채택의 장벽

### 최종 권고

```
[핵심 제어 레이어] = 자체 구현 (변경 없음)
  - Layer 1: EDAPhaseController (순수 Python FSM)
  - Layer 2: PurePythonHookProvider (HookProvider 인터페이스 기반, 교체 가능)
  - Layer 3: vLLM + lm-format-enforcer (Grammar-Constrained LLM)

[부가 기능 레이어] = 단계적 프레임워크 도입
  - RAG: LlamaIndex + llama-index-llms-vllm (RAG 필요 시)
  - 구조화 출력: Pydantic AI (tools 없는 검증 모드)
  - 프롬프트 최적화: DSPy (성능 병목 발생 시)

[미래 재평가]
  - Agno: 2026 하반기 성숙도 재평가 후 Layer 2 교체 결정
```

기존 보고서의 결론 — Claude Agent SDK + HOOK + 자체 구현 Phase 컨트롤러 — 은 이번 조사를 통해 더욱 강화된다. 10개 프레임워크 중 어느 것도 Phase FSM을 제공하지 않으며, grammar-constrained decoding은 프레임워크 선택과 무관하게 vLLM 레이어에서 해결된다. 프레임워크가 실질적으로 기여할 수 있는 영역은 RAG, 구조화 출력 검증, 프롬프트 최적화이며, 이 세 영역에서 LlamaIndex, Pydantic AI, DSPy가 각각의 역할을 담당한다.

**"처음부터 코딩하지 않는다"는 요구는 부가 기능 레이어에서 충족된다. 핵심 제어 레이어는 어차피 자체 구현이 필수이며, 이것이 ClockCanvas의 가장 중요한 컴포넌트이다.**

---

*본 보고서는 2026-02-24 기준으로 작성되었으며, clockcanvas_agent_architecture_report.md의 후속 조사 문서이다. 5단계 Agno 재평가 시점(2026 하반기)에 본 보고서를 갱신할 것을 권고한다.*
