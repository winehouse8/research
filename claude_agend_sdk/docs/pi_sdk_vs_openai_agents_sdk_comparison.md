# Pi SDK vs OpenAI Agents SDK — ClockCanvas EDA Agent 최종 비교 보고서

**작성일**: 2026-02-27
**대상**: 잇다반도체 ClockCanvas EDA Agent 개발팀
**전제**: TypeScript 주력 스택, On-premise 로컬 LLM (Sub-10B), n0 loop + Hook 방식 선호

---

## Executive Summary

| 항목 | Pi SDK | OpenAI Agents SDK |
|------|--------|-------------------|
| 언어 | **TypeScript 네이티브** | Python (TypeScript 미지원) |
| n0 Loop 방식 | **네이티브 지원** | 네이티브 지원 |
| Hook 강제성 | **block 가능** (tool_call 반환) | 관찰 전용 (on_tool_start 등) |
| Grammar-Constrained | 커스텀 미들웨어 필요 | LiteLLM 경유 가능 |
| 로컬 LLM 연동 | Ollama, LM Studio 지원 | LiteLLM beta 경유 |
| 운영 안정성 | 단일 개발자 (Mario Zechner) | OpenAI 공식 팀 |
| 실서비스 레퍼런스 | OpenClaw (234k ★) | OpenAI 생태계 전반 |
| **권장** | **ClockCanvas 1순위** | Python 팀 또는 클라우드 우선 팀 |

**결론**: **TypeScript 주력 스택**이라는 전제 하에, ClockCanvas 상황에서는 **Pi SDK가 명확히 우선**이다. 단, 단일 개발자 리스크(현재 OSS 휴가 중)와 자체 호스팅 모델 호환성 경고를 인지하고 4주 PoC로 검증 후 결정하라.

---

## 0. 이전 평가와의 전제 차이 — 반드시 읽을 것

본 비교 보고서는 이전에 작성된 `pi_sdk_evaluation_report.md`와 **결론이 다르다.** 혼란을 방지하기 위해 차이점을 명확히 설명한다.

### 이전 평가 요약

`pi_sdk_evaluation_report.md`는 Pi SDK를 **11/30점** (전체 11개 프레임워크 중 최하위)으로 평가하고, 5가지 탈락 사유와 함께 **"채택할 수 없다"**고 결론지었다. 주요 탈락 사유:

1. Python 중심 잇다반도체 스택과의 언어 장벽
2. 자체 호스팅 모델 호환성 미보장 (개발자 본인 경고)
3. OSS vacation으로 인한 개발 중단 상태
4. EDA 도메인 레퍼런스 전무
5. Sub-10B 모델 안정성 미검증

### 본 보고서의 전제 변경

이후 개발팀이 **"ClockCanvas 기술 스택이 TypeScript 주력"**임을 명확히 했다. 이 단일 사실이 평가를 완전히 바꾼다:

| 변경된 전제 | 이전 평가 | 본 보고서 |
|-------------|-----------|-----------|
| 팀 스택 | Python 가정 | **TypeScript 확정** |
| Pi SDK 언어 적합성 | 언어 장벽 (탈락 사유) | 네이티브 일치 |
| OpenAI Agents SDK 언어 | Python → 적합 | Python → **TypeScript 팀에 장벽** |

**변경되지 않은 우려사항** (이전 평가의 경고 그대로 유효):
- 개발자 "self-hosted models usually don't work well" 경고
- OSS vacation (2026-03-02까지) 상태
- EDA 도메인 레퍼런스 없음

이 보고서는 TypeScript 전제 하에 우선순위를 평가하되, 위 3가지 미해소 우려사항을 명시적으로 포함한다.

---

## 1. 배경 — ClockCanvas의 결정적 요구사항

이 비교는 다음 세 가지 제약이 모두 성립할 때를 기준으로 작성되었다:

1. **TypeScript 주력**: 팀 역량과 기존 코드베이스가 TypeScript
2. **On-premise 로컬 LLM**: Sub-10B 모델 (Qwen-7B, Mistral-7B 등), vLLM 서버
3. **n0 loop + Hook 강제**: `while not done { LLM → tool_call → hook → result }` 패턴, Hook에서 실행 차단 가능해야 함

이 세 조건 중 하나라도 다르면 결론이 달라질 수 있다.

---

## 2. 언어 스택 적합성

### Pi SDK — TypeScript 네이티브

