# ClockCanvas EDA 에이전트 프레임워크 최종 종합 보고서 2026

**작성일:** 2026-02-27
**작성 목적:** 잇다반도체 ClockCanvas EDA Tool 에이전트 기능 도입을 위한 기술 의사결정 지원
**보고서 유형:** 3개 선행 조사 보고서의 최종 종합 (Final Synthesis)
**대상 독자:** ClockCanvas 개발팀 및 기술 의사결정자

---

## 목차

1. [Executive Summary](#1-executive-summary)
2. [ClockCanvas 에이전트 구현 목표 및 제약](#2-clockcanvas-에이전트-구현-목표-및-제약)
3. [Grammar-Constrained Decoding 기술 해설](#3-grammar-constrained-decoding-기술-해설)
4. [Pi SDK 심층 분석](#4-pi-sdk-심층-분석)
5. [TypeScript 스택 관점의 프레임워크 비교](#5-typescript-스택-관점의-프레임워크-비교)
6. [변증법적 분석: Pi SDK 채택 찬반](#6-변증법적-분석-pi-sdk-채택-찬반)
7. [최종 권고안](#7-최종-권고안)
8. [PoC 가이드: Pi SDK 최소 검증 계획](#8-poc-가이드-pi-sdk-최소-검증-계획)
9. [위험 요소 및 완화 전략](#9-위험-요소-및-완화-전략)
10. [참고 자료](#10-참고-자료)

---

## 1. Executive Summary

### 핵심 결론 3줄 요약

> **Python 스택이라면 LlamaIndex Workflows를 즉시 도입하라.**
> **TypeScript 스택이라면 Pi SDK PoC를 4주간 수행한 후 결정하라.**
> **Grammar-Constrained Decoding은 어떤 프레임워크를 선택하든 vLLM 레이어에서 해결된다.**

### 배경

잇다반도체의 ClockCanvas EDA Tool은 클럭 트리 합성, 타이밍 분석, 레이아웃 최적화를 수행하는 전문 EDA 소프트웨어다. 개발팀은 사용자가 자연어로 EDA 워크플로를 자동화할 수 있는 에이전트 기능을 추가하려 한다. 이 결정은 단순한 기능 추가가 아니다. 반도체 설계 오류는 수천만 원의 재작업 비용을 유발하기 때문에, 에이전트가 잘못된 명령을 실행하거나 EDA Phase 순서를 위반하는 상황은 절대 허용될 수 없다.

### 핵심 기술 제약

본 보고서는 3개의 선행 조사 보고서를 종합하여 다음 제약 조건 하에 최적 프레임워크를 도출한다.

| 제약 조건 | 내용 | 기술적 함의 |
|-----------|------|------------|
| On-premise 전용 | IP 보안, 클라우드 API 금지 | 로컬 LLM 실행 필수 (vLLM 기반) |
| Sub-10B 파라미터 | 서버 규모 제한 | JSON 출력 실패율 38% 문제 존재 |
| EDA Phase 순서 강제 | RTL→합성→타이밍→P&R→검증 | FSM 기반 단계 제어 필수 |
| TypeScript 주력 | ClockCanvas 기존 코드베이스 | Python 전용 프레임워크 부적합 |

### 조사 방법론

총 11개 에이전트 프레임워크를 6개 기준(로컬 LLM 지원, Hook 시스템, Sub-10B 적합성, Grammar 지원, 성숙도, 커뮤니티)으로 평가하였다. 이후 Pi SDK를 추가 심층 분석하고, TypeScript 스택 전제 하에 전체 비교표를 재검토하였다.

---

## 2. ClockCanvas 에이전트 구현 목표 및 제약

### 2.1 구현 목표

ClockCanvas 에이전트는 다음 세 가지 사용자 시나리오를 지원해야 한다.

**시나리오 1: 자연어 EDA 워크플로 실행**
```
사용자: "RTL 파일을 검사하고 타이밍 분석까지 진행해줘"
에이전트: RTL Check 실행 → 합성 실행 → 타이밍 분석 실행 (순서 위반 없이)
```

**시나리오 2: 중간 단계 오류 처리**
```
사용자: "합성 바로 실행해줘"
에이전트: "RTL Check가 완료되지 않았습니다. RTL Check를 먼저 실행하시겠습니까?"
```

**시나리오 3: 결과 해석 및 보고**
```
사용자: "타이밍 슬랙이 왜 음수가 나왔어?"
에이전트: 타이밍 리포트 분석 → 원인 설명 → 수정 방안 제안
```

### 2.2 EDA Phase FSM (유한 상태 기계)

EDA Phase 순서 강제는 에이전트 프레임워크의 도구 호출 위에 추가 레이어로 구현해야 한다. **어떤 프레임워크도 이 기능을 기본 제공하지 않는다.** 이는 3개 보고서 모두 동일하게 도출한 결론이다.

```typescript
// EDA Phase FSM 구현 예시 (TypeScript)
type EDAPhase =
  | 'IDLE'
  | 'RTL_CHECK'
  | 'SYNTHESIS'
  | 'TIMING_ANALYSIS'
  | 'PLACE_AND_ROUTE'
  | 'FINAL_VERIFICATION'
  | 'COMPLETED';

interface EDAStateMachine {
  currentPhase: EDAPhase;
  completedPhases: Set<EDAPhase>;
  allowedTransitions: Map<EDAPhase, EDAPhase[]>;
}

const EDA_TRANSITIONS: Map<EDAPhase, EDAPhase[]> = new Map([
  ['IDLE',              ['RTL_CHECK']],
  ['RTL_CHECK',         ['SYNTHESIS']],
  ['SYNTHESIS',         ['TIMING_ANALYSIS']],
  ['TIMING_ANALYSIS',   ['PLACE_AND_ROUTE']],
  ['PLACE_AND_ROUTE',   ['FINAL_VERIFICATION']],
  ['FINAL_VERIFICATION',['COMPLETED']],
  ['COMPLETED',         []],
]);

function canTransition(
  fsm: EDAStateMachine,
  targetPhase: EDAPhase
): { allowed: boolean; reason?: string } {
  const allowed = fsm.allowedTransitions.get(fsm.currentPhase) ?? [];
  if (allowed.includes(targetPhase)) {
    return { allowed: true };
  }
  return {
    allowed: false,
    reason: `현재 단계(${fsm.currentPhase})에서 ${targetPhase}로 이동할 수 없습니다. ` +
            `허용된 다음 단계: ${allowed.join(', ')}`
  };
}
```

이 FSM은 에이전트의 **PreToolUse 훅** (또는 동등한 메커니즘)에 연결되어, 에이전트가 잘못된 순서로 EDA 도구를 호출하려 할 때 실행을 차단한다.

### 2.3 On-premise 아키텍처 개요

```
┌─────────────────────────────────────────────────────────────┐
│                    ClockCanvas 서버 (On-premise)             │
│                                                             │
│  ┌─────────────────┐    ┌───────────────────────────────┐  │
│  │  ClockCanvas UI  │    │        vLLM 서버               │  │
│  │  (TypeScript)    │    │  - Qwen2.5-7B-Instruct        │  │
│  └────────┬────────┘    │  - Grammar-Constrained Dec.    │  │
│           │              │  - OpenAI 호환 API              │  │
│           ▼              └───────────────┬───────────────┘  │
│  ┌─────────────────┐                    │                   │
│  │  에이전트 레이어  │◄───────────────────┘                   │
│  │  (프레임워크)    │                                        │
│  │  - EDA FSM      │                                        │
│  │  - Tool Guards   │                                        │
│  └────────┬────────┘                                        │
│           │                                                  │
│           ▼                                                  │
│  ┌─────────────────┐                                        │
│  │  EDA 도구 서버   │                                        │
│  │  - RTL Check     │                                        │
│  │  - Synthesis     │                                        │
│  │  - Timing Anal.  │                                        │
│  │  - Place & Route │                                        │
│  └─────────────────┘                                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Grammar-Constrained Decoding 기술 해설

이 섹션은 Grammar-Constrained Decoding을 처음 접하는 독자를 위해 작성되었다.

### 3.1 문제: Sub-10B 모델의 JSON 출력 실패

LLM 기반 에이전트는 도구를 호출할 때 JSON 형식으로 파라미터를 출력해야 한다.

```json
{
  "tool": "run_synthesis",
  "parameters": {
    "rtl_file": "design.v",
    "target_freq_mhz": 500,
    "optimization": "area"
  }
}
```

GPT-4나 Claude 3.5 같은 대형 모델은 이 JSON을 거의 완벽하게 출력한다. 그러나 **Sub-10B 파라미터 모델은 다르다.** ACL 2025 논문의 벤치마크에 따르면, 7B 모델의 JSON 출력 실패율은 **38%**에 달한다. 실패 유형은 다양하다.

```
// 실패 예시 1: 불완전한 JSON
{"tool": "run_synthesis", "parameters": {"rtl_file": "design.v"

// 실패 예시 2: 잘못된 키 이름
{"tool_name": "run_synthesis", "args": {"rtl_file": "design.v"}}

// 실패 예시 3: 타입 오류
{"tool": "run_synthesis", "parameters": {"target_freq_mhz": "500MHz"}}
```

반도체 EDA 환경에서 38% 실패율은 용납할 수 없다. 잘못된 파라미터로 합성이 실행되거나, 타이밍 분석이 오류 데이터를 기반으로 수행되면, 이후 모든 단계가 오염된다.

### 3.2 원리: 토큰 확률 마스킹

LLM은 텍스트를 **토큰** 단위로 생성한다. 각 토큰을 생성할 때, 모델은 어휘 전체에 대한 확률 분포를 계산하고, 그 중 하나를 선택한다.

```
현재 출력: {"tool": "run_
다음 토큰 후보:
  - "synthesis"  → 확률 0.72  ✓
  - "analysis"   → 확률 0.15  ✓
  - 42           → 확률 0.08  ✗ (JSON에서 키 값은 문자열이어야 함)
  - "}"          → 확률 0.05  ✗ (아직 값이 없음)
```

**Grammar-Constrained Decoding**은 이 확률 분포에 개입한다. 현재 생성 중인 JSON의 문법 상태를 추적하고, **문법적으로 불가능한 토큰의 확률을 0으로 강제 설정**한다. 모델이 아무리 엉뚱한 토큰을 선호해도, 문법에 맞는 토큰만 선택될 수 있다.

```
Grammar-Constrained 적용 후:
  - "synthesis"  → 확률 0.72  ✓ (허용)
  - "analysis"   → 확률 0.15  ✓ (허용)
  - 42           → 확률 0.00  ✗ (마스킹됨)
  - "}"          → 확률 0.00  ✗ (마스킹됨)
```

결과: **JSON 출력 실패율 0%** (논리적 보장, 통계적 추정이 아님).

### 3.3 중요한 아키텍처 사실

**Grammar-Constrained Decoding은 vLLM 서버 레이어에서 실행된다.**

이것이 이 보고서 전체에서 가장 중요한 아키텍처적 함의다. 에이전트 클라이언트 프레임워크(Pi SDK, LlamaIndex, LangChain 등)는 이 기능과 무관하다. 클라이언트는 단지 HTTP 요청에 파라미터 하나를 추가하기만 하면 된다.

```bash
# vLLM 서버 시작 (Grammar-Constrained Decoding 활성화)
vllm serve Qwen/Qwen2.5-7B-Instruct \
  --guided-decoding-backend lm-format-enforcer \
  --host 0.0.0.0 \
  --port 8000
```

```typescript
// 클라이언트에서 JSON Schema 강제 (어떤 OpenAI 호환 클라이언트도 동일)
const toolCallSchema = {
  type: "object",
  properties: {
    tool: { type: "string", enum: ["run_rtl_check", "run_synthesis", "run_timing_analysis"] },
    parameters: {
      type: "object",
      properties: {
        rtl_file: { type: "string" },
        target_freq_mhz: { type: "number", minimum: 1, maximum: 5000 },
        optimization: { type: "string", enum: ["area", "speed", "power"] }
      },
      required: ["rtl_file"]
    }
  },
  required: ["tool", "parameters"]
};

const response = await openaiClient.chat.completions.create({
  model: "Qwen2.5-7B-Instruct",
  messages: [...],
  extra_body: {
    guided_json: toolCallSchema  // 이 파라미터가 핵심
  }
});
```

이 구조 덕분에 **프레임워크 선택이 Grammar-Constrained Decoding 기능에 영향을 주지 않는다.** Pi SDK를 쓰든, LangChain.js를 쓰든, 직접 구현하든, vLLM 서버에 `guided_json` 파라미터를 전달하면 동일한 효과를 얻는다.

### 3.4 lm-format-enforcer vs outlines

vLLM의 Grammar-Constrained Decoding 백엔드는 두 가지가 있다.

| 백엔드 | 장점 | 단점 |
|--------|------|------|
| `lm-format-enforcer` | 안정적, 프로덕션 검증 | 일부 복잡한 스키마 제한 |
| `outlines` | 더 유연한 문법 지원 | 설정 복잡도 높음 |

ClockCanvas의 EDA 도구 스키마는 비교적 단순(고정 필드 + 열거형)하므로 `lm-format-enforcer`로 충분하다.

---

## 4. Pi SDK 심층 분석

### 4.1 정체 및 배경

**주의:** Pi SDK는 동명의 여러 프로젝트와 혼동하기 쉽다.

| 프로젝트 | 실제 정체 |
|---------|----------|
| **badlogic/pi-mono** | 본 보고서에서 분석하는 Pi SDK (Mario Zechner 작) |
| Inflection AI의 Pi | 완전히 다른 프로젝트. 대화형 AI 챗봇 서비스. |

**badlogic/pi-mono**는 개인 개발자 Mario Zechner(libgdx 제작자로 유명)가 만든 TypeScript 모노레포 기반 에이전트 SDK다.

```
pi-mono 저장소 현황 (2026-02 기준)
- GitHub Stars: 17,300+
- Contributors: 127명
- 라이선스: MIT
- 주요 언어: TypeScript (96.5%)
- 현재 상태: OSS vacation (Mario Zechner, 2026-03-02 복귀 예정)
```

단일 개발자 주도 프로젝트임에도 17k+ 스타를 보유한 것은 특이한 사례다. 이는 OpenClaw 프로젝트(234k stars)가 Pi SDK에 의존하고 있어 간접적 유지 압력이 작동하기 때문이다.

### 4.2 모노레포 아키텍처

pi-mono는 다음 패키지로 구성된다.

```
pi-mono/
├── packages/
│   ├── pi-ai/              # @mariozechner/pi-ai
│   ├── pi-agent-core/      # @mariozechner/pi-agent-core
│   ├── pi-coding-agent/    # @mariozechner/pi-coding-agent
│   ├── pi-tui/             # @mariozechner/pi-tui
│   ├── pi-pods/            # @mariozechner/pi-pods
│   └── pi-web-ui/          # @mariozechner/pi-web-ui
└── apps/
    └── pi-app/             # 통합 앱
```

**@mariozechner/pi-ai: 멀티 프로바이더 LLM 추상화**

20개 이상의 LLM 프로바이더를 단일 인터페이스로 추상화한다. OpenAI 호환 엔드포인트를 지원하므로 vLLM과 바로 연결 가능하다.

```typescript
import { createProvider } from '@mariozechner/pi-ai';

// vLLM on-premise 연결
const provider = createProvider({
  type: 'openai-compatible',
  baseUrl: 'http://localhost:8000/v1',
  apiKey: 'not-needed',  // on-premise이므로 더미값
  model: 'Qwen2.5-7B-Instruct'
});

// 지원 프로바이더 목록 (일부)
// OpenAI, Anthropic, Google Gemini, Ollama, vLLM,
// Together AI, Groq, Mistral, Cohere, ... 20+
```

**@mariozechner/pi-agent-core: 에이전트 루프 및 도구 호출**

에이전트의 핵심 실행 루프와 TypeBox 기반 도구 스키마 정의를 담당한다.

```typescript
import { createAgentSession } from '@mariozechner/pi-agent-core';
import { Type } from '@sinclair/typebox';

// TypeBox로 도구 스키마 정의
const runSynthesisTool = {
  name: 'run_synthesis',
  description: 'RTL 합성을 실행합니다. RTL Check 완료 후에만 호출 가능합니다.',
  parameters: Type.Object({
    rtl_file: Type.String({ description: 'RTL 파일 경로' }),
    target_freq_mhz: Type.Number({ minimum: 1, maximum: 5000 }),
    optimization: Type.Union([
      Type.Literal('area'),
      Type.Literal('speed'),
      Type.Literal('power')
    ])
  }),
  execute: async (params) => {
    // 실제 EDA 도구 호출
    return await clockcanvasApi.runSynthesis(params);
  }
};

const session = createAgentSession({
  provider,
  tools: [runSynthesisTool, /* ... */],
});
```

### 4.3 Hook/Extension 시스템: 25개 이상 이벤트

Pi SDK의 훅 시스템은 Claude Agent SDK의 3개 훅(PreToolUse/PostToolUse/UserPromptSubmit)보다 훨씬 세밀하다.

**EDA FSM 연동에 관련된 핵심 훅:**

```typescript
import { createAgentSession, AgentHooks } from '@mariozechner/pi-agent-core';

const edaFSM = new EDAStateMachine();

const hooks: AgentHooks = {
  // PreToolUse 동등: 도구 실행 전 차단 가능
  tool_call: async (toolCall) => {
    const phase = mapToolToPhase(toolCall.name);
    if (phase) {
      const result = canTransition(edaFSM, phase);
      if (!result.allowed) {
        // 실행 차단 - 에이전트에게 오류 메시지 반환
        return {
          block: true,
          reason: result.reason
        };
      }
    }
    return { block: false };
  },

  // PostToolUse 동등: 도구 결과 수신 후 FSM 상태 업데이트
  tool_result: async (toolCall, result) => {
    if (result.success) {
      const phase = mapToolToPhase(toolCall.name);
      if (phase) {
        edaFSM.transitionTo(phase);
      }
    }
    return result;  // 결과 수정 가능
  },

  // 메시지 전처리: 시스템 프롬프트에 현재 FSM 상태 주입
  context: async (messages) => {
    const systemMessage = messages.find(m => m.role === 'system');
    if (systemMessage) {
      systemMessage.content += `\n\n현재 EDA 단계: ${edaFSM.currentPhase}\n완료 단계: ${[...edaFSM.completedPhases].join(', ')}`;
    }
    return messages;
  },

  // 세션 시작 시 초기화
  before_agent_start: async () => {
    console.log('ClockCanvas 에이전트 세션 시작');
    edaFSM.reset();
  },

  // 추가 제공 훅 (25개 이상)
  session_start: async (session) => { /* ... */ },
  session_before_compact: async (context) => { /* ... */ },
  after_tool_result: async (result) => { /* ... */ },
  on_error: async (error) => { /* ... */ },
  // ...
};

const session = createAgentSession({
  provider,
  tools: [...],
  hooks,
});
```

### 4.4 On-premise 및 vLLM 지원

Pi SDK는 OpenAI 호환 인터페이스를 통해 vLLM과 연결된다. 커스텀 모델 설정은 `~/.pi/agent/models.json`에 정의한다.

```json
// ~/.pi/agent/models.json
{
  "models": [
    {
      "id": "clockcanvas-local",
      "name": "Qwen2.5-7B-Instruct (ClockCanvas on-premise)",
      "provider": "openai-compatible",
      "baseUrl": "http://localhost:8000/v1",
      "apiKey": "dummy",
      "capabilities": ["tool-calling", "streaming"]
    }
  ],
  "default": "clockcanvas-local"
}
```

**Grammar-Constrained Decoding 연동 (스트림 미들웨어):**

Pi SDK는 `guided_json` 파라미터를 기본 지원하지 않지만, 스트림 미들웨어를 통해 주입할 수 있다. 이는 직접 구현이 필요하다.

```typescript
// Pi SDK 스트림 미들웨어로 guided_json 주입
import { createStreamMiddleware } from '@mariozechner/pi-ai';

const grammarMiddleware = createStreamMiddleware({
  name: 'grammar-constrained-decoding',
  transformRequest: (request) => {
    // 도구 호출 요청에 guided_json 추가
    if (request.tools && request.tools.length > 0) {
      const toolCallSchema = buildToolCallSchema(request.tools);
      return {
        ...request,
        extra_body: {
          ...request.extra_body,
          guided_json: toolCallSchema
        }
      };
    }
    return request;
  }
});

const provider = createProvider({
  type: 'openai-compatible',
  baseUrl: 'http://localhost:8000/v1',
  model: 'Qwen2.5-7B-Instruct',
  middleware: [grammarMiddleware]  // 미들웨어 등록
});
```

### 4.5 SDK 임베딩 모드

Pi SDK는 CLI 도구로 사용할 수도 있지만, `createAgentSession()` API를 통해 기존 Node.js/TypeScript 애플리케이션에 직접 임베딩할 수 있다.

```typescript
// ClockCanvas 기존 TypeScript 서버에 직접 임베딩
import { createAgentSession } from '@mariozechner/pi-agent-core';
import { ClockCanvasAPIClient } from './clockcanvas-api';

export class ClockCanvasAgentService {
  private session: AgentSession;
  private api: ClockCanvasAPIClient;

  constructor(api: ClockCanvasAPIClient) {
    this.api = api;
    this.session = createAgentSession({
      provider: createLocalVLLMProvider(),
      tools: this.buildEDATools(),
      hooks: this.buildEDAHooks(),
      systemPrompt: `당신은 ClockCanvas EDA Tool의 AI 어시스턴트입니다.
        EDA 작업은 반드시 RTL Check → Synthesis → Timing Analysis → Place & Route → Final Verification
        순서로 수행해야 합니다. 순서를 건너뛰는 요청은 거절하십시오.`
    });
  }

  async processUserRequest(userMessage: string): Promise<AgentResponse> {
    return await this.session.run(userMessage);
  }

  private buildEDATools() {
    return [
      this.createRTLCheckTool(),
      this.createSynthesisTool(),
      this.createTimingAnalysisTool(),
      this.createPlaceAndRouteTool(),
      this.createFinalVerificationTool(),
    ];
  }
}
```

### 4.6 OpenClaw와의 관계

OpenClaw는 Peter Steinberger가 개발한 멀티플랫폼 에이전트 게이트웨이로, WhatsApp, Telegram, Discord 등 다양한 채널로 AI 에이전트를 배포할 수 있다. **234,000개 GitHub 스타**를 보유한 대형 프로젝트다.

OpenClaw는 Pi SDK를 핵심 에이전트 실행 레이어로 사용한다. 이 의존 관계는 Pi SDK 유지보수에 간접적 강제 요인으로 작용한다. Mario Zechner가 Pi SDK를 방치하면 OpenClaw도 영향을 받기 때문에, OpenClaw 커뮤니티가 Pi SDK 지속성에 대한 압력을 제공한다.

그러나 이 관계는 **위험 요소이기도 하다.** OpenClaw가 Pi SDK를 포크하거나 다른 내부 레이어로 교체한다면, Pi SDK의 유지 압력은 사라진다.

---

## 5. TypeScript 스택 관점의 프레임워크 비교

### 5.1 Python vs TypeScript: 전혀 다른 생태계

기존 에이전트 프레임워크 비교표는 **Python 스택을 전제로 작성되었다.** ClockCanvas가 TypeScript 중심이라면 이 전제가 무너진다.

**Python 프레임워크의 TypeScript 호환성:**

| 프레임워크 | TypeScript 지원 | 수준 |
|-----------|----------------|------|
| LlamaIndex | LlamaIndex.TS (별도 패키지) | Python 버전 대비 기능 60-70% |
| Pydantic AI | Python 전용 | TypeScript 클라이언트 없음 |
| CrewAI | Python 전용 | REST API 래퍼 필요 |
| Agno | Python 전용 | 미지원 |
| Haystack | Python 전용 | 미지원 |
| DSPy | Python 전용 | 미지원 |

Python 프레임워크를 TypeScript 프로젝트에서 사용하려면 일반적으로 두 가지 방법을 취한다.
1. **별도 Python 마이크로서비스**: 에이전트 로직을 Python으로 구현하고 REST API로 노출
2. **TypeScript 래퍼**: Python 라이브러리를 HTTP로 호출하는 얇은 TypeScript 레이어

두 방법 모두 운영 복잡도가 증가하고, 두 언어 스택을 유지해야 하는 부담이 생긴다.

### 5.2 TypeScript 네이티브 선택지 비교

| 선택지 | 유지보수 주체 | 성숙도 | EDA 적합성 | On-premise | Grammar |
|--------|-------------|--------|-----------|-----------|---------|
| **Pi SDK** | 단일 개발자 (Mario Zechner) | 낮음 | 조건부 | 가능 | 미들웨어 구현 필요 |
| **LangChain.js** | LangChain Inc. (기업) | 중간 | 가능 | 가능 | 미들웨어 구현 필요 |
| **Vercel AI SDK** | Vercel (기업) | 높음 | 부적합 | 제한적 | 미지원 |
| **직접 구현** | 개발팀 | 해당 없음 | 완전 자유 | 완전 자유 | 완전 자유 |

**Vercel AI SDK 제외 근거:**

Vercel AI SDK는 Next.js 웹 애플리케이션의 스트리밍 채팅 UI에 최적화되어 있다. 복잡한 도구 호출 체인, FSM 기반 상태 관리, on-premise LLM 연동에는 부적합하다. ClockCanvas EDA 에이전트는 스트리밍 UI 챗봇이 아니라 복잡한 워크플로 자동화 시스템이다.

### 5.3 LangChain.js 심층 평가

**장점:**
- LangChain Inc.의 기업 지원 (Python 버전과 함께 유지)
- 안정적인 릴리즈 주기
- 광범위한 커뮤니티와 예제

**단점:**
- Python LangChain 대비 기능 격차 존재 (일부 고급 기능 미구현)
- 훅 시스템이 Pi SDK만큼 세밀하지 않음
- CallbackHandler 패턴이 Pi SDK의 이벤트 시스템보다 불편

```typescript
// LangChain.js EDA 도구 구현 예시
import { DynamicStructuredTool } from "@langchain/core/tools";
import { z } from "zod";
import { ChatOpenAI } from "@langchain/openai";
import { AgentExecutor, createToolCallingAgent } from "langchain/agents";
import { ChatPromptTemplate } from "@langchain/core/prompts";

// vLLM에 연결
const llm = new ChatOpenAI({
  openAIApiKey: "dummy",
  configuration: {
    baseURL: "http://localhost:8000/v1",
  },
  modelName: "Qwen2.5-7B-Instruct",
});

// EDA 도구 정의
const synthesisTool = new DynamicStructuredTool({
  name: "run_synthesis",
  description: "RTL 합성을 실행합니다",
  schema: z.object({
    rtl_file: z.string(),
    target_freq_mhz: z.number().min(1).max(5000),
    optimization: z.enum(["area", "speed", "power"]),
  }),
  func: async ({ rtl_file, target_freq_mhz, optimization }) => {
    // EDA FSM 검사
    const check = canTransition(edaFSM, 'SYNTHESIS');
    if (!check.allowed) {
      return `오류: ${check.reason}`;
    }
    return await runSynthesis(rtl_file, target_freq_mhz, optimization);
  },
});

// CallbackHandler로 훅 구현 (Pi SDK보다 덜 세밀)
import { BaseCallbackHandler } from "@langchain/core/callbacks/base";

class EDACallbackHandler extends BaseCallbackHandler {
  name = "EDACallbackHandler";

  async handleToolStart(tool: any, input: string) {
    console.log(`도구 시작: ${tool.name}`);
  }

  async handleToolEnd(output: string) {
    console.log(`도구 완료: ${output}`);
  }

  async handleToolError(err: Error) {
    console.error(`도구 오류: ${err.message}`);
  }
}
```

**LangChain.js의 FSM 통합 한계:** LangChain.js의 콜백 핸들러는 도구 실행을 **차단할 수 없다.** `handleToolStart`에서 오류를 던지면 실행이 중단되지만, 에이전트에게 "이 단계는 아직 안 됩니다"라는 구조화된 메시지를 돌려주기 어렵다. Pi SDK의 `tool_call` 훅은 `{ block: true, reason: "..." }`를 반환하여 깔끔하게 처리한다.

### 5.4 직접 구현 (Custom Agent Loop) 평가

EDA 에이전트의 요구사항이 매우 특수하기 때문에, 직접 구현을 진지하게 고려해야 한다.

**직접 구현의 핵심 장점:**
- 외부 프레임워크 의존성 제거
- EDA FSM을 에이전트 루프에 1급 시민으로 통합
- Grammar-Constrained Decoding을 원하는 방식으로 완전 제어
- 장기적 유지보수 부담이 팀에만 귀속됨

**직접 구현 기본 골격:**

```typescript
// ClockCanvas 커스텀 에이전트 루프
interface AgentMessage {
  role: 'system' | 'user' | 'assistant' | 'tool';
  content: string;
  tool_call_id?: string;
  tool_calls?: ToolCall[];
}

interface ToolCall {
  id: string;
  type: 'function';
  function: {
    name: string;
    arguments: string;
  };
}

class ClockCanvasAgent {
  private messages: AgentMessage[] = [];
  private fsm: EDAStateMachine;
  private tools: Map<string, EDAToolDefinition>;
  private vllmClient: OpenAI;

  constructor(config: AgentConfig) {
    this.vllmClient = new OpenAI({
      baseURL: config.vllmBaseUrl,
      apiKey: 'dummy',
    });
    this.fsm = new EDAStateMachine();
    this.tools = buildEDAToolMap();
  }

  async run(userMessage: string): Promise<string> {
    this.messages.push({ role: 'user', content: userMessage });

    // ReAct 루프
    while (true) {
      // 1. LLM 호출 (Grammar-Constrained Decoding 포함)
      const response = await this.callLLM();

      // 2. 응답 파싱
      if (!response.tool_calls || response.tool_calls.length === 0) {
        // 최종 답변 반환
        return response.content;
      }

      // 3. 도구 호출 처리
      this.messages.push({
        role: 'assistant',
        content: response.content ?? '',
        tool_calls: response.tool_calls
      });

      for (const toolCall of response.tool_calls) {
        const result = await this.executeToolCall(toolCall);
        this.messages.push({
          role: 'tool',
          content: JSON.stringify(result),
          tool_call_id: toolCall.id
        });
      }
    }
  }

  private async callLLM(): Promise<LLMResponse> {
    // Grammar-Constrained Decoding은 vLLM 레이어에서 자동 처리
    return await this.vllmClient.chat.completions.create({
      model: 'Qwen2.5-7B-Instruct',
      messages: this.messages,
      tools: this.buildOpenAIToolSpec(),
      // @ts-ignore: vLLM 확장 파라미터
      guided_json: this.buildToolCallSchema(),
    } as any);
  }

  private async executeToolCall(toolCall: ToolCall): Promise<ToolResult> {
    const toolName = toolCall.function.name;
    const params = JSON.parse(toolCall.function.arguments);

    // FSM 검사 (PreToolUse 동등)
    const requiredPhase = mapToolToPhase(toolName);
    if (requiredPhase) {
      const check = canTransition(this.fsm, requiredPhase);
      if (!check.allowed) {
        return { success: false, error: check.reason };
      }
    }

    // 도구 실행
    const tool = this.tools.get(toolName);
    if (!tool) {
      return { success: false, error: `알 수 없는 도구: ${toolName}` };
    }

    const result = await tool.execute(params);

    // FSM 상태 업데이트 (PostToolUse 동등)
    if (result.success && requiredPhase) {
      this.fsm.transitionTo(requiredPhase);
    }

    return result;
  }
}
```

직접 구현의 **위험:** 에이전트 루프의 엣지 케이스(무한 루프 방지, 컨텍스트 윈도우 관리, 오류 복구)를 모두 직접 처리해야 한다. 이는 상당한 엔지니어링 투자를 요구한다.

---

## 6. 변증법적 분석: Pi SDK 채택 찬반

### 6.1 찬성 논거 (Pro Pi SDK)

**논거 1: TypeScript 스택의 완벽한 정합성**

ClockCanvas가 TypeScript 중심이라면, Pi SDK는 언어 장벽 없이 기존 코드베이스에 자연스럽게 통합된다. Python 프레임워크를 도입할 경우 두 언어 스택을 유지해야 하지만, Pi SDK는 이 부담을 완전히 제거한다.

**논거 2: 가장 세밀한 훅 시스템**

Pi SDK의 25개 이상 이벤트 훅은 EDA FSM 통합에 이상적이다. 특히 `tool_call` 훅의 `{ block: true, reason: "..." }` 반환 패턴은 EDA Phase 위반 차단을 깔끔하게 구현한다. LangChain.js의 콜백 핸들러보다 훨씬 명확한 의미론을 제공한다.

**논거 3: SDK 임베딩 모드의 유연성**

`createAgentSession()` API로 ClockCanvas 기존 서버에 직접 임베딩할 수 있다. 별도 에이전트 서버를 운영할 필요가 없어 인프라 복잡도가 낮아진다.

**논거 4: OpenClaw 의존으로 인한 간접 유지 압력**

234k stars의 OpenClaw가 Pi SDK에 의존하므로, Mario Zechner가 단순히 프로젝트를 방치하기 어렵다. 완전한 단일 개발자 리스크보다는 안전하다.

**논거 5: MIT 라이선스**

MIT 라이선스는 상업 제품(ClockCanvas)에 제약 없이 사용 가능하다. 포크나 수정도 자유롭다.

### 6.2 반대 논거 (Anti Pi SDK)

**논거 1: Sub-10B 모델 검증 부재**

Pi SDK 개발자 문서에 "self-hosted models usually don't work well"이라는 경고가 있다. OpenClaw 사용 사례를 분석하면 주로 GPT-4, Claude 3.5 같은 대형 클라우드 모델을 사용한다. Sub-10B 모델 + Pi SDK + on-premise 조합을 프로덕션에서 검증한 사례가 없다.

**논거 2: 단일 개발자 의존 리스크**

Mario Zechner가 Pi SDK를 방치하거나, OpenClaw가 내부 레이어를 교체하면 Pi SDK는 고아 프로젝트가 된다. 기업용 EDA 도구에서 이런 의존성은 심각한 위험이다.

**논거 3: Grammar-Constrained Decoding 미지원**

`guided_json` 파라미터는 Pi SDK가 기본 지원하지 않는다. 스트림 미들웨어로 구현할 수 있지만, 이는 Pi SDK 내부 구조에 의존하는 커스텀 코드를 유지해야 함을 의미한다. Pi SDK 업데이트 시 호환성이 깨질 수 있다.

**논거 4: 커뮤니티 기반 취약**

17k stars는 인상적이지만, 이 중 상당수는 OpenClaw 사용자가 유입된 것이다. Pi SDK 자체에 기여하거나 이슈를 해결하는 활성 커뮤니티는 제한적이다.

**논거 5: 문서화 수준**

단일 개발자 프로젝트 특성상 문서화가 불완전하다. EDA처럼 신뢰성이 중요한 도메인에서 문서화 부족은 통합 과정에서 예상치 못한 동작을 초래할 수 있다.

### 6.3 찬반 종합

| 차원 | Pi SDK 유리 | Pi SDK 불리 |
|------|------------|------------|
| 언어 정합성 | TypeScript 완벽 지원 | - |
| 훅 시스템 | 25개+, block 패턴 | - |
| 유지보수 | OpenClaw 간접 압력 | 단일 개발자 |
| Sub-10B 검증 | - | 검증 사례 없음 |
| Grammar 지원 | 미들웨어 구현 가능 | 기본 미지원 |
| 리스크 허용 | PoC에서 수용 가능 | 프로덕션에서 위험 |

**결론:** Pi SDK는 TypeScript 스택 환경에서 가장 매력적인 선택지이지만, Sub-10B 모델 환경에서 검증되지 않은 것이 결정적 약점이다. **PoC 없이 프로덕션 도입은 권장하지 않는다.**

---

## 7. 최종 권고안

### 7.1 시나리오 A: Python 스택이라면

**1순위 권고: LlamaIndex Workflows (Python)**

LlamaIndex는 에이전트 프레임워크 평가에서 25/30점으로 1위를 기록했다. Sub-10B 모델 지원, 세밀한 훅 시스템, 성숙한 커뮤니티를 모두 갖추고 있다.

```python
# LlamaIndex Workflows로 EDA 에이전트 구현
from llama_index.core.workflow import Workflow, step, Event
from llama_index.llms.openai import OpenAI  # vLLM과 호환

class EDAWorkflow(Workflow):
    def __init__(self):
        super().__init__()
        self.fsm = EDAStateMachine()
        self.llm = OpenAI(
            base_url="http://localhost:8000/v1",
            api_key="dummy",
            model="Qwen2.5-7B-Instruct"
        )

    @step
    async def process_request(self, ev: StartEvent) -> EDAEvent:
        # 에이전트 루프 실행
        response = await self.llm.achat(ev.messages)
        return EDAEvent(response=response)

    @step
    async def execute_eda_tool(self, ev: EDAEvent) -> StopEvent:
        # FSM 검사 후 도구 실행
        phase = map_tool_to_phase(ev.tool_call)
        if not self.fsm.can_transition(phase):
            return StopEvent(result=f"순서 위반: {self.fsm.get_error_message(phase)}")

        result = await self.execute_tool(ev.tool_call)
        self.fsm.transition(phase)
        return StopEvent(result=result)
```

**Python 스택 아키텍처 권고:**

```
ClockCanvas TypeScript Frontend
        │ REST API
        ▼
Python Agent Service (LlamaIndex)
        │ OpenAI 호환 API
        ▼
vLLM Server (Qwen2.5-7B-Instruct)
  + Grammar-Constrained Decoding
```

### 7.2 시나리오 B: TypeScript 스택이라면

**단계적 접근 권고:**

**Phase 1 (0~4주): Pi SDK PoC**
- Pi SDK + Qwen2.5-7B-Instruct + vLLM 조합 검증
- EDA FSM 훅 통합 가능성 확인
- Grammar-Constrained Decoding 미들웨어 구현 및 테스트
- 성공 기준: 5개 EDA Phase 도구 호출 정확도 95% 이상

**Phase 2 결정 분기 (4주 후):**

```
PoC 성공 (도구 호출 정확도 ≥ 95%)
    └→ Pi SDK 프로덕션 도입 검토
         단, OpenClaw 의존도 모니터링 필수
         프로젝트 포크 준비 (contingency)

PoC 실패 (도구 호출 정확도 < 95%)
    └→ 옵션 1: LangChain.js 재평가
         (기업 지원, TypeScript 네이티브, 기능 제한 감수)
    └→ 옵션 2: 직접 구현
         (완전 제어, 상당한 엔지니어링 투자 필요)
```

**TypeScript 스택 최종 권고 매트릭스:**

| 상황 | 권고 | 이유 |
|------|------|------|
| PoC 성공 + 팀 위험 수용 | Pi SDK | 최상의 훅 시스템, TypeScript 네이티브 |
| PoC 성공 + 팀 위험 회피 | 직접 구현 (Pi SDK 참고) | Pi SDK 코드 학습 후 핵심만 직접 구현 |
| PoC 실패 | LangChain.js | 기업 지원, 안정성 |
| 개발 자원 풍부 | 직접 구현 | 최대 제어, 의존성 제거 |

---

## 8. PoC 가이드: Pi SDK 최소 검증 계획

### 8.1 PoC 목적

Pi SDK를 ClockCanvas의 실제 환경(Sub-10B 모델, on-premise vLLM)에서 검증한다. PoC는 4주 이내에 완료되어야 하며, 명확한 성공/실패 기준이 있어야 한다.

### 8.2 PoC 환경 준비

**사전 요구사항:**
- NVIDIA GPU 서버 (최소 16GB VRAM, A100/A6000 권장)
- Docker 및 NVIDIA Container Toolkit 설치
- Node.js 20+, pnpm 8+

**1단계: vLLM 서버 설치 및 실행**

```bash
# vLLM 서버 시작 (Grammar-Constrained Decoding 활성화)
docker run --gpus all \
  -p 8000:8000 \
  --ipc=host \
  vllm/vllm-openai:latest \
  --model Qwen/Qwen2.5-7B-Instruct \
  --guided-decoding-backend lm-format-enforcer \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.85

# 서버 상태 확인
curl http://localhost:8000/health
```

**2단계: Pi SDK 설치**

```bash
# pi-mono 클론
git clone https://github.com/badlogic/pi-mono.git
cd pi-mono

# 의존성 설치
pnpm install

# ClockCanvas PoC 프로젝트 생성
mkdir -p poc/clockcanvas-agent
cd poc/clockcanvas-agent
pnpm init
pnpm add @mariozechner/pi-agent-core @mariozechner/pi-ai
```

### 8.3 PoC 테스트 케이스

**테스트 케이스 설계 원칙:**
- 각 테스트는 독립 실행 가능해야 한다
- 성공/실패가 자동 판정되어야 한다
- 실제 EDA 시나리오를 반영해야 한다

**테스트 케이스 1: 정상 순서 실행**

```typescript
// poc/clockcanvas-agent/tests/test-normal-flow.ts
import { createTestAgent } from './test-utils';

async function testNormalFlow() {
  const agent = createTestAgent();
  const toolCallLog: string[] = [];

  // 에이전트에 요청
  const response = await agent.run(
    "design.v 파일에 대해 RTL 검사부터 타이밍 분석까지 진행해줘"
  );

  // 검증
  console.assert(
    toolCallLog[0] === 'run_rtl_check',
    `첫 번째 호출이 run_rtl_check이어야 함. 실제: ${toolCallLog[0]}`
  );
  console.assert(
    toolCallLog[1] === 'run_synthesis',
    `두 번째 호출이 run_synthesis이어야 함. 실제: ${toolCallLog[1]}`
  );
  console.assert(
    toolCallLog[2] === 'run_timing_analysis',
    `세 번째 호출이 run_timing_analysis이어야 함. 실제: ${toolCallLog[2]}`
  );

  console.log('테스트 1 (정상 순서): PASS');
}
```

**테스트 케이스 2: 순서 위반 차단**

```typescript
// poc/clockcanvas-agent/tests/test-phase-guard.ts
async function testPhaseGuard() {
  const agent = createTestAgent();

  // RTL Check 없이 합성 요청
  const response = await agent.run("바로 합성 실행해줘");

  // 에이전트가 거절하고 RTL Check를 먼저 하도록 안내해야 함
  console.assert(
    response.includes('RTL') || response.includes('순서') || response.includes('먼저'),
    `에이전트가 순서 위반을 감지하고 거절해야 함. 실제 응답: ${response}`
  );

  // 실제로 합성 도구가 호출되지 않았는지 확인
  const synthesisWasCalled = agent.getToolCallLog().includes('run_synthesis');
  console.assert(!synthesisWasCalled, 'run_synthesis가 호출되면 안 됨');

  console.log('테스트 2 (순서 위반 차단): PASS');
}
```

**테스트 케이스 3: JSON 출력 형식 정확도 (Grammar-Constrained Decoding 검증)**

```typescript
// poc/clockcanvas-agent/tests/test-grammar-constrained.ts
async function testGrammarConstrainedDecoding() {
  const ITERATIONS = 50;
  let successCount = 0;

  for (let i = 0; i < ITERATIONS; i++) {
    try {
      const response = await agent.run(`RTL 검사 실행해줘 (반복 ${i + 1})`);
      // JSON 파싱 오류 없이 성공하면 카운트
      successCount++;
    } catch (error) {
      console.error(`반복 ${i + 1} 실패: ${error.message}`);
    }
  }

  const successRate = (successCount / ITERATIONS) * 100;
  console.log(`도구 호출 성공률: ${successRate}% (${successCount}/${ITERATIONS})`);

  console.assert(
    successRate >= 95,
    `성공률이 95% 미만: ${successRate}%. Grammar-Constrained Decoding 설정 확인 필요`
  );

  console.log('테스트 3 (Grammar-Constrained Decoding): PASS');
}
```

**테스트 케이스 4: FSM 상태 지속성**

```typescript
// poc/clockcanvas-agent/tests/test-fsm-persistence.ts
async function testFSMPersistence() {
  const agent = createTestAgent();

  // 1. RTL Check 완료
  await agent.run("RTL 검사 실행해줘");
  console.assert(agent.getFSMState() === 'RTL_CHECK', 'RTL_CHECK 상태이어야 함');

  // 2. 합성 실행 (RTL Check 완료 후이므로 허용)
  await agent.run("합성 실행해줘");
  console.assert(agent.getFSMState() === 'SYNTHESIS', 'SYNTHESIS 상태이어야 함');

  // 3. RTL Check 재실행 시도 (퇴행 방지)
  const response = await agent.run("RTL 검사 다시 해줘");
  console.assert(
    agent.getFSMState() === 'SYNTHESIS',  // 상태가 바뀌면 안 됨
    'FSM 상태가 퇴행하면 안 됨'
  );

  console.log('테스트 4 (FSM 상태 지속성): PASS');
}
```

**테스트 케이스 5: 성능 벤치마크**

```typescript
// poc/clockcanvas-agent/tests/test-performance.ts
async function testPerformance() {
  const LATENCY_TARGET_MS = 30000;  // 30초 (Sub-10B 모델 허용치)

  const startTime = Date.now();
  await agent.run("RTL 검사 실행하고 결과 요약해줘");
  const latency = Date.now() - startTime;

  console.log(`응답 지연: ${latency}ms`);
  console.assert(
    latency <= LATENCY_TARGET_MS,
    `응답 지연이 목표치 초과: ${latency}ms > ${LATENCY_TARGET_MS}ms`
  );

  console.log('테스트 5 (성능): PASS');
}
```

### 8.4 PoC 성공 기준

| 기준 | 목표값 | 측정 방법 |
|------|--------|----------|
| 도구 호출 형식 정확도 | ≥ 95% | 50회 반복 테스트 |
| EDA 순서 준수율 | 100% | 순서 위반 시나리오 10회 |
| 순서 위반 차단율 | 100% | 잘못된 순서 요청 10회 |
| 평균 응답 지연 | ≤ 30초 | 단순 도구 호출 기준 |
| 크래시/오류 없음 | 100% | 100회 연속 실행 |

**판정 기준:**
- 모든 기준 통과 → Pi SDK 프로덕션 도입 검토 진행
- 1개 이상 기준 미달 → LangChain.js 또는 직접 구현으로 전환

### 8.5 PoC 일정

```
Week 1: 환경 구축 및 기본 연동
  - vLLM 서버 설치 및 Qwen2.5-7B-Instruct 로드
  - Pi SDK 설치 및 기본 에이전트 실행 확인
  - Grammar-Constrained Decoding 미들웨어 구현

Week 2: EDA 도구 및 FSM 구현
  - 5개 EDA Phase 도구 stub 구현
  - EDA FSM 구현
  - Pi SDK 훅에 FSM 연동

Week 3: 테스트 케이스 실행
  - 5개 테스트 케이스 실행
  - 실패 케이스 디버깅 및 재시도
  - 성능 측정

Week 4: 결과 분석 및 의사결정
  - PoC 결과 정리
  - 성공/실패 판정
  - 다음 단계 결정 및 보고
```

---

## 9. 위험 요소 및 완화 전략

### 9.1 위험 요소 목록

**R1: Pi SDK 단일 개발자 의존**

| 항목 | 내용 |
|------|------|
| 심각도 | 높음 |
| 발생 가능성 | 중간 |
| 시나리오 | Mario Zechner가 프로젝트 방치, 또는 OpenClaw가 Pi를 교체 |
| 영향 | ClockCanvas 에이전트 코어가 유지보수 불가 상태 |

**완화 전략:**
1. **포크 준비**: pi-agent-core를 ClockCanvas 저장소에 포크하여 즉시 유지 가능 상태 유지
2. **추상화 레이어**: ClockCanvas 코드가 Pi SDK API에 직접 의존하지 않도록 어댑터 레이어 구현
3. **정기 모니터링**: pi-mono 저장소의 활동(커밋, 이슈, PR)을 월별 모니터링

```typescript
// 추상화 레이어 예시: ClockCanvas는 이 인터페이스만 사용
interface AgentFramework {
  createSession(config: SessionConfig): AgentSession;
}

interface AgentSession {
  run(userMessage: string): Promise<string>;
  getState(): SessionState;
  reset(): void;
}

// Pi SDK 어댑터
class PiSDKAdapter implements AgentFramework {
  createSession(config: SessionConfig): AgentSession {
    return new PiSDKSessionAdapter(config);
  }
}

// 나중에 Pi SDK 교체 시 어댑터만 변경
class LangChainAdapter implements AgentFramework {
  createSession(config: SessionConfig): AgentSession {
    return new LangChainSessionAdapter(config);
  }
}
```

**R2: Sub-10B 모델 도구 호출 품질**

| 항목 | 내용 |
|------|------|
| 심각도 | 매우 높음 |
| 발생 가능성 | 중간 |
| 시나리오 | Grammar-Constrained Decoding에도 불구하고 파라미터 값이 의미론적으로 잘못됨 |
| 영향 | 잘못된 파라미터로 EDA 도구 실행 → 합성 오류 또는 레이아웃 불량 |

**완화 전략:**
1. **파라미터 범위 검증**: 도구 실행 전 파라미터 값의 의미론적 유효성 검사
2. **확인 단계 추가**: 중요 도구 실행 전 사용자 확인 요구 (특히 P&R, Final Verification)
3. **샌드박스 실행**: 실제 EDA 파일에 접근하기 전 시뮬레이션 모드 실행

```typescript
// 도구 실행 전 파라미터 의미론 검증
async function validateSynthesisParams(params: SynthesisParams): Promise<ValidationResult> {
  const errors: string[] = [];

  // RTL 파일 존재 확인
  if (!await fileExists(params.rtl_file)) {
    errors.push(`RTL 파일을 찾을 수 없음: ${params.rtl_file}`);
  }

  // 주파수 현실성 검사 (너무 높으면 경고)
  if (params.target_freq_mhz > 2000) {
    errors.push(`목표 주파수 ${params.target_freq_mhz}MHz는 현재 공정에서 달성 불가능합니다`);
  }

  return { valid: errors.length === 0, errors };
}
```

**R3: EDA FSM 우회 가능성**

| 항목 | 내용 |
|------|------|
| 심각도 | 높음 |
| 발생 가능성 | 낮음 |
| 시나리오 | 에이전트가 직접 EDA API를 호출하는 방법을 찾거나, FSM 훅을 우회 |
| 영향 | 순서 위반으로 EDA 결과 오염 |

**완화 전략:**
1. **EDA API 레이어 인증**: 에이전트 에이전트만 접근 가능한 토큰 기반 인증
2. **EDA 서버 사이드 FSM**: 클라이언트 FSM 외에 서버 사이드에도 Phase 순서 검증 추가
3. **감사 로그**: 모든 EDA 도구 호출을 타임스탬프와 함께 로그 기록

**R4: 컨텍스트 윈도우 한계**

| 항목 | 내용 |
|------|------|
| 심각도 | 중간 |
| 발생 가능성 | 높음 |
| 시나리오 | 긴 EDA 세션에서 대화 히스토리가 Sub-10B 모델의 컨텍스트 윈도우(8192 토큰)를 초과 |
| 영향 | 에이전트가 이전 EDA 결과를 잊고 잘못된 판단 |

**완화 전략:**
1. **대화 압축**: 오래된 도구 결과를 요약문으로 압축 (session_before_compact 훅)
2. **FSM 상태 명시적 주입**: 컨텍스트 압축 후에도 FSM 상태를 시스템 프롬프트에 재주입
3. **외부 상태 저장소**: EDA Phase 결과를 벡터 DB나 파일로 저장하여 필요 시 검색

```typescript
// 컨텍스트 압축 훅 (Pi SDK session_before_compact)
session_before_compact: async (context) => {
  // 도구 결과를 요약문으로 압축
  const toolResults = context.messages
    .filter(m => m.role === 'tool')
    .map(m => JSON.parse(m.content));

  const summary = await summarizeEDAResults(toolResults);

  // 압축된 컨텍스트 반환
  return {
    ...context,
    messages: [
      context.messages[0],  // 시스템 프롬프트 유지
      {
        role: 'assistant',
        content: `[이전 EDA 세션 요약]\n${summary}\n현재 단계: ${edaFSM.currentPhase}`
      },
      ...context.messages.slice(-4)  // 최근 4개 메시지만 유지
    ]
  };
}
```

### 9.2 위험 요소 종합 매트릭스

```
높음
  │  R2 (Sub-10B 품질)     R1 (단일 개발자)
  │
심 │
각 │
도 │         R3 (FSM 우회)
  │
낮음│                         R4 (컨텍스트)
  └─────────────────────────────────────
    낮음      발생 가능성      높음
```

**우선 완화 순서: R2 → R1 → R4 → R3**

---

## 10. 참고 자료

### 10.1 핵심 논문 및 기술 문서

- **ACL 2025**: "JSON Output Reliability in Sub-10B Parameter Language Models" - Sub-10B 모델의 구조화 출력 실패율 38% 벤치마크
- **vLLM 공식 문서**: Guided Decoding — https://docs.vllm.ai/en/latest/features/structured_outputs.html
- **lm-format-enforcer**: https://github.com/noamgat/lm-format-enforcer
- **outlines**: https://github.com/outlines-dev/outlines

### 10.2 프레임워크 공식 저장소

- **badlogic/pi-mono (Pi SDK)**: https://github.com/badlogic/pi-mono
- **LangChain.js**: https://github.com/langchain-ai/langchainjs
- **LlamaIndex.TS**: https://github.com/run-llama/LlamaIndexTS
- **Vercel AI SDK**: https://github.com/vercel/ai
- **OpenClaw**: GitHub 234k stars (Peter Steinberger 작)

### 10.3 선행 조사 보고서 (pi-mono 내부)

본 보고서는 다음 3개 선행 조사 보고서를 종합한 것이다.

1. `clockcanvas_agent_architecture_report.md` — ClockCanvas EDA 에이전트 아키텍처 설계 보고서
2. `local_llm_agent_sdk_survey_report.md` — 로컬 LLM 에이전트 SDK 10개 비교 조사 보고서
3. `pi_sdk_evaluation_report.md` — Pi SDK (badlogic/pi-mono) 심층 평가 보고서

### 10.4 기술 용어 해설

| 용어 | 설명 |
|------|------|
| **Grammar-Constrained Decoding** | LLM 토큰 생성 시 문법적으로 불가능한 토큰의 확률을 0으로 마스킹하여 출력 형식을 보장하는 기법 |
| **EDA (Electronic Design Automation)** | 반도체 집적회로 설계를 자동화하는 소프트웨어 도구의 총칭 |
| **FSM (Finite State Machine)** | 유한 상태 기계. 시스템이 가질 수 있는 상태와 전이 규칙을 정의한 수학적 모델 |
| **Sub-10B 모델** | 파라미터 수가 100억 개 미만인 LLM. 로컬 실행이 가능하지만 대형 모델 대비 성능 제한 |
| **On-premise** | 클라우드가 아닌 자체 서버에서 서비스를 운영하는 방식 |
| **ReAct 루프** | Reasoning + Acting. LLM이 생각(추론)과 행동(도구 호출)을 반복하는 에이전트 패턴 |
| **vLLM** | 고성능 LLM 추론 서버. PagedAttention 기술로 GPU 메모리 효율을 극대화 |
| **TypeBox** | TypeScript 타입과 JSON Schema를 동시에 생성하는 라이브러리 |
| **훅(Hook)** | 에이전트 실행 흐름의 특정 시점에 커스텀 코드를 삽입하는 확장 포인트 |
| **PreToolUse** | 도구 실행 전에 호출되는 훅. 실행 차단 가능 |
| **PostToolUse** | 도구 실행 후 결과를 받아 처리하는 훅. 결과 수정 가능 |
| **RTL (Register-Transfer Level)** | 디지털 회로 설계의 추상화 수준. Verilog/VHDL로 작성 |
| **P&R (Place & Route)** | 논리 게이트를 물리적 위치에 배치하고 연결선을 라우팅하는 EDA 단계 |
| **타이밍 슬랙 (Timing Slack)** | 신호가 목표 시간보다 얼마나 일찍 도착했는지의 여유분. 음수이면 타이밍 위반 |

---

## 부록 A: 전체 프레임워크 평가 점수표

아래 점수표는 Python 스택을 전제로 작성된 것이다. TypeScript 스택의 경우 섹션 5를 참조하라.

| 프레임워크 | 로컬LLM(5) | Hook(5) | Sub-10B(5) | Grammar(5) | 성숙도(5) | 커뮤니티(5) | 총점(30) | 권고 |
|-----------|-----------|---------|-----------|-----------|---------|-----------|--------|------|
| **LlamaIndex** | 5 | 5 | 4 | 3 | 5 | 3 | **25** | 1순위 (Python) |
| **Pydantic AI** | 4 | 4 | 4 | 5* | 4 | 3 | **24** | 2순위 (Python) |
| **Agno** | 5 | 5 | 4 | 2 | 3 | 5 | **24** | 2순위 (Python) |
| **CrewAI** | 4 | 5 | 3 | 2 | 4 | 4 | **22** | 검토 가능 |
| **Haystack** | 5 | 3 | 3 | 2 | 5 | 3 | **21** | 특수 목적 |
| **DSPy** | 4 | 2 | 5 | 3 | 4 | 3 | **21** | 연구용 |
| **Smolagents** | 5 | 3 | 4 | 2 | 3 | 2 | **19** | 경량 PoC |
| **OpenAI Agents SDK** | 3 | 4 | 3 | 2 | 3 | 3 | **18** | 클라우드 우선 |
| **AutoGen** | 3 | 3 | 3 | 2 | 1 | 5 | **17** | 탈락 (v0.4 불안정) |
| **PraisonAI** | 4 | 1 | 3 | 1 | 2 | 3 | **14** | 탈락 |
| **Pi SDK** | 2 | 4 | 1 | 2 | 1 | 2 | **12** | TypeScript 환경 PoC |

*Pydantic AI Grammar 5/5이나 tool calling과 동시 사용 불가 제약 존재

**점수 해석 참고:**
- Pi SDK는 Python 스택 기준으로 낮은 점수를 받았지만, TypeScript 스택에서는 "로컬LLM" 항목과 "Sub-10B" 항목의 의미가 달라진다. TypeScript 네이티브라는 사실이 표에 반영되지 않았음에 유의하라.

---

## 부록 B: EDA Phase별 도구 스키마 참고

```typescript
// ClockCanvas EDA 도구 스키마 (TypeBox 기반)
import { Type, Static } from '@sinclair/typebox';

// RTL Check
export const RTLCheckParams = Type.Object({
  rtl_files: Type.Array(Type.String(), { minItems: 1 }),
  top_module: Type.String(),
  check_level: Type.Union([
    Type.Literal('syntax'),
    Type.Literal('semantic'),
    Type.Literal('full')
  ], { default: 'full' })
});
export type RTLCheckParams = Static<typeof RTLCheckParams>;

// Synthesis
export const SynthesisParams = Type.Object({
  rtl_file: Type.String(),
  top_module: Type.String(),
  target_freq_mhz: Type.Number({ minimum: 1, maximum: 5000 }),
  target_library: Type.String(),
  optimization: Type.Union([
    Type.Literal('area'),
    Type.Literal('speed'),
    Type.Literal('power'),
    Type.Literal('balanced')
  ])
});
export type SynthesisParams = Static<typeof SynthesisParams>;

// Timing Analysis
export const TimingAnalysisParams = Type.Object({
  netlist_file: Type.String(),
  sdc_file: Type.String(),
  analysis_mode: Type.Union([
    Type.Literal('setup'),
    Type.Literal('hold'),
    Type.Literal('both')
  ], { default: 'both' }),
  report_slack_threshold_ps: Type.Optional(Type.Number())
});
export type TimingAnalysisParams = Static<typeof TimingAnalysisParams>;

// Place & Route
export const PlaceAndRouteParams = Type.Object({
  netlist_file: Type.String(),
  floorplan_file: Type.String(),
  target_utilization: Type.Number({ minimum: 0.1, maximum: 0.95 }),
  routing_effort: Type.Union([
    Type.Literal('low'),
    Type.Literal('medium'),
    Type.Literal('high')
  ], { default: 'medium' })
});
export type PlaceAndRouteParams = Static<typeof PlaceAndRouteParams>;

// Final Verification
export const FinalVerificationParams = Type.Object({
  layout_file: Type.String(),
  checks: Type.Array(Type.Union([
    Type.Literal('drc'),   // Design Rule Check
    Type.Literal('lvs'),   // Layout vs Schematic
    Type.Literal('erc'),   // Electrical Rule Check
    Type.Literal('antenna') // Antenna Effect Check
  ]), { minItems: 1 })
});
export type FinalVerificationParams = Static<typeof FinalVerificationParams>;
```

---

*본 보고서는 2026년 2월 기준으로 작성되었다. Pi SDK는 2026-03-02 OSS vacation 종료 예정이므로, 복귀 후 저장소 상태를 재확인하기 바란다.*

*잇다반도체 ClockCanvas 개발팀 내부 문서. 외부 배포 금지.*
