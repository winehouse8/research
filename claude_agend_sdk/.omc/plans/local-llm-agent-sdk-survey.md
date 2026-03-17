# Work Plan: 로컬/온프레미스 LLM Agent SDK/오픈소스 프레임워크 비교 조사 보고서

**Plan ID:** local-llm-agent-sdk-survey
**Created:** 2026-02-24
**Output:** `/home/jovyan/deephunter-data-volumes/research/claude_agend_sdk/docs/local_llm_agent_sdk_survey_report.md`
**Language:** 한국어

---

## Context

### Original Request
로컬/온프레미스 LLM 위에서 동작하는 Agent SDK 및 오픈소스 프레임워크에 대한 체계적 비교 조사 보고서를 작성한다. 사용자는 "처음부터 코딩하지 않고 기존 구현체 위에서 개발"하길 원하며, "p1" 같은 프레임워크를 언급했다 (PraisonAI 또는 Pydantic AI 가능성).

### Prior Research Summary
기존 보고서 (`docs/clockcanvas_agent_architecture_report.md`)에서 다음이 확인됨:
- **결론:** 훅 패턴 + 순수 Python 미들웨어 (온프레미스 vLLM) 권고
- **Claude Agent SDK:** Anthropic 모델 전용이며, 온프레미스 비-Anthropic 모델 공식 지원 안 함 (GitHub #7178 CLOSED/NOT_PLANNED)
- **LangGraph:** 배제됨 (graph-lock 문제, 성숙도 이슈, 과도한 복잡성)
- **핵심 요구사항:** Sub-10B 온프레미스 모델, Grammar-constrained decoding, Phase-lock 패턴, Hook/미들웨어 아키텍처
- **방식 B (순수 Python 미들웨어):** Claude Agent SDK 없이도 훅 패턴을 직접 구현 가능하다고 결론

### Research Gap
기존 보고서는 Claude Agent SDK + Hook vs LangGraph 두 가지만 비교했다. 그러나 2025-2026년에 등장한 다수의 오픈소스 Agent 프레임워크가 로컬 LLM을 공식 지원하며, 이들 중 일부는 "처음부터 코딩하지 않고" 사용 가능한 수준의 추상화를 제공한다. 이 gap을 메우는 것이 본 조사의 목적이다.

---

## Work Objectives

### Core Objective
ClockCanvas EDA 에이전트에 적합한 로컬/온프레미스 LLM Agent 프레임워크를 식별하고, 변증법적(정반합) 분석을 통해 최종 권고안을 도출한다.

### Deliverables
1. **프레임워크 개별 분석 카드** (최소 8개 프레임워크)
2. **비교 매트릭스** (6개 평가 기준 x N개 프레임워크)
3. **변증법적 분석** (정-반-합 3라운드)
4. **최종 권고 + 구현 방향**
5. **한국어 보고서** (`docs/local_llm_agent_sdk_survey_report.md`)

### Definition of Done
- [ ] 최소 8개 프레임워크가 개별 분석됨
- [ ] 각 프레임워크에 대해 6개 평가 기준이 모두 조사됨
- [ ] 비교 매트릭스가 완성됨
- [ ] 정반합 분석이 최소 2라운드 수행됨
- [ ] 최종 권고안이 ClockCanvas 특수 요구사항에 기반하여 도출됨
- [ ] 보고서가 한국어로 작성되어 docs/에 저장됨
- [ ] 기존 보고서와의 연속성이 확보됨 (상호 참조)

---

## Must Have / Must NOT Have

### Must Have (Guardrails)
- 모든 프레임워크에 대해 **로컬 LLM 지원 여부**를 실증적으로 확인 (공식 문서, GitHub 이슈, 코드 레벨)
- 각 프레임워크의 **최신 버전** 기준 분석 (2025-2026)
- ClockCanvas **특수 요구사항** (Sub-10B, Grammar-constrained decoding, Hook 패턴, 온프레미스) 기반 평가
- **정반합 구조**의 변증법적 분석 포함
- 기존 보고서 결론 (훅 패턴 + 순수 Python 미들웨어)과의 **비교/검증**
- "p1" 후보 (PraisonAI) 반드시 포함

### Must NOT Have
- 클라우드 전용 프레임워크를 주요 후보로 포함하지 않음
- 영어로 작성하지 않음 (한국어 필수)
- 기존 보고서의 결론을 무비판적으로 수용하지 않음 (새로운 프레임워크가 더 나을 수 있음)
- 프레임워크 공식 마케팅 문구만으로 평가하지 않음 (실제 코드/이슈 확인)

---

## Evaluation Criteria (6 Axes)

| # | 평가 기준 | 설명 | 가중치 |
|---|-----------|------|--------|
| 1 | 로컬/온프레미스 LLM 공식 지원 | vLLM, Ollama, llama.cpp 등과의 통합 | 높음 (필수) |
| 2 | Hook/미들웨어 패턴 지원 | PreToolUse/PostToolUse 유사 기능, 도구 호출 가로채기/수정 | 높음 |
| 3 | Sub-10B 모델 호환성 | 작은 모델에서의 안정적 도구 호출, 구조화 출력 | 높음 |
| 4 | Grammar-constrained decoding 통합 | Outlines, XGrammar, lm-format-enforcer 등과의 통합 | 중간 |
| 5 | 프로덕션 성숙도 | API 안정성, 버전 관리, 문서화 수준, 알려진 프로덕션 사례 | 중간 |
| 6 | 커뮤니티/기업 채택 현황 | GitHub stars, 기업 후원, 활발한 개발 현황 | 낮음 |

---

## Target Frameworks (Investigation Order)

### Tier 1: Primary Candidates (로컬 LLM 지원 명시적)

| # | 프레임워크 | 왜 조사하는가 | 조사 우선순위 |
|---|-----------|---------------|--------------|
| 1 | **PraisonAI** | 사용자가 "p1"으로 언급한 후보, 로컬 LLM 지원 주장 | P0 |
| 2 | **Pydantic AI** | "p1" 또 다른 후보, 구조화 출력에 강점, 로컬 모델 지원 | P0 |
| 3 | **Smolagents (HuggingFace)** | HF 생태계, 로컬 모델 네이티브 지원 설계 | P0 |
| 4 | **LlamaIndex (llama-agents)** | 로컬 LLM 중심 생태계, agent orchestration 지원 | P0 |

### Tier 2: Strong Contenders

| # | 프레임워크 | 왜 조사하는가 | 조사 우선순위 |
|---|-----------|---------------|--------------|
| 5 | **OpenAI Agents SDK** | 오픈소스, 비-OpenAI 모델도 지원 가능, 훅 패턴 유사 기능 | P1 |
| 6 | **CrewAI** | 멀티에이전트 오케스트레이션, 로컬 모델 지원 주장 | P1 |
| 7 | **AutoGen (Microsoft)** | 멀티에이전트, 로컬 모델 지원, 기업 후원 | P1 |

### Tier 3: Additional Investigation

| # | 프레임워크 | 왜 조사하는가 | 조사 우선순위 |
|---|-----------|---------------|--------------|
| 8 | **Haystack (deepset)** | 파이프라인 기반, 로컬 모델 통합 | P2 |
| 9 | **LangChain/LangGraph** | 기존 보고서 보완, 최신 변경사항 반영 | P2 |
| 10 | **DSPy** | 프로그래밍 모델이 독특, 최적화 프레임워크 | P2 |
| 11 | **Atomic Agents** | 경량 에이전트 프레임워크, 최소 의존성 | P2 |
| 12 | **기타 2025-2026 신규** | 웹 서치로 발견되는 최신 프레임워크 | P2 |

---

## Task Flow and Dependencies

```
TASK 1: 최신 프레임워크 랜드스케이프 웹 서치
    |
    v
TASK 2-A ~ 2-D: Tier 1 프레임워크 심층 조사 (병렬)
    |
    v
TASK 3-A ~ 3-C: Tier 2 프레임워크 조사 (병렬)
    |
    v
TASK 4-A ~ 4-D: Tier 3 프레임워크 조사 (병렬)
    |
    v
TASK 5: 비교 매트릭스 작성
    |
    v
TASK 6: 변증법적 분석 (정반합)
    |
    v
TASK 7: 최종 권고안 도출
    |
    v
TASK 8: 보고서 작성 및 저장
    |
    v
TASK 9: 보고서 검증 및 교차 참조
```

---

## Detailed TODOs

### TASK 1: 최신 프레임워크 랜드스케이프 웹 서치

**목적:** 2025-2026년 기준 로컬 LLM Agent 프레임워크 전체 지형도 파악

**Web Search Queries:**
```
1. "local LLM agent framework 2025 2026 comparison"
2. "on-premise LLM agent SDK open source"
3. "best agent frameworks for local models 2026"
4. "PraisonAI local LLM agent"
5. "pydantic-ai vs smolagents vs crewai local model 2026"
6. "vLLM compatible agent frameworks"
7. "agent framework tool calling small models sub-10B"
8. "오픈소스 에이전트 프레임워크 로컬 LLM 비교 2025"
```

**Acceptance Criteria:**
- [ ] 최소 10개 프레임워크 목록 확보
- [ ] 각 프레임워크의 GitHub URL, 최신 버전, 로컬 LLM 지원 여부 초기 확인
- [ ] 사용자가 언급한 "p1"의 정체 확인

---

### TASK 2-A: PraisonAI 심층 조사

**목적:** 사용자가 "p1"으로 언급했을 가능성이 높은 프레임워크 심층 분석

**Web Search Queries:**
```
1. "PraisonAI documentation local LLM setup"
2. "PraisonAI vLLM integration"
3. "PraisonAI tool calling hook middleware"
4. "PraisonAI production deployment on-premise"
5. "PraisonAI GitHub issues limitations"
6. site:github.com/MervinPraison/PraisonAI
```

**Investigation Points:**
- [ ] 로컬 LLM 연동 방식 (Ollama? vLLM? litellm?)
- [ ] 도구 호출 메커니즘 (function calling? ReAct?)
- [ ] Hook/미들웨어 패턴 유사 기능 존재 여부
- [ ] Sub-10B 모델에서의 동작 안정성 보고
- [ ] Grammar-constrained decoding 통합 가능성
- [ ] 프로덕션 사례 및 커뮤니티 규모

**Acceptance Criteria:**
- [ ] 6개 평가 기준 모두에 대한 정보 수집
- [ ] ClockCanvas 적합성 초기 판단

---

### TASK 2-B: Pydantic AI 심층 조사

**목적:** 구조화 출력에 강점을 가진 프레임워크의 로컬 LLM 지원 분석

**Web Search Queries:**
```
1. "pydantic-ai local model support vLLM ollama"
2. "pydantic-ai structured output tool calling"
3. "pydantic-ai agent hooks middleware callbacks"
4. "pydantic-ai vs langchain 2026"
5. "pydantic-ai production readiness"
6. site:ai.pydantic.dev documentation
```

**Investigation Points:**
- [ ] 로컬 LLM 백엔드 지원 (OpenAI 호환 API? 직접 통합?)
- [ ] Pydantic 기반 구조화 출력이 Grammar-constrained decoding을 대체/보완 가능한지
- [ ] 에이전트 실행 루프에서의 hook/callback 메커니즘
- [ ] Sub-10B 모델과의 호환성
- [ ] 타입 안전성이 EDA 도메인에 주는 이점
- [ ] 프로덕션 성숙도 및 API 안정성

**Acceptance Criteria:**
- [ ] 6개 평가 기준 모두에 대한 정보 수집
- [ ] Pydantic 기반 구조화 출력의 실질적 이점 분석

---

### TASK 2-C: Smolagents (HuggingFace) 심층 조사

**목적:** HuggingFace 생태계의 경량 에이전트 프레임워크 분석

**Web Search Queries:**
```
1. "smolagents huggingface local model agent"
2. "smolagents tool calling vLLM"
3. "smolagents vs langchain lightweight agent"
4. "smolagents hook middleware callback"
5. "smolagents small model compatibility"
6. site:huggingface.co/docs/smolagents
```

**Investigation Points:**
- [ ] HF Transformers/vLLM과의 네이티브 통합 수준
- [ ] CodeAgent vs ToolCallingAgent 모드 분석
- [ ] 도구 호출 가로채기/수정 메커니즘
- [ ] Sub-10B 모델 최적화 전략
- [ ] Grammar-constrained decoding 통합 (HF generate() 파이프라인)
- [ ] 경량성이 EDA 도메인에 주는 이점/한계

**Acceptance Criteria:**
- [ ] 6개 평가 기준 모두에 대한 정보 수집
- [ ] HF 생태계 통합의 실질적 가치 평가

---

### TASK 2-D: LlamaIndex (llama-agents) 심층 조사

**목적:** 로컬 LLM 중심 생태계의 에이전트 오케스트레이션 분석

**Web Search Queries:**
```
1. "llamaindex llama-agents local LLM orchestration"
2. "llamaindex agent vLLM integration"
3. "llamaindex tool calling hooks callbacks"
4. "llamaindex workflows agent 2025 2026"
5. "llamaindex vs langchain agent comparison"
6. site:docs.llamaindex.ai agent
```

**Investigation Points:**
- [ ] llama-agents vs LlamaIndex Workflows 현재 상태
- [ ] 로컬 LLM 통합 방식 및 수준
- [ ] 도구 호출 인터셉트 메커니즘
- [ ] Sub-10B 모델 지원 경험
- [ ] Grammar-constrained decoding 통합
- [ ] 프로덕션 성숙도

**Acceptance Criteria:**
- [ ] 6개 평가 기준 모두에 대한 정보 수집
- [ ] LlamaIndex Workflows의 현재 성숙도 판단

---

### TASK 3-A: OpenAI Agents SDK 심층 조사

**목적:** OpenAI의 오픈소스 에이전트 SDK가 비-OpenAI 로컬 모델에서 동작하는지 검증

**Web Search Queries:**
```
1. "openai agents SDK non-OpenAI model local LLM"
2. "openai agents SDK vLLM ollama compatible"
3. "openai agents SDK hooks guardrails middleware"
4. "openai agents SDK open source custom provider"
5. site:github.com/openai/openai-agents-python
```

**Investigation Points:**
- [ ] 비-OpenAI 모델 백엔드 지원 방식 (custom provider?)
- [ ] Guardrails 기능이 Hook 패턴과 유사한지
- [ ] Handoff 패턴의 EDA 워크플로우 적용 가능성
- [ ] Sub-10B 모델에서의 tool calling 안정성
- [ ] 오픈소스 라이선스 및 커뮤니티 활성도

**Acceptance Criteria:**
- [ ] 비-OpenAI 모델 지원이 실제로 동작하는지 확인 (코드 레벨)
- [ ] Guardrails/Hook 기능 비교 분석

---

### TASK 3-B: CrewAI 심층 조사

**목적:** 멀티에이전트 오케스트레이션 프레임워크의 로컬 LLM 지원 분석

**Web Search Queries:**
```
1. "CrewAI local LLM ollama vLLM setup"
2. "CrewAI tool calling hook callback"
3. "CrewAI production deployment on-premise"
4. "CrewAI small model compatibility issues"
5. "CrewAI vs autogen vs langgraph 2026"
6. site:docs.crewai.com
```

**Investigation Points:**
- [ ] 로컬 LLM 연동 방식 (litellm 기반?)
- [ ] 에이전트 간 통신 패턴의 EDA 적용 가능성
- [ ] 도구 호출 검증/수정 메커니즘
- [ ] Sub-10B 모델에서의 멀티에이전트 안정성
- [ ] 프로덕션 사례

**Acceptance Criteria:**
- [ ] 6개 평가 기준 모두에 대한 정보 수집

---

### TASK 3-C: AutoGen (Microsoft) 심층 조사

**목적:** Microsoft 후원 멀티에이전트 프레임워크의 로컬 LLM 지원 분석

**Web Search Queries:**
```
1. "AutoGen 0.4 local LLM vLLM ollama"
2. "AutoGen agent tool calling hooks"
3. "AutoGen vs CrewAI vs LangGraph 2026"
4. "AG2 autogen fork comparison"
5. "AutoGen production deployment on-premise"
6. site:microsoft.github.io/autogen
```

**Investigation Points:**
- [ ] AutoGen 0.4 (최신 아키텍처 리팩토링) 상태
- [ ] AG2 포크와의 관계 및 현재 상태
- [ ] 로컬 LLM 통합 방식
- [ ] 도구 호출 인터셉트/검증 메커니즘
- [ ] Sub-10B 모델 호환성
- [ ] 프로덕션 성숙도 (Microsoft 지원 수준)

**Acceptance Criteria:**
- [ ] AutoGen 0.4 vs AG2 현재 상태 명확화
- [ ] 6개 평가 기준 모두에 대한 정보 수집

---

### TASK 4-A: Haystack (deepset) 조사

**Web Search Queries:**
```
1. "Haystack deepset agent local LLM pipeline"
2. "Haystack agent tool calling 2025 2026"
3. site:docs.haystack.deepset.ai agent
```

**Investigation Points:**
- [ ] 파이프라인 기반 아키텍처의 에이전트 기능 성숙도
- [ ] 로컬 LLM 통합 수준
- [ ] 도구 호출 및 Hook 유사 기능

---

### TASK 4-B: LangChain/LangGraph 최신 업데이트 보완 조사

**Web Search Queries:**
```
1. "LangGraph 2026 update local LLM improvements"
2. "LangGraph production issues 2025 2026"
3. "LangChain LCEL agent local model"
```

**Investigation Points:**
- [ ] 기존 보고서 이후 변경 사항
- [ ] 로컬 LLM 지원 개선 여부
- [ ] 기존 보고서 결론의 유효성 재검증

---

### TASK 4-C: DSPy 조사

**Web Search Queries:**
```
1. "DSPy agent tool calling local LLM"
2. "DSPy vs pydantic-ai structured output"
3. "DSPy ReAct module on-premise"
```

**Investigation Points:**
- [ ] DSPy의 프로그래밍 패러다임이 EDA 에이전트에 적합한지
- [ ] 로컬 LLM 최적화 기능 (프롬프트 자동 최적화)
- [ ] 도구 호출 메커니즘

---

### TASK 4-D: 기타 최신 프레임워크 탐색

**Web Search Queries:**
```
1. "new agent framework 2025 2026 open source local LLM"
2. "atomic agents lightweight framework"
3. "ControlFlow prefect agent framework"
4. "Mirascope AI agent framework"
5. "agency-swarm local model"
```

**Investigation Points:**
- [ ] 2025-2026년 새로 등장한 주목할 만한 프레임워크 식별
- [ ] 각각의 로컬 LLM 지원 여부 빠른 확인

---

### TASK 5: 비교 매트릭스 작성

**Depends on:** TASK 1-4 완료

**작업 내용:**
1. 6개 평가 기준 x N개 프레임워크 매트릭스 구성
2. 각 셀에 O/△/X 또는 점수 (1-5) 부여
3. 가중 합산 점수 계산
4. ClockCanvas 특수 요구사항 기반 가중치 적용

**매트릭스 템플릿:**
```
| 프레임워크 | 로컬LLM (필수) | Hook패턴 | Sub-10B | Grammar | 성숙도 | 커뮤니티 | 가중합 |
|-----------|---------------|---------|---------|---------|-------|---------|--------|
| PraisonAI | ?/5           | ?/5     | ?/5     | ?/5     | ?/5   | ?/5     | ?      |
| ...       | ...           | ...     | ...     | ...     | ...   | ...     | ...    |
```

**Acceptance Criteria:**
- [ ] 최소 8개 프레임워크가 매트릭스에 포함
- [ ] 모든 셀에 근거가 있는 점수 부여
- [ ] 상위 3개 후보 식별

---

### TASK 6: 변증법적 분석 (정반합)

**Depends on:** TASK 5 완료

**작업 내용:**

#### Round 1: 상위 후보 정반합
- **정(正):** 매트릭스 상위 3개 프레임워크의 핵심 장점
  - 각 프레임워크가 ClockCanvas에 가져다 주는 고유한 가치
  - "처음부터 코딩하지 않아도 되는" 정도의 추상화 수준
- **반(反):** 상위 3개 프레임워크의 근본적 한계
  - Sub-10B 모델에서의 실질적 문제
  - Hook 패턴 부재/미성숙으로 인한 제어 한계
  - 프레임워크 종속성 리스크
- **합(合):** 1차 종합 권고
  - 어떤 프레임워크가 ClockCanvas 요구사항에 가장 부합하는가
  - 하이브리드 접근 (프레임워크 + 자체 미들웨어)의 가능성

#### Round 2: 기존 결론과의 대비
- **정(正):** 기존 보고서 결론 (순수 Python 미들웨어)의 강점 재확인
- **반(反):** 새로 발견된 프레임워크가 순수 Python 미들웨어보다 나은 점
  - 개발 속도, 커뮤니티 지원, 유지보수 용이성
  - "처음부터 코딩하지 않는다"는 요구사항 충족 여부
- **합(合):** 최종 종합 권고
  - 프레임워크 채택 vs 자체 구현 vs 하이브리드 최종 판단
  - 구체적 구현 경로 제시

**Acceptance Criteria:**
- [ ] 최소 2라운드의 정반합 분석 수행
- [ ] 기존 보고서 결론과의 명시적 비교
- [ ] 최종 권고가 논리적으로 도출됨

---

### TASK 7: 최종 권고안 도출

**Depends on:** TASK 6 완료

**작업 내용:**
1. 변증법적 분석 결과를 기반으로 최종 1-2개 프레임워크 선정
2. 선정된 프레임워크의 구체적 사용 방법 제시
3. ClockCanvas 3계층 아키텍처에서의 위치 명시
4. 기존 보고서의 Layer 2 (Hook 레이어)를 어떤 프레임워크로 구현할지 결정
5. 마이그레이션/도입 전략 (점진적 vs 일괄)

**Acceptance Criteria:**
- [ ] 명확한 "이것을 사용하라" 결론
- [ ] 기존 3계층 아키텍처와의 통합 방안
- [ ] 구체적 시작 코드 또는 설정 예시 포함

---

### TASK 8: 보고서 작성 및 저장

**Depends on:** TASK 7 완료

**Output:** `/home/jovyan/deephunter-data-volumes/research/claude_agend_sdk/docs/local_llm_agent_sdk_survey_report.md`

**보고서 구조:**

```markdown
# 로컬/온프레미스 LLM Agent SDK 오픈소스 프레임워크 비교 조사 보고서

## 목차

## 1. 개요
### 1.1 목적
### 1.2 기존 연구 맥락 (clockcanvas_agent_architecture_report.md 요약)
### 1.3 조사 범위 및 방법론

## 2. 조사 대상 프레임워크 목록
### 2.1 선정 기준
### 2.2 전체 프레임워크 목록 및 분류

## 3. 평가 기준
### 3.1 평가 축 정의 (6개)
### 3.2 ClockCanvas 특수 요구사항 기반 가중치

## 4. 프레임워크 개별 분석
### 4.1 PraisonAI
### 4.2 Pydantic AI
### 4.3 Smolagents (HuggingFace)
### 4.4 LlamaIndex
### 4.5 OpenAI Agents SDK
### 4.6 CrewAI
### 4.7 AutoGen (Microsoft)
### 4.8 Haystack
### 4.9 LangChain/LangGraph (보완 분석)
### 4.10 DSPy
### 4.11 기타 주목할 프레임워크

## 5. 비교 매트릭스
### 5.1 정량 평가표
### 5.2 상위 후보 선별

## 6. 변증법적 분석 (정반합)
### 6.1 Round 1: 상위 후보 정반합
#### 6.1.1 정(正): 주요 장점
#### 6.1.2 반(反): 근본적 한계
#### 6.1.3 합(合): 1차 종합
### 6.2 Round 2: 기존 결론 대비
#### 6.2.1 정(正): 순수 Python 미들웨어의 강점
#### 6.2.2 반(反): 프레임워크 채택의 이점
#### 6.2.3 합(合): 최종 종합

## 7. 최종 권고
### 7.1 권고 프레임워크 및 근거
### 7.2 ClockCanvas 3계층 아키텍처 통합 방안
### 7.3 구현 방향 및 시작점
### 7.4 기존 보고서 결론과의 관계

## 8. 부록
### 8.1 프레임워크별 GitHub 정보
### 8.2 참고 자료 및 출처
```

**Acceptance Criteria:**
- [ ] 위 구조를 따르는 완성된 보고서
- [ ] 한국어로 작성
- [ ] 모든 주장에 출처/근거 포함
- [ ] 코드 예시 포함 (주요 후보의 사용법)
- [ ] docs/ 디렉토리에 저장

---

### TASK 9: 보고서 검증 및 교차 참조

**Depends on:** TASK 8 완료

**작업 내용:**
1. 보고서 내 모든 사실 관계 검증 (프레임워크 버전, 기능 지원 여부)
2. 기존 보고서 (`clockcanvas_agent_architecture_report.md`)와의 일관성 확인
3. 누락된 프레임워크가 없는지 최종 확인
4. 변증법적 분석의 논리적 일관성 검증

**Acceptance Criteria:**
- [ ] 두 보고서 간 상호 참조 링크 포함
- [ ] 사실 관계 오류 없음
- [ ] 최종 권고가 두 보고서 모두의 분석 결과와 일관됨

---

## Commit Strategy

| Commit | 내용 | 시점 |
|--------|------|------|
| 1 | 초안: 프레임워크 개별 분석 카드 완성 | TASK 2-4 완료 후 |
| 2 | 비교 매트릭스 + 변증법 분석 추가 | TASK 5-6 완료 후 |
| 3 | 최종 보고서 완성 | TASK 7-9 완료 후 |

---

## Success Criteria

1. **완전성:** 최소 8개 프레임워크가 6개 평가 기준으로 분석됨
2. **실용성:** "처음부터 코딩하지 않고" 사용 가능한 프레임워크가 명확히 식별됨
3. **논리성:** 정반합 분석이 기존 보고서 결론을 검증하거나 대안을 제시함
4. **구체성:** 최종 권고가 "이 프레임워크를 이렇게 사용하라"는 수준의 구체성을 가짐
5. **연속성:** 기존 보고서와의 맥락적 연결이 자연스러움
6. **최신성:** 2025-2026년 기준 최신 정보 반영

---

## Estimated Effort

| Task Group | 예상 시간 | 비고 |
|-----------|----------|------|
| TASK 1 (랜드스케이프) | 15분 | 웹 서치 기반 |
| TASK 2 (Tier 1 조사) | 40분 | 4개 프레임워크 x 10분 |
| TASK 3 (Tier 2 조사) | 30분 | 3개 프레임워크 x 10분 |
| TASK 4 (Tier 3 조사) | 20분 | 빠른 탐색 |
| TASK 5 (매트릭스) | 15분 | 종합 |
| TASK 6 (정반합) | 20분 | 분석적 사고 |
| TASK 7 (권고안) | 10분 | 결론 도출 |
| TASK 8 (보고서 작성) | 30분 | 문서화 |
| TASK 9 (검증) | 10분 | 교차 확인 |
| **총계** | **~190분** | |

---

## Notes for Executor

- 웹 서치 시 각 프레임워크의 **공식 문서**와 **GitHub 리포지토리**를 반드시 확인할 것
- "로컬 LLM 지원"은 마케팅 문구가 아닌 **실제 코드 레벨**에서 확인할 것
- 기존 보고서의 결론 (훅 패턴 + 순수 Python)이 여전히 최선인지, 아니면 특정 프레임워크가 더 나은지를 **열린 마음으로** 평가할 것
- Sub-10B 모델에서의 실제 동작 여부가 핵심 — 대부분의 프레임워크는 GPT-4/Claude 급 모델을 전제로 설계되었을 가능성이 높음
- Context7 도구를 활용하여 각 프레임워크의 최신 문서를 조회할 것