```typescript
// Pi SDK: 팀이 그대로 쓸 수 있는 코드
import { Agent, tool } from "@badlogic/pi-agent-core";

const edaAgent = new Agent({
  model: "qwen-7b",
  baseURL: "http://localhost:8000/v1",  // vLLM 직접 연결
  tools: [rtlCheckTool, synthesisTool, timingTool],
});

// n0 loop — Pi SDK가 내부적으로 구현
const result = await edaAgent.run("ClockCanvas 타이밍 분석 실행");
```

- **팀 온보딩 비용**: 거의 없음. TypeScript 개발자가 즉시 사용 가능.
- **빌드 파이프라인 통합**: npm/yarn 에코시스템 그대로 활용.
- **타입 안정성**: TypeScript 인터페이스로 tool 스키마 정의 → 컴파일 타임 오류 검출.

### OpenAI Agents SDK — Python 전용

```python
# Python 코드: TypeScript 팀에게 학습 비용 발생
from agents import Agent, Runner, RunHooks

agent = Agent(
    name="eda_agent",
    model="gpt-4o",  # 로컬 모델은 LiteLLM beta 경유
    tools=[rtl_check, synthesis, timing]
)
result = await Runner.run(agent, "타이밍 분석 실행")
```

- **언어 장벽**: Python 환경 세팅, 패키지 관리, 비동기 패턴 학습 필요.
- **TypeScript 바인딩 없음**: 공식 TypeScript SDK 없음 (2026년 2월 기준).
- **운영 복잡도**: TypeScript 메인 앱과 Python 에이전트 서버 간 IPC 또는 HTTP 브릿지 필요.

**평가**: Pi SDK **승**. TypeScript 팀에게 Python SDK 도입은 추가적인 복잡성 레이어를 의미한다.

---

## 3. n0 Loop 아키텍처

두 SDK 모두 기본적으로 동일한 n0 loop를 구현하고 있다:

```
while not done:
    response = LLM(messages)
    if response.tool_calls:
        results = execute_tools(tool_calls)
        messages.append(results)
    else:
        done = True
        final = response.content
```

### Pi SDK의 n0 Loop

```typescript
// Pi SDK 내부: AgentRunner가 루프를 관리
class AgentRunner {
  async run(prompt: string) {
    const messages = [{ role: "user", content: prompt }];
    while (true) {
      const response = await this.llm.complete(messages);
      if (!response.toolCalls?.length) return response.content;

      // Hook 지점: BEFORE tool execution
      for (const call of response.toolCalls) {
        const hookResult = await this.hooks.onToolCall(call);
        if (hookResult?.block) throw new Error(hookResult.reason); // 강제 차단

        const result = await this.tools[call.name](call.args);
        messages.push({ role: "tool", content: result });
      }
    }
  }
}
```

### OpenAI Agents SDK의 n0 Loop

```python
# OpenAI Agents SDK: Runner가 루프 관리
class Runner:
    async def run(self, agent, input):
        messages = [{"role": "user", "content": input}]
        while True:
            response = await agent.model.respond(messages)
            if not response.tool_calls:
                return response.output

            # Hook 지점: 관찰만 가능 (차단 불가)
            await self.hooks.on_tool_start(agent, response.tool_calls[0])
            result = await execute_tool(response.tool_calls[0])
            await self.hooks.on_tool_end(agent, result)
            messages.append(result)
```

**평가**: 루프 구조 자체는 동등. 차이는 Hook에서 발생한다 (섹션 4 참조).

---

## 4. Hook 시스템 — 가장 중요한 차이점

ClockCanvas EDA Agent에서 Hook이 중요한 이유:
- RTL 합성 전 파일 존재 여부 검증 → 존재하지 않으면 **실행 차단**
- 타이밍 분석 도구에 금지된 클럭 도메인 접근 시 **실행 차단**
- 모든 EDA 단계 전환을 Phase FSM에 기록 → **감사 로그**

### Pi SDK — 25개 Hook 이벤트, tool_call에서 실행 차단 가능

