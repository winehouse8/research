# 신뢰성 있는 개발 에이전트를 위한 결정론적+비결정론적 혼합 전략

## Pi SDK, Claude Code, OpenAI Agents SDK 심층 비교 분석

> **작성일:** 2026년 3월 3일
> **분류:** 기술 분석 보고서 (개정판)
> **목적:** 결정론적 코드(필수 테스트, 스펙 우선, 양방향 추적성, 린트 게이트)와 비결정론적 에이전트를 혼합하는 신뢰성 있는 개발 에이전트 구축을 위한 프레임워크 선택
> **전제:** ISO 26262 준수가 목표이며, 개발/커스터마이징 의향 있음
> **이전 보고서와의 관계:** 본 보고서는 `coding-agent-comparison-iso26262.md` 및 `pi_sdk_evaluation_report.md`의 Pi 관련 평가를 정정한다

---

## 목차

1. [서론: 왜 이 보고서가 필요한가](#1-서론)
2. [Stripe Minions Blueprint 분석](#2-stripe-minions-blueprint-분석)
3. [결정론적 코드 주입 관점에서의 비교 프레임워크](#3-결정론적-코드-주입-비교-프레임워크)
4. [Pi SDK 상세 분석: 28개 이벤트와 핵심 차별화 기능](#4-pi-sdk-상세-분석)
5. [Claude Code Hook 시스템 분석](#5-claude-code-hook-시스템-분석)
6. [OpenAI Agents SDK 분석](#6-openai-agents-sdk-분석)
7. [플랫폼별 결정론적 주입 시나리오별 비교](#7-시나리오별-비교)
8. [신뢰성 있는 개발 에이전트 아키텍처 설계](#8-아키텍처-설계)
9. [최종 권고사항](#9-최종-권고사항)
10. [결론](#10-결론)
11. [Human in the Loop (HITL) 전략](#11-human-in-the-loop-hitl-전략)
12. [신뢰성-효율성 Trade-off 전략](#12-신뢰성-효율성-trade-off-전략)

---

## 1. 서론

### 1.1 이전 보고서 평가의 핵심 오류

이전 보고서 `coding-agent-comparison-iso26262.md`는 Pi SDK에 대해 다음과 같이 결론지었다.

> "Pi는 ISO 26262 환경에 비권장한다. 안전 게이트 없음, 문서화 강제 불가, 감사 추적 없음, 설계 철학 불일치."

그리고 `pi_sdk_evaluation_report.md`는 Pi SDK를 조사 대상 전체 중 최하위(11/30점)로 평가하며 "채택 불가"를 선언했다.

**본 보고서는 이 평가를 정정한다.**

오류의 근원은 평가 기준의 혼동이었다. 이전 보고서들은 Pi SDK를 "즉시 사용 가능한 ISO 26262 준수 도구"로서 평가했다. 그러나 사용자의 실제 질문은 전혀 다른 것이었다.

> "개발/커스터마이징 의향이 있는 경우, 결정론적 코드와 비결정론적 에이전트를 혼합하는 데 어떤 프레임워크가 최적인가?"

이 질문에 대한 답은 완전히 다르다. **커스터마이징 의향이 있는 경우, Pi SDK는 최적의 선택이다.**

### 1.2 핵심 테제: 최소주의가 최대 확장성을 만든다

Pi SDK의 설계 철학은 "Primitives, not opinions(의견 없는 프리미티브)"이다. 이전 보고서는 이 철학을 약점으로 해석했다. 그러나 결정론적 게이트를 직접 설계하려는 개발자 관점에서, 이 철학은 가장 강력한 장점이다.

- **Claude Code**: 17개 이벤트, 외부 서브프로세스, 기존 훅 구조에 맞춰야 함
- **OpenAI Agents SDK**: RunHooks는 관찰 전용, Guardrails가 실제 게이트이지만 Python 전용
- **Pi SDK**: **28개 이벤트**, 인프로세스 TypeScript, MIT 라이선스, 소규모 코드베이스, 포킹 가능

빈 캔버스가 가장 많은 그림을 그릴 수 있다. Pi SDK의 미니멀리즘은 바로 이 빈 캔버스다.

### 1.3 결정론적+비결정론적 혼합의 중요성

신뢰성 있는 개발 에이전트의 핵심 과제는 다음 두 세계를 연결하는 것이다.

```
결정론적 세계                      비결정론적 세계
─────────────────────             ─────────────────────
lint 게이트                        코드 구현
CI 실행                            CI 실패 수정
git 커밋/푸시                      스펙 분석
테스트 통과 검증                   설계 결정
추적성 매트릭스 업데이트            리팩토링
```

비결정론적 LLM을 신뢰성 있게 만드는 방법은 LLM의 지능을 향상시키는 것이 아니다. LLM 주변에 결정론적 벽(walls)을 세우는 것이다. Stripe는 이것을 "1,300개 이상의 PR/주"로 실증했다.

---

## 2. Stripe Minions Blueprint 분석

### 2.1 Blueprint의 정의

2026년 2월, Stripe는 자사의 완전 자율 코딩 에이전트 시스템 Minions의 아키텍처를 공개했다. 핵심 개념은 **Blueprint**이다.

Blueprint는 **상태머신(state machine)**이다. 이 상태머신은 두 종류의 노드로 구성된다.

```
Blueprint 상태머신 표기법:

  ┌─────────────┐        ╭─────────────╮
  │  결정론적    │        │  에이전트   │
  │  노드(사각형)│        │  노드(구름) │
  └─────────────┘        ╰─────────────╯

결정론적 노드: 입력 → 출력이 항상 동일, 사람이 결과를 예측 가능
에이전트 노드: LLM이 판단, 비결정론적, 창의적 추론 필요
```

### 2.2 Stripe Minions의 구체적 Blueprint

Stripe Minions의 Blueprint를 재구성하면 다음과 같다.

```
[Slack 태스크 수신]
        │
        ▼
 ┌──────────────────┐
 │  컨텍스트 하이드레이션 │  ← 결정론적 노드 (사각형)
 │  (Context Hydration) │     관련 코드, 문서, 히스토리 로드
 │  [에이전트 루프 전에] │     LLM 호출 없음, 순수 결정론적
 └──────────┬───────┘
            │
            ▼
    ╭───────────────╮
    │   태스크 구현  │  ← 에이전트 노드 (구름)
    │  (Implement)  │     LLM이 코드 작성, 도구 실행
    ╰───────┬───────╯
            │
            ▼
 ┌──────────────────┐
 │    lint 게이트    │  ← 결정론적 노드
 │  (lint passes?)  │     lint 실패 시: 에이전트 노드로 되돌림
 └──────────┬───────┘
            │ 통과
            ▼
 ┌──────────────────┐
 │    CI 실행       │  ← 결정론적 노드
 │  (CI passing?)   │     최대 2회 허용
 └──────────┬───────┘
            │ 통과 또는
            │ 2회 실패 시
            ▼
    ╭───────────────╮
    │  CI 실패 수정  │  ← 에이전트 노드 (2회 제한)
    │  (Fix CI)     │
    ╰───────┬───────╯
            │
            ▼
 ┌──────────────────┐
 │   git push        │  ← 결정론적 노드
 └──────────┬───────┘
            │
            ▼
 ┌──────────────────┐
 │  인간 PR 리뷰     │  ← 결정론적 노드 (필수 종단 게이트)
 │  [에이전트 불가]  │     에이전트가 절대 우회할 수 없음
 └──────────┬───────┘
            │
            ▼
          [병합]
```

### 2.3 "벽이 모델보다 중요하다"

Stripe의 핵심 통찰은 다음 한 문장으로 요약된다.

> **"The walls matter more than the model."**
> (벽이 모델보다 중요하다.)

그리고 더 구체적으로:

> **"Putting LLMs into contained boxes compounds into system-wide reliability upside."**
> (LLM을 제한된 상자에 넣는 것이 시스템 전체의 신뢰성을 복리로 향상시킨다.)

이 철학의 실증: Stripe는 주당 1,300개 이상의 PR을 1조 달러 이상의 결제 코드베이스에 병합한다. 이것은 모델의 지능이 아니라 **결정론적 게이트의 중첩**이 만든 결과다.

### 2.4 결정론적 노드의 특성 분석

Stripe Blueprint에서 결정론적 노드의 공통 특성은 다음과 같다.

| 특성 | 설명 | 예시 |
|------|------|------|
| 예측 가능한 출력 | 동일 입력 → 항상 동일 출력 | lint 결과, CI 통과/실패 |
| 인간이 검증 가능 | 결과를 사람이 직접 확인 가능 | git log, 테스트 보고서 |
| LLM 호출 없음 | 순수 코드/스크립트로 실행 | bash 스크립트, CI 파이프라인 |
| 게이트 역할 | 통과/실패로 다음 노드 제어 | lint 통과 → 다음 단계 |
| 컨텍스트 하이드레이션 | **에이전트 루프 이전에 실행** | 코드 검색, 문서 로드 |

**중요 포인트**: 컨텍스트 하이드레이션(Context Hydration)은 결정론적 노드다. LLM에게 관련 컨텍스트를 주입하는 과정이 에이전트 루프가 시작되기 **전에** 결정론적으로 실행된다.

### 2.5 Blueprint를 구현하려면 무엇이 필요한가

이 Blueprint를 실제로 구현하기 위해 필요한 기술적 요소는 다음과 같다.

1. **도구 호출 차단 능력**: 에이전트 노드에서 결정론적 노드로 제어를 이전하는 하드 게이트
2. **LLM 컨텍스트 수정 능력**: 매 LLM 호출 전에 결정론적으로 메시지를 주입/수정
3. **도구 가시성 제어 능력**: 상태머신의 현재 상태에 따라 LLM에게 보이는 도구를 제한
4. **시스템 프롬프트 교체 능력**: 에이전트 시작 시 동적으로 지침을 주입
5. **도구 결과 수정 능력**: LLM이 보는 도구 실행 결과를 미들웨어로 가공

이 다섯 가지 능력을 가장 완전하게, 가장 낮은 추상화 레벨에서 제공하는 프레임워크가 최적이다.

---

## 3. 결정론적 코드 주입 비교 프레임워크

### 3.1 무엇을 평가할 것인가

세 프레임워크를 비교하기 위해 다음 여섯 가지 핵심 능력을 평가 기준으로 정의한다.

| 능력 번호 | 능력명 | 설명 |
|-----------|--------|------|
| C1 | 하드 블로킹 | 도구 호출을 즉시, 인프로세스로 차단하는 능력 |
| C2 | LLM 컨텍스트 주입 | 매 LLM API 호출 전 메시지 배열을 수정하는 능력 |
| C3 | 시스템 프롬프트 교체 | 에이전트 시작 시 시스템 프롬프트를 동적으로 교체하는 능력 |
| C4 | 도구 결과 수정 | LLM이 받는 도구 실행 결과를 미들웨어로 가공하는 능력 |
| C5 | 도구 가시성 제어 | 상태에 따라 LLM에게 보이는 도구를 동적으로 제한하는 능력 |
| C6 | 상태 영속성 | 결정론적 상태를 세션 간에 유지하는 능력 |

### 3.2 프레임워크별 이벤트 수 비교

```
이벤트 수 = 개입(intervention) 기회의 수

Pi SDK:              ████████████████████████████  28개
Claude Code:         █████████████████            17개
OpenAI Agents SDK:   ███████                       7개 (RunHooks 기준)
                                                   (Guardrails 별도)
```

이벤트 수 자체가 전부는 아니지만, 결정론적 게이트를 삽입할 수 있는 기회의 수를 의미한다. Pi SDK는 Claude Code보다 11개(65%) 더 많은 개입 지점을 제공한다.

### 3.3 구현 방식의 차이: 인프로세스 vs 서브프로세스

이것은 단순한 편의성 차이가 아니라 아키텍처적 차이다.

```
Claude Code 훅 실행 방식:
──────────────────────────
Claude Code 프로세스
    │
    │ 훅 트리거
    ▼
셸 서브프로세스 생성 (fork/exec)
    │
    │ 환경 변수, JSON stdin 전달
    ▼
bash/python 스크립트 실행
    │
    │ stdout JSON 파싱
    ▼
결과를 Claude Code 프로세스에 반환

오버헤드: 프로세스 생성, IPC, JSON 직렬화/역직렬화
상태 공유: 없음 (각 훅 호출은 독립적)


Pi SDK 훅 실행 방식:
──────────────────────────
Pi 에이전트 프로세스 (Node.js)
    │
    │ 이벤트 발생
    ▼
TypeScript 핸들러 함수 (동일 프로세스)
    │
    │ 직접 메모리 접근
    ▼
상태 변수, 클로저, 클래스 인스턴스 접근

오버헤드: 함수 호출 오버헤드만
상태 공유: 완전한 인프로세스 상태 공유 가능
```

인프로세스 실행의 핵심 장점: **핸들러 간에 TypeScript 변수를 직접 공유할 수 있다.** 상태머신의 현재 상태를 메모리 변수로 관리하고, 모든 이벤트 핸들러가 동일한 상태에 접근한다. Claude Code 훅은 이것이 불가능하다.

---

## 4. Pi SDK 상세 분석

### 4.1 이전 평가의 정정

`pi_sdk_evaluation_report.md`에서 Pi SDK의 `tool_call` 이벤트에 대해 다음과 같이 기술했다.

> "관찰(observational) 중심으로 설계되어 있으며 도구 실행을 강제로 차단하는 enforcement 메커니즘이 명시적이지 않다."

이것은 오류다. Pi SDK의 공식 문서(extensions.md)는 다음을 명시한다.

```typescript
// Pi SDK 공식 문서에서 확인된 실제 API
session.on("tool_call", async (event) => {
  if (shouldBlock(event.toolName)) {
    return { block: true, reason: "이 도구는 현재 상태에서 허용되지 않습니다." };
  }
  // undefined 반환 시 정상 실행
});
```

`return { block: true, reason: "..." }` 은 도구 실행을 완전히 차단하고 LLM에게 차단 이유를 피드백으로 반환한다. 이것은 Claude Code의 `permissionDecision: "deny"` 패턴과 구조적으로 동일하며, 서브프로세스 없이 인프로세스로 실행된다는 점에서 오히려 더 강력하다.

### 4.2 Pi SDK 28개 이벤트 완전 분류

Pi SDK v0.55.4 (2026년 3월 2일 릴리스)의 이벤트 시스템을 범주별로 정리한다.

#### 범주 1: 리소스 (1개)

| 이벤트명 | 발생 시점 | 결정론적 주입 활용 |
|---------|-----------|------------------|
| `resource` | 리소스 로드 시 | 외부 설정, 규칙 파일 로드 검증 |

#### 범주 2: 세션 (10개)

| 이벤트명 | 발생 시점 | 결정론적 주입 활용 |
|---------|-----------|------------------|
| `session_before_start` | 세션 시작 직전 | 환경 초기화, 스펙 파일 존재 검증 |
| `session_after_start` | 세션 시작 직후 | 초기 상태 변수 설정 |
| `session_before_compact` | 컨텍스트 압축 직전 | 중요 상태 보존 |
| `session_after_compact` | 컨텍스트 압축 직후 | 압축 후 상태 복원 |
| `session_before_switch` | 세션 전환 직전 | 현재 세션 상태 저장 |
| `session_after_switch` | 세션 전환 직후 | 새 세션 상태 로드 |
| `session_before_resume` | 세션 재개 직전 | 재개 시 결정론적 컨텍스트 재주입 |
| `session_after_resume` | 세션 재개 직후 | 재개 후 상태 검증 |
| `session_before_end` | 세션 종료 직전 | **필수 아티팩트 검증, 미완료 시 차단** |
| `session_after_end` | 세션 종료 직후 | 감사 로그 기록 |

#### 범주 3: 에이전트 생명주기 (7개)

| 이벤트명 | 발생 시점 | 결정론적 주입 활용 |
|---------|-----------|------------------|
| `before_agent_start` | 에이전트 루프 시작 직전 | **시스템 프롬프트 교체, 컨텍스트 주입** |
| `after_agent_end` | 에이전트 루프 완료 직후 | 완료 아티팩트 검증 |
| `turn_start` | 각 턴(LLM 호출) 시작 | 턴별 결정론적 컨텍스트 갱신 |
| `turn_end` | 각 턴 완료 | 턴 결과 검증, 상태 전환 |
| `first_token` | 첫 토큰 생성 시 | 응답 시작 모니터링 |
| `error` | 에러 발생 시 | 에러 분류, 결정론적 복구 로직 |
| `abort` | 에이전트 중단 시 | 중단 이유 기록, 상태 롤백 |

#### 범주 4: 메시지 스트리밍 (3개)

| 이벤트명 | 발생 시점 | 결정론적 주입 활용 |
|---------|-----------|------------------|
| `message_start` | 메시지 스트림 시작 | 스트리밍 세션 초기화 |
| `message_delta` | 스트리밍 청크 수신 | 실시간 콘텐츠 모니터링 |
| `message_end` | 메시지 완료 | 완성된 메시지 후처리 |

#### 범주 5: 도구 실행 (3개)

| 이벤트명 | 발생 시점 | 결정론적 주입 활용 |
|---------|-----------|------------------|
| `tool_start` | 도구 실행 시작 | 실행 전 사전 조건 검증 |
| `tool_end` | 도구 실행 완료 | 실행 결과 검증, 상태 전환 트리거 |
| `tool_error` | 도구 실행 에러 | 에러 분류, 재시도 정책 결정 |

#### 범주 6: 도구 인터셉션 (2개) — 핵심 차별화 기능

| 이벤트명 | 발생 시점 | 결정론적 주입 활용 |
|---------|-----------|------------------|
| `tool_call` | 도구 호출 직전 | **하드 블로킹** — `return { block: true, reason }` |
| `tool_result` | 도구 결과 처리 시 | **미들웨어 체인** — LLM이 보는 결과 수정 |

#### 범주 7: 입력/bash (2개)

| 이벤트명 | 발생 시점 | 결정론적 주입 활용 |
|---------|-----------|------------------|
| `input` | 사용자 입력 수신 | 입력 전처리, 스펙 파일 연동 |
| `bash` | bash 명령 실행 | bash 명령 감사, 위험 명령 차단 |

#### 범주 8: 컨텍스트 주입 (1개) — Pi SDK 고유 기능

| 이벤트명 | 발생 시점 | 결정론적 주입 활용 |
|---------|-----------|------------------|
| `context` | **모든 LLM API 호출 직전** | **전체 메시지 배열 인터셉트/수정** |

### 4.3 Pi SDK 핵심 차별화 기능 상세

#### 4.3.1 `context` 이벤트 — Pi SDK 고유, 가장 강력한 기능

`context` 이벤트는 Pi SDK에서만 제공하는 고유 기능이다. 이 이벤트는 **모든 단일 LLM API 호출 직전에** 발화하며, 핸들러는 LLM에 전달될 전체 메시지 배열을 수정하여 반환할 수 있다.

```typescript
// context 이벤트: 모든 LLM 호출 전 메시지 배열 인터셉트
session.on("context", async (event) => {
  const messages = event.messages;

  // 스펙 파일을 결정론적으로 읽어 모든 LLM 호출에 주입
  const specContent = await fs.readFile("SPEC.md", "utf-8");
  const specVersion = await getSpecVersion(); // git hash 등

  // 메시지 배열 앞에 결정론적 컨텍스트 주입
  return [
    {
      role: "system",
      content: `[결정론적 컨텍스트 - 매 호출 주입]
스펙 버전: ${specVersion}
현재 상태: ${getCurrentState()}
허용된 작업: ${getAllowedActions().join(", ")}

--- SPEC.md 내용 ---
${specContent}
`
    },
    ...messages
  ];
});
```

이것이 Claude Code에서 불가능한 이유: Claude Code에는 "모든 LLM 호출 전에 발화하는" 이벤트가 없다. `UserPromptSubmit`은 사용자 입력 시 한 번만 발화하며, 에이전트 루프 내의 중간 LLM 호출에는 개입할 수 없다.

#### 4.3.2 `tool_call` — 하드 블로킹 인터셉터

```typescript
// 린트 게이트: 코드 작성 전 린트 통과 강제
session.on("tool_call", async (event) => {
  if (event.toolName === "bash") {
    const command = event.params.command as string;

    // git commit 시도 감지
    if (command.includes("git commit")) {
      // 결정론적 린트 실행
      const lintResult = await runLint();
      if (!lintResult.passed) {
        return {
          block: true,
          reason: `린트 게이트 실패. 커밋 차단됨.\n${lintResult.errors.join("\n")}\n\n린트 오류를 수정한 후 다시 커밋하십시오.`
        };
      }

      // 결정론적 테스트 실행
      const testResult = await runTests();
      if (!testResult.passed) {
        return {
          block: true,
          reason: `테스트 게이트 실패. 커밋 차단됨.\n실패한 테스트: ${testResult.failed.join(", ")}\n\n모든 테스트가 통과한 후 커밋하십시오.`
        };
      }
    }

    // 위험한 명령 차단
    if (isDangerousCommand(command)) {
      return {
        block: true,
        reason: `위험 명령 차단: ${command}`
      };
    }
  }
  // undefined 반환 시 정상 실행
});
```

#### 4.3.3 `before_agent_start` — 시스템 프롬프트 교체와 컨텍스트 주입

```typescript
// before_agent_start: 에이전트 루프 시작 전 시스템 프롬프트 동적 교체
session.on("before_agent_start", async () => {
  const planModeEnabled = getState("planModeEnabled");
  const currentPhase = getState("currentPhase");
  const pendingSpec = await loadPendingSpec();

  if (planModeEnabled) {
    return {
      // 기존 시스템 프롬프트를 완전히 교체
      systemPrompt: `[계획 모드 활성화]
당신은 지금 계획 수립 단계에 있습니다. 코드를 작성하거나 파일을 수정하지 마십시오.
현재 태스크를 분석하고 구현 계획만을 작성하십시오.
계획이 승인되면 실행 모드로 전환됩니다.`,
      // 추가 컨텍스트 메시지 주입
      message: {
        customType: "plan-mode-context",
        content: `[계획 모드 컨텍스트]
스펙: ${pendingSpec}
현재 Phase: ${currentPhase}
허용 작업: 분석, 설계, 계획 수립만`,
        display: false // UI에 표시하지 않음
      }
    };
  }
});
```

#### 4.3.4 `tool_result` — LLM이 보는 도구 결과 수정

```typescript
// tool_result: LLM이 받는 도구 결과를 미들웨어로 가공
session.on("tool_result", async (event) => {
  if (event.toolName === "bash" && event.result.includes("error")) {
    // 린트 결과를 구조화된 형식으로 변환하여 LLM에 전달
    const parsedErrors = parseLintErrors(event.result);
    return {
      // LLM이 받는 결과를 수정
      result: JSON.stringify({
        status: "lint_errors",
        errorCount: parsedErrors.length,
        errors: parsedErrors,
        instruction: "위의 린트 오류를 모두 수정하십시오."
      })
    };
  }
  // undefined 반환 시 원본 결과 그대로 LLM에 전달
});
```

#### 4.3.5 `setActiveTools()` — 상태머신 기반 도구 가시성 제어

```typescript
// 상태머신 전환 시 LLM에게 보이는 도구를 동적으로 제한
const STATE_TOOLS = {
  "planning": ["read_file", "search_code", "list_directory"],
  "implementing": ["read_file", "write_file", "edit_file", "bash"],
  "testing": ["bash", "read_file"],
  "committing": ["bash"],  // git 명령만
};

session.on("turn_end", async (event) => {
  const currentState = getState("currentPhase");
  const allowedTools = STATE_TOOLS[currentState];

  // LLM이 볼 수 있는 도구를 현재 상태로 제한
  session.setActiveTools(allowedTools);
});
```

#### 4.3.6 `pi.appendEntry()` — 세션 트리 인식 상태 영속성

```typescript
// 결정론적 상태를 JSONL 파일에 세션 트리 구조로 저장
await session.appendEntry({
  type: "deterministic-gate",
  timestamp: new Date().toISOString(),
  gate: "lint-check",
  result: "passed",
  details: {
    errorsFound: 0,
    filesChecked: 12,
    specVersion: currentSpecVersion
  }
});

// 추적성 매트릭스 업데이트 기록
await session.appendEntry({
  type: "traceability",
  specId: "REQ-042",
  implementedIn: "src/auth/login.ts",
  testIds: ["TEST-101", "TEST-102"],
  timestamp: new Date().toISOString()
});
```

### 4.4 계획 모드 상태머신 예제 — 이미 검증된 패턴

Pi SDK의 공식 확장 예제에는 3-상태 상태머신이 계획 모드로 구현되어 있다. 이것은 이론이 아니라 검증된 패턴이다.

```typescript
// 3-상태 상태머신: planModeEnabled / executionMode / todoItems
// Pi SDK 공식 확장(extensions) 예제에서 발췌

let planModeEnabled = false;
let todoItems: string[] = [];
let executionMode = false;

// 상태 1: 계획 모드 — bash 명령 차단
session.on("tool_call", async (event) => {
  if (!planModeEnabled || event.toolName !== "bash") return;

  const command = event.params.command as string;
  if (!isSafeReadCommand(command)) {
    return {
      block: true,
      reason: `계획 모드 활성화: ${command} 명령이 차단되었습니다. 계획 수립 단계에서는 읽기 전용 명령만 허용됩니다.`
    };
  }
});

// 상태 2: 계획 모드 컨텍스트 주입
session.on("before_agent_start", async () => {
  if (planModeEnabled) {
    return {
      message: {
        customType: "plan-mode-context",
        content: `[계획 모드 활성화]
현재 미결 태스크: ${todoItems.join(", ")}
지침: 코드 수정 없이 분석과 계획만 수행하십시오.
계획 완료 후 '/execute' 명령으로 실행 모드 전환 가능합니다.`,
        display: false
      }
    };
  }
});

// 상태 3: 실행 모드 전환 시 도구 가시성 갱신
session.on("input", async (event) => {
  if (event.input.trim() === "/execute") {
    planModeEnabled = false;
    executionMode = true;
    session.setActiveTools(["read_file", "write_file", "edit_file", "bash"]);
  }
  if (event.input.trim() === "/plan") {
    planModeEnabled = true;
    executionMode = false;
    session.setActiveTools(["read_file", "bash"]); // 읽기 전용만
  }
});
```

이 예제가 증명하는 것: Pi SDK는 상태머신 구현을 위한 도구를 이미 제공하고 있으며, 이것이 의도된 사용 패턴이다.

### 4.5 활발한 유지보수 — 이전 평가 정정

`pi_sdk_evaluation_report.md`에서 Pi SDK의 가장 큰 위험 중 하나로 "OSS vacation (2026-03-02까지 일시 중단)"을 지적했다.

**이 우려는 이제 해소되었다.**

- Mario Zechner의 예정된 복귀일: 2026년 3월 2일
- **Pi SDK v0.55.4: 2026년 3월 2일 릴리스** (바로 오늘)

즉, Zechner는 복귀 즉시 새 버전을 릴리스했다. 이것은 프로젝트가 활발하게 유지보수되고 있음을 의미한다.

추가적으로:
- MIT 라이선스: 포킹 및 자체 유지 완전 허용
- 소규모 코드베이스(약 70개 확장 예제 포함): 포킹 용이
- 약 70개의 공식 확장 예제: 패턴 참조 충분
- 17,300+ GitHub Stars: 커뮤니티 관심 지속

### 4.6 Pi SDK 능력 평가 요약

| 능력 | Pi SDK | 구현 방법 |
|------|--------|----------|
| C1: 하드 블로킹 | 인프로세스, 동기적 | `tool_call` → `{ block: true }` |
| C2: LLM 컨텍스트 주입 | 모든 LLM 호출에 | `context` 이벤트 |
| C3: 시스템 프롬프트 교체 | 에이전트 시작마다 | `before_agent_start` |
| C4: 도구 결과 수정 | 미들웨어 체인 | `tool_result` |
| C5: 도구 가시성 제어 | 완전한 상태머신 | `setActiveTools()` |
| C6: 상태 영속성 | 세션 트리 인식 | `pi.appendEntry()` |

**여섯 가지 핵심 능력 모두 완전히 지원한다.**

---

## 5. Claude Code Hook 시스템 분석

### 5.1 Claude Code 17개 이벤트 분류

Claude Code는 4가지 핸들러 유형과 17개 이벤트를 제공한다.

#### 핸들러 유형별 분류

```
command 핸들러: 셸 명령 실행 (모든 훅의 기본 타입)
http 핸들러: HTTP 요청
prompt 핸들러: 프롬프트 수정
agent 핸들러: 에이전트 수준 제어
```

#### 17개 이벤트 목록

| 이벤트명 | 카테고리 | 차단 능력 | 결정론적 활용 |
|---------|---------|-----------|-------------|
| `PreToolUse` | 도구 제어 | `permissionDecision: "deny"` | 린트 게이트, 쓰기 차단 |
| `PostToolUse` | 도구 제어 | `decision: "block"` | 결과 검증 |
| `UserPromptSubmit` | 입력 제어 | exit 2로 차단 | 스펙 컨텍스트 주입 |
| `Stop` | 완료 제어 | `continue: true`로 강제 재개 | 필수 아티팩트 검증 |
| `SubagentStop` | 서브에이전트 | exit 2로 차단 | 서브에이전트 결과 검증 |
| `SessionStart` | 세션 | 없음 | 환경 초기화 |
| `TaskCompleted` | 태스크 | exit 2로 차단 | 완료 조건 강제 |
| `TeammateIdle` | 팀 제어 | 작업 강제 | 멀티에이전트 조율 |
| `ConfigChange` | 설정 | 변경 차단 | 설정 보호 |
| `PreBash` | bash | 차단 가능 | bash 명령 감사 |
| `PostBash` | bash | 없음 | bash 결과 처리 |
| `PreEdit` | 편집 | 차단 가능 | 편집 내용 검증 |
| `PostEdit` | 편집 | 없음 | 편집 후 린트 |
| `PreRead` | 읽기 | 차단 가능 | 접근 제어 |
| `Notification` | 알림 | 없음 | 상태 모니터링 |
| `MCPToolCall` | MCP | 차단 가능 | MCP 도구 게이팅 |
| `MCPToolResult` | MCP | 없음 | MCP 결과 처리 |

### 5.2 Claude Code의 강점

#### PreToolUse — 도구 실행 전 결정론적 게이트

```bash
#!/bin/bash
# PreToolUse 훅: 파일 쓰기 전 린트 게이트
TOOL_NAME="$CLAUDE_TOOL_NAME"
FILE_PATH="$CLAUDE_TOOL_INPUT_FILE_PATH"

if [[ "$TOOL_NAME" == "Write" && "$FILE_PATH" == *.ts ]]; then
  # 결정론적 린트 실행
  LINT_RESULT=$(eslint "$FILE_PATH" --format json 2>&1)
  LINT_ERRORS=$(echo "$LINT_RESULT" | jq '.[0].errorCount // 0')

  if [ "$LINT_ERRORS" -gt 0 ]; then
    echo "{\"permissionDecision\": \"deny\", \"denyReason\": \"린트 오류 ${LINT_ERRORS}건 발견. 오류 수정 후 다시 쓰십시오.\"}"
    exit 0
  fi
fi

echo '{"permissionDecision": "allow"}'
```

#### Stop — 완료 조건 강제 (ISO 26262에서 핵심)

```bash
#!/bin/bash
# Stop 훅: 필수 아티팩트 없으면 에이전트 재개 강제
REQUIRED_FILES=(
  "docs/spec.md"
  "docs/traceability-matrix.md"
  "tests/unit/*.test.ts"
)

for file in "${REQUIRED_FILES[@]}"; do
  if ! ls $file 2>/dev/null | head -1 > /dev/null; then
    echo "{\"continue\": true, \"reason\": \"${file} 누락. 이 파일을 생성한 후 완료할 수 있습니다.\"}"
    exit 0
  fi
done

echo '{"continue": false}'
```

#### UserPromptSubmit — 스펙 우선 컨텍스트 주입

```bash
#!/bin/bash
# UserPromptSubmit 훅: 모든 프롬프트에 스펙 컨텍스트 주입
SPEC_CONTENT=$(cat SPEC.md 2>/dev/null || echo "스펙 파일 없음")
SPEC_VERSION=$(git log -1 --format="%h" -- SPEC.md 2>/dev/null || echo "unknown")

echo "{\"additionalContext\": \"[스펙 우선 컨텍스트 - 버전 ${SPEC_VERSION}]\\n${SPEC_CONTENT}\"}"
```

#### 훅 범위 시스템 — 기업 환경의 강점

Claude Code의 훅 범위 시스템은 기업 환경에서 강력하다.

```
범위 우선순위 (낮은 번호 = 더 높은 우선순위):
1. 엔터프라이즈 정책 (org 수준, 사용자 오버라이드 불가)
2. 프로젝트 수준 (.claude/settings.json, git 추적 가능)
3. 로컬 수준 (.claude/settings.local.json, git 비추적)
4. 글로벌 수준 (~/.claude/settings.json)
5. 플러그인 수준
```

`.claude/settings.json`은 git으로 추적되므로 팀 전체에 결정론적 훅 설정을 배포할 수 있다.

### 5.3 Claude Code의 한계

#### 한계 1: 서브프로세스 오버헤드

모든 훅은 셸 서브프로세스로 실행된다. 이는 다음을 의미한다.

- 각 훅 호출마다 프로세스 생성 오버헤드
- 훅 간 상태 공유 불가 (환경 변수 또는 파일을 통해서만 가능)
- JSON 직렬화/역직렬화 오버헤드

#### 한계 2: `context` 이벤트 없음

Claude Code에는 Pi SDK의 `context` 이벤트에 해당하는 기능이 없다. 에이전트 루프 내의 모든 중간 LLM 호출에 결정론적 컨텍스트를 주입하는 것이 불가능하다.

`UserPromptSubmit`은 사용자가 프롬프트를 제출할 때 한 번만 발화한다. 에이전트가 내부적으로 여러 번의 LLM 호출을 수행하는 동안, 중간 호출에 컨텍스트를 주입할 방법이 없다.

#### 한계 3: 도구 결과 수정 불가

Claude Code의 `PostToolUse`는 도구 결과를 **관찰**할 수 있지만, LLM이 받는 결과를 **수정**할 수 없다. Pi SDK의 `tool_result` 이벤트와 달리, 도구 결과 미들웨어가 없다.

#### 한계 4: 훅 간 상태 공유 불가

모든 훅이 독립적인 서브프로세스로 실행되므로, TypeScript 변수나 클래스 인스턴스를 훅 간에 공유할 수 없다. 상태 공유는 파일 시스템(JSON 파일 등)을 통해서만 가능하며, 이는 레이스 컨디션과 직렬화 오버헤드를 수반한다.

### 5.4 Claude Code 능력 평가 요약

| 능력 | Claude Code | 구현 방법 | 한계 |
|------|-------------|----------|------|
| C1: 하드 블로킹 | 서브프로세스 | `PreToolUse` deny | 오버헤드 있음 |
| C2: LLM 컨텍스트 주입 | 부분적 | `UserPromptSubmit` additionalContext | 첫 프롬프트만 |
| C3: 시스템 프롬프트 교체 | 없음 | 해당 없음 | 불가 |
| C4: 도구 결과 수정 | 없음 | 해당 없음 | 불가 |
| C5: 도구 가시성 제어 | 없음 | 해당 없음 | 불가 |
| C6: 상태 영속성 | 부분적 | transcript_path | 훅 간 공유 불가 |

---

## 6. OpenAI Agents SDK 분석

### 6.1 RunHooks — 관찰 전용 설계

OpenAI Agents SDK의 RunHooks는 **명시적으로 관찰(observation) 전용으로 설계**되었다. 모든 훅 메서드는 `None`을 반환한다.

```python
from agents import RunHooks, Agent, RunContextWrapper
from typing import Any

class ReliableDevHooks(RunHooks):
    async def on_agent_start(
        self,
        context: RunContextWrapper,
        agent: Agent
    ) -> None:  # 반환값 없음 — 관찰만 가능
        print(f"에이전트 시작: {agent.name}")
        # 실행 차단 불가

    async def on_tool_start(
        self,
        context: RunContextWrapper,
        agent: Agent,
        tool: Any
    ) -> None:  # 반환값 없음 — 관찰만 가능
        print(f"도구 시작: {tool.name}")
        # tool 실행 차단 불가
        # 예외 발생 시 전체 실행 오류로 처리됨 (의도된 사용 패턴 아님)

    async def on_llm_end(
        self,
        context: RunContextWrapper,
        agent: Agent,
        response: Any
    ) -> None:  # 반환값 없음 — 관찰만 가능
        print(f"LLM 응답 완료")
        # 응답 수정 불가
```

#### 알려진 RunHooks 버그

- `on_llm_start` / `on_llm_end`: RunHooks에서는 동작하지 않음. AgentHooks에서만 동작. (Issue #1612, 미해결)
- `on_run_start` / `on_run_end`: "Not Planned"으로 종료됨 (Issue #2016, 2025년 12월)
- 호스팅 도구(web search, code interpreter)에서는 tool 훅이 발화하지 않음 (Issue #1889)

### 6.2 Guardrails — 실제 게이트 메커니즘

RunHooks가 관찰 전용인 반면, **Guardrails가 OpenAI Agents SDK의 실제 게이팅 메커니즘**이다.

```python
from agents import (
    Agent, Runner, RunContextWrapper,
    input_guardrail, output_guardrail,
    tool_input_guardrail, tool_output_guardrail,
    GuardrailFunctionOutput, InputGuardrailTripwireTriggered
)

# 입력 가드레일: 에이전트 시작 시 스펙 검증
@input_guardrail
async def spec_first_guardrail(
    context: RunContextWrapper,
    agent: Agent,
    input: str
) -> GuardrailFunctionOutput:
    # 스펙 파일 존재 여부 결정론적 검증
    spec_exists = os.path.exists("SPEC.md")
    spec_has_requirements = validate_spec_format("SPEC.md") if spec_exists else False

    if not spec_exists or not spec_has_requirements:
        return GuardrailFunctionOutput(
            output_info="스펙 파일 없음 또는 형식 오류",
            tripwire_triggered=True  # 실행 중단
        )

    return GuardrailFunctionOutput(
        output_info="스펙 검증 통과",
        tripwire_triggered=False
    )

# 도구 입력 가드레일: bash 명령 실행 전 린트 게이트
@tool_input_guardrail(tool_name="bash")
async def lint_gate_guardrail(
    context: RunContextWrapper,
    agent: Agent,
    input: Any
) -> GuardrailFunctionOutput:
    command = input.get("command", "")

    if "git commit" in command:
        # 결정론적 린트 실행
        lint_result = subprocess.run(
            ["eslint", ".", "--format", "json"],
            capture_output=True, text=True
        )
        lint_data = json.loads(lint_result.stdout)
        error_count = sum(f["errorCount"] for f in lint_data)

        if error_count > 0:
            return GuardrailFunctionOutput(
                output_info=f"린트 오류 {error_count}건. 커밋 차단.",
                tripwire_triggered=True  # 실행 중단
            )

    return GuardrailFunctionOutput(
        output_info="린트 검증 통과",
        tripwire_triggered=False
    )

# 에이전트에 가드레일 적용
agent = Agent(
    name="reliable_dev_agent",
    model="gpt-4o",
    input_guardrails=[spec_first_guardrail],
    tools=[bash_tool, write_file_tool, read_file_tool]
)
```

#### 가드레일의 특성

- **모든 가드레일은 예외(tripwire)로 실행을 중단**: `tripwire_triggered=True` 시 `InputGuardrailTripwireTriggered` 예외 발생
- **입력 가드레일은 에이전트 실행과 병렬로 시작 가능**: 성능 최적화
- **LLM 평가 vs 결정론적 평가**: 가드레일 내부 로직을 개발자가 완전히 제어. 결정론적 Python 코드로 구현 가능

### 6.3 `is_enabled` — 동적 도구 은폐

```python
import json

def load_current_state():
    with open("workflow_state.json") as f:
        return json.load(f)

# 현재 상태에 따라 도구를 LLM 시야에서 은폐
@function_tool(
    is_enabled=lambda ctx, agent: load_current_state()["phase"] == "implementing"
)
def write_file(path: str, content: str) -> str:
    """파일 쓰기: implementing 단계에서만 활성화"""
    with open(path, "w") as f:
        f.write(content)
    return f"파일 작성 완료: {path}"

@function_tool(
    is_enabled=lambda ctx, agent: load_current_state()["phase"] == "testing"
)
def run_tests(test_pattern: str) -> str:
    """테스트 실행: testing 단계에서만 활성화"""
    result = subprocess.run(
        ["pytest", test_pattern, "--json-report"],
        capture_output=True, text=True
    )
    return result.stdout
```

`is_enabled`는 "차단(block)"이 아닌 "은폐(hide)"다. LLM이 해당 도구의 존재 자체를 알지 못하므로, 잘못된 도구를 선택하려는 시도조차 발생하지 않는다. 이것은 일부 시나리오에서 블로킹보다 더 강력한 방어 전략이다.

### 6.4 내장 추적 시스템 — OpenAI Agents SDK의 실질적 강점

OpenAI Agents SDK의 가장 뚜렷한 강점은 **내장 추적(tracing) 시스템**이다.

```python
from agents import trace, custom_span

# 결정론적 게이트를 추적 스팬으로 감싸기
async def run_with_tracing():
    with trace("reliable-dev-workflow"):
        # 결정론적 노드를 커스텀 스팬으로 기록
        with custom_span("lint-gate"):
            lint_result = run_lint()

        with custom_span("spec-validation"):
            spec_result = validate_spec()

        # 에이전트 실행
        result = await Runner.run(
            agent,
            "구현 태스크",
            hooks=dev_hooks
        )
```

- 모든 LLM 호출, 도구 실행, 가드레일 평가에 자동으로 스팬 생성
- `trace_metadata`: 결정론적 메타데이터 첨부 가능
- Datadog, Langfuse, Weights & Biases 통합 내장
- 양방향 추적성을 위한 구조화된 감사 추적

### 6.5 LangGraph — 상태머신 오케스트레이션 (별도 프레임워크)

OpenAI Agents SDK 자체는 상태머신 오케스트레이션을 제공하지 않는다. 이를 위해 **LangGraph**(v1.0, 2025년 10월)를 별도로 사용한다.

```python
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

# Stripe Minions 패턴을 LangGraph 상태머신으로 구현
class DevWorkflowState(TypedDict):
    task: str
    spec_loaded: bool
    lint_passed: bool
    tests_passed: bool
    ci_attempts: int
    ready_for_review: bool

def build_workflow():
    workflow = StateGraph(DevWorkflowState)

    # 결정론적 노드 추가
    workflow.add_node("hydrate_context", hydrate_context_node)  # 결정론적
    workflow.add_node("lint_gate", lint_gate_node)               # 결정론적
    workflow.add_node("test_gate", test_gate_node)               # 결정론적
    workflow.add_node("ci_gate", ci_gate_node)                   # 결정론적

    # 에이전트 노드 추가
    workflow.add_node("implement", agent_implement_node)          # 비결정론적
    workflow.add_node("fix_ci", agent_fix_ci_node)               # 비결정론적

    # 상태 전환 엣지
    workflow.add_edge(START, "hydrate_context")
    workflow.add_edge("hydrate_context", "implement")
    workflow.add_conditional_edges(
        "implement",
        lambda s: "lint_gate" if s["code_written"] else "implement"
    )
    workflow.add_conditional_edges(
        "lint_gate",
        lambda s: "test_gate" if s["lint_passed"] else "implement"
    )
    workflow.add_conditional_edges(
        "ci_gate",
        lambda s: END if s["ci_attempts"] >= 2 else "fix_ci"
    )

    return workflow.compile(checkpointer=MemorySaver())
```

LangGraph는 강력하지만 별도의 의존성이다. OpenAI Agents SDK + LangGraph = 두 프레임워크의 학습 비용.

### 6.6 Temporal — 내구성 있는 워크플로우

크래시 복구가 필요한 장기 실행 워크플로우에는 Temporal을 사용할 수 있다.

```python
from temporalio import workflow, activity

@activity.defn
async def run_lint_gate() -> bool:
    """결정론적 린트 게이트 — Temporal 액티비티"""
    result = subprocess.run(["eslint", "."], capture_output=True)
    return result.returncode == 0

@workflow.defn
class DevWorkflow:
    @workflow.run
    async def run(self, task: str) -> str:
        # 결정론적 노드를 Temporal 액티비티로 실행
        await workflow.execute_activity(
            run_lint_gate,
            schedule_to_close_timeout=timedelta(minutes=5)
        )
        # 크래시 후 재시작 시 이 지점부터 재개
```

### 6.7 OpenAI Agents SDK 능력 평가 요약

| 능력 | OpenAI Agents SDK | 구현 방법 | 한계 |
|------|------------------|----------|------|
| C1: 하드 블로킹 | Guardrails로 가능 | `tripwire_triggered=True` | RunHooks는 불가 |
| C2: LLM 컨텍스트 주입 | `call_model_input_filter` | RunConfig 설정 | 제한적 |
| C3: 시스템 프롬프트 교체 | 없음 | 해당 없음 | 불가 |
| C4: 도구 결과 수정 | `tool_output_guardrail` | 가드레일 | 부분적 |
| C5: 도구 가시성 제어 | `is_enabled` lambda | 동적 은폐 | 블로킹 아닌 은폐 |
| C6: 상태 영속성 | 내장 추적 + LangGraph | 풍부한 옵션 | LangGraph 별도 필요 |

---

## 7. 시나리오별 비교

### 7.1 시나리오 1: 스펙 우선 (Spec-First)

**요건**: 스펙 파일(SPEC.md)을 먼저 작성하지 않으면 구현을 시작할 수 없다.

| 구현 방법 | Pi SDK | Claude Code | OpenAI Agents SDK |
|---------|--------|-------------|------------------|
| 메커니즘 | `context` + `before_agent_start` 시스템 프롬프트 교체 | `UserPromptSubmit` exit 2 | 입력 가드레일 |
| 강제 방법 | 인프로세스 TypeScript 함수 | 셸 서브프로세스 | Python 함수 |
| 매 LLM 호출마다 주입 | 가능 (`context` 이벤트) | 불가 | 불가 |
| 구현 복잡도 | 낮음 | 낮음 | 중간 |

```typescript
// Pi SDK: 스펙 우선 강제
session.on("context", async (event) => {
  const specExists = await fs.access("SPEC.md").then(() => true).catch(() => false);
  if (!specExists) {
    // 모든 LLM 호출을 스펙 작성 요청으로 리디렉션
    return [{
      role: "system",
      content: "SPEC.md 파일이 없습니다. 구현을 시작하기 전에 SPEC.md를 작성하십시오. 스펙에는 요건, 제약사항, 추적성 ID가 포함되어야 합니다."
    }];
  }
  // 스펙 내용을 모든 LLM 호출에 주입
  const spec = await fs.readFile("SPEC.md", "utf-8");
  return [{ role: "system", content: `[스펙 문서]\n${spec}` }, ...event.messages];
});
```

### 7.2 시나리오 2: 테스트 게이트 (Tests Must Pass Before Commit)

**요건**: 테스트가 통과하지 않으면 git commit을 실행할 수 없다.

| 구현 방법 | Pi SDK | Claude Code | OpenAI Agents SDK |
|---------|--------|-------------|------------------|
| 메커니즘 | `tool_call` 블로킹 | `PreToolUse` deny | `@tool_input_guardrail` |
| 실행 방식 | 인프로세스 | 서브프로세스 | Python 함수 |
| 에러 피드백 | `reason` 문자열 | `denyReason` | tripwire + 에러 메시지 |
| 상태 공유 | 직접 변수 공유 | 파일 시스템 | 컨텍스트 변수 |

```typescript
// Pi SDK: 테스트 게이트
session.on("tool_call", async (event) => {
  if (event.toolName === "bash") {
    const cmd = event.params.command as string;
    if (/git\s+commit/.test(cmd)) {
      const testResult = await runTestSuite(); // 결정론적 실행
      if (testResult.failed > 0) {
        return {
          block: true,
          reason: `테스트 게이트 실패: ${testResult.failed}개 테스트 실패\n` +
                  `실패 목록:\n${testResult.failedTests.join("\n")}\n\n` +
                  `모든 테스트가 통과한 후 커밋하십시오.`
        };
      }
      if (testResult.coverage < 80) {
        return {
          block: true,
          reason: `커버리지 게이트 실패: ${testResult.coverage}% (최소 80% 필요)\n` +
                  `추가 테스트를 작성하여 커버리지를 높이십시오.`
        };
      }
    }
  }
});
```

### 7.3 시나리오 3: 린트 게이트 (Lint at Specific Stages)

**요건**: 특정 단계(예: 파일 저장 후, 커밋 전)에 린트를 강제 실행한다.

| 구현 방법 | Pi SDK | Claude Code | OpenAI Agents SDK |
|---------|--------|-------------|------------------|
| 메커니즘 | `tool_result` 결과 수정 | `PostToolUse` decision:block | `@tool_output_guardrail` |
| 결과 수정 능력 | LLM이 보는 결과 직접 수정 | 없음 (관찰만) | 가드레일로 차단 |
| 린트 피드백 | 구조화된 결과로 변환 | 별도 메시지로 주입 어려움 | tripwire로 중단 |

```typescript
// Pi SDK: 파일 쓰기 후 린트 결과를 구조화하여 LLM에 전달
session.on("tool_result", async (event) => {
  if (event.toolName === "write_file") {
    const filePath = event.params.path as string;
    if (filePath.endsWith(".ts") || filePath.endsWith(".js")) {
      const lintResult = await runESLint(filePath);
      if (lintResult.errorCount > 0) {
        // LLM이 받는 도구 결과를 린트 피드백으로 교체
        return {
          result: JSON.stringify({
            fileWritten: true,
            lintStatus: "failed",
            errors: lintResult.messages.map(m => ({
              line: m.line,
              column: m.column,
              rule: m.ruleId,
              message: m.message
            })),
            instruction: "위의 린트 오류를 수정하십시오. 오류 수정 후 파일을 다시 저장하십시오."
          })
        };
      }
    }
  }
});
```

### 7.4 시나리오 4: 양방향 추적성 (Bidirectional Traceability)

**요건**: 요건 ID → 구현 → 테스트 케이스 간의 양방향 추적성을 유지한다.

| 구현 방법 | Pi SDK | Claude Code | OpenAI Agents SDK |
|---------|--------|-------------|------------------|
| 메커니즘 | `pi.appendEntry()` JSONL | transcript_path 파싱 | 내장 추적 + trace_metadata |
| 세션 인식 | 세션 트리 인식 JSONL | 세션 번호만 | 스팬 계층 구조 |
| 구조화 수준 | 완전한 커스텀 구조 | 부분적 | 높음 (Langfuse 등) |
| 외부 통합 | 직접 구현 | 없음 | Datadog/Langfuse/W&B |

```typescript
// Pi SDK: 추적성 엔트리 기록
session.on("tool_end", async (event) => {
  if (event.toolName === "write_file") {
    const filePath = event.params.path as string;

    // 추적성 엔트리를 세션 트리 인식 JSONL에 기록
    await session.appendEntry({
      type: "implementation",
      timestamp: new Date().toISOString(),
      specIds: extractSpecIds(filePath),        // 파일에서 REQ-XXX 추출
      implementedFile: filePath,
      sessionId: session.id,
      turnId: currentTurn
    });
  }

  if (event.toolName === "bash" && event.params.command.includes("test")) {
    const testResults = parseTestResults(event.result);

    await session.appendEntry({
      type: "test-execution",
      timestamp: new Date().toISOString(),
      testIds: testResults.map(t => t.id),
      passedTests: testResults.filter(t => t.passed).map(t => t.id),
      failedTests: testResults.filter(t => !t.passed).map(t => t.id)
    });
  }
});
```

### 7.5 시나리오 5: 에이전트 조기 종료 차단

**요건**: 에이전트가 태스크를 완료하지 않고 조기 종료하려 할 때 강제로 계속하게 한다.

| 구현 방법 | Pi SDK | Claude Code | OpenAI Agents SDK |
|---------|--------|-------------|------------------|
| 메커니즘 | `turn_end` + `tool_call` | `Stop` hook `continue: true` | 없음 (RunHooks에서 불가) |
| 강제 재개 | 가능 | 가능 | 불가 |

```typescript
// Pi SDK: 태스크 미완료 시 에이전트 재개 강제
session.on("turn_end", async (event) => {
  const requiredArtifacts = [
    "docs/spec.md",
    "tests/unit/",
    "docs/traceability-matrix.md"
  ];

  const missingArtifacts = await checkMissingArtifacts(requiredArtifacts);

  if (missingArtifacts.length > 0 && isAgentAttemptingToStop(event)) {
    // 에이전트가 종료를 시도하지 못하도록 추가 지시 주입
    await session.sendMessage({
      role: "user",
      content: `[시스템 게이트] 다음 필수 아티팩트가 아직 생성되지 않았습니다:\n` +
               missingArtifacts.map(a => `- ${a}`).join("\n") +
               `\n\n위 아티팩트를 모두 생성한 후 완료할 수 있습니다.`
    });
  }
});
```

### 7.6 종합 비교 매트릭스

| 요건 | Pi SDK | Claude Code | OpenAI Agents SDK |
|------|:------:|:-----------:|:-----------------:|
| 스펙 우선 강제 | `context` + `before_agent_start` | `UserPromptSubmit` exit 2 | 입력 가드레일 |
| 매 LLM 호출 컨텍스트 주입 | **고유 기능** (`context`) | 불가 | `call_model_input_filter` |
| 테스트 게이트 | `tool_call` 블로킹 | `PreToolUse` deny | `@tool_input_guardrail` |
| 린트 게이트 | `tool_result` 결과 수정 | `PostToolUse` (수정 불가) | `@tool_output_guardrail` |
| 양방향 추적성 | `pi.appendEntry()` | transcript_path | 내장 추적 |
| 상태머신 강제 | `setActiveTools()` + 블로킹 | 훅 조합 (복잡) | LangGraph (별도) |
| 에이전트 조기 종료 차단 | `turn_end` + 메시지 주입 | `Stop` hook | 불가 |
| 도구 결과 수정 | `tool_result` 미들웨어 | 없음 | `@tool_output_guardrail` |
| 시스템 프롬프트 교체 | `before_agent_start` | 없음 | 없음 |
| 인프로세스 실행 | 완전 인프로세스 | 서브프로세스 | Python 인프로세스 |
| 상태 공유 | TypeScript 변수 직접 공유 | 파일 시스템만 | Python 변수 |
| 이벤트 수 | **28개** | 17개 | 7개 (Guardrails 별도) |
| 언어 | TypeScript | bash/any | Python |
| 라이선스 | MIT | 독점 | MIT |

---

## 8. 아키텍처 설계

### 8.1 Stripe Minions 패턴을 Pi SDK로 구현하기

Stripe Minions의 Blueprint를 Pi SDK로 구현하는 구체적인 아키텍처를 제시한다.

#### 8.1.1 전체 아키텍처 다이어그램

```
신뢰성 있는 개발 에이전트 (Pi SDK 기반)

┌─────────────────────────────────────────────────────────────────────┐
│                      Pi 에이전트 프로세스 (Node.js)                  │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                 상태머신 컨트롤러                              │   │
│  │  currentPhase: "planning" | "implementing" | "testing" |     │   │
│  │                "linting" | "committing"                      │   │
│  │  specVersion: string                                         │   │
│  │  ciAttempts: number (최대 2)                                 │   │
│  │  requiredArtifacts: string[]                                 │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                │                                     │
│       ┌────────────────────────┼────────────────────────────┐        │
│       │ 이벤트 핸들러         │                            │        │
│       ▼                        ▼                            ▼        │
│  ┌─────────┐             ┌──────────┐                ┌──────────┐   │
│  │context  │             │tool_call │                │tool_result│  │
│  │이벤트   │             │이벤트    │                │이벤트    │   │
│  │(매 LLM  │             │(하드     │                │(결과     │   │
│  │호출 전) │             │블로킹)   │                │미들웨어) │   │
│  └────┬────┘             └────┬─────┘                └────┬─────┘   │
│       │                       │                            │         │
│       ▼                       ▼                            ▼         │
│  스펙 컨텍스트            게이트 체크:              린트 결과 구조화   │
│  주입/업데이트            - 린트 통과?              테스트 결과 파싱  │
│                           - 테스트 통과?            추적성 엔트리 기록│
│                           - 상태머신 허용?                           │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │              결정론적 게이트 시퀀스                           │   │
│  │                                                              │   │
│  │  [컨텍스트 하이드레이션] → [구현] → [린트] → [테스트] →    │   │
│  │  [CI] → [최대 2회 재시도] → [push] → [인간 리뷰] → [병합]  │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

#### 8.1.2 완전한 Pi SDK 구현 예제

```typescript
import { createSession, Session } from "@mariozechner/pi-coding-agent";
import * as fs from "fs/promises";
import { exec } from "child_process";
import { promisify } from "util";

const execAsync = promisify(exec);

// 상태머신 상태 정의
type DevPhase =
  | "planning"
  | "implementing"
  | "linting"
  | "testing"
  | "committing"
  | "done";

interface AgentState {
  phase: DevPhase;
  specVersion: string;
  ciAttempts: number;
  lintPassed: boolean;
  testsPassed: boolean;
  requiredArtifacts: string[];
}

// 결정론적 게이트 함수들
async function runLintGate(): Promise<{ passed: boolean; errors: string[] }> {
  try {
    const { stdout } = await execAsync("eslint . --format json");
    const results = JSON.parse(stdout);
    const errors = results.flatMap((f: any) =>
      f.messages.filter((m: any) => m.severity === 2).map((m: any) =>
        `${f.filePath}:${m.line}:${m.column} ${m.message} (${m.ruleId})`
      )
    );
    return { passed: errors.length === 0, errors };
  } catch (e: any) {
    const errors = e.stdout ? JSON.parse(e.stdout).flatMap((f: any) =>
      f.messages.map((m: any) => `${f.filePath}:${m.line} ${m.message}`)
    ) : [e.message];
    return { passed: false, errors };
  }
}

async function runTestGate(): Promise<{
  passed: boolean;
  failed: string[];
  coverage: number;
}> {
  try {
    const { stdout } = await execAsync("npx jest --json --coverage");
    const results = JSON.parse(stdout);
    const failed = results.testResults
      .filter((t: any) => t.status === "failed")
      .map((t: any) => t.testFilePath);
    const coverage = results.coverageMap
      ? calculateOverallCoverage(results.coverageMap)
      : 0;
    return { passed: failed.length === 0, failed, coverage };
  } catch (e: any) {
    return { passed: false, failed: ["테스트 실행 오류"], coverage: 0 };
  }
}

async function checkRequiredArtifacts(
  artifacts: string[]
): Promise<string[]> {
  const missing: string[] = [];
  for (const artifact of artifacts) {
    try {
      await fs.access(artifact);
    } catch {
      missing.push(artifact);
    }
  }
  return missing;
}

// 상태머신 기반 에이전트 설정
async function createReliableDevAgent() {
  const state: AgentState = {
    phase: "planning",
    specVersion: "",
    ciAttempts: 0,
    lintPassed: false,
    testsPassed: false,
    requiredArtifacts: [
      "SPEC.md",
      "docs/traceability-matrix.md",
    ],
  };

  const session = await createSession({
    // Pi SDK 기본 설정
  });

  // ─────────────────────────────────────────────
  // 이벤트 1: context — 모든 LLM 호출 전 스펙 주입
  // ─────────────────────────────────────────────
  session.on("context", async (event) => {
    const messages = event.messages;

    // 결정론적으로 스펙 파일 읽기
    let specContent = "";
    try {
      specContent = await fs.readFile("SPEC.md", "utf-8");
    } catch {
      specContent = "[스펙 파일 없음 — SPEC.md를 먼저 작성하십시오]";
    }

    // 현재 상태를 LLM 컨텍스트에 주입
    return [
      {
        role: "system",
        content: `[결정론적 에이전트 컨텍스트]
현재 Phase: ${state.phase}
CI 시도 횟수: ${state.ciAttempts}/2
린트 통과: ${state.lintPassed ? "예" : "아니오"}
테스트 통과: ${state.testsPassed ? "예" : "아니오"}

[스펙 문서 — 모든 구현은 이 스펙을 따라야 함]
${specContent}

[현재 Phase에서 허용된 작업]
${getAllowedActions(state.phase).join(", ")}`,
      },
      ...messages,
    ];
  });

  // ─────────────────────────────────────────────
  // 이벤트 2: before_agent_start — 시스템 프롬프트 교체
  // ─────────────────────────────────────────────
  session.on("before_agent_start", async () => {
    return {
      systemPrompt: buildSystemPrompt(state.phase),
      message:
        state.phase === "planning"
          ? {
              customType: "phase-context",
              content: `[계획 모드] 구현 전 스펙을 분석하고 계획을 수립하십시오.`,
              display: false,
            }
          : undefined,
    };
  });

  // ─────────────────────────────────────────────
  // 이벤트 3: tool_call — 하드 블로킹 게이트
  // ─────────────────────────────────────────────
  session.on("tool_call", async (event) => {
    const { toolName, params } = event;

    // 도구 가시성: 현재 Phase에서 허용되지 않은 도구 차단
    const allowedTools = getAllowedToolsForPhase(state.phase);
    if (!allowedTools.includes(toolName)) {
      return {
        block: true,
        reason: `Phase '${state.phase}'에서 '${toolName}'은 허용되지 않습니다.\n` +
                `현재 허용된 도구: ${allowedTools.join(", ")}`,
      };
    }

    // bash 명령별 게이트
    if (toolName === "bash") {
      const command = params.command as string;

      // git commit 게이트: 린트 + 테스트 + 아티팩트 검증
      if (/git\s+commit/.test(command)) {
        // 게이트 1: 린트
        const lintResult = await runLintGate();
        if (!lintResult.passed) {
          state.lintPassed = false;
          state.phase = "linting";
          session.setActiveTools(getAllowedToolsForPhase("linting"));
          return {
            block: true,
            reason: `[린트 게이트 실패] 커밋 차단됨\n` +
                    `발견된 오류 (${lintResult.errors.length}건):\n` +
                    lintResult.errors.slice(0, 10).join("\n") +
                    `\n\n린트 오류를 모두 수정한 후 다시 커밋을 시도하십시오.`,
          };
        }
        state.lintPassed = true;

        // 게이트 2: 테스트
        const testResult = await runTestGate();
        if (!testResult.passed) {
          state.testsPassed = false;
          state.phase = "testing";
          session.setActiveTools(getAllowedToolsForPhase("testing"));
          return {
            block: true,
            reason: `[테스트 게이트 실패] 커밋 차단됨\n` +
                    `실패한 테스트 (${testResult.failed.length}건):\n` +
                    testResult.failed.join("\n") +
                    `\n커버리지: ${testResult.coverage}% (최소 80% 필요)\n\n` +
                    `실패한 테스트를 수정한 후 다시 커밋하십시오.`,
          };
        }
        state.testsPassed = true;

        // 게이트 3: 필수 아티팩트
        const missing = await checkRequiredArtifacts(state.requiredArtifacts);
        if (missing.length > 0) {
          return {
            block: true,
            reason: `[아티팩트 게이트 실패] 커밋 차단됨\n` +
                    `누락된 필수 파일:\n` +
                    missing.map((f) => `  - ${f}`).join("\n") +
                    `\n\n위 파일들을 생성한 후 커밋하십시오.`,
          };
        }

        // 모든 게이트 통과
        state.phase = "committing";
        session.setActiveTools(getAllowedToolsForPhase("committing"));
      }

      // git push 게이트
      if (/git\s+push/.test(command)) {
        if (!state.lintPassed || !state.testsPassed) {
          return {
            block: true,
            reason: `[Push 게이트] 린트와 테스트가 먼저 통과해야 합니다.`,
          };
        }
      }

      // CI 재시도 제한 (Stripe 패턴: 최대 2회)
      if (command.includes("ci") || command.includes("test:ci")) {
        state.ciAttempts++;
        if (state.ciAttempts > 2) {
          return {
            block: true,
            reason: `[CI 게이트] CI 최대 시도 횟수(2회) 초과. 인간 검토가 필요합니다.\n` +
                    `자동화된 수정을 중단하고 개발자에게 에스컬레이션하십시오.`,
          };
        }
      }
    }

    // undefined 반환: 정상 실행
  });

  // ─────────────────────────────────────────────
  // 이벤트 4: tool_result — 도구 결과 미들웨어
  // ─────────────────────────────────────────────
  session.on("tool_result", async (event) => {
    if (event.toolName === "write_file" || event.toolName === "edit_file") {
      const filePath = event.params.path as string;

      // 파일 쓰기 후 즉시 린트 실행 및 결과 구조화
      if (filePath.match(/\.(ts|js|tsx|jsx)$/)) {
        const lintResult = await runLintGate();
        if (!lintResult.passed) {
          // LLM이 받는 결과를 구조화된 린트 피드백으로 교체
          return {
            result: JSON.stringify({
              fileWritten: filePath,
              status: "lint_errors",
              errorCount: lintResult.errors.length,
              errors: lintResult.errors.slice(0, 20),
              instruction:
                "파일이 저장되었지만 린트 오류가 있습니다. 위 오류들을 수정하십시오.",
            }),
          };
        }
      }

      // 추적성 엔트리 기록
      await session.appendEntry({
        type: "file-written",
        timestamp: new Date().toISOString(),
        file: filePath,
        phase: state.phase,
        specIds: await extractSpecReferences(filePath),
      });
    }
  });

  // ─────────────────────────────────────────────
  // 이벤트 5: turn_end — 상태 전환 및 도구 갱신
  // ─────────────────────────────────────────────
  session.on("turn_end", async () => {
    // 상태에 따라 활성 도구 동적 갱신
    session.setActiveTools(getAllowedToolsForPhase(state.phase));
  });

  // ─────────────────────────────────────────────
  // 이벤트 6: session_before_end — 완료 조건 검증
  // ─────────────────────────────────────────────
  session.on("session_before_end", async () => {
    const missing = await checkRequiredArtifacts(state.requiredArtifacts);
    if (missing.length > 0) {
      // 세션 종료 차단하고 누락 아티팩트 생성 요청
      await session.sendMessage({
        role: "user",
        content:
          `[세션 종료 게이트] 다음 필수 파일이 없습니다:\n` +
          missing.map((f) => `- ${f}`).join("\n") +
          `\n\n이 파일들을 모두 생성한 후 종료할 수 있습니다.`,
      });
    }

    // 최종 감사 로그 기록
    await session.appendEntry({
      type: "session-summary",
      timestamp: new Date().toISOString(),
      finalPhase: state.phase,
      ciAttempts: state.ciAttempts,
      lintPassed: state.lintPassed,
      testsPassed: state.testsPassed,
      missingArtifacts: missing,
    });
  });

  return session;
}

// 상태머신 헬퍼 함수들
function getAllowedToolsForPhase(phase: DevPhase): string[] {
  const PHASE_TOOLS: Record<DevPhase, string[]> = {
    planning: ["read_file", "list_directory", "search_code", "bash"],
    implementing: ["read_file", "write_file", "edit_file", "bash", "search_code"],
    linting: ["read_file", "edit_file", "bash"],  // 린트 수정용
    testing: ["read_file", "write_file", "bash"], // 테스트 작성/실행용
    committing: ["bash"],                           // git 명령만
    done: [],
  };
  return PHASE_TOOLS[phase];
}

function getAllowedActions(phase: DevPhase): string[] {
  const PHASE_ACTIONS: Record<DevPhase, string[]> = {
    planning: ["파일 읽기", "코드 검색", "분석", "계획 수립"],
    implementing: ["파일 읽기/쓰기", "코드 작성", "bash 실행"],
    linting: ["린트 오류 수정", "파일 편집"],
    testing: ["테스트 작성", "테스트 실행"],
    committing: ["git add", "git commit", "git push"],
    done: [],
  };
  return PHASE_ACTIONS[phase];
}

function buildSystemPrompt(phase: DevPhase): string {
  const prompts: Record<DevPhase, string> = {
    planning: `당신은 소프트웨어 설계자입니다. 지금은 계획 단계입니다.
코드를 작성하거나 파일을 수정하지 마십시오.
SPEC.md를 분석하고 구현 계획을 수립하십시오.`,
    implementing: `당신은 소프트웨어 개발자입니다. SPEC.md에 따라 코드를 구현하십시오.
모든 구현은 스펙의 요건 ID(REQ-XXX)를 코드 주석에 포함해야 합니다.`,
    linting: `린트 오류 수정 중입니다. 린트 오류만 수정하고 다른 변경은 하지 마십시오.`,
    testing: `테스트 작성/수정 중입니다. 실패한 테스트를 수정하거나 누락된 테스트를 추가하십시오.`,
    committing: `커밋 준비가 완료되었습니다. 변경사항을 커밋하십시오.`,
    done: `태스크가 완료되었습니다.`,
  };
  return prompts[phase];
}
```

### 8.2 ISO 26262 관점에서의 결정론적 게이트 체계

ISO 26262 준수를 목표로 하는 경우, Pi SDK 기반 에이전트의 게이트 체계는 다음과 같이 설계된다.

```
ISO 26262 게이트 체계 (Pi SDK 기반)

입력: 태스크 (Slack / 티켓)
  │
  ▼ [결정론적] context 이벤트
스펙 파일(SPEC.md) + ASIL 레벨 + 추적성 ID 주입
  │
  ▼ [결정론적] before_agent_start
시스템 프롬프트에 ASIL 요건 포함
  │
  ▼ [비결정론적] 구현 에이전트 루프
    ╭────────────────────╮
    │  코드 구현         │
    ╰────────────────────╯
  │
  ▼ [결정론적] tool_call 게이트 (write_file 시)
MISRA-C 또는 ESLint 검사 → 실패 시 { block: true }
  │ 통과
  ▼ [결정론적] tool_result 미들웨어
린트 결과를 구조화하여 LLM에 전달
  │
  ▼ [비결정론적] CI 실패 수정 에이전트 (최대 2회)
    ╭────────────────────╮
    │  CI 실패 수정      │
    ╰────────────────────╯
  │
  ▼ [결정론적] tool_call 게이트 (git commit 시)
  1. 린트 게이트 (필수 통과)
  2. 테스트 게이트 (필수 통과)
  3. 커버리지 게이트 (ASIL별 기준)
  4. 아티팩트 게이트 (SWU, 추적성 매트릭스 등)
  │ 모두 통과
  ▼ [결정론적] appendEntry()
양방향 추적성 매트릭스 업데이트
  │
  ▼ [결정론적] 인간 PR 리뷰 (에이전트 불가)
  ASIL-A/B: 다른 사람, ASIL-C: 다른 팀, ASIL-D: 다른 조직
  │
  ▼ [결정론적] session_before_end 게이트
필수 ISO 26262 아티팩트 완전성 검증
  │
  ▼ 병합
```

---

## 9. 최종 권고사항

### 9.1 1순위: Pi SDK

**개발/커스터마이징 의향이 있는 경우, Pi SDK가 최적의 선택이다.**

#### 선택 이유 1: 이벤트 수 — 최대 개입 표면

28개 이벤트는 Claude Code의 17개보다 65% 더 많다. 이것은 결정론적 게이트를 삽입할 수 있는 기회가 더 많음을 의미한다.

```
Pi SDK:     ████████████████████████████  28개 이벤트
Claude Code: █████████████████            17개 이벤트
OpenAI:     ███████                        7개 이벤트 (RunHooks)
```

#### 선택 이유 2: `context` 이벤트 — 유일한 전체 컨텍스트 제어

Pi SDK만이 모든 LLM API 호출 전에 발화하는 이벤트를 제공한다. 이것은 Stripe Minions의 "컨텍스트 하이드레이션은 결정론적"이라는 원칙을 완전히 구현할 수 있는 유일한 메커니즘이다.

Claude Code의 `UserPromptSubmit`은 사용자 입력 시 한 번만 발화한다. 에이전트 루프 내의 중간 LLM 호출에는 개입할 수 없다.

#### 선택 이유 3: `tool_call` 블로킹 — 인프로세스 하드 게이트

```typescript
return { block: true, reason: "린트 게이트 실패" };
```

이 단 한 줄이 Claude Code의 셸 서브프로세스 없이, 동일한 Node.js 프로세스 내에서 즉시 실행된다. 프로세스 생성 오버헤드 없음, JSON 직렬화 오버헤드 없음, 상태 공유 문제 없음.

#### 선택 이유 4: `tool_result` 미들웨어 — LLM이 보는 세계 제어

도구가 반환하는 결과를 LLM이 받기 전에 수정할 수 있다. 이것은 에이전트의 세계관(world model)을 결정론적으로 형성하는 능력이다. Claude Code와 OpenAI Agents SDK의 RunHooks에는 이 능력이 없다.

#### 선택 이유 5: `setActiveTools()` — 상태머신 기반 도구 제한

```typescript
session.setActiveTools(["read_file", "bash"]); // 테스트 단계에서
```

현재 상태머신 상태에 따라 LLM이 볼 수 있는 도구를 동적으로 제한한다. Stripe Blueprint의 "에이전트를 제한된 상자에 넣는다"는 원칙의 직접적 구현이다.

#### 선택 이유 6: MIT 라이선스 + 소규모 코드베이스 = 포킹 가능

Claude Code는 Anthropic 독점 소프트웨어다. Pi SDK는 MIT 라이선스이며 코드베이스가 작아 필요한 기능을 직접 추가하거나 버그를 수정할 수 있다. 커스터마이징 의향이 있다는 전제에서 이것은 결정적인 장점이다.

#### 선택 이유 7: v0.55.4 릴리스 (2026년 3월 2일) — 활발한 유지보수

이전 보고서의 "OSS vacation으로 개발 중단" 우려는 해소되었다. Zechner는 예정된 복귀일인 2026년 3월 2일에 즉시 새 버전을 릴리스했다.

#### 선택 이유 8: TypeScript — 타입 안전한 확장 개발

TypeScript의 타입 시스템은 결정론적 게이트를 구현할 때 컴파일 타임에 오류를 잡는다. ISO 26262 컨텍스트에서 런타임 오류보다 컴파일 타임 오류가 훨씬 안전하다.

#### 선택 이유 9: 계획 모드 예제 = 검증된 상태머신 패턴

Pi SDK의 공식 확장 예제가 이미 3-상태 상태머신을 구현하고 있다. 이것은 Pi SDK로 상태머신 기반 에이전트를 구축하는 것이 의도된 사용 패턴임을 의미한다. 바퀴를 다시 발명하지 않아도 된다.

#### Pi SDK 채택 시 권고 사항

```
1. Pi SDK 포크 전략
   - MIT 라이선스 활용, 내부 레지스트리에 @your-org/pi-agent-core 유지
   - 핵심 API만 의존: session.on(), session.setActiveTools(), session.appendEntry()

2. 상태머신 설계 우선
   - Stripe Blueprint를 참고하여 Phase 정의
   - 각 Phase별 허용 도구 목록 명시

3. 결정론적 게이트 구현 순서
   a. context 이벤트: 스펙 파일 주입
   b. tool_call 이벤트: 린트/테스트/아티팩트 게이트
   c. tool_result 이벤트: 린트 결과 구조화
   d. session_before_end 이벤트: 완료 조건 검증
   e. setActiveTools(): 상태별 도구 제한

4. ISO 26262 추가 요소
   - appendEntry()로 양방향 추적성 매트릭스 유지
   - 인간 리뷰 단계는 에이전트가 절대 우회 불가하도록 설계
   - ASIL 레벨별 커버리지 게이트 값을 context 이벤트로 주입
```

### 9.2 2순위: Claude Code

**커스터마이징 의향이 제한적이고 즉시 사용 가능한 솔루션이 필요한 경우 Claude Code를 선택한다.**

Claude Code는 다음 상황에서 Pi SDK보다 유리하다.

- 기존 Anthropic Claude 모델을 사용하고 있으며 변경 의향이 없는 경우
- ISO 26262 훅 설정을 bash 스크립트 수준에서 즉시 구현하고 싶은 경우
- 팀이 TypeScript보다 bash/Python에 더 익숙한 경우
- 기업 정책으로 훅 설정을 git으로 추적해야 하는 경우 (`.claude/settings.json`)

**Claude Code의 한계 (다시 한번 강조)**:
- `context` 이벤트 없음: 에이전트 루프 내 중간 LLM 호출에 컨텍스트 주입 불가
- `tool_result` 수정 불가: LLM이 보는 도구 결과를 변경할 수 없음
- 훅 간 상태 공유 불가: 파일 시스템을 통한 우회만 가능
- 17개 이벤트: Pi SDK의 28개보다 11개 적음

### 9.3 3순위: OpenAI Agents SDK

**Python 전용 팀이며 풍부한 추적 시스템이 최우선이고 상태머신을 LangGraph로 분리 관리하는 경우에 한해 고려한다.**

OpenAI Agents SDK의 강점:
- 가장 풍부한 내장 추적 (Langfuse, Datadog, W&B 통합)
- Guardrails: 결정론적 게이팅 메커니즘 (RunHooks와 별개)
- LangGraph v1.0: 성숙한 상태머신 오케스트레이션

OpenAI Agents SDK의 한계:
- Python 전용 (TypeScript 미지원)
- RunHooks는 관찰 전용 (알려진 버그 다수)
- 상태머신을 위해 LangGraph를 별도로 학습해야 함
- `context` 이벤트 없음
- 시스템 프롬프트 동적 교체 불가

### 9.4 세 프레임워크 최종 비교

| 항목 | Pi SDK | Claude Code | OpenAI Agents SDK |
|------|:------:|:-----------:|:-----------------:|
| **이벤트 수** | **28개** | 17개 | 7개 |
| **모든 LLM 호출 컨텍스트 주입** | **고유** | 없음 | 없음 |
| **인프로세스 하드 블로킹** | **완전** | 서브프로세스 | Guardrails만 |
| **도구 결과 수정** | **가능** | 없음 | 제한적 |
| **시스템 프롬프트 동적 교체** | **가능** | 없음 | 없음 |
| **도구 가시성 제어** | **setActiveTools()** | 없음 | is_enabled |
| **상태 공유** | TypeScript 변수 | 파일 시스템 | Python 변수 |
| **추적 시스템** | 커스텀 | transcript | **내장 최강** |
| **상태머신** | 내장 패턴 | 복잡한 훅 조합 | LangGraph 별도 |
| **라이선스** | **MIT** | 독점 | MIT |
| **커스터마이징** | **최대** | 중간 | 중간 |
| **언어** | TypeScript | bash/any | Python만 |
| **유지보수 상태** | **활발 (v0.55.4)** | Anthropic 지원 | OpenAI 지원 |

---

## 10. 결론

### 10.1 핵심 통찰의 재확인

Stripe Minions는 "벽이 모델보다 중요하다"를 1,300개 이상의 PR/주로 실증했다. 신뢰성 있는 개발 에이전트의 본질은 LLM의 지능이 아니라, LLM 주변에 세운 결정론적 벽의 두께와 정밀도다.

이 벽을 세우기 위해 필요한 것은 명확하다.

1. LLM이 무엇을 할 수 있는지 제한하는 하드 게이트
2. LLM이 무엇을 보는지 제어하는 컨텍스트 주입
3. LLM의 세계관을 형성하는 도구 결과 미들웨어
4. 현재 상태를 반영하는 동적 도구 가시성 제어

이 네 가지를 **모두**, **인프로세스에서**, **28개의 개입 지점에서** 제공하는 프레임워크는 Pi SDK뿐이다.

### 10.2 이전 평가의 최종 정정

이전 보고서들이 Pi SDK를 "비권장" 또는 "부적합"으로 분류한 것은 평가 기준의 혼동에서 비롯되었다. "즉시 사용 가능한 ISO 26262 준수 도구"로서의 Pi SDK는 확실히 부족하다. 그러나 "커스터마이징을 통해 결정론적+비결정론적 혼합 에이전트를 구축하기 위한 최적의 기반"으로서의 Pi SDK는 세 프레임워크 중 명백히 최우수다.

최소주의(minimalism)는 결핍이 아니라 선택의 자유다. Pi SDK의 빈 캔버스 위에서, 커스터마이징 의향이 있는 개발자는 정확히 자신이 필요한 신뢰성 아키텍처를 구축할 수 있다.

### 10.3 권고 요약

```
커스터마이징 의향 있음 + TypeScript 스택 + 최대 제어 필요
    → Pi SDK (1순위)

즉시 사용 + Anthropic 에코시스템 + bash 친숙
    → Claude Code (2순위)

Python 팀 + 추적이 최우선 + LangGraph 병행
    → OpenAI Agents SDK (3순위)
```

신뢰성은 모델에서 오지 않는다. 벽에서 온다. Pi SDK는 그 벽을 가장 세밀하게, 가장 완전하게 설계할 수 있는 도구다.

> **참고:** 본 보고서는 SPEC_AgentForDev.md의 세 가지 요구사항 중 **요구사항 2 (결정론적+비결정론적 혼합)** 를 중점적으로 다룬다. 나머지 두 요구사항에 대한 심층 분석은 추가 섹션을 참고하라.
> - **요구사항 1 (Human in the Loop 전략)**: [섹션 11 참조](#11-human-in-the-loop-hitl-전략)
> - **요구사항 3 (신뢰성-효율성 Trade-off)**: [섹션 12 참조](#12-신뢰성-효율성-trade-off-전략)

---

## 11. Human in the Loop (HITL) 전략

### 11.1 HITL의 중요성과 SPEC 요구사항

코딩 에이전트의 자율성이 향상될수록, 역설적으로 **인간 개입의 전략적 배치**가 더 중요해진다. 완전 자율 에이전트는 아직 현실이 아니다. SPEC은 이 점을 명확히 한다.

> **"claude code 처럼 중간중간 사람이 필요한 단계에서는 사람과 같이 채팅하여 결정해야함. 신뢰성이 높은 코딩 에이전트를 만들기 위해서는 아직은 필요한 단계로 보임"**

Stripe Minions가 주당 1,300개 이상의 PR을 처리하면서도 "인간 PR 리뷰"를 **필수 종단 게이트**로 유지하는 것은 우연이 아니다. 1조 달러 규모의 결제 코드베이스에서 인간을 제거하는 것이 아니라, 인간의 개입 시점을 **최적화**하는 것이 핵심이다.

#### HITL의 두 가지 수준

HITL은 단일 개념이 아니라 두 가지 구별되는 수준으로 분류된다.

```
수준 1: 종단 게이트 HITL (Terminal Gate HITL)
─────────────────────────────────────────────
[에이전트 자율 실행 완료] → [인간 PR 리뷰] → [병합/거부]

  특성: 에이전트 실행이 완전히 끝난 후 인간이 최종 판단
  예시: Stripe Minions의 PR 리뷰, 단계 전환 승인
  이미 분석됨: 본 보고서 섹션 2 (Stripe Minions Blueprint)

수준 2: 중간 실행 HITL (Mid-Execution HITL)
─────────────────────────────────────────────
[에이전트 실행 중] → [불확실성 감지] → [인간에게 질문] → [답변 수신] → [실행 재개]

  특성: 에이전트 실행 도중 인간이 실시간으로 개입
  예시: 설계 결정, 모호한 요구사항 해소, 위험 연산 승인
  본 섹션의 핵심 분석 대상
```

종단 게이트 HITL만으로는 충분하지 않다. 에이전트가 잘못된 설계 방향으로 200줄의 코드를 작성한 후 PR 리뷰에서 거부되는 것보다, 10줄을 작성한 시점에 "API 설계 방식 A vs B 중 어느 것을 선호합니까?"라고 물어보는 것이 비용 효율적이다.

---

### 11.2 Claude Code의 대화형 HITL 패턴

Claude Code는 가장 성숙한 대화형 HITL을 제공한다. CLI/IDE 환경에서 사용자와 실시간으로 대화하며, 다섯 가지 HITL 메커니즘을 내장하고 있다.

#### 11.2.1 Tool Use 승인 프롬프트

Claude Code의 기본 HITL 메커니즘은 **도구 사용 승인**이다. `allowedTools`에 포함되지 않은 도구를 호출하려 할 때, 에이전트는 자동으로 일시 중단되고 사용자에게 승인을 요청한다.

```
[Claude] 다음 명령을 실행하려고 합니다:
  bash: rm -rf ./legacy-module/

  Allow? [y/n/a(allow all)]
```

이 패턴은 `.claude/settings.json`의 `permissions` 설정으로 세밀하게 제어된다.

```json
{
  "permissions": {
    "allow": [
      "Read",
      "Glob",
      "Grep",
      "Bash(npm test*)",
      "Bash(npm run lint*)",
      "Bash(git status)",
      "Bash(git diff*)",
      "Bash(git log*)"
    ],
    "deny": [
      "Bash(git push*)",
      "Bash(git checkout main)",
      "Bash(rm -rf*)",
      "Bash(docker rm*)"
    ]
  }
}
```

**HITL 관점에서의 분석**: `allow`에 포함된 도구는 자동 승인(HITL 우회), `deny`에 포함된 도구는 무조건 차단(HITL 불필요), **양쪽 모두에 없는 도구**가 HITL 대상이 된다. 이 3단계 분류 체계는 HITL의 빈도를 최적화하는 핵심 설계다. 모든 도구에 승인을 요구하면 사용자 피로(approval fatigue)가 발생하고, 모든 도구를 허용하면 안전성이 사라진다.

#### 11.2.2 Plan Mode

Claude Code의 Plan Mode는 **실행 전 인간 승인**을 구조화한다.

```
사용자: "인증 모듈을 JWT에서 OAuth2로 마이그레이션해줘"

[Claude - Plan Mode]
다음 계획을 수립했습니다:

1. 현재 JWT 의존성 분석 (auth/jwt.ts, middleware/auth.ts, tests/auth.test.ts)
2. OAuth2 클라이언트 라이브러리 설치 (passport-oauth2)
3. auth/oauth2.ts 신규 모듈 생성
4. middleware/auth.ts의 JWT 검증을 OAuth2 토큰 검증으로 교체
5. 환경변수 추가 (.env.example 업데이트)
6. 기존 테스트를 OAuth2 기반으로 마이그레이션
7. 통합 테스트 추가

이 계획을 진행할까요? 수정할 사항이 있으면 알려주세요.
```

Plan Mode는 중간 실행 HITL의 가장 자연스러운 형태다. 에이전트가 코드를 작성하기 **전에** 인간이 방향을 검증한다. 잘못된 방향으로 진행한 후 되돌리는 비용을 제로에 가깝게 줄인다.

#### 11.2.3 Permission 시스템: allow/deny/allowAll 패턴

실행 중 승인 요청이 발생하면, 사용자에게 세 가지 선택지가 제공된다.

| 선택지 | 의미 | HITL 영향 |
|--------|------|----------|
| `y` (allow) | 이번 한 번만 승인 | 다음 동일 요청 시 다시 물어봄 |
| `n` (deny) | 이번 한 번 거부 | 에이전트에게 거부 사유 피드백 |
| `a` (allowAll) | 이 세션에서 이 도구 유형 전체 승인 | 이후 HITL 건너뜀 |

`allowAll`은 **점진적 신뢰 구축** 메커니즘이다. 초기에는 모든 `Bash` 명령에 승인을 요구하다가, 사용자가 에이전트의 행동 패턴을 확인한 후 `allowAll`로 전환하면 이후 동일 유형의 HITL이 생략된다.

#### 11.2.4 AskUserQuestion 도구

Claude Code 에이전트는 `AskUserQuestion`이라는 구조화된 도구를 통해 실행 도중 인간에게 명시적으로 질문할 수 있다.

```
[Claude가 AskUserQuestion 도구를 호출]

질문: 데이터베이스 마이그레이션 전략을 선택해야 합니다.

선택지:
  1. 인플레이스 마이그레이션 (기존 테이블 직접 수정)
  2. 블루-그린 마이그레이션 (새 테이블 생성 후 전환)
  3. 점진적 마이그레이션 (읽기는 양쪽, 쓰기는 새 테이블)

추가 컨텍스트: 현재 users 테이블에 230만 행이 있으며,
다운타임 허용 여부에 따라 전략이 달라집니다.

사용자의 선택: _
```

이 도구의 핵심은 에이전트가 **스스로 불확실성을 인식**하고 인간에게 위임한다는 점이다. LLM이 임의로 결정하는 것이 아니라, 구조화된 선택지와 함께 컨텍스트를 제공하여 인간이 정보에 기반한 결정(informed decision)을 내리도록 한다.

#### 11.2.5 Hook 기반 HITL

Claude Code의 Hook 시스템을 활용하면 프로그래밍 방식으로 HITL 게이트를 삽입할 수 있다. `Stop` 훅은 에이전트가 종료하려 할 때 인간 확인을 강제한다.

```bash
#!/bin/bash
# .claude/hooks/stop-phase-gate.sh
# Stop hook: 단계 전환 시 인간 승인을 강제하는 게이트

PHASE_STATE=".claude/dev-phase-state.json"

if [ ! -f "$PHASE_STATE" ]; then
  echo '{"continue": true}'
  exit 0
fi

PHASE=$(jq -r '.phase' "$PHASE_STATE")
PHASE_COMPLETE=$(jq -r '.phaseComplete' "$PHASE_STATE")

# SPEC 단계 완료 시: 인간이 검토 후 다음 단계로 전환해야 함
if [ "$PHASE" = "SPEC" ] && [ "$PHASE_COMPLETE" = "true" ]; then
  echo '{"continue": true, "reason": "스펙 검토가 필요합니다. 스펙 내용을 확인한 후 phase_transition approve SPEC->TESTCASE 명령을 내려주세요."}'
  exit 0
fi

# TESTCASE 단계 완료 시: TC 목록을 인간이 검증해야 함
if [ "$PHASE" = "TESTCASE" ] && [ "$PHASE_COMPLETE" = "true" ]; then
  echo '{"continue": true, "reason": "테스트 케이스 목록을 검토해 주세요. TC가 요구사항을 충분히 커버하는지 확인 후 phase_transition approve TESTCASE->CODING 명령을 내려주세요."}'
  exit 0
fi

# 그 외: 정상 종료 허용
echo '{"continue": false}'
```

`prompt` 타입 훅을 사용하면 특정 시점에 인간 입력을 강제 주입할 수 있다.

```bash
#!/bin/bash
# .claude/hooks/prompt-risk-assessment.sh
# PreToolUse hook: 고위험 연산 전 인간 컨텍스트 주입

TOOL_NAME=$(echo "$CLAUDE_HOOK_EVENT" | jq -r '.tool_name')
TOOL_INPUT=$(echo "$CLAUDE_HOOK_EVENT" | jq -r '.tool_input')

# 프로덕션 관련 명령 감지
if echo "$TOOL_INPUT" | grep -qiE "(production|prod|deploy|migration)"; then
  echo "{\"additionalContext\": \"[HUMAN REVIEW REQUIRED] 프로덕션 관련 연산이 감지되었습니다. 이 작업이 의도된 것인지 사용자에게 확인하십시오. AskUserQuestion 도구를 사용하여 사용자에게 진행 여부를 물어보십시오.\"}"
fi
```

---

### 11.3 Pi SDK에서의 HITL 구현

Pi SDK는 HITL을 내장 기능으로 제공하지 않지만, 28개 이벤트 시스템의 유연성 덕분에 **완전한 커스텀 HITL**을 구현할 수 있다. 오히려 이 접근이 더 강력한 제어를 가능하게 한다.

#### 11.3.1 `tool_call` 이벤트를 통한 승인 게이트

Pi SDK의 `tool_call` 이벤트에서 `block: true`를 반환하면 도구 실행이 즉시 차단된다. 이를 인간 승인과 결합하면 Claude Code의 승인 프롬프트와 동등한 HITL을 구현할 수 있다.

```typescript
import { createSession } from "@anthropic-ai/sdk";
import * as readline from "readline";

// Human approval request utility
async function requestHumanApproval(context: {
  tool: string;
  input: Record<string, unknown>;
  reason: string;
}): Promise<boolean> {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });

  return new Promise((resolve) => {
    console.log(`\n${"=".repeat(60)}`);
    console.log(`[HUMAN APPROVAL REQUIRED]`);
    console.log(`Tool: ${context.tool}`);
    console.log(`Input: ${JSON.stringify(context.input, null, 2)}`);
    console.log(`Reason: ${context.reason}`);
    console.log(`${"=".repeat(60)}`);

    rl.question("Approve? [y/n]: ", (answer) => {
      rl.close();
      resolve(answer.toLowerCase() === "y");
    });
  });
}

// Risk level assessment
function assessRiskLevel(
  toolName: string,
  toolInput: Record<string, unknown>
): "low" | "medium" | "high" | "critical" {
  const command = (toolInput.command as string) || "";

  // Critical: production-affecting operations
  if (/rm\s+-rf|drop\s+table|truncate|production|deploy/i.test(command)) {
    return "critical";
  }
  // High: destructive file operations, git push
  if (/git\s+push|git\s+reset|rm\s+/i.test(command)) {
    return "high";
  }
  // Medium: file writes, package installation
  if (toolName === "write_file" || /npm\s+install|pip\s+install/i.test(command)) {
    return "medium";
  }
  // Low: read-only operations
  return "low";
}

// HITL via tool_call blocking
session.on("tool_call", async (event) => {
  const riskLevel = assessRiskLevel(event.toolName, event.params);

  if (riskLevel === "critical" || riskLevel === "high") {
    const approved = await requestHumanApproval({
      tool: event.toolName,
      input: event.params,
      reason: `Risk level: ${riskLevel} — Human approval required`,
    });

    if (!approved) {
      return {
        block: true,
        reason: `[HUMAN DENIED] Operation blocked by human reviewer. ` +
                `Risk level: ${riskLevel}. ` +
                `Please propose an alternative approach.`,
      };
    }
  }
  // Low/medium risk: auto-approve
});
```

#### 11.3.2 `context` 이벤트를 통한 중간 컨텍스트 주입

Pi SDK의 고유 기능인 `context` 이벤트는 **매 LLM 호출 전**에 발화한다. 이를 활용하면 에이전트 루프 중간에 인간의 결정을 주입할 수 있다.

```typescript
// Human decision queue — external process (e.g., web UI) pushes decisions here
interface HumanDecision {
  id: string;
  question: string;
  answer: string;
  timestamp: number;
}

const pendingDecisions: HumanDecision[] = [];

// Polling-based: check if human has provided input via external channel
async function checkForHumanInput(): Promise<HumanDecision[]> {
  const decisionsFile = ".claude/human-decisions.json";
  try {
    const raw = await fs.readFile(decisionsFile, "utf-8");
    const decisions: HumanDecision[] = JSON.parse(raw);
    // Clear consumed decisions
    await fs.writeFile(decisionsFile, "[]");
    return decisions;
  } catch {
    return [];
  }
}

// Mid-execution human context injection via context event
session.on("context", async (event) => {
  const humanDecisions = await checkForHumanInput();

  if (humanDecisions.length > 0) {
    // Inject human decisions into the LLM context
    const decisionMessages = humanDecisions.map((d) => ({
      role: "user" as const,
      content:
        `[HUMAN DECISION — ${new Date(d.timestamp).toISOString()}]\n` +
        `Question: ${d.question}\n` +
        `Decision: ${d.answer}\n` +
        `Note: This decision was made by a human reviewer. ` +
        `Follow this decision strictly.`,
    }));

    return [...decisionMessages, ...event.messages];
  }

  return event.messages;
});
```

#### 11.3.3 `before_agent_start` 이벤트를 통한 사전 게이트

에이전트 실행 시작 전에 인간이 태스크를 검토하고 승인/수정할 수 있다.

```typescript
// Pre-execution HITL gate
session.on("before_agent_start", async () => {
  const taskDescription = getState("currentTask");
  const phase = getState("currentPhase");

  // Phase transition requires explicit human approval
  if (getState("pendingPhaseTransition")) {
    const transition = getState("pendingPhaseTransition");
    console.log(`\n[PHASE TRANSITION APPROVAL REQUIRED]`);
    console.log(`From: ${transition.from} → To: ${transition.to}`);
    console.log(`Artifacts produced: ${transition.artifacts.join(", ")}`);

    const approved = await requestHumanApproval({
      tool: "phase_transition",
      input: transition,
      reason: `Phase transition from ${transition.from} to ${transition.to}`,
    });

    if (!approved) {
      return {
        systemPrompt:
          `[PHASE TRANSITION DENIED] ` +
          `인간 리뷰어가 ${transition.from} → ${transition.to} 전환을 거부했습니다. ` +
          `현재 단계(${transition.from})에서 추가 작업이 필요합니다. ` +
          `인간의 피드백을 기다리십시오.`,
      };
    }

    setState("currentPhase", transition.to);
    clearState("pendingPhaseTransition");
  }

  return {
    systemPrompt: buildPhasePrompt(phase),
  };
});
```

#### 11.3.4 `pi.appendEntry()`를 통한 인간 결정 영속화

인간의 결정을 세션 로그에 영속적으로 기록하여 감사 추적(audit trail)을 구축한다.

```typescript
// Record human decisions in session-aware JSONL
async function recordHumanDecision(
  session: Session,
  decision: {
    type: "approval" | "rejection" | "modification" | "escalation";
    phase: string;
    context: string;
    humanInput: string;
    rationale?: string;
  }
): Promise<void> {
  await session.appendEntry({
    entryType: "human-in-the-loop",
    timestamp: new Date().toISOString(),
    ...decision,
    // ISO 26262 traceability
    traceabilityId: `HITL-${Date.now()}`,
  });
}
```

---

### 11.4 OpenAI Agents SDK의 HITL 패턴

OpenAI Agents SDK는 HITL을 위한 전용 메커니즘이 제한적이다. 그러나 `handoff` 패턴과 Guardrails를 조합하면 부분적인 HITL을 구현할 수 있다.

#### 11.4.1 `handoff` 패턴: 에이전트 간 위임을 통한 HITL

OpenAI의 `handoff`는 에이전트가 다른 에이전트에게 태스크를 위임하는 메커니즘이다. "인간 에이전트"를 정의하여 HITL을 구현한다.

```python
from agents import Agent, handoff, Runner, RunContextWrapper
from typing import Any

# Human escalation handler
async def on_human_escalation(ctx: RunContextWrapper[Any], input_data: str) -> None:
    """Called when an agent hands off to human"""
    print(f"\n{'='*60}")
    print(f"[HUMAN ESCALATION]")
    print(f"Agent requests human decision:")
    print(f"  Context: {input_data}")
    print(f"{'='*60}")

# Human agent — represents the human decision point
human_agent = Agent(
    name="human_reviewer",
    instructions="""You represent a human reviewer.
    When you receive a request, present it clearly and wait for human input.
    The human's decision is final and must be followed.""",
    model="gpt-4o",
)

# Coding agent with human escalation capability
coding_agent = Agent(
    name="reliable_dev_agent",
    instructions="""You are a coding agent. When you encounter:
    1. Ambiguous requirements → hand off to human_reviewer
    2. High-risk operations → hand off to human_reviewer
    3. Design decisions with multiple valid options → hand off to human_reviewer
    Never proceed with uncertainty. Always escalate to human.""",
    model="gpt-4o",
    handoffs=[
        handoff(
            agent=human_agent,
            on_handoff=on_human_escalation,
            tool_name_override="escalate_to_human",
            tool_description_override="Escalate to human when decision requires human judgment"
        )
    ],
)
```

#### 11.4.2 Guardrails를 HITL 게이트로 활용

Guardrails의 `tripwire`를 인간 개입 트리거로 활용할 수 있다. 단, tripwire가 발동되면 실행이 **완전히 중단**되므로, "일시 중지 후 재개"가 아니라 "중단 후 인간이 새 실행을 시작"하는 패턴이 된다.

```python
from agents import (
    Agent, input_guardrail, GuardrailFunctionOutput,
    InputGuardrailTripwireTriggered
)

@input_guardrail
async def human_review_gate(
    context: RunContextWrapper,
    agent: Agent,
    input: str
) -> GuardrailFunctionOutput:
    """High-risk operation detection — triggers human review"""
    risk_keywords = ["delete", "drop", "production", "deploy", "migration"]
    detected = [kw for kw in risk_keywords if kw.lower() in input.lower()]

    if detected:
        return GuardrailFunctionOutput(
            output_info=f"Human review required. Risk keywords: {detected}",
            tripwire_triggered=True  # Halts execution entirely
        )

    return GuardrailFunctionOutput(
        output_info="No risk detected",
        tripwire_triggered=False
    )

# Usage: caller must catch and handle the tripwire
async def run_with_hitl(task: str):
    try:
        result = await Runner.run(
            coding_agent,
            task,
        )
        return result
    except InputGuardrailTripwireTriggered as e:
        print(f"[HITL TRIGGERED] {e.guardrail_result.output_info}")
        human_decision = input("Approve and continue? [y/n]: ")
        if human_decision.lower() == "y":
            # Re-run with human approval injected
            return await Runner.run(
                coding_agent,
                f"[HUMAN APPROVED] {task}",
            )
        else:
            print("Task cancelled by human.")
            return None
```

#### 11.4.3 OpenAI HITL의 구조적 한계

OpenAI Agents SDK의 HITL에는 본질적인 한계가 있다.

1. **일시 중지/재개 없음**: tripwire는 실행을 완전히 중단한다. Claude Code처럼 "일시 중지 → 인간 응답 → 재개"가 불가능하다.
2. **컨텍스트 손실**: tripwire로 중단 후 새 실행을 시작하면 이전 에이전트 루프의 중간 상태가 손실된다.
3. **RunHooks는 관찰 전용**: `on_tool_start`에서 실행을 차단할 수 없다 (섹션 6.1 참조).
4. **중간 컨텍스트 주입 불가**: Pi SDK의 `context` 이벤트나 Claude Code의 `prompt` 훅에 해당하는 기능이 없다.

---

### 11.5 HITL 시점 결정 기준

"언제 인간이 개입해야 하는가"는 에이전트 시스템 설계의 핵심 질문이다. 과도한 개입은 자동화의 이점을 없애고, 부족한 개입은 치명적 오류를 허용한다. 다음 결정 기준표는 개입 트리거, 상황, 권장 방식을 체계적으로 정리한다.

#### 11.5.1 개입 트리거별 결정 매트릭스

| 개입 트리거 | 예시 상황 | 위험 수준 | 권장 개입 방식 | Claude Code + OMC | Pi SDK | OpenAI Agents SDK |
|------------|-----------|----------|---------------|:-----------------:|:------:|:-----------------:|
| **설계 결정 불확실성** | "API를 REST vs GraphQL 중 어느 것으로?" | Medium | AskUserQuestion / 대화형 | AskUserQuestion 도구 | `input` 이벤트 + 터미널 | handoff to human agent |
| **요구사항 모호성** | "성능 기준이 명시되지 않음" | Medium | 대화형 명확화 | Plan Mode에서 질문 | `context` 이벤트에 주입 | handoff |
| **고위험 연산** | "프로덕션 DB 스키마 변경" | Critical | 강제 승인 게이트 | `deny` + PreToolUse hook | `tool_call` block | guardrail tripwire |
| **단계 전환 승인** | "SPEC → TESTCASE 전환" | High | 명시적 인간 명령 | Stop hook + 메시지 | `before_agent_start` 게이트 | guardrail (제한적) |
| **ASIL-C/D 검토** | "안전 관련 함수 변경" | Critical | 다른 팀 리뷰 강제 | 외부 프로세스 + hook | 외부 프로세스 + 이벤트 | 외부 프로세스 (통합 어려움) |
| **Confidence 임계값 미달** | "LLM 응답의 확신도 < 70%" | Medium | 인간에게 검증 요청 | prompt hook으로 검증 강제 | `context` 이벤트에서 감지 | 없음 |
| **E2E 버그 발견** | "인간이 직접 발견한 버그" | High | TDD-first 재진입 | dev-phase-state.json 업데이트 | 상태 업데이트 + 재시작 | 새 실행 시작 |
| **외부 의존성 변경** | "새 라이브러리 도입" | Medium | 보안 검토 후 승인 | PreToolUse에서 npm install 차단 | `tool_call` block | guardrail |
| **비가역적 연산** | "파일 삭제, git force push" | Critical | 이중 확인 (double confirm) | deny 후 명시적 재요청 | block + 확인 루프 | tripwire (재시작 필요) |

#### 11.5.2 Confidence 기반 자동 판단 기준

```
Confidence Level에 따른 HITL 정책:

  ≥ 90%: 자동 진행 (HITL 불필요)
         예: "단위 테스트 추가", "타입 오류 수정"

  70-89%: 경고 표시 후 자동 진행 (soft HITL)
          예: "리팩토링 방향 결정", "에러 핸들링 전략"

  50-69%: 인간에게 선택지 제시 (active HITL)
          예: "두 가지 설계 중 선택", "불명확한 요구사항 해석"

  < 50%:  즉시 중단, 인간 판단 필수 (hard HITL)
          예: "요구사항이 모순됨", "도메인 지식 부족"
```

실제 구현에서 confidence는 LLM이 자체적으로 보고하는 것이 아니라, **구조화된 프롬프트**를 통해 추출한다. 예를 들어, 에이전트에게 "이 결정에 대한 확신도를 1-10으로 평가하고, 7 미만이면 AskUserQuestion을 사용하라"고 지시하는 방식이다.

---

### 11.6 Stripe Minions 패턴의 중간 단계 HITL 확장

Stripe Minions의 원래 Blueprint에서 인간은 최종 PR 리뷰라는 **단일 종단 게이트**에만 존재한다. 본 절에서는 이 패턴을 중간 실행 HITL로 확장한다.

#### 11.6.1 기존 패턴 vs 확장 패턴

```
기존 Stripe Minions 패턴 (종단 게이트 HITL만):
══════════════════════════════════════════════

  [Slack 태스크 수신]
          ↓
  [컨텍스트 하이드레이션]     ← 결정론적
          ↓
  [에이전트: 태스크 구현]     ← 비결정론적 (자율 실행)
          ↓
  [린트 게이트]               ← 결정론적
          ↓
  [CI 실행]                   ← 결정론적
          ↓
  [git push]                  ← 결정론적
          ↓
  ┌─────────────────────┐
  │  인간 PR 리뷰       │     ← 유일한 HITL (종단 게이트)
  │  [에이전트 우회 불가]│
  └─────────┬───────────┘
          ↓
        [병합]


확장된 중간 HITL 패턴 (dev-phase-state-machine 통합):
═══════════════════════════════════════════════════════

  [태스크 수신]
          ↓
  ┌───────────────────────────────┐
  │  에이전트: 스펙 분석 & 작성   │  ← 비결정론적
  │  (SPEC phase)                 │
  └───────────────┬───────────────┘
                  ↓
  ╔═══════════════════════════════╗
  ║  인간: 스펙 승인?             ║  ← 중간 HITL #1 (설계 결정)
  ║                               ║
  ║  [승인] → 다음 단계           ║     Stop hook 또는
  ║  [수정요청] → 스펙 재작성     ║     before_agent_start 게이트
  ║  [거부] → 태스크 취소         ║
  ╚═══════════════╤═══════════════╝
                  ↓ 승인
  ┌───────────────────────────────┐
  │  에이전트: 테스트 케이스 작성  │  ← 비결정론적
  │  (TESTCASE phase)             │
  └───────────────┬───────────────┘
                  ↓
  ╔═══════════════════════════════╗
  ║  인간: TC 리뷰?              ║  ← 중간 HITL #2 (추적성 검증)
  ║                               ║
  ║  검증 항목:                   ║     모든 요구사항이 TC로 커버?
  ║  - REQ → TC 매핑 완전성      ║     누락된 엣지 케이스?
  ║  - 엣지 케이스 커버리지       ║
  ║  - ASIL 등급에 맞는 TC 수    ║
  ╚═══════════════╤═══════════════╝
                  ↓ 승인
  ┌───────────────────────────────┐
  │  에이전트: 코드 구현           │  ← 비결정론적
  │  (CODING phase)               │
  │                               │
  │  도구 승인 HITL:              │  ← 도구별 미세 HITL
  │  - 파일 삭제 → 인간 승인      │     (risk level 기반)
  │  - 새 의존성 추가 → 인간 승인  │
  │  - 설계 변경 → AskUserQuestion│
  └───────────────┬───────────────┘
                  ↓
  ┌───────────────────────────────┐
  │  결정론적: lint + test 게이트  │  ← 자동 게이트 (HITL 아님)
  │  (TEST phase)                 │
  │                               │
  │  lint 실패 → 에이전트 재시도  │
  │  test 실패 → 에이전트 재시도  │
  │  최대 2회 재시도              │
  └───────────────┬───────────────┘
                  ↓ 통과
  ╔═══════════════════════════════╗
  ║  인간: E2E 테스트 수행        ║  ← 중간 HITL #3 (수동 검증)
  ║                               ║
  ║  인간이 직접 실행하여 확인:   ║     자동화 불가능한 검증
  ║  - UI 동작 확인               ║     (시각적 검증, UX 평가 등)
  ║  - 엣지 케이스 수동 테스트    ║
  ║  - 버그 발견 시 → TDD 재진입 ║
  ╚═══════════════╤═══════════════╝
                  ↓ 통과
  ┌───────────────────────────────┐
  │  결정론적: git push           │  ← 자동
  └───────────────┬───────────────┘
                  ↓
  ╔═══════════════════════════════╗
  ║  인간: PR 리뷰               ║  ← 종단 HITL (Stripe 패턴 유지)
  ║  [에이전트 우회 불가]         ║
  ╚═══════════════╤═══════════════╝
                  ↓
                [병합]
```

#### 11.6.2 확장의 핵심 원칙

이 확장은 세 가지 원칙을 따른다.

1. **결정론적 게이트와 HITL 게이트의 구분**: 린트/테스트 통과는 결정론적 게이트다 (자동 판단 가능). 스펙 승인, TC 검증은 HITL 게이트다 (인간 판단 필요). 둘을 혼동하면 안 된다.

2. **HITL 게이트는 단계 전환점에 배치**: 에이전트가 **다른 종류의 작업**으로 전환하는 시점이 HITL의 최적 위치다. 스펙 → TC, TC → 코드, 코드 → 테스트 각 전환점은 이전 단계의 산출물을 인간이 검증하는 자연스러운 시점이다.

3. **도구 수준 HITL은 위험도에 비례**: 코딩 단계에서 모든 도구 호출에 승인을 요구하면 생산성이 붕괴한다. 위험 수준에 따라 자동 승인/경고/차단을 구분한다.

#### 11.6.3 dev-phase-state.json과 HITL 통합

```json
{
  "phase": "TESTCASE",
  "phaseComplete": false,
  "hitlRequired": true,
  "hitlType": "phase_transition",
  "hitlStatus": "pending",
  "hitlContext": {
    "from": "SPEC",
    "to": "TESTCASE",
    "specVersion": "a3f2b1c",
    "specApprovedBy": "developer@company.com",
    "specApprovedAt": "2026-03-04T10:30:00Z",
    "artifacts": ["SPEC.md", "docs/requirements.md"]
  },
  "history": [
    {
      "phase": "SPEC",
      "hitlDecision": "approved",
      "hitlBy": "developer@company.com",
      "hitlAt": "2026-03-04T10:30:00Z",
      "hitlComment": "스펙 검토 완료. API 설계는 REST 방식으로 확정."
    }
  ]
}
```

이 상태 파일은 git으로 추적되므로, HITL 결정의 전체 이력이 코드베이스에 영속적으로 기록된다. ISO 26262의 감사 추적 요건을 자연스럽게 충족한다.

---

### 11.7 프레임워크별 HITL 능력 비교 매트릭스

세 프레임워크의 HITL 능력을 체계적으로 비교한다.

| HITL 기능 | Claude Code + OMC | Pi SDK | OpenAI Agents SDK |
|-----------|:-----------------:|:------:|:-----------------:|
| **실행 중 도구 승인** | ✅ 기본 내장 (allow/deny/ask) | ✅ `tool_call` block | ✅ guardrail tripwire |
| **대화형 질문 (구조화)** | ✅ AskUserQuestion (네이티브) | ⚙️ `input` 이벤트 + 커스텀 UI | ⚙️ handoff to human agent |
| **단계 전환 승인** | ✅ Stop hook + 메시지 | ✅ `before_agent_start` 게이트 | ⚙️ guardrail (재시작 필요) |
| **중간 컨텍스트 주입** | ✅ prompt hook (additionalContext) | ✅ `context` 이벤트 (매 LLM 호출) | ❌ 없음 |
| **ASIL 기반 조건부 HITL** | ⚙️ hook에서 ASIL 파일 읽어 조건 분기 | ✅ 완전 커스텀 (인프로세스) | ❌ 지원 없음 |
| **인간 부재 시 폴백** | ⚙️ timeout 없음 (무한 대기) | ✅ 커스텀 timeout + 폴백 구현 | ❌ tripwire는 즉시 중단 |
| **일시 중지/재개** | ✅ 네이티브 (CLI 대기) | ✅ 이벤트 루프에서 await | ❌ tripwire는 실행 종료 |
| **점진적 신뢰 (allowAll)** | ✅ 세션 내 allowAll | ⚙️ 커스텀 구현 필요 | ❌ 없음 |
| **IDE 통합 HITL** | ✅ VS Code, JetBrains (네이티브) | ❌ 터미널 전용 | ❌ API 전용 |
| **OMC 스킬과 HITL 통합** | ✅ ralph, ralplan 연동 | ❌ 해당 없음 | ❌ 해당 없음 |
| **인간 결정 감사 추적** | ⚙️ transcript_path에 기록 | ✅ `appendEntry()` JSONL | ⚙️ trace 스팬에 기록 |
| **다중 인간 리뷰어** | ⚙️ 외부 프로세스 필요 | ✅ 외부 큐 + 이벤트 통합 | ❌ 단일 handoff만 |

**범례**: ✅ 네이티브/쉬운 구현 | ⚙️ 가능하나 커스텀 필요 | ❌ 불가 또는 극히 제한적

#### 비교 분석 요약

**Claude Code + OMC**의 HITL 강점은 **사용자 경험**이다. CLI/IDE에서 자연스러운 대화형 HITL을 제공하며, 개발자가 추가 코드를 작성하지 않아도 기본적인 승인/거부/질문 패턴이 동작한다. OMC 스킬(ralph, ralplan)과의 통합은 dev-phase-state-machine과 HITL을 자연스럽게 연결한다.

**Pi SDK**의 HITL 강점은 **프로그래밍 가능성**이다. 28개 이벤트를 자유롭게 조합하여 어떤 HITL 패턴이든 구현할 수 있다. 특히 `context` 이벤트를 통한 매 LLM 호출 컨텍스트 주입은 Pi SDK의 고유 기능이며, 이는 인간 결정을 에이전트 루프 깊숙이 주입할 수 있게 한다.

**OpenAI Agents SDK**의 HITL은 **구조적으로 제한적**이다. handoff는 에이전트 간 위임이라는 우아한 추상화이지만, 실시간 대화형 HITL에는 부적합하다. tripwire의 "중단 후 재시작" 모델은 중간 상태 손실을 야기한다.

---

### 11.8 권고 HITL 아키텍처 (Claude Code + OMC 기반)

본 보고서의 아키텍처 방향(섹션 8, 9에서 도출)에 따라, Claude Code + OMC + Hook 기반의 권고 HITL 구현을 제시한다.

#### 11.8.1 dev-phase-state-machine과 HITL 통합 아키텍처

```
┌────────────────────────────────────────────────────────────┐
│                Claude Code + OMC HITL 아키텍처              │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              .claude/settings.json                    │  │
│  │                                                      │  │
│  │  permissions:                                        │  │
│  │    allow: [Read, Glob, Grep, Bash(npm test*)]       │  │
│  │    deny: [Bash(git push --force*)]                  │  │
│  │                                                      │  │
│  │  hooks:                                              │  │
│  │    PreToolUse:  → risk-assessment.sh                │  │
│  │    Stop:        → phase-gate.sh                     │  │
│  │    PostToolUse: → traceability-record.sh            │  │
│  └──────────────────────────────────────────────────────┘  │
│                           │                                │
│                           ▼                                │
│  ┌──────────────────────────────────────────────────────┐  │
│  │          dev-phase-state-machine                      │  │
│  │                                                      │  │
│  │  SPEC ──[HITL: 스펙승인]──→ TESTCASE                │  │
│  │  TESTCASE ──[HITL: TC검증]──→ CODING                │  │
│  │  CODING ──[자동: lint/test]──→ TEST                  │  │
│  │  TEST ──[HITL: E2E검증]──→ REVIEW                   │  │
│  │  REVIEW ──[HITL: PR리뷰]──→ DONE                    │  │
│  └──────────────────────────────────────────────────────┘  │
│                           │                                │
│                           ▼                                │
│  ┌──────────────────────────────────────────────────────┐  │
│  │          OMC 스킬 통합                                │  │
│  │                                                      │  │
│  │  /ralplan → Plan Mode + HITL (스펙 단계)            │  │
│  │  /ralph   → 구현 + 도구 승인 HITL (코딩 단계)      │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘
```

#### 11.8.2 단계별 HITL 구현

**SPEC 단계: AskUserQuestion을 통한 스펙 확인**

이 단계에서 에이전트는 요구사항을 분석하고 SPEC.md를 작성한다. 작성 완료 후 AskUserQuestion으로 인간에게 확인을 요청한다.

```
[에이전트 → 인간]
AskUserQuestion: SPEC.md 작성을 완료했습니다.

핵심 설계 결정:
  1. 인증 방식: OAuth2 (PKCE flow)
  2. 데이터 저장: PostgreSQL + Redis 캐시
  3. API 스타일: REST (OpenAPI 3.1 스펙 포함)

선택지:
  A) 승인 — TESTCASE 단계로 진행
  B) 수정 요청 — 구체적인 수정 사항을 알려주세요
  C) 거부 — 태스크 취소

사용자 선택: _
```

인간의 응답에 따라 dev-phase-state.json이 업데이트되고, Stop hook이 단계 전환을 제어한다.

**TESTCASE 단계: TC 리스트 검증**

에이전트가 생성한 테스트 케이스 목록을 인간이 검토한다. 핵심은 **추적성 검증**이다.

```
[에이전트 → 인간]
AskUserQuestion: 테스트 케이스 작성을 완료했습니다.

추적성 매트릭스:
  REQ-001 (사용자 로그인)    → TC-001, TC-002, TC-003
  REQ-002 (세션 관리)       → TC-004, TC-005
  REQ-003 (비밀번호 재설정)  → TC-006, TC-007, TC-008
  REQ-004 (2FA)             → (미커버) ⚠️

경고: REQ-004에 대한 테스트 케이스가 없습니다.

선택지:
  A) 승인 — 현재 TC로 CODING 단계 진행
  B) TC 추가 요청 — REQ-004 관련 TC 작성 지시
  C) 스펙으로 회귀 — REQ-004 요구사항 재검토

사용자 선택: _
```

**CODING 단계: 도구별 위험도 기반 승인**

코딩 단계에서는 모든 도구에 HITL을 적용하면 생산성이 급락한다. 위험도 기반 선택적 HITL을 적용한다.

```json
{
  "permissions": {
    "allow": [
      "Read", "Glob", "Grep",
      "Write",
      "Edit",
      "Bash(npm test*)",
      "Bash(npm run lint*)",
      "Bash(npx tsc --noEmit*)",
      "Bash(git add*)",
      "Bash(git status)",
      "Bash(git diff*)"
    ],
    "deny": [
      "Bash(git push --force*)",
      "Bash(rm -rf /)*",
      "Bash(DROP TABLE*)",
      "Bash(sudo *)"
    ]
  }
}
```

`allow`와 `deny` 어디에도 없는 연산(예: `git commit`, `npm install <new-package>`, `git push`)은 자동으로 HITL 대상이 된다. 사용자에게 승인을 요청하고, `allowAll` 옵션으로 세션 내 동일 유형 승인을 일괄 처리할 수 있다.

**TEST 단계: E2E 테스트 수동 검증 프롬프트**

자동 테스트(lint, unit test)가 통과한 후, E2E 검증이 필요한 경우 인간에게 수동 테스트를 요청한다.

```
[에이전트 → 인간]
AskUserQuestion: 모든 자동 테스트가 통과했습니다.

테스트 결과:
  - Unit tests: 47/47 passed
  - Lint: 0 errors, 0 warnings
  - Type check: passed

E2E 수동 검증이 필요합니다:
  1. http://localhost:3000 에서 로그인 플로우 테스트
  2. OAuth2 리다이렉트 동작 확인
  3. 세션 만료 후 재로그인 확인

수동 테스트 완료 후 결과를 알려주세요:
  A) 모든 E2E 테스트 통과
  B) 버그 발견 — 구체적인 증상을 설명해주세요
  C) E2E 테스트 건너뛰기 — PR 리뷰로 진행

사용자 선택: _
```

사용자가 B를 선택하면, 에이전트는 보고된 버그에 대해 **TDD-first 재진입**을 수행한다. 먼저 버그를 재현하는 테스트를 작성하고, 그 테스트가 통과하도록 코드를 수정한다.

#### 11.8.3 인간 부재 시 전략

실무 환경에서 인간이 항상 즉시 응답할 수 있는 것은 아니다. HITL 요청에 인간이 응답하지 않는 상황에 대한 전략이 필요하다.

```
HITL 요청 후 인간 부재 시 정책:

  [즉시] HITL 요청 발송 (AskUserQuestion / Stop hook)
     ↓
  [대기] 에이전트 일시 중단 — 다른 태스크 진행 가능 (Claude Code CLI에서)
     ↓
  [선택적] Slack/Email 알림 발송 (외부 hook 연동)
     ↓
  [무한 대기] Claude Code는 기본적으로 timeout 없이 대기
     ↓
  [권고] 팀 정책으로 HITL 응답 SLA 설정
          - 설계 결정: 4시간 이내
          - 위험 연산 승인: 1시간 이내
          - 단계 전환: 2시간 이내
          - ASIL-C/D 검토: 24시간 이내 (다른 팀 포함)
```

Pi SDK에서는 `setTimeout`과 폴백 로직으로 프로그래밍적 대응이 가능하지만, Claude Code + OMC 환경에서는 외부 알림 시스템과의 연동이 더 실용적이다.

#### 11.8.4 HITL 감사 추적

모든 HITL 상호작용은 감사 추적 가능하게 기록되어야 한다. Claude Code의 `transcript_path`와 `PostToolUse` hook을 조합하여 구현한다.

```bash
#!/bin/bash
# .claude/hooks/record-hitl-decision.sh
# PostToolUse hook: HITL 결정을 구조화된 로그에 기록

TOOL_NAME=$(echo "$CLAUDE_HOOK_EVENT" | jq -r '.tool_name')

# AskUserQuestion 결과를 감사 로그에 기록
if [ "$TOOL_NAME" = "AskUserQuestion" ]; then
  QUESTION=$(echo "$CLAUDE_HOOK_EVENT" | jq -r '.tool_input.question // "unknown"')
  RESULT=$(echo "$CLAUDE_HOOK_EVENT" | jq -r '.tool_result // "unknown"')
  TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  PHASE=$(jq -r '.phase' .claude/dev-phase-state.json 2>/dev/null || echo "unknown")

  # Append to audit log (JSONL format)
  echo "{\"type\":\"hitl_decision\",\"timestamp\":\"$TIMESTAMP\",\"phase\":\"$PHASE\",\"question\":\"$QUESTION\",\"humanResponse\":\"$RESULT\"}" >> .claude/hitl-audit-log.jsonl
fi
```

이 감사 로그는 ISO 26262의 추적성 요건을 충족하며, git으로 추적되어 코드 변경 이력과 함께 인간 결정 이력이 영속적으로 보존된다.

---

### 11.9 소결

HITL은 코딩 에이전트의 약점을 보완하는 방어 장치가 아니라, **에이전트 시스템의 신뢰성을 구성하는 필수 설계 요소**다. 핵심 통찰은 다음 세 가지로 요약된다.

1. **종단 게이트만으로는 부족하다**: Stripe Minions의 PR 리뷰는 최소한의 HITL이다. 중간 실행 HITL(스펙 승인, TC 검증, 설계 결정)이 추가되어야 비용 효율적인 에이전트 시스템이 완성된다.

2. **HITL의 빈도는 위험도에 비례해야 한다**: 모든 연산에 인간 승인을 요구하면 자동화의 의미가 사라진다. Confidence 임계값과 위험 수준에 따른 선택적 HITL이 최적이다.

3. **Claude Code + OMC는 가장 자연스러운 HITL을 제공한다**: CLI/IDE 환경에서의 대화형 HITL, AskUserQuestion, 3단계 permission 시스템(allow/ask/deny), Stop hook 기반 단계 게이트는 개발자 경험을 해치지 않으면서 신뢰성을 확보하는 균형점이다. Pi SDK는 프로그래밍 가능성에서 우위이나, 기본 제공 HITL UX가 없어 추가 구현 비용이 발생한다.

---

## 12. 신뢰성-효율성 Trade-off 전략

---

### 12.1 SPEC의 핵심 긴장: 신뢰성과 효율성 사이

SPEC 요구사항은 다음과 같은 근본적 긴장을 명시한다:

> "모든 Agent를 langgraph방식의 상태머신으로 만든다면 신뢰성은 올라가지만,
> 해당 시스템이 처리할 수 있는 task가 적어지므로 효율성은 떨어짐."

이 문장은 코딩 에이전트 시스템 설계에서 가장 중요한 아키텍처 결정을 압축하고 있다.
양 극단을 시각화하면 다음과 같다:

```
신뢰성 ↑                          효율성 ↑
────────────────────────────────────────────
상태머신 + 엄격한 게이트           one-loop agent + 게이트 없음
처리 가능 task 범위 ↓              처리 가능 task 범위 ↑
개발/설정 비용 ↑                   개발/설정 비용 ↓
자율성 ↓                           자율성 ↑
```

그러나 이 긴장을 단순한 이분법으로 치환하는 것은 오류다. 실제 시스템은 스펙트럼 위의
한 점을 선택하며, 그 선택은 태스크의 성격에 따라 동적으로 이동할 수 있다.
본 섹션에서는 이 스펙트럼을 체계적으로 정의하고, 태스크 유형별 최적 위치를 결정하는
전략을 제시한다.

핵심 주장은 다음과 같다: **신뢰성과 효율성은 zero-sum이 아니다.**
올바른 레벨의 게이트를 올바른 태스크에 적용하면 양쪽 모두를 최적화할 수 있다.

---

### 12.2 "효율성"의 다차원 정의

"효율성"을 단일 지표로 논하면 논의가 공전한다.
본 보고서에서는 효율성을 4개 독립 차원으로 분해하여 정의한다.

#### E1: 처리 가능 태스크 범위 (유연성, Flexibility)

| 항목 | 내용 |
|------|------|
| **정의** | 에이전트가 해결 가능한 태스크의 다양성과 범위 |
| **측정** | 처리 가능 태스크 유형 수, 예외 상황 처리율 |
| **상태머신 방식** | 사전 정의된 노드와 전이만 처리 가능 → 범위 제한 |
| **one-loop 방식** | LLM 판단으로 모든 상황 대응 → 범위 무제한 (단, 신뢰성 불보장) |

상태머신에 노드가 10개 정의되어 있다면, 그 에이전트는 10가지 유형의 작업만 수행할 수 있다.
11번째 유형의 태스크가 들어오면 시스템은 거부하거나 잘못된 노드로 라우팅한다.
반면 one-loop agent는 LLM의 범용 추론 능력을 그대로 활용하므로 이론적으로 무한한
태스크를 처리할 수 있으나, 각 태스크의 결과를 보장할 수 없다.

#### E2: 개발/배포 비용 (Time-to-Deploy)

| 항목 | 내용 |
|------|------|
| **정의** | 에이전트 시스템을 설계, 구현, 유지보수하는 데 드는 총 비용 |
| **측정** | 초기 설정 시간, 새 기능 추가 시간, 디버깅 시간 |
| **상태머신 방식** | 높은 초기 비용, 예측 가능한 유지보수 |
| **one-loop 방식** | 낮은 초기 비용, 비예측적 유지보수 (프롬프트 디버깅) |

상태머신은 "설계 → 구현 → 테스트"의 전통적 소프트웨어 개발 비용을 요구한다.
one-loop agent는 프롬프트 하나로 시작 가능하지만, 프로덕션에서 발생하는 edge case를
프롬프트로 패치하는 비용이 시간이 갈수록 비선형적으로 증가한다.

#### E3: 런타임 오버헤드 (성능, Performance)

| 항목 | 내용 |
|------|------|
| **정의** | 게이트 실행으로 인한 추가 지연 시간과 LLM 호출 비용 |
| **측정** | 게이트당 평균 실행 시간, LLM 호출 증가율, 추가 토큰 소비량 |
| **예시** | PreToolUse hook = ~5-50ms/tool call, Stop hook = ~100-500ms/session |

게이트의 유형에 따라 오버헤드가 크게 달라진다:
- **결정론적 게이트** (파일 경로 패턴 매칭): ~1-5ms, 무시 가능
- **스크립트 게이트** (lint, test 실행): ~100ms-30s, 태스크 종류에 비례
- **LLM 기반 게이트** (의미론적 판단): ~500ms-5s, 추가 비용 발생
- **HITL 게이트** (인간 승인 대기): ~분-시간 단위, 비동기 처리 필수

#### E4: 에이전트 자율성 (창의적 문제 해결, Autonomy)

| 항목 | 내용 |
|------|------|
| **정의** | 에이전트가 예상 외 방법으로 문제를 해결할 수 있는 자유도 |
| **측정** | 비표준 해결책 채택률, 사용자 추가 개입 빈도 |
| **과도한 게이트의 부작용** | 창의적 해결책 차단, 우회 경로 탐색 불가 |

이 차원은 종종 간과되지만 에이전트 시스템의 핵심 가치와 직결된다.
에이전트를 사용하는 근본 이유는 인간이 미처 생각하지 못한 접근법을 LLM이 제안할 수 있기
때문이다. 과도한 게이트는 이 가치를 소멸시킨다.

**4차원 요약 다이어그램:**

```
              E1 유연성
                 ↑
                 │
        E4 자율성 ┼─────→ E2 개발 비용
                 │
                 ↓
              E3 성능

※ 각 차원은 독립적으로 최적화 가능하며,
   게이트 레벨에 따라 각 차원의 값이 변화한다.
```

---

### 12.3 결정론적 제어 강도 스펙트럼 (Level 0-4)

결정론적 제어의 강도를 5단계로 정의한다.
각 레벨은 이전 레벨의 상위 집합(superset)이다.

#### Level 0: Pure Agent (게이트 없음)

```
구성:   one-loop agent만 사용. 어떤 가드레일도 없음.
적합:   탐색적 프로토타이핑, 개인 실험, PoC 개발
신뢰성: ★☆☆☆☆
효율성: ★★★★★ (E1~E4 모두 최대)
구현 비용: 0시간
예:     claude code 기본 실행, pi 기본 실행
```

Level 0은 에이전트의 원시적 능력을 그대로 활용한다.
모든 결정을 LLM에 위임하며, 출력의 품질은 전적으로 모델 성능에 의존한다.
프로토타이핑 단계에서는 이것이 최적이지만,
프로덕션 코드에 적용하면 **회귀 버그, 보안 취약점, 코드 규약 위반**이 비결정적으로 발생한다.

#### Level 1: 최소 게이트 (커밋 전 검증만)

```
구성:   커밋 전 lint + test 실행 (PostToolUse 또는 pre-commit hook)
적합:   단순 버그 수정, 설정 변경, 소규모 패치
신뢰성: ★★☆☆☆
효율성: ★★★★☆
구현 비용: 2-4시간 (hook 스크립트 2개)
적용 조건: 기존 테스트 스위트가 있고 변경 범위가 작을 때
```

**구현 예시 (Claude Code hook):**
```json
// .claude/hooks/postToolUse_bash.sh
// Trigger: PostToolUse event on Bash tool
// Purpose: Intercept git commit and run validation

if echo "$TOOL_INPUT" | grep -q "git commit"; then
  echo "Running pre-commit validation..."
  npm run lint && npm run test:affected
  if [ $? -ne 0 ]; then
    echo "BLOCK: Lint or test failed. Commit rejected."
    exit 1
  fi
fi
```

Level 1은 "에이전트가 자유롭게 작업하되, 결과물을 커밋하기 전에 최소한의 품질 검증을 수행한다"는 철학이다. 기존 CI/CD 파이프라인의 왼쪽 이동(shift-left)으로 볼 수 있다.

#### Level 2: 중간 게이트 (상태별 도구 제한 + 컨텍스트 주입)

```
구성:   개발 단계(phase)별 파일 쓰기 제한 + 프롬프트 주입 + 선택적 HITL
적합:   기능 개발, 모듈 추가, 중간 규모 변경
신뢰성: ★★★☆☆
효율성: ★★★☆☆
구현 비용: 1-2일 (dev-phase-state.json + 5-7개 hook)
적용 조건: 스펙-TC-코드 추적성(traceability)이 필요할 때
```

**핵심 메커니즘:**
- `dev-phase-state.json`으로 현재 개발 단계를 추적
- 단계별로 허용되는 도구와 파일 경로를 제한
- 단계 전이 시 검증 조건(gate condition)을 확인
- SubTask 프롬프트에 현재 단계 컨텍스트를 자동 주입

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ spec_tdd │───→│   impl   │───→│  verify  │───→│  commit  │
└──────────┘    └──────────┘    └──────────┘    └──────────┘
  Write: spec     Write: src     Write: none     Write: none
  Read: all       Read: all      Read: all       Read: all
  Gate: TC 존재    Gate: lint     Gate: test      Gate: review
```

이 레벨은 본 보고서의 dev-phase-state-machine.md에서 설계한 시스템에 해당하며,
**결정론적 혼합(deterministic mixing)**의 실용적 시작점이다.

#### Level 3: 전체 게이트 (Stripe Minions 패턴 풀 적용)

```
구성:   상태머신 + 각 노드별 결정론/비결정론 선택 + 인간 게이트
적합:   신규 기능 개발, 팀 협업 프로젝트, 크로스 모듈 변경
신뢰성: ★★★★☆
효율성: ★★☆☆☆
구현 비용: 1-2주 (상태머신 + 모든 게이트 구현)
적용 조건: ASIL-A/B 수준 요구, 팀 규모 3명 이상
```

**Stripe Minions 패턴 적용:**
- 상위 에이전트(ralph)가 태스크를 분해하고 하위 에이전트에 배분
- 각 하위 에이전트는 제한된 범위 내에서만 작업 수행
- 병합 시 상위 에이전트가 충돌 해결 및 통합 검증
- LangGraph 상태머신으로 전체 워크플로우를 오케스트레이션

```python
# LangGraph state machine skeleton (Level 3)
from langgraph.graph import StateGraph

workflow = StateGraph(DevState)

workflow.add_node("plan", plan_node)          # Deterministic: structured output
workflow.add_node("decompose", decompose_node) # Deterministic: task splitting
workflow.add_node("execute", execute_node)      # Non-deterministic: agent coding
workflow.add_node("review", review_node)        # Deterministic: automated checks
workflow.add_node("approve", human_gate)        # HITL: human approval

workflow.add_edge("plan", "decompose")
workflow.add_edge("decompose", "execute")
workflow.add_edge("execute", "review")
workflow.add_conditional_edges("review", route_review)  # pass → approve, fail → execute
workflow.add_edge("approve", END)
```

#### Level 4: 최대 게이트 (ISO 26262 ASIL-D 수준)

```
구성:   엄격한 상태머신 + 인간 승인 필수 + 감사 로그 + 외부 리뷰
적합:   안전 관련 코드 (브레이크, 조향, 에어백 제어 등), ASIL-C/D
신뢰성: ★★★★★
효율성: ★☆☆☆☆
구현 비용: 수개월 (ISO 26262 표준 준수 포함)
적용 조건: 기능 안전 요구사항이 존재하고 법적 책임이 따르는 경우
```

Level 4는 에이전트를 "보조 도구"로 격하시키고, 모든 결정에 인간 전문가의 승인을 요구한다.
코드 한 줄을 생성할 때마다 추적 가능한 감사 로그를 남기며,
외부 안전 심사관이 전체 프로세스를 검토할 수 있는 형식으로 산출물을 관리한다.
이 레벨은 기능 안전 전문가(functional safety engineer)와 함께 설계해야 한다.

#### 5개 레벨 종합 비교표

| 속성 | Level 0 | Level 1 | Level 2 | Level 3 | Level 4 |
|:----:|:-------:|:-------:|:-------:|:-------:|:-------:|
| **게이트 수** | 0 | 1-2 | 5-7 | 15-20 | 30+ |
| **신뢰성** | ★☆☆☆☆ | ★★☆☆☆ | ★★★☆☆ | ★★★★☆ | ★★★★★ |
| **E1 유연성** | ★★★★★ | ★★★★☆ | ★★★☆☆ | ★★☆☆☆ | ★☆☆☆☆ |
| **E2 개발비용** | ★★★★★ | ★★★★☆ | ★★★☆☆ | ★★☆☆☆ | ★☆☆☆☆ |
| **E3 성능** | ★★★★★ | ★★★★☆ | ★★★★☆ | ★★★☆☆ | ★★☆☆☆ |
| **E4 자율성** | ★★★★★ | ★★★★☆ | ★★★☆☆ | ★★☆☆☆ | ★☆☆☆☆ |
| **적합 대상** | 프로토타입 | 버그 수정 | 기능 개발 | 팀 프로젝트 | 안전 코드 |
| **구현 비용** | 0h | 2-4h | 1-2일 | 1-2주 | 수개월 |
| **HITL 빈도** | 없음 | 필요시 | 단계 전이 | 노드별 | 모든 결정 |

---

### 12.4 태스크 유형별 게이트 레벨 배분 전략

모든 태스크에 동일한 게이트 레벨을 적용하는 것은 비효율적이다.
태스크의 **위험도(risk)**와 **영향 범위(blast radius)**에 따라 적절한 레벨을 배분해야 한다.

#### 태스크 유형-레벨 매핑 테이블

| 태스크 유형 | 예시 | 권장 레벨 | 핵심 이유 |
|:----------:|:----:|:---------:|:--------:|
| 탐색적 프로토타이핑 | PoC 개발, 기술 조사, 벤치마크 | Level 0 | 빠른 반복이 최우선, 결과물이 폐기될 수 있음 |
| 단순 버그 수정 | 오타 수정, 소형 로직 버그, 1-2파일 변경 | Level 1 | 기존 TC로 회귀 검증 가능, 변경 범위 명확 |
| 설정 파일 변경 | CI/CD 설정, 환경 변수, 빌드 설정 | Level 1 | 회귀 리스크 낮음, 롤백 용이 |
| 문서/주석 업데이트 | README, API 문서, 코드 주석 | Level 0-1 | 코드 동작에 영향 없음 |
| 독립 모듈 기능 개발 | 새 유틸리티 함수, 헬퍼 클래스 추가 | Level 2 | 추적성 확보 필요, 기존 코드와 결합도 낮음 |
| 핵심 비즈니스 로직 변경 | 결제 로직, 인증/인가 수정, 데이터 처리 | Level 2-3 | 회귀 위험 높음, 비즈니스 영향 직접적 |
| 신규 기능 (팀 협업) | 새 API 엔드포인트, 신규 서비스 모듈 | Level 3 | 여러 파일/모듈 영향, 팀원 간 코드 충돌 가능 |
| 리팩토링 (구조 변경) | 모듈 분리, 디자인 패턴 적용, 의존성 정리 | Level 2-3 | 동작 보존이 핵심, 광범위 영향 |
| 플랫폼 아키텍처 변경 | DB 마이그레이션, 프레임워크 업그레이드 | Level 3-4 | 시스템 전체 영향, 롤백 비용 높음 |
| 안전 관련 코드 (ASIL) | 브레이크 제어 SW, 의료 기기 펌웨어 | Level 4 | 기능 안전 필수, 법적 책임 수반 |

#### 배분 원칙

1. **최소 충분 원칙**: 태스크에 필요한 최소 레벨을 적용한다. 과잉 게이트는 생산성을 저해한다.
2. **상향 조정 원칙**: 불확실성이 높으면 한 단계 상향 적용한다.
3. **파일 기반 판단**: 수정 대상 파일의 중요도가 태스크 유형보다 우선한다.
   (예: 프로토타입 작업이라도 `src/core/auth.ts`를 수정한다면 Level 2 이상 적용)
4. **팀 규모 고려**: 2명 이상 협업 시 최소 Level 2, 4명 이상이면 Level 3을 권장한다.

---

### 12.5 의사결정 플로우차트: 어느 레벨을 선택할까?

#### 의사결정 흐름도

```
태스크 시작
    │
    ▼
┌─────────────────────────┐
│ 안전 관련 코드인가?       │──Yes──→ Level 4 (ASIL 준수 필수)
│ (ASIL, 의료기기, 법적책임) │
└─────────────────────────┘
    │ No
    ▼
┌─────────────────────────┐
│ 여러 팀이 협업하는가?     │──Yes──→ Level 3 (전체 게이트)
│ (크로스팀, 4명+)          │
└─────────────────────────┘
    │ No
    ▼
┌─────────────────────────┐
│ 핵심 비즈니스 로직을      │──Yes──→ Level 2-3 (중간-전체 게이트)
│ 변경하는가?               │         ├ 단일 모듈 → Level 2
└─────────────────────────┘         └ 크로스 모듈 → Level 3
    │ No
    ▼
┌─────────────────────────┐
│ 새 기능/모듈인가?         │──Yes──→ Level 2 (중간 게이트)
│ (새 파일 생성 포함)        │
└─────────────────────────┘
    │ No
    ▼
┌─────────────────────────┐
│ 기존 기능 버그 수정?      │──Yes──→ Level 1 (최소 게이트)
│ (기존 TC 존재)            │
└─────────────────────────┘
    │ No (탐색/실험/문서)
    ▼
Level 0 (게이트 없음)
```

#### 보조 판단 기준: 파일 중요도 오버라이드

```
수정 대상 파일 확인
    │
    ▼
[core/*, auth/*, payment/*, safety/*]  → 최소 Level 2 강제
[config/*, .env*, docker*]             → 최소 Level 1 강제
[docs/*, README*, *.md]                → Level 0 허용
[test/*, __tests__/*]                  → 현재 레벨 유지
```

#### 설정 파일 기반 자동화

실제 프로젝트에서는 위 판단을 수동으로 하지 않고 설정 파일로 자동화한다:

```json
// .agent-profile.json
{
  "default_level": 1,
  "task_overrides": {
    "safety_critical": 4,
    "team_feature": 3,
    "new_module": 2,
    "bugfix": 1,
    "prototype": 0
  },
  "file_overrides": {
    "level_2_minimum": [
      "src/core/**",
      "src/auth/**",
      "src/payment/**"
    ],
    "level_1_minimum": [
      "*.config.*",
      "docker-compose.*",
      ".env*"
    ],
    "level_0_allowed": [
      "docs/**",
      "scripts/experimental/**",
      "*.md"
    ]
  },
  "auto_detect": {
    "enabled": true,
    "patterns": {
      "safety_critical": ["**/brake/**", "**/safety/**", "ASIL-*"],
      "new_module": ["src/modules/*/index.ts"],
      "test_only": ["**/*.test.*", "**/*.spec.*"]
    },
    "keywords": {
      "safety_critical": ["ASIL", "safety", "brake", "airbag"],
      "team_feature": ["epic", "story", "cross-team"],
      "prototype": ["poc", "spike", "experiment", "prototype"]
    }
  },
  "escalation": {
    "auto_escalate_on_failure": true,
    "max_retry_before_escalate": 2
  }
}
```

이 설정 파일은 Claude Code의 hook 시스템에서 읽어와 SubTask 프롬프트에
자동으로 게이트 레벨 컨텍스트를 주입하는 데 사용한다.

---

### 12.6 반정량적 비교: 비용 vs 신뢰성

#### 비용-신뢰성 비교표

| 레벨 | 초기 구현 비용 | 유지보수 비용/월 | 런타임 오버헤드 | 버그 탈출률 감소 | ROI 시점 |
|:----:|:------------:|:--------------:|:-------------:|:--------------:|:--------:|
| Level 0 | 0시간 | 0시간 | 0ms | 0% (기준선) | 즉시 |
| Level 1 | 2-4시간 | ~1시간 | ~50ms/커밋 | ~20% | ~2주 |
| Level 2 | 8-16시간 (1-2일) | 2-4시간 | ~200ms/단계전이 | ~50% | ~1개월 |
| Level 3 | 40-80시간 (1-2주) | ~8시간 (1일) | ~500ms/노드 | ~75% | ~3개월 |
| Level 4 | 수백 시간 (수개월) | 수십 시간 (수일) | ~2s/게이트 | ~95% | 12개월+ |

**주의:** 위 수치는 경험적 추정치이며, 프로젝트 규모/팀 역량/도메인에 따라 크게 달라질 수 있다.

#### ROI 곡선 분석

```
버그 탈출률 감소 (%)
100│                                          ● Level 4 (95%)
   │
 75│                          ● Level 3 (75%)
   │
 50│              ● Level 2 (50%)
   │
 25│  ● Level 1 (20%)
   │
  0│● Level 0
   └──────────────────────────────────────── 구현 비용 (시간)
    0    4     16      80        수백

핵심 관찰: Level 1→2 전이의 비용 대비 효과가 가장 크다.
          Level 3→4 전이는 비용이 급증하지만 한계 효과는 20%p에 그친다.
```

#### 레벨별 경제적 타당성 분석

**Level 1이 합리적인 경우:**
- 에이전트가 주 5회 이상 커밋을 생성하는 프로젝트
- 기존 lint/test 인프라가 이미 존재
- 2주 내 ROI → 거의 모든 프로젝트에서 즉시 도입 가능

**Level 2가 합리적인 경우:**
- 월 10건 이상 기능 개발 태스크가 에이전트에 할당되는 경우
- 스펙-TC-코드 추적성이 팀 규정 또는 프로세스에 요구되는 경우
- 1개월 내 ROI → 에이전트를 일상적으로 사용하는 팀

**Level 3가 합리적인 경우:**
- 에이전트가 크로스 모듈 변경을 수행하는 팀 프로젝트
- 에이전트 생성 코드의 프로덕션 버그가 월 1건 이상 발생
- 3개월 내 ROI → 에이전트 의존도가 높은 조직

**Level 4가 합리적인 경우:**
- 법적/규제 요구사항이 존재 (ISO 26262, IEC 62304 등)
- 버그의 비용이 인명 피해 또는 대규모 재정 손실에 해당
- 12개월+ ROI → 선택이 아닌 필수

---

### 12.7 "둘 다 챙긴 시스템" 아키텍처

신뢰성과 효율성을 동시에 확보하는 핵심 전략은 **적응형 게이트 시스템(Adaptive Gate System)**이다.
모든 태스크에 동일한 레벨을 적용하는 대신,
태스크의 특성에 따라 게이트 레벨을 동적으로 조정한다.

#### 아키텍처 개요

```
태스크 입력 (사용자 프롬프트 또는 이슈)
    │
    ▼
┌─────────────────────────────────┐
│ 1. .agent-profile.json 읽기     │
│    (프로젝트별 게이트 정책)       │
└─────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│ 2. 태스크 유형 자동 감지          │
│    ├─ 파일 패턴 매칭              │
│    ├─ 태스크 설명 키워드 분석      │
│    └─ 이전 태스크 이력 참조       │
└─────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│ 3. 게이트 레벨 결정              │
│    ├─ auto_detect 결과           │
│    ├─ file_overrides 적용        │
│    └─ 최종 레벨 = max(모든 판단)  │
└─────────────────────────────────┘
    │
    ├── Level 0 → [one-loop agent 직접 실행]
    │               hook 없음, 최대 속도
    │
    ├── Level 1 → [agent + commit hooks]
    │               PostToolUse: git commit 감지 → lint + test
    │
    ├── Level 2 → [agent + dev-phase-state + 5-7개 hooks]
    │               단계별 도구 제한 + 컨텍스트 주입 + 전이 검증
    │
    ├── Level 3 → [state machine + 15-20개 gates]
    │               LangGraph 오케스트레이션 + 병렬 에이전트 + HITL
    │
    └── Level 4 → [full ASIL pipeline + human gates]
                    모든 결정에 인간 승인 + 감사 로그 + 외부 리뷰
```

#### 4가지 핵심 메커니즘

**1. 적응형 게이트 시스템 (Adaptive Gating)**

Level 0에서 시작하되, 태스크 분석 결과에 따라 필요한 게이트만 활성화한다.

```python
# Pseudocode: Adaptive gate activation
def determine_gate_level(task, profile):
    level = profile.default_level

    # Keyword-based detection
    for keyword_level, keywords in profile.auto_detect.keywords.items():
        if any(kw in task.description.lower() for kw in keywords):
            level = max(level, LEVEL_MAP[keyword_level])

    # File-based override
    for file in task.affected_files:
        for pattern_list, min_level in profile.file_overrides.items():
            if matches_any(file, pattern_list):
                level = max(level, min_level)

    return level
```

**2. 점진적 강화 (Progressive Hardening)**

에이전트 실행 중에도 게이트 레벨을 상향 조정할 수 있다.
예를 들어, Level 1로 시작한 버그 수정이 예상보다 많은 파일을 수정하기 시작하면
자동으로 Level 2로 전환한다.

```
실행 중 모니터링:
  IF 수정 파일 수 > threshold  → 레벨 상향
  IF core 디렉토리 접근 감지   → 레벨 상향
  IF 테스트 실패 2회 연속      → 레벨 상향 + HITL 게이트 활성화
```

**3. 컨텍스트 인식 게이트 (Context-Aware Gates)**

게이트가 활성화/비활성화되는 조건을 파일 컨텍스트에 연결한다.
동일한 태스크 내에서도 수정 대상 파일에 따라 게이트 강도가 달라진다.

```
예: "사용자 프로필 페이지 리디자인" 태스크
  - src/components/Profile.tsx 수정 → Level 1 (UI 컴포넌트)
  - src/api/user.ts 수정 → Level 2 (API 레이어)
  - src/core/auth.ts 수정 → Level 3 (인증 핵심 로직)
```

**4. 이스케이프 해치 (Escape Hatch)**

인간 개발자가 예외적 상황에서 게이트 레벨을 수동으로 오버라이드할 수 있다.
이때 오버라이드 사유를 기록하여 추후 감사(audit)에 활용한다.

```bash
# Emergency override: temporarily lower gate level
claude --gate-level 0 --override-reason "hotfix: production down, need immediate deploy"

# Override is logged for audit
# [2026-03-04T14:30:00Z] GATE_OVERRIDE: Level 2 → 0, reason: "hotfix: production down"
```

---

### 12.8 회사 내부 정착 로드맵

게이트 시스템의 조직 도입은 기술적 구현만큼이나 **문화적 변화 관리**가 중요하다.
다음은 6개월 이상에 걸친 점진적 도입 전략이다.

#### 1단계: 기반 구축 (1-2개월)

| 항목 | 내용 |
|------|------|
| **목표** | Level 0 → Level 1 마이그레이션, 기본 인프라 구축 |
| **활동** | 팀 전체에 기본 hook 시스템 도입 |
| | pre-commit hook으로 lint + test 자동 실행 |
| | dev-phase-state.json 개념 교육 (아직 적용은 안 함) |
| | 성공 메트릭 기준선(baseline) 측정 |
| **산출물** | `.claude/hooks/` 디렉토리 표준 템플릿 |
| | 에이전트 생성 코드의 현재 버그 탈출률 측정 데이터 |
| **리스크** | 개발자 저항 → "자유도 제한" 우려 해소 필요 |
| **대응** | Level 1은 커밋 시점에만 작동하므로 개발 중 자유도는 보존됨을 강조 |

#### 2단계: Level 2 확산 (3-4개월)

| 항목 | 내용 |
|------|------|
| **목표** | 신규 기능 개발에 Level 2 의무화, 기존 프로젝트에 점진적 적용 |
| **활동** | 파일럿 프로젝트 2-3개에 Level 2 적용 |
| | dev-phase-state.json + hook 5-7개 실전 투입 |
| | 팀별 커스터마이징 가이드 작성 |
| | 격주 레트로스펙티브에서 게이트 효과 측정 및 피드백 반영 |
| **산출물** | .agent-profile.json 팀 표준안 |
| | "게이트가 잡아낸 버그" 사례 모음 |
| | 게이트 도입 전후 버그 탈출률 비교 데이터 |
| **리스크** | 게이트가 bottleneck이 되어 개발 속도 저하 |
| **대응** | 게이트 실행 시간 모니터링, 30초 초과 시 최적화 |

#### 3단계: Level 3 선택적 적용 (5-6개월)

| 항목 | 내용 |
|------|------|
| **목표** | 중요 시스템에 Stripe Minions 패턴 적용 |
| **활동** | 에이전트 오케스트레이션 (ralph/ralplan 패턴) 정착 |
| | 상태머신 기반 워크플로우 2-3개 구축 |
| | 팀별 gate-profile.json 표준화 |
| | 크로스팀 프로젝트에 Level 3 파일럿 |
| **산출물** | LangGraph 기반 워크플로우 템플릿 |
| | 에이전트 오케스트레이션 운영 가이드 |
| **리스크** | 상태머신 복잡도 폭발, 유지보수 비용 증가 |
| **대응** | 노드 수를 7개 이하로 제한, 단순한 상태머신부터 시작 |

#### 4단계: Level 4 필요 영역 확인 (6개월+)

| 항목 | 내용 |
|------|------|
| **목표** | 안전 관련 코드 식별 및 Level 4 적용 |
| **활동** | 기능 안전 요구사항이 있는 코드 영역 식별 |
| | 외부 안전 전문가 컨설팅 |
| | 전사 메트릭 대시보드 구축 |
| | 외부 감사(audit) 준비 |
| **산출물** | ASIL 등급별 코드 영역 맵 |
| | 감사 대응 문서 패키지 |
| **리스크** | Level 4 비용이 에이전트 사용 이점을 초과 |
| **대응** | Level 4 적용 범위를 최소한으로 한정, 나머지는 Level 3 유지 |

#### 전사 성공 메트릭

| 메트릭 | 측정 방법 | 목표 |
|--------|----------|------|
| **에이전트 생성 버그의 프로덕션 탈출률** | 프로덕션 버그 중 에이전트 생성 코드 기인 비율 | 1단계 대비 50% 감소 |
| **스펙-TC-코드 추적성 커버리지** | Level 2+ 태스크 중 추적성이 확보된 비율 | 80% 이상 |
| **개발 사이클 시간** | 태스크 시작 → 머지까지 소요 시간 | 게이트 도입 전 대비 +10% 이내 |
| **개발자 만족도** | 분기별 설문 (자율성 vs 신뢰성 균형) | 4.0/5.0 이상 |
| **게이트 실행 시간 비율** | 전체 태스크 시간 중 게이트 실행 비율 | 15% 이하 |

```
정착 타임라인 시각화:

Month:  1    2    3    4    5    6    7    8+
        ├────┤    ├────┤    ├────┤    ├────→
        │ 1단계  │ 2단계  │ 3단계  │ 4단계
        │ L0→L1 │ L2 확산│ L3 선택│ L4 필요영역
        │       │       │ 적용   │ 확인
        ▼       ▼       ▼       ▼
메트릭: 기준선   20%↓    50%↓    75%↓  (버그 탈출률)
        측정     버그     버그     버그
```

---

### 12.9 핵심 교훈: 올바른 균형점 찾기

본 섹션의 분석에서 도출된 핵심 교훈 5가지를 정리한다.

**교훈 1: 신뢰성과 효율성은 zero-sum이 아니다.**

동일한 게이트 레벨을 모든 태스크에 적용하면 zero-sum처럼 보이지만,
태스크 유형별로 적절한 레벨을 배분하면 **전체 시스템 수준에서 양쪽 모두를 최적화**할 수 있다.
프로토타입에는 Level 0, 핵심 로직에는 Level 3을 적용하는 것이
전체에 Level 2를 일괄 적용하는 것보다 신뢰성과 효율성 모두에서 우월하다.

**교훈 2: 과도한 게이트는 에이전트의 가치를 소멸시킨다.**

에이전트를 도입하는 이유는 개발 속도 향상과 창의적 문제 해결이다.
모든 결정에 인간 승인을 요구하는 Level 4를 일반 개발에 적용하면,
에이전트 없이 직접 개발하는 것보다 오히려 느려진다.
게이트는 "에이전트의 가치를 보존하면서 위험을 관리하는" 도구여야 한다.

**교훈 3: 게이트의 목적은 "에이전트 통제"가 아니라 "안전한 환경 제공"이다.**

게이트를 "에이전트가 실수하지 못하게 막는 장치"로 인식하면 과도한 제어로 이어진다.
올바른 관점은 "에이전트가 실수해도 시스템이 안전한 상태를 유지하는 환경"이다.
이 관점 전환은 게이트 설계 철학에 근본적 차이를 만든다:

```
통제 관점:  에이전트 → [게이트: 차단] → 실행 불가
안전 관점:  에이전트 → [실행] → [게이트: 검증] → 통과/롤백
```

안전 관점에서는 에이전트가 먼저 행동하고, 게이트가 사후 검증한다.
이 방식이 에이전트의 자율성(E4)을 보존하면서도 신뢰성을 확보하는 핵심 패턴이다.

**교훈 4: Claude Code + OMC 조합은 Level 0-3을 모두 커버하는 최실용적 솔루션이다.**

- **Level 0**: Claude Code 기본 실행
- **Level 1**: Claude Code + pre-commit hook (PostToolUse)
- **Level 2**: Claude Code + OMC hooks (dev-phase-state-machine)
- **Level 3**: Claude Code + OMC + LangGraph 오케스트레이션

이 스택은 단일 도구 체인으로 4개 레벨을 점진적으로 도입할 수 있다는 점에서,
처음부터 별도 시스템을 구축하는 것보다 현실적이다.

**교훈 5: Level 4는 기능 안전 전문가와 함께 설계해야 한다.**

Level 4는 소프트웨어 엔지니어링 영역을 넘어 기능 안전(functional safety) 영역이다.
ISO 26262, IEC 62304 등의 표준을 충족하려면 해당 도메인의 전문 지식이 필수적이며,
에이전트 시스템 설계자가 단독으로 구현할 수 있는 범위를 초과한다.

---

**요약: 본 섹션에서 제시한 5레벨 스펙트럼과 태스크 유형별 배분 전략은,
SPEC이 제기한 "신뢰성-효율성 긴장"에 대한 실용적 해법이다.
모든 것을 결정론적으로 만들 필요도, 모든 것을 에이전트에 맡길 필요도 없다.
올바른 레벨을, 올바른 태스크에, 올바른 시점에 적용하는 것이 핵심이다.**


## 부록: 참고 자료

| 자료 | 출처 | 날짜 |
|------|------|------|
| Stripe Minions 블로그 (Part 1, 2) | stripe.dev/blog | 2026년 2월 |
| Pi SDK 공식 문서 (extensions.md) | github.com/badlogic/pi-mono | 2026년 3월 |
| Pi SDK v0.55.4 릴리스 노트 | github.com/badlogic/pi-mono/releases | 2026년 3월 2일 |
| Claude Code Hook 공식 문서 | docs.anthropic.com/claude-code/hooks | 2025-2026 |
| OpenAI Agents SDK 공식 문서 | openai.github.io/openai-agents-python | 2025-2026 |
| OpenAI Agents SDK Issue #1612 (on_llm_start 버그) | github.com/openai/openai-agents-python | 2025년 12월 |
| OpenAI Agents SDK Issue #2016 (on_run_start 종료) | github.com/openai/openai-agents-python | 2025년 12월 |
| OpenAI Agents SDK Issue #1889 (호스팅 도구 훅 미작동) | github.com/openai/openai-agents-python | 2025년 |
| LangGraph v1.0 릴리스 | langchain.com/langgraph | 2025년 10월 |
| ISO 26262:2018 | ISO 공식 표준 | 2018 |
| ISO/PAS 8800 | ISO 공식 표준 | 2024 |

### 이전 보고서와의 관계

| 보고서 | Pi 관련 평가 | 본 보고서와의 관계 |
|--------|-------------|-------------------|
| `coding-agent-comparison-iso26262.md` | Pi 비권장 (즉시 사용 불가 기준) | 평가 기준 정정 — 커스터마이징 전제 시 번복 |
| `pi_sdk_evaluation_report.md` | 최하위 11/30 (Python 스택 전제) | 전제 오류 — TypeScript + 커스터마이징 전제 시 번복 |
| `pi_sdk_vs_openai_agents_sdk_comparison.md` | TypeScript 전제 시 Pi 1순위 | 본 보고서와 일치, 결정론적 주입 관점 추가 |
| `agent_framework_final_report_2026.md` | TypeScript 스택 Pi PoC 권장 | 본 보고서와 일치, 상태머신 관점 확장 |

---

*본 보고서는 2026년 3월 3일 기준으로 작성되었습니다. AI 에이전트 프레임워크는 빠르게 진화하고 있으므로 실제 적용 전 최신 API 문서를 확인하십시오.*

*중요: 본 보고서는 이전 보고서 `coding-agent-comparison-iso26262.md`의 Pi SDK 비권장 평가를 공식 정정합니다. 평가 기준(즉시 사용 가능 도구 vs 커스터마이징 기반 최적 플랫폼)의 차이로 인한 결론의 역전이며, 두 평가 모두 각자의 기준 내에서는 논리적으로 일관성이 있습니다.*