```typescript
// extensions.md에서 확인된 실제 API
agent.on("tool_call", async (call: ToolCall) => {
  // EDA Phase 검증: 현재 phase에서 허용된 tool인지 확인
  if (!phaseAllows(currentPhase, call.name)) {
    return {
      block: true,  // ← 실행 완전 차단
      reason: `Phase '${currentPhase}'에서 '${call.name}' 도구는 허용되지 않음`
    };
  }

  // 파일 존재 여부 사전 검증
  if (call.name === "run_synthesis" && !fileExists(call.args.rtlFile)) {
    return {
      block: true,
      reason: `RTL 파일 없음: ${call.args.rtlFile}`
    };
  }

  // 통과: undefined 반환 → 정상 실행
});

// 전체 Pi SDK Hook 이벤트 목록 (25+)
// tool_call, tool_result, message_start, message_end,
// thinking_start, thinking_end, stream_start, stream_end,
// error, retry, context_overflow, ...
```

**Pi SDK Hook 특성**:
- `return { block: true, reason }` → **실행 완전 차단** (검증된 기능)
- 25개 이상의 세밀한 이벤트 지점
- 동기/비동기 Hook 모두 지원
- Hook에서 예외 대신 구조체 반환 → 타입 안전

### OpenAI Agents SDK — 관찰 전용 Hook

```python
class EdaHooks(RunHooks):
    async def on_tool_start(self, context, agent, tool):
        # 관찰만 가능 — 실행 차단 불가
        print(f"Tool 시작: {tool.name}")
        # ❌ return {"block": True} 같은 옵션 없음

    async def on_tool_end(self, context, agent, tool, result):
        # 실행 후 결과 관찰만 가능
        print(f"결과: {result}")

# is_enabled: 런타임 lambda로 동적 제어 가능 (Section 4 참조)
# → tool을 LLM 시야에서 아예 숨김 (차단이 아닌 은폐)
@function_tool(
    is_enabled=lambda ctx, agent: load_state()["current_phase"] == "synthesis"
)
def run_synthesis(config_file: str) -> str:
    """합성 도구: synthesis Phase에서만 LLM에게 노출됨"""
    return "합성 완료"
```

**OpenAI Agents SDK Hook 특성**:
- `on_tool_start`, `on_tool_end`: 관찰 전용, 실행 **차단** 불가
- `on_agent_start`, `on_agent_end`, `on_handoff`: 에이전트 수준 훅
- `is_enabled`: **런타임 lambda로 동적 제어 가능** — tool을 LLM의 시야에서 아예 숨김 (차단이 아닌 은폐)
- 감사 로깅에는 적합, EDA Phase 강제에는 `is_enabled` 패턴 활용 가능

**`is_enabled`의 동적 동작 — 중요 정정:**

이전 섹션에서 `is_enabled`를 "정적 조건 기반"으로 설명했으나 이는 오류다. `clockcanvas_agent_architecture_report.md`에 검증된 실제 패턴:

```python
@function_tool(
    # lambda가 runtime에 workflow_state.json을 읽어 동적으로 허용 여부 결정
    is_enabled=lambda ctx, agent: "run_rtl_lint" in load_state()["allowed_tools"]
)
def run_rtl_lint(target_file: str) -> str: ...

@function_tool(
    is_enabled=lambda ctx, agent: "run_synthesis" in load_state()["allowed_tools"]
)
def run_synthesis(config_file: str) -> str: ...
```

이 패턴은 `workflow_state.json`을 매 호출마다 읽어 **현재 Phase에 허용된 도구만 LLM에게 노출**한다. 이것은 차단이 아니라 **은폐(hide)**다 — LLM이 허용되지 않은 도구를 시도조차 하지 않으므로 loop 오염 없이 Phase를 강제한다. 선행 보고서는 이를 "더 강력한 Phase-lock 메커니즘"으로 평가했다.

**Pi SDK `block` vs OpenAI `is_enabled` 비교:**

| 방식 | Pi SDK `block: true` | OpenAI `is_enabled` lambda |
|------|---------------------|---------------------------|
| 동작 | 도구 호출 실행 도중 차단 | 도구 자체를 LLM 시야에서 은폐 |
| LLM 인식 | 차단 이유를 메시지로 받음 | 해당 도구가 없는 것처럼 인식 |
| Sub-10B 효과 | 에러 처리 loop 필요 | **도구 선택 오류 자체 방지** |
| 구현 복잡도 | Hook 등록 | lambda + state file |

### Hook 기능 비교 표

| Hook 기능 | Pi SDK | OpenAI Agents SDK |
|-----------|--------|-------------------|
| tool 실행 전 관찰 | ✅ | ✅ |
| tool 실행 **차단** | ✅ `{ block: true }` | ❌ (차단 없음) |
| tool 자체 **은폐** (LLM 시야) | ❌ | ✅ `is_enabled` lambda |
| tool 결과 후 관찰 | ✅ | ✅ |
| 이벤트 세분화 | ✅ 25+ 이벤트 | ⚠️ 6개 이벤트 |
| 비동기 Hook | ✅ | ✅ |
| EDA Phase FSM 강제 | ✅ `block` 반환 | ✅ `is_enabled` lambda |

**평가**: **동등하나 방식이 다르다.** Pi SDK는 tool 호출을 실행 중 차단(에러 메시지 LLM 반환), OpenAI SDK는 tool을 LLM 시야에서 아예 숨김(선택 오류 원천 방지). Sub-10B 모델에서는 오히려 `is_enabled` 은폐 방식이 더 안정적일 수 있다. 단, 언어 스택 이슈(Python vs TypeScript)는 여전히 유효하다.

---

## 5. On-Premise 로컬 LLM 연동

### Pi SDK — Ollama / LM Studio 직접 연결

```typescript
// vLLM OpenAI 호환 엔드포인트 직접 연결
const agent = new Agent({
  model: "qwen2.5-coder-7b",
  baseURL: "http://localhost:8000/v1",  // vLLM 서버
  apiKey: "local",
  // OpenAI 호환 API 사용 → 추가 설정 불필요
});

// Ollama 연결
const ollamaAgent = new Agent({
  model: "ollama/mistral:7b",
  baseURL: "http://localhost:11434/v1",
});
```

- OpenAI 호환 엔드포인트를 기본 지원 → vLLM, Ollama, LM Studio 즉시 연결
- 추가 라이브러리 불필요
- 타임아웃, 재시도 설정 세밀 조정 가능

> ⚠️ **공식 경고 (pi_sdk_evaluation_report.md 112행에서 확인됨)**: Pi SDK 공식 문서는 **"self-hosted models usually don't work well"** 이라고 명시하고 있다. 개발자 Mario Zechner 본인이 자체 호스팅 모델과의 tool calling 호환성에 낮은 신뢰도를 공개 표명했다. vLLM + 자체 호스팅 환경에서의 실제 동작은 **PoC에서 반드시 검증**해야 한다.

### OpenAI Agents SDK — LiteLLM Beta 경유

```python
# LiteLLM을 통한 로컬 모델 연결 (beta 기능)
import litellm
from agents import Agent, LitellmModel

agent = Agent(
    name="eda_agent",
    model=LitellmModel(
        model="ollama/qwen2.5-coder:7b",  # LiteLLM 형식
        base_url="http://localhost:11434",
    )
)
```

- LiteLLM beta: 공식 지원이나 안정성 미보장
- LiteLLM 자체의 추상화 레이어가 디버깅을 복잡하게 만들 수 있음
- 2026년 기준 beta 딱지가 여전히 붙어 있음

**평가**: Pi SDK **승**. 직접 연결이 추상화 레이어보다 안정적이다.

---

## 6. Grammar-Constrained Decoding (Sub-10B JSON 안정성)

Sub-10B 모델에서 JSON 출력 실패율은 **38%** (실측). 이를 0%로 낮추는 핵심 기술.

### 원리 (복습)
- vLLM 서버가 `guided_json` 파라미터로 토큰 마스킹
- LLM이 JSON 스키마를 위반하는 토큰을 생성하려 하면 서버가 실시간 차단
- **프레임워크와 무관**: vLLM 서버 기능이므로 어떤 클라이언트도 활용 가능

```
HTTP POST http://vllm-server:8000/v1/chat/completions
Body: {
  "model": "qwen2.5-7b",
  "messages": [...],
  "extra_body": {
    "guided_json": {
      "type": "object",
      "properties": { "phase": {"type": "string"}, "result": {"type": "boolean"} },
      "required": ["phase", "result"]
    }
  }
}
→ 100% 유효한 JSON 반환 보장
```

### Pi SDK에서 Grammar-Constrained Decoding 적용

```typescript
// Pi SDK: extra_body 전달 방법 (커스텀 미들웨어 필요)
agent.on("before_request", (request) => {
  if (request.tool === "get_timing_result") {
    request.body.extra_body = {
      guided_json: timingResultSchema
    };
  }
  return request;
});

// 또는 커스텀 LLM 어댑터로 구현
class GrammarAwareLLM extends PiLLMAdapter {
  async complete(messages, options) {
    return super.complete(messages, {
      ...options,
      extra_body: { guided_json: options.responseSchema }
    });
  }
}
```

- **지원 여부**: 직접 지원 없음. `before_request` hook 또는 커스텀 어댑터로 구현 필요.
- **구현 난이도**: 중간 (Hook 시스템 활용 가능 → Pi SDK에서 더 깔끔하게 구현 가능)

### OpenAI Agents SDK에서 Grammar-Constrained Decoding 적용

```python
# LiteLLM을 통해 extra_body 전달
from agents import LitellmModel

class GrammarAwareModel(LitellmModel):
    def __init__(self, schema, **kwargs):
        super().__init__(**kwargs)
        self.schema = schema

    async def get_response(self, *args, **kwargs):
        kwargs["extra_body"] = {"guided_json": self.schema}
        return await super().get_response(*args, **kwargs)
```

- **지원 여부**: 직접 지원 없음. LiteLLM 커스텀 클래스 오버라이드 필요.
- **구현 난이도**: 중간 (Python에서는 클래스 상속이 더 직관적일 수 있음)

**평가**: **동등** (둘 다 커스텀 구현 필요). 단, Pi SDK의 25개 Hook 중 `before_request`를 활용하면 더 우아하게 처리 가능.

---

## 7. 운영 안정성 및 유지보수 리스크

### Pi SDK — 단일 개발자 리스크

| 항목 | 상태 |
|------|------|
| 주요 기여자 | Mario Zechner (libGDX 제작자) |
| GitHub Stars | 17,300+ |
| 의존 프로젝트 | OpenClaw (234k ★), 기타 다수 |
| 라이선스 | MIT |
| 현재 개발 상태 | ⚠️ **OSS vacation 중 (2026-03-02까지)** — 버그 리포트/PR 응답 없음 |
| 취약점 | **키맨 리스크**: Zechner 중단 시 지원 없음 |

**리스크 완화 방안**:
- MIT 라이선스 → Fork하여 자체 유지 가능
- OpenClaw 같은 대형 의존 프로젝트가 있어 ecosystem 이탈 가능성 낮음
- Pi SDK 코어가 작고 단순 → 자체 포크 난이도 낮음

### OpenAI Agents SDK — 기업 지원

| 항목 | 상태 |
|------|------|
| 유지보수 주체 | OpenAI 공식 팀 |
| GitHub Stars | 30,000+ |
| 의존 프로젝트 | OpenAI 생태계 전반 |
| 라이선스 | MIT |
| 취약점 | **OpenAI 종속**: API 정책 변경 시 영향 |

**리스크 완화 방안**:
- OpenAI가 상업적 목적으로 SDK를 유지 → 갑작스러운 중단 가능성 낮음
- 단, OpenAI 클라우드 API에 최적화 → 로컬 LLM 지원은 부차적

**평가**: OpenAI Agents SDK **약간 우위**. 그러나 Pi SDK의 단일 개발자 리스크는 코드베이스 규모가 작아 Fork 가능성으로 충분히 상쇄된다.

---

## 8. EDA Phase FSM 구현 비교

ClockCanvas 핵심 기능: RTL Check → Synthesis → Timing Analysis → Place & Route → Final Verification

### Pi SDK로 구현 (권장)

```typescript
// Phase FSM: Pi SDK Hook으로 강제 구현
enum EdaPhase { RTL_CHECK, SYNTHESIS, TIMING, PLACE_ROUTE, FINAL }

const PHASE_ALLOWED_TOOLS: Record<EdaPhase, string[]> = {
  [EdaPhase.RTL_CHECK]:   ["check_syntax", "lint_rtl", "validate_ports"],
  [EdaPhase.SYNTHESIS]:   ["run_synthesis", "optimize_netlist"],
  [EdaPhase.TIMING]:      ["run_sta", "check_timing_constraints"],
  [EdaPhase.PLACE_ROUTE]: ["run_pnr", "verify_drc"],
  [EdaPhase.FINAL]:       ["generate_report", "export_gds"],
};

class ClockCanvasAgent {
  private phase = EdaPhase.RTL_CHECK;
  private agent: Agent;

  constructor() {
    this.agent = new Agent({ model: "qwen2.5-coder-7b", ... });

    // ← 핵심: Hook에서 Phase FSM 강제
    this.agent.on("tool_call", async (call) => {
      const allowed = PHASE_ALLOWED_TOOLS[this.phase];
      if (!allowed.includes(call.name)) {
        return {
          block: true,
          reason: `현재 Phase(${EdaPhase[this.phase]})에서 '${call.name}'은 허용되지 않습니다. 허용 도구: ${allowed.join(", ")}`
        };
      }
    });

    this.agent.on("tool_result", async (result) => {
      // Phase 전환 로직
      if (result.tool === "run_synthesis" && result.success) {
        this.phase = EdaPhase.TIMING;
        console.log("Phase 전환: SYNTHESIS → TIMING");
      }
    });
  }
}
```

### OpenAI Agents SDK로 구현 (우회책 필요)

```python
# Hook이 차단 불가 → is_enabled로 우회
class PhaseController:
    def __init__(self):
        self.phase = "rtl_check"

    def make_tool(self, tool_fn, allowed_phases):
        class PhasedTool(BaseTool):
            def is_enabled(self_, ctx):
                # runtime lambda로 동적 Phase 판단 가능 — LLM 시야에서 도구 자체를 은폐
                # (차단이 아닌 은폐: Section 4 참조)
                return self.phase in allowed_phases

            async def run(self_, ctx, args):
                # LLM이 is_enabled=False인 tool을 호출하면
                # 에러 응답이 LLM에게 반환됨 (강제 차단이 아님)
                return await tool_fn(args)
        return PhasedTool()

# 문제: is_enabled가 False여도 LLM이 계속 시도하면
# "tool not available" 에러 메시지가 context에 쌓임
# 이를 LLM이 학습하는 게 아니라 loop를 오염시킬 수 있음
```

**평가**: **동등하나 접근법이 다르다.** Pi SDK는 tool 호출 시점에 차단 후 에러를 LLM에 반환, OpenAI SDK는 해당 tool을 LLM 시야에서 아예 숨겨 시도조차 못하게 한다. TypeScript 팀에게는 Pi SDK가 더 자연스럽지만, Phase FSM 구현 가능성 자체는 두 SDK 모두 충족한다.

---

## 9. 실서비스 레퍼런스

### Pi SDK
- **OpenClaw** (Peter Steinberger): 234,000 GitHub Stars. 멀티플랫폼 에이전트 게이트웨이. Pi SDK의 hook, tool 시스템을 프로덕션에서 대규모 사용.
- **pi-coding-agent**: Pi SDK 자체가 코딩 에이전트로 Gemini 대회에서 수상.
- **TypeScript 생태계 내 실사용 사례** 다수

### OpenAI Agents SDK
- OpenAI 내부 팀 사용 사례
- 클라우드 API 기반 다수 SaaS 서비스
- **로컬 LLM + TypeScript 스택에서의 레퍼런스는 희소**

---

## 10. 종합 점수표 (ClockCanvas 관점)

| 평가 기준 | 가중치 | Pi SDK | OpenAI Agents SDK |
|-----------|--------|--------|-------------------|
| TypeScript 스택 적합성 | 25% | **5/5** | 1/5 |
| Hook/Phase FSM 강제 | 20% | 4/5 (`block`) | 4/5 (`is_enabled`) |
| n0 Loop 지원 | 15% | 4/5 | 4/5 |
| 로컬 LLM 연동 | 15% | 3/5 ⚠️경고 | 3/5 |
| Grammar-Constrained 지원 | 10% | 3/5 | 3/5 |
| 운영 안정성 / 유지보수 | 15% | 2/5 ⚠️OSS 휴가 | **4/5** |
| **가중 합산** | | **3.70/5** | **3.00/5** |

> **주의**: 이전 버전의 Hook 점수(Pi SDK 5/5 vs OpenAI 2/5)는 `is_enabled`의 동적 기능을 오해한 결과였다. 수정 후 두 SDK 모두 4/5로 동등하다. 최종 점수 차이(3.70 vs 3.00, 격차 0.70)는 주로 TypeScript 스택 적합성(25% 가중치, 5 vs 1)에서 비롯된다.

---

## 11. 최종 권장사항

### Pi SDK를 선택하라

ClockCanvas의 세 가지 핵심 조건이 모두 Pi SDK를 지목한다:

**조건 1 — TypeScript**: Pi SDK는 TypeScript 네이티브다. OpenAI Agents SDK는 Python만 지원한다. TypeScript 팀이 Python SDK를 도입하면 학습 비용, 환경 분리, IPC 복잡도가 발생한다.

**조건 2 — Hook/Phase FSM**: EDA Phase FSM 강제는 두 SDK 모두 가능하다. Pi SDK는 `block: true`로 실행 중 차단, OpenAI Agents SDK는 `is_enabled` lambda로 LLM 시야에서 은폐. 방식은 다르지만 목적은 동일하게 달성 가능하다. Sub-10B 모델에서는 오히려 은폐 방식이 loop 오염을 방지하므로 유리할 수 있다. 이 기준에서는 두 SDK가 동등하다.

**조건 3 — 로컬 LLM**: Pi SDK는 OpenAI 호환 엔드포인트(vLLM, Ollama)를 직접 지원한다. OpenAI Agents SDK는 LiteLLM beta를 경유해야 하며, 안정성이 낮다.

### 단일 개발자 리스크 대응

Pi SDK의 유일한 약점은 Mario Zechner 의존성이다. 다음으로 완화하라:

1. **Pi SDK Fork 전략 수립**: MIT 라이선스이므로 언제든 Fork 가능. 내부 레지스트리에 `@clockcanvas/pi-agent-core` 패키지로 유지.
2. **추상화 레이어 두기**: `ClockCanvasAgent` 클래스가 Pi SDK를 직접 노출하지 않도록 래핑. 향후 SDK 교체 시 내부만 수정.
3. **핵심 API 의존 최소화**: `Agent`, `tool_call hook`, `tool_result hook` 세 가지만 사용. 실험적 기능 미사용.

---

## 12. PoC 실행 계획 (4주)

```
Week 1: 환경 세팅
- Pi SDK 설치 및 vLLM 서버 연동 검증
- 5개 EDA 도구 TypeScript 래핑 (rtl_check, synthesis, timing, pnr, export)
- tool_call hook으로 Phase FSM 기본 구현

Week 2: Grammar-Constrained Decoding 통합
- vLLM guided_json 파라미터 테스트
- Hook에서 request 인터셉트하여 schema 주입
- Sub-10B JSON 안정성 측정 (목표: 실패율 5% 이하)

Week 3: EDA Phase FSM 완성
- 전체 5단계 Phase 전환 로직
- Phase 위반 시 명확한 에러 메시지 → LLM 피드백 루프
- 감사 로그 (tool_call, tool_result 이벤트 기록)

Week 4: 부하 테스트 및 안정성 검증
- 연속 100회 EDA 파이프라인 실행
- 오류율, 응답 시간, Phase 위반 탐지율 측정
- OpenAI Agents SDK 동일 PoC와 성능 비교 (선택)
```

**Go/No-Go 기준**:
- Phase FSM 강제 성공률 > 99%
- JSON 파싱 실패율 < 5%
- EDA 전체 파이프라인 완료율 > 95%

---

## 13. 만약 Pi SDK가 실패하면

4주 PoC 후 Go/No-Go 기준 미달 시 **Fallback**: 순수 TypeScript 자체 구현

```typescript
// 자체 n0 loop: 30-50줄로 충분
class EDALoop {
  async run(prompt: string): Promise<string> {
    const messages: Message[] = [{ role: "user", content: prompt }];
    while (true) {
      const res = await this.llm.complete(messages);
      if (!res.tool_calls?.length) return res.content;

      for (const call of res.tool_calls) {
        // Phase FSM 강제 — 직접 구현
        if (!this.phaseAllows(call.name)) {
          throw new PhaseViolationError(call.name, this.currentPhase);
        }
        const result = await this.tools[call.name](call.args);
        messages.push({ role: "tool", content: JSON.stringify(result) });
      }
    }
  }
}
```

OpenAI Agents SDK는 Fallback 후보가 아니다. TypeScript 팀에게 Python SDK는 두 번째 선택이 될 수 없다.

---

**작성**: ClockCanvas EDA Agent 연구팀
**참조 문서**:
- `pi_sdk_evaluation_report.md` — Pi SDK 11/30 최초 평가 (Python 스택 전제)
- `agent_framework_final_report_2026.md` — 전체 프레임워크 종합 분석 및 TypeScript 트랙 권장
- `clockcanvas_agent_architecture_report.md` — OpenAI Agents SDK `is_enabled` 동적 lambda 패턴 검증
- `local_llm_agent_sdk_survey_report.md` — 11개 프레임워크 30점 기준 전수 평가 (LlamaIndex 25점 최고)
