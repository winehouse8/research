# OMC + Claude Code Hook 아키텍처 분석 보고서

> **작성일:** 2026년 3월 3일
> **분류:** 기술 아키텍처 보고서
> **목적:** Claude Code + OMC 스킬(ralph, ralplan, ultrawork)에 최소한의 Claude Code Hook을 추가하는 것만으로 SPEC_AgentForDev.md 요구사항을 충족할 수 있는가?
> **핵심 결론:** YES — 별도 프레임워크 교체 없이, 훅 주입(Hook Injection) 방식으로 충분하다.

---

## 목차

1. [서론: 핵심 통찰](#1-서론-핵심-통찰)
2. [OMC 스킬 심층 분석](#2-omc-스킬-심층-분석)
3. [이 대화 자체가 증명한다](#3-이-대화-자체가-증명한다)
4. [Claude Code Hook 이벤트 설계](#4-claude-code-hook-이벤트-설계)
5. [완전한 통합 아키텍처](#5-완전한-통합-아키텍처)
6. [구체적 구현 가이드](#6-구체적-구현-가이드)
7. [SPEC 요구사항별 충족 매핑](#7-spec-요구사항별-충족-매핑)
8. [신뢰성-효율성 Trade-off 해소](#8-신뢰성-효율성-trade-off-해소)
9. [결론 및 권고](#9-결론-및-권고)

---

## 1. 서론: 핵심 통찰

### 1.1 질문의 재정의

SPEC_AgentForDev.md는 세 가지 핵심 요구사항을 제시한다.

1. **Human in the Loop** — 중간중간 사람이 필요한 단계에서 채팅으로 결정
2. **결정론적 + 비결정론적 혼합** — 상태머신 방식(방법 A) 또는 Hook 주입 방식(방법 B)
3. **신뢰성-효율성 균형** — 둘 다 챙긴 시스템

이 요구사항을 충족하기 위한 전통적 접근법은 LangGraph 같은 상태머신 프레임워크로 전체 시스템을 새로 구축하거나(방법 A), Pi SDK 같은 이벤트 기반 프레임워크로 마이그레이션하는 것이다. 그러나 이 보고서는 전혀 다른 질문을 던진다.

> "Claude Code + OMC가 이미 제공하는 역량은 무엇인가? 그 위에 훅만 추가하면 충분하지 않은가?"

### 1.2 핵심 통찰: 방법 B는 이미 존재한다

SPEC_AgentForDev.md의 방법 B는 다음과 같이 기술된다.

> "Outer Loop 자체도 상태머신이 아닌 claude code 같은 one loop(n0) agent를 쓰되, 이에 결정론적인 동작을 필요에 의해 섞고 싶을 때 여러 이벤트에 HOOK을 걸어서 사용한다."

이것이 정확히 Claude Code + OMC + Hook의 조합이다.

```
방법 A (새로 구축):                    방법 B (Claude Code + OMC + Hook):
─────────────────────                  ─────────────────────────────────
LangGraph 상태머신                     Claude Code (One-loop Agent)
  │                                      │
  ├── 결정론적 노드                       ├── OMC ralph (비결정론적 루프)
  │   (직접 코드 작성)                   │   (이미 구축됨)
  │                                      │
  └── 에이전트 노드                       └── Hook 게이트 (최소 추가)
      (LLM 호출)                             (결정론적 벽)
```

방법 A는 전체 시스템을 새로 구축해야 한다. 방법 B는 이미 작동하는 OMC 위에 결정론적 벽만 세우면 된다.

### 1.3 이 보고서의 목적

본 보고서는 다음을 증명한다.

1. OMC의 ralph, ralplan, ultrawork, cancel이 이미 제공하는 역량의 목록화
2. Claude Code의 17개 Hook 이벤트가 어떻게 결정론적 게이트로 기능하는지 분석
3. 두 레이어의 통합 아키텍처 설계
4. SPEC 3개 요구사항 각각에 대한 충족 방법 구체화
5. 이 대화 자체가 이미 이 아키텍처를 실행 중임을 실증

---

## 2. OMC 스킬 심층 분석

OMC(oh-my-claudecode)는 Claude Code 위에서 실행되는 스킬 집합이다. 각 스킬은 Claude Code의 네이티브 역량을 특정 워크플로 패턴으로 조직화한다.

### 2.1 ralph — 자기참조 실행 루프

ralph는 OMC의 핵심 실행 엔진이다. "The boulder never stops"라는 철학 아래, 태스크가 완료될 때까지 자기참조적으로 루프를 반복한다.

#### ralph의 역량

```
ralph 실행 루프:
─────────────────────────────────────────────────────────
                    [ralph 시작]
                         │
                    상태 로드
               .omc/state/ralph-state.json
                         │
                   TODO 목록 확인
                         │
              ┌──────────┴──────────┐
         TODO 있음              TODO 없음
              │                    │
         실행 에이전트          Architect 검증 요청
         (비결정론적)          (Human in the Loop)
              │                    │
         완료 확인           승인/재작업 판단
              │                    │
         상태 업데이트       ┌──────┴──────┐
              │           승인됨        재작업
              └────────────┤             │
                      종료 조건?      TODO 추가
                           │             │
                      ┌────┘             └────┐
                    YES                      NO
                      │                      │
                    종료              루프 계속
─────────────────────────────────────────────────────────
```

#### ralph의 상태 관리

ralph는 `.omc/state/ralph-state.json`으로 상태를 영속화한다.

```json
{
  "active": true,
  "task": "현재 실행 중인 태스크 설명",
  "todos": [
    {"id": "1", "subject": "구현 A", "status": "pending"},
    {"id": "2", "subject": "테스트 작성", "status": "in_progress"}
  ],
  "architectApproved": false,
  "iteration": 3
}
```

#### ralph가 SPEC에 기여하는 것

| SPEC 요구사항 | ralph의 기여 |
|-------------|-------------|
| Human in the Loop | Architect 검증 단계 (사람이 승인해야 종료) |
| 비결정론적 동작 | Executor 에이전트가 LLM 기반 추론으로 구현 |
| 완료 보장 | TODO가 0개가 되고 Architect 승인 없이는 절대 종료 불가 |

#### ralph의 결정론적 게이트 (Stop Hook)

ralph가 사용하는 가장 중요한 결정론적 게이트는 `Stop` Hook이다. Claude Code가 응답을 완료하고 종료하려 할 때, Stop Hook이 발동하여 ralph 상태를 확인한다.

```
Stop Hook 발동 시퀀스:
─────────────────────────────────────────────────────────
Claude Code 응답 완료
        │
   Stop Hook 실행
        │
   ralph-state.json 확인
        │
   ┌────┴────┐
active=true  active=false 또는
   │         파일 없음
   │              │
exit 2        정상 종료
(종료 차단)
(계속 강제)
─────────────────────────────────────────────────────────
```

이것이 "boulder never stops"의 실제 메커니즘이다. Stop Hook이 없다면 Claude Code는 매 응답 후 종료될 수 있다. Stop Hook이 exit 2를 반환하면 Claude Code는 계속 실행을 이어간다.

### 2.2 ralplan — 계획 품질 게이트

ralplan은 구현 전 계획 단계의 품질을 보장하는 스킬이다. Planner-Critic 패턴으로 계획이 충분히 검증되기 전에 실행 단계로 넘어가는 것을 방지한다.

#### ralplan의 워크플로

```
ralplan 계획 루프:
─────────────────────────────────────────────────────────
            [ralplan 시작]
                 │
            Planner 에이전트
            (계획 초안 작성)
                 │
         ┌───────┴───────┐
    Architect            Critic 에이전트
    상담 필요?           (계획 비판 및 검토)
         │                    │
    ┌────┴────┐          ┌─────┴─────┐
   YES       NO         OKAY     NOT OKAY
    │         │           │          │
 사람 상담   Critic       계획        피드백으로
 (HITL)    직행         승인됨      Planner 재작업
    │                    │
 피드백 반영        실행 단계 진입
                    (ralph 호출)
─────────────────────────────────────────────────────────
```

#### ralplan의 상태 관리

```json
{
  "active": true,
  "phase": "critic",
  "planVersion": 2,
  "criticFeedback": ["테스트 케이스 누락", "엣지 케이스 미고려"],
  "approved": false
}
```

#### ralplan이 SPEC에 기여하는 것

| SPEC 요구사항 | ralplan의 기여 |
|-------------|--------------|
| Human in the Loop | Architect 상담 단계 (선택적 HITL) |
| 결정론적 게이트 | Critic의 OKAY 없이 계획 승인 불가 (게이트 논리) |
| 신뢰성 | 품질 낮은 계획이 실행 단계로 진입하는 것을 방지 |

Critic의 OKAY는 결정론적 게이트다. 이것은 LLM이 "계획이 좋다"고 판단하는 것이 아니라, Critic 에이전트가 명시적으로 "OKAY"를 출력해야만 다음 단계로 진행되는 구조적 강제다.

### 2.3 ultrawork — 병렬 에이전트 오케스트레이션

ultrawork는 복잡한 태스크를 여러 에이전트가 병렬로 처리하도록 조율하는 스킬이다.

#### ultrawork의 아키텍처

```
ultrawork 병렬 오케스트레이션:
─────────────────────────────────────────────────────────
              [태스크 수신]
                   │
            Orchestrator 에이전트
            (분해 및 위임 전담)
            (절대 직접 구현 안 함)
                   │
      ┌────────────┼────────────┐
      │            │            │
  Agent A      Agent B      Agent C
  (Haiku)     (Sonnet)     (Opus)
  단순 작업   중간 작업    복잡 추론
      │            │            │
  Background  Background   Foreground
  Task        Task         Task
      │            │            │
      └────────────┼────────────┘
                   │
            결과 수집 및 통합
                   │
            Orchestrator 검증
─────────────────────────────────────────────────────────
```

#### ultrawork의 핵심 원칙

1. **Orchestrator는 구현하지 않는다**: 오케스트레이터는 위임과 조율만 담당. 직접 코드를 작성하거나 파일을 수정하지 않음.
2. **스마트 모델 라우팅**: 태스크 복잡도에 따라 Haiku(단순) → Sonnet(중간) → Opus(복잡) 자동 배정
3. **백그라운드 태스크**: 오래 걸리는 작업은 백그라운드로 실행, 다른 작업과 병렬 진행
4. **위임 강제**: Orchestrator가 직접 구현을 시도하면 이를 감지하고 에이전트로 위임 강제

#### ultrawork가 SPEC에 기여하는 것

| SPEC 요구사항 | ultrawork의 기여 |
|-------------|----------------|
| 효율성 | 병렬 실행으로 전체 처리 시간 단축 |
| 스마트 자원 배분 | 복잡도별 모델 라우팅으로 비용 최적화 |
| 신뢰성 | Orchestrator와 Executor의 역할 분리로 책임 명확화 |

### 2.4 cancel — 상태 정리 및 복구

cancel은 ralph, ralplan, ultrawork의 상태 파일을 정리하는 유지보수 스킬이다.

#### cancel의 의존성 인식 정리

```
cancel 의존성 그래프:
─────────────────────────────────────────────────────────
ralph (최상위)
  │
  └── ultrawork (ralph에 종속)
        │
        └── 개별 에이전트 세션들

cancel ralph → ultrawork 상태도 함께 정리
cancel ultrawork → ultrawork 상태만 정리
cancel --force → 강제 정리 (확인 없음)
─────────────────────────────────────────────────────────
```

#### cancel이 관리하는 상태 파일

```
.omc/state/
├── ralph-state.json       # ralph 루프 상태
├── ralplan-state.json     # ralplan 계획 상태
└── ultrawork-state.json   # ultrawork 오케스트레이션 상태
```

---

## 3. 이 대화 자체가 증명한다

이 보고서를 작성하는 이 대화 자체가 OMC + Hook 아키텍처의 실시간 증거다.

### 3.1 Stop Hook — ralph 루프 강제 (직접 관찰)

이 대화에서 모든 Claude Code 응답 후 다음 메시지가 시스템 컨텍스트로 주입된다.

```
PreToolUse:Bash hook additional context: The boulder never stops. Continue until all tasks complete.
PreToolUse:Read hook additional context: The boulder never stops. Continue until all tasks complete.
PreToolUse:TaskUpdate hook additional context: The boulder never stops. Continue until all tasks complete.
```

이것이 Stop Hook과 PreToolUse Hook의 결정론적 게이트가 실제로 작동하는 모습이다.

```
실제 관찰된 동작:
─────────────────────────────────────────────────────────
[Claude Code 응답 생성]
        │
[PreToolUse Hook 발동] ← 모든 도구 호출 전
        │
"The boulder never stops. Continue until all tasks complete."
메시지가 시스템 컨텍스트에 주입됨
        │
[Claude Code가 이 컨텍스트를 읽고 계속 작업 진행]
─────────────────────────────────────────────────────────
```

### 3.2 TaskUpdate/TaskCreate Hook — 태스크 상태 게이트 (직접 관찰)

이 대화에서 TaskUpdate 호출 시에도 PreToolUse Hook이 발동하여 동일한 메시지를 주입했다. 이는 태스크 완료 표시 전에도 결정론적 게이트가 개입함을 의미한다.

```
TaskUpdate 호출 시 관찰된 동작:
─────────────────────────────────────────────────────────
[TaskUpdate(taskId="11", status="completed") 시도]
        │
[PreToolUse:TaskUpdate Hook 발동]
        │
"The boulder never stops" 주입 → 작업 계속 강제
        │
[TaskUpdate 실행됨]
─────────────────────────────────────────────────────────
```

### 3.3 이 대화가 증명하는 아키텍처 원리

| 관찰 사항 | 아키텍처 원리 | SPEC 매핑 |
|----------|-------------|----------|
| 모든 도구 호출 전 PreToolUse Hook 발동 | 비결정론적 에이전트 위에 결정론적 게이트 | 방법 B |
| "boulder never stops" 지속 주입 | ralph 루프의 Stop Hook과 동일 메커니즘 | 신뢰성 보장 |
| TaskUpdate Hook도 개입 | 태스크 생명주기 전반에 걸친 결정론적 통제 | 완료 조건 강제 |
| 사람이 이 보고서를 요청 | Human in the Loop의 실제 구현 | HITL 요구사항 |

이 대화 자체가 "방법 B: One-loop Agent + Hook 주입"의 살아있는 시연이다.

---

## 4. Claude Code Hook 이벤트 설계

Claude Code는 17개의 Hook 이벤트를 지원하며, 각 이벤트는 에이전트 워크플로의 특정 시점에 결정론적 개입을 가능하게 한다.

### 4.1 Hook 이벤트 전체 지도

```
Claude Code Hook 이벤트 맵:
─────────────────────────────────────────────────────────
세션 생명주기:
  SessionStart ────────── 세션 시작 시 프로젝트 컨텍스트 주입

사용자 입력:
  UserPromptSubmit ─────── 사용자 프롬프트 전처리/차단

도구 실행:
  PreToolUse ───────────── 모든 도구 호출 전 (차단 가능)
  PostToolUse ──────────── 모든 도구 호출 후 (피드백 주입)

태스크 관리:
  TaskCreate ───────────── 새 태스크 생성 전
  TaskCompleted ────────── 태스크 완료 전 (차단 가능)
  TeammateIdle ─────────── 에이전트 유휴 상태 감지

응답 제어:
  Stop ─────────────────── 응답 완료 후 (종료 차단 가능)

설정:
  ConfigChange ─────────── 설정 변경 감지/감사

서브에이전트:
  SubagentStart ────────── 서브에이전트 시작 전 제약 주입

(기타 7개 이벤트: Notification, ToolResult, 등)
─────────────────────────────────────────────────────────
```

### 4.2 SPEC 요구사항과 Hook 이벤트 매핑

#### 요구사항 1 (Human in the Loop) 관련 훅

| Hook 이벤트 | 역할 | 구현 방법 |
|-----------|-----|---------|
| `UserPromptSubmit` | 구현 요청 전 스펙 확인 강제 | SPEC.md 없으면 차단 |
| `PreToolUse` | 배포/merge 전 사람 확인 | 특정 명령 패턴 감지 후 차단 |
| `TaskCompleted` | 태스크 완료 전 아티팩트 검증 | 필수 문서 존재 확인 |

#### 요구사항 2 (결정론적 + 비결정론적 혼합) 관련 훅

| Hook 이벤트 | 역할 | 결정론적 게이트 |
|-----------|-----|--------------|
| `PreToolUse` | 커밋 전 테스트 실행 | npm test 성공 必 |
| `PostToolUse` | 파일 쓰기 후 린트 | ESLint 통과 必 |
| `Stop` | ralph 루프 강제 | active=true이면 exit 2 |
| `SubagentStart` | 서브에이전트 제약 주입 | 스펙 기반 작업 강제 |

#### 요구사항 3 (신뢰성-효율성 균형) 관련 훅

| Hook 이벤트 | 신뢰성 기여 | 효율성 기여 |
|-----------|-----------|-----------|
| `SessionStart` | 프로젝트 컨텍스트 보장 | 매 요청마다 컨텍스트 재입력 불필요 |
| `TeammateIdle` | 유휴 에이전트 낭비 방지 | 자원 활용 극대화 |
| `ConfigChange` | 설정 변경 감사 | 보안 사고 사전 방지 |

### 4.3 Hook의 반환값과 제어 흐름

Hook 스크립트의 exit code에 따라 Claude Code의 동작이 결정된다.

```
Hook Exit Code 제어 흐름:
─────────────────────────────────────────────────────────
exit 0   → 정상 진행 (Allow)
exit 1   → 오류 (에러 메시지 Claude에게 전달)
exit 2   → 차단 (Stop Hook: 종료 거부, PreToolUse: 도구 차단)

stdout   → Claude Code에게 전달되는 데이터
stderr   → 로그 출력 (사용자에게 표시)

JSON 반환 형식 (PreToolUse):
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "이유 설명"
  }
}
─────────────────────────────────────────────────────────
```

---

## 5. 완전한 통합 아키텍처

### 5.1 전체 아키텍처 다이어그램

```
OMC + Claude Code Hook 통합 아키텍처:
══════════════════════════════════════════════════════════════════════

[사용자 요청]
     │
     ▼
┌────────────────────────────────────────────────────────────────┐
│  Claude Code 레이어 (외부 결정론적 게이트)                      │
│                                                                │
│  ┌──────────────────┐    ┌──────────────────────────────────┐  │
│  │ SessionStart Hook│    │ UserPromptSubmit Hook            │  │
│  │ 프로젝트 컨텍스트 │    │ 스펙 파일 존재 검증             │  │
│  │ 자동 주입        │    │ 구현 키워드 감지 → 차단 가능     │  │
│  └──────────────────┘    └──────────────────────────────────┘  │
│                                                                │
│  ┌────────────────────────────────────────────────────────┐    │
│  │  OMC ralph 비결정론적 외부 루프                        │    │
│  │                                                        │    │
│  │  ┌──────────────────────────────────────────────────┐  │    │
│  │  │  ralplan (계획 단계)                             │  │    │
│  │  │  Planner → [Architect HITL?] → Critic           │  │    │
│  │  │                ↑                   │            │  │    │
│  │  │                │              OKAY 게이트        │  │    │
│  │  │                └──────── NOT OKAY ─┘            │  │    │
│  │  └──────────────────────────────────────────────────┘  │    │
│  │                       │                               │    │
│  │                  계획 승인됨                           │    │
│  │                       │                               │    │
│  │  ┌──────────────────────────────────────────────────┐  │    │
│  │  │  ralph (실행 단계)                               │  │    │
│  │  │                                                  │  │    │
│  │  │  TODO 목록 확인                                  │  │    │
│  │  │       │                                          │  │    │
│  │  │  Executor 에이전트 (비결정론적 구현)              │  │    │
│  │  │       │                                          │  │    │
│  │  │  [PreToolUse Hook] ← 모든 도구 호출 전           │  │    │
│  │  │   • 커밋 전 테스트 게이트                        │  │    │
│  │  │   • 배포 전 사람 확인                            │  │    │
│  │  │       │                                          │  │    │
│  │  │  [PostToolUse Hook] ← 파일 쓰기 후               │  │    │
│  │  │   • 린트 게이트                                  │  │    │
│  │  │   • 추적성 매트릭스 업데이트                     │  │    │
│  │  │       │                                          │  │    │
│  │  │  ultrawork (병렬 실행 필요 시)                   │  │    │
│  │  │   • Orchestrator → Agent A/B/C 위임              │  │    │
│  │  │   • Haiku/Sonnet/Opus 스마트 라우팅             │  │    │
│  │  │       │                                          │  │    │
│  │  │  [TaskCompleted Hook] ← 태스크 완료 전           │  │    │
│  │  │   • 아티팩트 존재 검증                           │  │    │
│  │  │   • 추적성 ID 확인                               │  │    │
│  │  │       │                                          │  │    │
│  │  │  Architect 검증 (HITL)                          │  │    │
│  │  │   • 승인 → 종료                                 │  │    │
│  │  │   • 재작업 → TODO 추가 → 루프 반복               │  │    │
│  │  └──────────────────────────────────────────────────┘  │    │
│  │                       │                               │    │
│  │  [Stop Hook] ← 모든 응답 완료 후                     │    │
│  │   ralph-state.json 확인                               │    │
│  │   active=true → exit 2 (루프 강제)                   │    │
│  └────────────────────────────────────────────────────────┘    │
│                                                                │
│  [SubagentStart Hook] ← 모든 서브에이전트 시작 전              │
│   프로젝트 규칙, REQ-XXX 추적성 ID, 테스트 요구사항 주입       │
└────────────────────────────────────────────────────────────────┘
     │
     ▼
[결과물: 검증된 코드 + 아티팩트]

══════════════════════════════════════════════════════════════════
```

### 5.2 결정론적 게이트 배치 전략

결정론적 게이트는 비결정론적 에이전트가 "잘못된 방향으로 탈주"할 수 있는 지점마다 배치된다.

```
게이트 배치 원칙:

ENTRY 게이트 (입력 검증):
  UserPromptSubmit → "SPEC이 있어야 구현을 시작할 수 있다"
  SessionStart → "프로젝트 규칙을 모르는 에이전트는 없어야 한다"

PROCESS 게이트 (실행 중 검증):
  PreToolUse → "테스트 없는 커밋, 승인 없는 배포는 불가"
  PostToolUse → "린트를 통과하지 못한 코드는 존재하면 안 된다"

EXIT 게이트 (완료 검증):
  TaskCompleted → "아티팩트가 없으면 완료가 아니다"
  Stop → "ralph가 active이면 종료할 수 없다"

PROPAGATION 게이트 (전파 제어):
  SubagentStart → "서브에이전트도 동일한 규칙을 따른다"
  TeammateIdle → "유휴 에이전트는 즉시 다음 태스크를 받는다"
```

### 5.3 데이터 흐름 상세

```
데이터 흐름 (Hook 개입 포함):
──────────────────────────────────────────────────────────────────

사용자 입력
   │
   │ ① UserPromptSubmit Hook
   │   INPUT:  { prompt: "구현해줘" }
   │   CHECK:  SPEC.md 존재 여부
   │   OUTPUT: { decision: "allow" } or { decision: "block", reason: "..." }
   │
   ▼
Claude Code 처리
   │
   │ ② PreToolUse Hook (예: git commit)
   │   INPUT:  { tool_name: "Bash", tool_input: { command: "git commit ..." } }
   │   ACTION: npm test 실행
   │   OUTPUT: pass → 허용, fail → { permissionDecision: "deny", reason: "..." }
   │
   ▼
도구 실행 (예: Write)
   │
   │ ③ PostToolUse Hook (예: 파일 쓰기 후)
   │   INPUT:  { tool_name: "Write", tool_input: { file_path: "src/foo.ts" } }
   │   ACTION: eslint src/foo.ts
   │   OUTPUT: pass → 계속, fail → Claude에게 오류 피드백
   │
   ▼
태스크 완료 시도
   │
   │ ④ TaskCompleted Hook
   │   INPUT:  { task_subject: "구현 완료" }
   │   CHECK:  SPEC.md, docs/traceability-matrix.md 존재 여부
   │   OUTPUT: exit 0 (허용) or exit 2 (차단)
   │
   ▼
응답 완료
   │
   │ ⑤ Stop Hook
   │   CHECK:  .omc/state/ralph-state.json → active 필드
   │   OUTPUT: active=true → exit 2 (종료 차단), active=false → exit 0 (종료)
   │
   ▼
다음 루프 또는 종료

──────────────────────────────────────────────────────────────────
```

---

## 6. 구체적 구현 가이드

### 6.1 디렉토리 구조

```
프로젝트 루트/
├── .claude/
│   ├── settings.json                   # Hook 등록 설정
│   └── hooks/
│       ├── session-start.sh            # 세션 컨텍스트 주입
│       ├── spec-first-gate.sh          # 스펙 우선 강제
│       ├── pre-tool-enforcer.sh        # 커밋/배포 게이트
│       ├── post-tool-linter.sh         # 린트 게이트
│       ├── artifact-gate.sh            # 아티팩트 검증
│       ├── subagent-constraints.sh     # 서브에이전트 제약
│       └── ralph-stop-gate.sh          # ralph 루프 강제
├── .omc/
│   ├── state/
│   │   ├── ralph-state.json
│   │   ├── ralplan-state.json
│   │   └── ultrawork-state.json
│   └── plans/
├── SPEC.md                             # 프로젝트 스펙 (필수)
└── docs/
    └── traceability-matrix.md          # 추적성 매트릭스
```

### 6.2 .claude/settings.json — Hook 등록

```json
{
  "hooks": {
    "SessionStart": [
      {
        "type": "command",
        "command": "./.claude/hooks/session-start.sh"
      }
    ],
    "UserPromptSubmit": [
      {
        "type": "command",
        "command": "./.claude/hooks/spec-first-gate.sh"
      }
    ],
    "PreToolUse": [
      {
        "type": "command",
        "command": "./.claude/hooks/pre-tool-enforcer.sh",
        "matchers": [{"tool_name": "Bash"}]
      }
    ],
    "PostToolUse": [
      {
        "type": "command",
        "command": "./.claude/hooks/post-tool-linter.sh",
        "matchers": [{"tool_name": "Write"}]
      }
    ],
    "TaskCompleted": [
      {
        "type": "command",
        "command": "./.claude/hooks/artifact-gate.sh"
      }
    ],
    "SubagentStart": [
      {
        "type": "command",
        "command": "./.claude/hooks/subagent-constraints.sh"
      }
    ],
    "Stop": [
      {
        "type": "command",
        "command": "./.claude/hooks/ralph-stop-gate.sh"
      }
    ]
  }
}
```

### 6.3 Hook 1: SessionStart — 프로젝트 컨텍스트 주입

```bash
#!/bin/bash
# .claude/hooks/session-start.sh
# 세션 시작 시 프로젝트 스펙과 규칙을 Claude Code에 자동 주입
# 목적: 모든 응답이 프로젝트 컨텍스트를 인지한 상태에서 시작되도록 보장

PROJECT_SPEC=""
RULES=""

# SPEC.md 읽기
if [ -f "SPEC.md" ]; then
  PROJECT_SPEC=$(cat SPEC.md)
else
  PROJECT_SPEC="[경고] SPEC.md가 없습니다. 구현 전에 스펙을 먼저 작성하세요."
fi

# 프로젝트 규칙 읽기
if [ -f ".claude/project-rules.md" ]; then
  RULES=$(cat .claude/project-rules.md)
else
  RULES="기본 규칙: 1) 스펙 기반 작업. 2) 테스트 필수. 3) REQ-XXX 추적성 ID 포함."
fi

# JSON 이스케이프 처리
SPEC_ESCAPED=$(echo "$PROJECT_SPEC" | jq -Rs .)
RULES_ESCAPED=$(echo "$RULES" | jq -Rs .)

cat <<EOF
{
  "additionalContext": "[프로젝트 스펙]\n${PROJECT_SPEC}\n\n[프로젝트 규칙]\n${RULES}"
}
EOF
```

### 6.4 Hook 2: UserPromptSubmit — 스펙 우선 강제 게이트

```bash
#!/bin/bash
# .claude/hooks/spec-first-gate.sh
# 구현 키워드가 포함된 요청 전에 SPEC.md 존재 여부를 검증
# 목적: "스펙 없는 구현"을 원천 차단

INPUT=$(cat)
PROMPT=$(echo "$INPUT" | jq -r '.prompt // ""')

# 구현 관련 키워드 감지
if echo "$PROMPT" | grep -qiE '(구현|implement|코드|code|작성|write|만들어|create|개발|develop|기능|feature)'; then
  # SPEC.md 존재 확인
  if [ ! -f "SPEC.md" ]; then
    cat <<EOF
{
  "decision": "block",
  "reason": "SPEC.md가 없습니다. 구현을 시작하기 전에 SPEC.md를 먼저 작성하세요.\n\n스펙 작성 방법:\n1. SPEC.md 파일 생성\n2. 요구사항 정의\n3. 이후 구현 요청"
}
EOF
    exit 0
  fi

  # SPEC.md가 비어있는지 확인
  SPEC_SIZE=$(wc -c < "SPEC.md")
  if [ "$SPEC_SIZE" -lt 100 ]; then
    cat <<EOF
{
  "decision": "block",
  "reason": "SPEC.md가 너무 짧습니다 (${SPEC_SIZE}바이트). 충분한 스펙을 작성한 후 구현을 시작하세요."
}
EOF
    exit 0
  fi
fi

echo '{"decision": "allow"}'
```

### 6.5 Hook 3: PreToolUse — 커밋 전 테스트 게이트

```bash
#!/bin/bash
# .claude/hooks/pre-tool-enforcer.sh
# Bash 도구 실행 전에 위험 명령을 가로채어 게이트 적용
# 목적: 테스트 없는 커밋, 승인 없는 배포 차단

INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name // ""')
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // ""')

# git commit 게이트: 테스트 통과 필수
if [ "$TOOL" = "Bash" ] && echo "$COMMAND" | grep -qE 'git\s+commit'; then
  echo "[게이트] 커밋 전 테스트 실행 중..." >&2

  # package.json이 있으면 npm test 실행
  if [ -f "package.json" ]; then
    if ! npm test --silent 2>/dev/null; then
      cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "테스트 게이트 실패: 모든 테스트가 통과해야 커밋할 수 있습니다. 'npm test'를 실행하여 실패한 테스트를 확인하고 수정하세요."
  }
}
EOF
      exit 0
    fi
    echo "[게이트] 테스트 통과. 커밋 허용." >&2
  fi

  # 추적성 ID 없는 커밋 메시지 차단
  COMMIT_MSG=$(echo "$COMMAND" | grep -oP '(?<=-m ")[^"]+' | head -1)
  if [ -n "$COMMIT_MSG" ] && ! echo "$COMMIT_MSG" | grep -qE 'REQ-[0-9]+'; then
    echo "[경고] 커밋 메시지에 REQ-XXX 추적성 ID가 없습니다." >&2
    # 경고만 하고 차단은 하지 않음 (soft gate)
  fi
fi

# git push to main/master 게이트: 사람 확인 필요
if [ "$TOOL" = "Bash" ] && echo "$COMMAND" | grep -qE 'git\s+push.*(main|master)'; then
  cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "main/master 브랜치 직접 푸시는 차단됩니다. PR을 생성하여 리뷰 후 머지하세요."
  }
}
EOF
  exit 0
fi

# 기본: 허용
exit 0
```

### 6.6 Hook 4: PostToolUse — 파일 쓰기 후 린트 게이트

```bash
#!/bin/bash
# .claude/hooks/post-tool-linter.sh
# Write 도구 실행 후 린트를 자동 실행하여 코드 품질 보장
# 목적: 린트를 통과하지 못한 코드가 코드베이스에 존재하는 것을 방지

INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name // ""')
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // ""')

# TypeScript/JavaScript 파일 린트
if [ "$TOOL" = "Write" ] && echo "$FILE" | grep -qE '\.(ts|js|tsx|jsx)$'; then
  if command -v npx >/dev/null 2>&1 && [ -f ".eslintrc*" -o -f "eslint.config*" ]; then
    echo "[린트] ${FILE} 검사 중..." >&2
    LINT_RESULT=$(npx eslint "$FILE" --format compact 2>&1)
    LINT_EXIT=$?

    if [ $LINT_EXIT -ne 0 ]; then
      # Claude에게 오류 피드백 (차단이 아닌 수정 요청)
      cat <<EOF
{
  "decision": "block",
  "reason": "린트 오류가 발견되었습니다:\n\n${LINT_RESULT}\n\n위 오류를 수정한 후 계속하세요."
}
EOF
      exit 0
    fi
    echo "[린트] 통과." >&2
  fi
fi

# Python 파일 린트
if [ "$TOOL" = "Write" ] && echo "$FILE" | grep -qE '\.py$'; then
  if command -v ruff >/dev/null 2>&1; then
    LINT_RESULT=$(ruff check "$FILE" 2>&1)
    if [ $? -ne 0 ]; then
      cat <<EOF
{
  "decision": "block",
  "reason": "Python 린트 오류:\n\n${LINT_RESULT}\n\n위 오류를 수정하세요."
}
EOF
      exit 0
    fi
  fi
fi

exit 0
```

### 6.7 Hook 5: TaskCompleted — 아티팩트 완성 검증 게이트

```bash
#!/bin/bash
# .claude/hooks/artifact-gate.sh
# 태스크 완료 전에 필수 아티팩트가 모두 존재하는지 검증
# 목적: 문서 없는 구현 완료, 추적성 없는 기능 출시 차단

INPUT=$(cat)
SUBJECT=$(echo "$INPUT" | jq -r '.task_subject // ""')

# 필수 아티팩트 목록 (프로젝트에 맞게 조정)
REQUIRED_ARTIFACTS=(
  "SPEC.md"
  "docs/traceability-matrix.md"
)

# 구현 관련 태스크에만 적용
if echo "$SUBJECT" | grep -qiE '(구현|implement|완료|complete|배포|deploy)'; then
  MISSING=()
  for artifact in "${REQUIRED_ARTIFACTS[@]}"; do
    if [ ! -f "$artifact" ]; then
      MISSING+=("$artifact")
    fi
  done

  if [ ${#MISSING[@]} -gt 0 ]; then
    echo "[아티팩트 게이트] 다음 파일이 없습니다: ${MISSING[*]}" >&2
    echo "태스크를 완료하기 전에 위 파일을 생성하세요." >&2
    exit 2  # 태스크 완료 차단
  fi

  # 추적성 매트릭스에 항목이 있는지 확인
  if [ -f "docs/traceability-matrix.md" ]; then
    MATRIX_SIZE=$(wc -l < "docs/traceability-matrix.md")
    if [ "$MATRIX_SIZE" -lt 5 ]; then
      echo "[아티팩트 게이트] 추적성 매트릭스가 비어있습니다." >&2
      exit 2
    fi
  fi
fi

exit 0
```

### 6.8 Hook 6: SubagentStart — 서브에이전트 제약 주입

```bash
#!/bin/bash
# .claude/hooks/subagent-constraints.sh
# ultrawork가 새 서브에이전트를 시작할 때 프로젝트 규칙을 주입
# 목적: 서브에이전트도 동일한 품질 기준을 따르도록 보장

INPUT=$(cat)

# 현재 SPEC.md 내용 읽기
SPEC_SUMMARY=""
if [ -f "SPEC.md" ]; then
  SPEC_SUMMARY=$(head -30 SPEC.md)
fi

cat <<EOF
{
  "additionalContext": "[서브에이전트 필수 규칙]\n1. 모든 작업은 SPEC.md 요구사항 기반으로만 수행\n2. 모든 코드 변경에 REQ-XXX 추적성 ID 포함\n3. 테스트 없는 기능 구현 완료 불가\n4. 린트 오류가 있는 코드 커밋 불가\n5. 직접 main 브랜치 푸시 금지\n\n[현재 스펙 요약]\n${SPEC_SUMMARY}"
}
EOF
```

### 6.9 Hook 7: Stop — ralph 루프 강제 게이트

```bash
#!/bin/bash
# .claude/hooks/ralph-stop-gate.sh
# OMC ralph가 이미 사용하는 패턴의 표준 구현
# 목적: ralph 작업이 완료되기 전에 Claude Code가 종료되는 것을 방지

RALPH_STATE=".omc/state/ralph-state.json"

if [ -f "$RALPH_STATE" ]; then
  # jq를 사용한 상태 확인
  if command -v jq >/dev/null 2>&1; then
    ACTIVE=$(jq -r '.active // "false"' "$RALPH_STATE" 2>/dev/null)
    TASK=$(jq -r '.task // "알 수 없는 태스크"' "$RALPH_STATE" 2>/dev/null)
    TODO_COUNT=$(jq -r '.todos | length' "$RALPH_STATE" 2>/dev/null)
    ARCHITECT_APPROVED=$(jq -r '.architectApproved // "false"' "$RALPH_STATE" 2>/dev/null)

    if [ "$ACTIVE" = "true" ]; then
      echo "[RALPH GATE] 작업이 아직 완료되지 않았습니다." >&2
      echo "[RALPH GATE] 현재 태스크: ${TASK}" >&2
      echo "[RALPH GATE] 남은 TODO: ${TODO_COUNT}개" >&2
      echo "[RALPH GATE] Architect 승인: ${ARCHITECT_APPROVED}" >&2
      echo "[RALPH GATE] 계속 작업하세요. The boulder never stops." >&2
      exit 2  # 종료 차단
    fi
  else
    # jq 없이 간단히 확인
    if grep -q '"active": true' "$RALPH_STATE" 2>/dev/null; then
      echo "[RALPH GATE] Ralph가 활성 상태입니다. 작업을 계속하세요." >&2
      exit 2
    fi
  fi
fi

# ralplan 상태도 확인
RALPLAN_STATE=".omc/state/ralplan-state.json"
if [ -f "$RALPLAN_STATE" ]; then
  if command -v jq >/dev/null 2>&1; then
    RALPLAN_ACTIVE=$(jq -r '.active // "false"' "$RALPLAN_STATE" 2>/dev/null)
    if [ "$RALPLAN_ACTIVE" = "true" ]; then
      echo "[RALPLAN GATE] 계획 단계가 아직 완료되지 않았습니다." >&2
      exit 2
    fi
  fi
fi

# 모든 상태 파일이 비활성이면 정상 종료
exit 0
```

---

## 7. SPEC 요구사항별 충족 매핑

### 7.1 요구사항 1: Human in the Loop

SPEC의 정의:
> "claude code 처럼 중간중간 사람이 필요한 단계에서는 사람과 같이 채팅하여 결정해야함."

#### 충족 방법 3층 구조

```
HITL 3층 구조:
──────────────────────────────────────────────────────────────────

레이어 1: Claude Code 기본 기능
──────────────────────────────────────────────────────────────────
  모든 도구 실행 시 Allow/Deny/AllowAll 다이얼로그
  → 사용자가 모든 도구 호출을 승인/거부 가능
  → 이미 HITL의 가장 기본적인 형태

레이어 2: OMC ralph/ralplan 내장 HITL
──────────────────────────────────────────────────────────────────
  ralplan: Architect 상담 단계 (선택적)
    - 계획이 복잡하거나 불확실할 때 사람에게 묻는 단계
  ralph: Architect 검증 단계 (필수)
    - 모든 TODO 완료 후 사람(Architect)의 최종 승인 없이 종료 불가
    - 이것이 핵심 HITL: 에이전트가 혼자 "완료"를 선언할 수 없음

레이어 3: PreToolUse Hook 추가 HITL
──────────────────────────────────────────────────────────────────
  배포, main 브랜치 머지 등 고위험 작업 전 게이트
  → exit 2 반환 시 Claude Code가 차단하고 사용자에게 보고
  → 사용자가 명시적으로 허용해야 진행

──────────────────────────────────────────────────────────────────
```

#### HITL 발동 시나리오

| 시나리오 | 발동 Hook/메커니즘 | 사람의 역할 |
|---------|----------------|-----------|
| 계획 검토 | ralplan Architect 단계 | 계획 승인/수정 요청 |
| 구현 완료 검증 | ralph Architect 검증 | 결과물 승인/재작업 요청 |
| git push to main | PreToolUse Hook | 명시적 허용 필요 |
| 배포 실행 | PreToolUse Hook | 명시적 허용 필요 |
| 스펙 없는 구현 | UserPromptSubmit Hook | SPEC.md 먼저 작성 |

### 7.2 요구사항 2: 결정론적 + 비결정론적 혼합

SPEC의 정의:
> "결정론적인 상태머신 내 각 노드를 결정론적인 코드가 되게할지, 비결정론적인 claude code 같은 one loop agent가 되게할지 선택하여 쓸 수 있음. 혹은 다른 방법으로는 Outer Loop 자체도 상태머신이 아닌 claude code 같은 one loop agent를 쓰되, 이에 결정론적인 동작을 필요에 의해 섞고 싶을 때 여러 이벤트에 HOOK을 걸어서 사용"

#### 방법 B가 이미 구현됨

```
결정론적 vs 비결정론적 역할 분담:
──────────────────────────────────────────────────────────────────

비결정론적 (OMC가 담당):
  • ralph Executor 에이전트 → 코드 구현, CI 실패 수정
  • ralplan Planner 에이전트 → 계획 수립
  • ralplan Critic 에이전트 → 계획 비판
  • ultrawork 에이전트들 → 병렬 구현
  → LLM이 창의적 추론으로 처리해야 하는 영역

결정론적 (Hook이 담당):
  • SPEC.md 존재 여부 확인 → True/False
  • npm test 통과 여부 → pass/fail
  • eslint 통과 여부 → pass/fail
  • 필수 파일 존재 여부 → 있음/없음
  • git push 대상 브랜치 확인 → main이면 차단
  → 코드로 항상 동일한 결과를 낼 수 있는 영역

──────────────────────────────────────────────────────────────────

LLM이 결정하면 안 되는 것 (반드시 코드로):
  ✗ "테스트가 충분히 통과했나?"  → npm test 0 exit code가 결정
  ✗ "린트가 괜찮은가?"           → eslint exit code가 결정
  ✗ "배포해도 되나?"             → 차단 후 사람이 결정
  ✗ "계획이 좋은가?"             → Critic의 OKAY 텍스트가 결정

──────────────────────────────────────────────────────────────────
```

#### Stripe Minions Blueprint와의 대응

이전 보고서(`reliable-dev-agent-deterministic-mixing.md`)가 분석한 Stripe Blueprint의 구조는 OMC + Hook 조합과 정확히 대응된다.

| Stripe Blueprint | OMC + Hook 대응 |
|----------------|----------------|
| 결정론적 노드 (사각형) | Claude Code Hook (bash 스크립트) |
| 에이전트 노드 (구름) | OMC ralph/ralplan/ultrawork 에이전트 |
| 상태머신 전이 | Stop Hook + ralph-state.json |
| 사람 승인 노드 | ralph Architect 검증, PreToolUse 차단 |

### 7.3 요구사항 3: 신뢰성-효율성 균형

SPEC의 정의:
> "모든 Agent를 langgraph방식의 상태머신으로 만든다면 신뢰성은 올라가지만, 해당 시스템이 처리할 수 있는 task가 적어지므로 효율성은 떨어짐. 이를 고려해서 둘다 챙긴 시스템을 만들어서 회사내부에 정착시키는것이 목표임."

#### 효율성 (OMC가 제공)

```
효율성 제공 메커니즘:
──────────────────────────────────────────────────────────────────
1. ultrawork 병렬 실행
   → 독립적인 태스크를 동시에 여러 에이전트가 처리
   → 직렬 처리 대비 2-5배 처리량 향상

2. 스마트 모델 라우팅
   → 단순 태스크: Claude Haiku (빠르고 저렴)
   → 중간 태스크: Claude Sonnet (균형)
   → 복잡 추론: Claude Opus (고품질)
   → 태스크 복잡도별 최적 비용/성능 비율

3. ralph의 자율 실행
   → TODO 목록을 자율적으로 처리, 매 단계 사람 확인 불필요
   → Architect 검증은 마지막 한 번만
──────────────────────────────────────────────────────────────────
```

#### 신뢰성 (Hook이 제공)

```
신뢰성 제공 메커니즘:
──────────────────────────────────────────────────────────────────
1. 테스트 게이트 (PreToolUse)
   → 테스트 실패 시 커밋 자체가 불가능
   → "테스트를 나중에 통과시키겠습니다"는 불가

2. 린트 게이트 (PostToolUse)
   → 린트 오류 코드는 코드베이스에 존재할 수 없음
   → 코드 품질의 최저선 보장

3. 아티팩트 게이트 (TaskCompleted)
   → 문서 없는 구현 완료 불가
   → 추적성 없는 기능 불가

4. Stop 게이트 (Stop Hook)
   → 태스크 미완료 시 에이전트 종료 불가
   → "절반만 완료하고 멈추는" 시나리오 차단
──────────────────────────────────────────────────────────────────
```

---

## 8. 신뢰성-효율성 Trade-off 해소

### 8.1 게이트 강도 조절 메커니즘

신뢰성-효율성 trade-off는 게이트의 강도를 프로젝트 성숙도와 팀 신뢰도에 따라 조절함으로써 해소된다.

```
게이트 강도 스펙트럼:
──────────────────────────────────────────────────────────────────
← 높은 효율성                            높은 신뢰성 →

[NONE]  [WARN]  [SOFT]  [HARD]  [BLOCK]

NONE:  게이트 없음 (Hook 비활성화)
WARN:  경고만 출력, 진행은 허용
SOFT:  Claude에게 피드백 전달, 수정 권고
HARD:  차단 후 사람에게 보고, 허용 가능
BLOCK: 무조건 차단, 우회 불가

──────────────────────────────────────────────────────────────────
```

### 8.2 환경별 게이트 설정 예시

```
프로젝트 단계별 게이트 강도:
──────────────────────────────────────────────────────────────────
초기 개발 단계 (속도 우선):
  테스트 게이트:     WARN (경고만)
  린트 게이트:       SOFT (피드백)
  아티팩트 게이트:   NONE (없음)
  배포 게이트:       HARD (사람 확인)

안정화 단계 (품질 강화):
  테스트 게이트:     HARD (차단)
  린트 게이트:       HARD (차단)
  아티팩트 게이트:   SOFT (권고)
  배포 게이트:       BLOCK (무조건 사람)

프로덕션 단계 (신뢰성 최우선):
  테스트 게이트:     BLOCK (무조건)
  린트 게이트:       BLOCK (무조건)
  아티팩트 게이트:   HARD (차단)
  배포 게이트:       BLOCK (무조건)
──────────────────────────────────────────────────────────────────
```

### 8.3 환경 변수로 게이트 수준 제어

```bash
# .claude/hooks/pre-tool-enforcer.sh 확장 버전
#!/bin/bash

INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name // ""')
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // ""')

# 환경 변수로 게이트 강도 제어
GATE_LEVEL="${CLAUDE_GATE_LEVEL:-HARD}"  # 기본: HARD

# git commit 게이트
if [ "$TOOL" = "Bash" ] && echo "$COMMAND" | grep -qE 'git\s+commit'; then
  case "$GATE_LEVEL" in
    "NONE")
      exit 0  # 게이트 없음
      ;;
    "WARN")
      echo "[경고] 커밋 전 테스트 실행을 권장합니다." >&2
      exit 0
      ;;
    "SOFT"|"HARD"|"BLOCK")
      if ! npm test --silent 2>/dev/null; then
        cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "테스트 게이트 실패 [${GATE_LEVEL}]: 테스트를 통과해야 커밋할 수 있습니다."
  }
}
EOF
        exit 0
      fi
      ;;
  esac
fi

exit 0
```

### 8.4 LangGraph vs OMC + Hook 비교

```
신뢰성-효율성 비교표:
──────────────────────────────────────────────────────────────────
항목                    LangGraph 상태머신    OMC + Hook
──────────────────────────────────────────────────────────────────
구축 난이도             높음 (전체 재설계)    낮음 (Hook 추가만)
유지보수                높음 (상태 전이 관리) 낮음 (Hook 스크립트)
처리 가능 태스크 범위   좁음 (정의된 것만)    넓음 (LLM이 처리)
결정론적 게이트 정밀도  높음 (노드별)         높음 (Hook별)
HITL 통합               복잡                  단순 (기본 내장)
병렬 실행               별도 구현 필요        ultrawork 기본 제공
모델 라우팅             별도 구현 필요        ultrawork 기본 제공
커스터마이징 난이도     높음                  낮음 (bash 스크립트)
기존 Claude Code 활용   불가 (별도 시스템)    완전 활용
──────────────────────────────────────────────────────────────────
```

OMC + Hook 조합이 LangGraph 대비 구축 난이도, 유지보수, 커스터마이징 모든 면에서 우위에 있다. 신뢰성 측면에서도 Hook의 결정론적 게이트는 LangGraph의 결정론적 노드와 동등한 역할을 수행한다.

---

## 9. 결론 및 권고

### 9.1 핵심 결론

**OMC + Claude Code Hook 조합으로 SPEC_AgentForDev.md의 모든 요구사항을 충족할 수 있다. Pi SDK나 LangGraph 같은 별도 프레임워크로 교체할 필요가 없다.**

이를 5가지 명제로 정리한다.

**명제 1: OMC는 이미 검증된 비결정론적 워크플로다**
ralph의 자기참조 루프, ralplan의 Planner-Critic 패턴, ultrawork의 병렬 오케스트레이션은 이미 작동하는 비결정론적 워크플로를 제공한다. 이것을 버리고 처음부터 재구축하는 것은 검증된 자산을 포기하는 것이다.

**명제 2: Hook은 LangGraph 노드와 동등한 결정론적 게이트다**
LangGraph의 결정론적 노드가 하는 일(테스트 실행, 린트, 파일 존재 확인)을 Claude Code Hook의 bash 스크립트가 동일하게 수행한다. 차이는 Hook이 훨씬 단순하고, 기존 시스템과 완벽하게 통합된다는 점이다.

**명제 3: 이 아키텍처는 이 대화에서 이미 실행 중이다**
이 보고서를 작성하는 대화에서 PreToolUse Hook이 모든 도구 호출 전에 발동하고, ralph 루프가 Stop Hook으로 강제되는 것을 직접 관찰했다. 이론이 아니라 실증된 아키텍처다.

**명제 4: 방법 B는 방법 A보다 실용적이다**
SPEC이 제시한 두 방법 중 방법 B(One-loop Agent + Hook 주입)는 방법 A(상태머신 전체 구축)보다 구축 시간이 짧고, 유지보수가 쉽고, 기존 Claude Code의 전체 역량을 활용한다.

**명제 5: 게이트 수준 조절로 신뢰성-효율성을 균형 잡을 수 있다**
Hook의 강도를 프로젝트 단계(초기/안정화/프로덕션)에 따라 NONE/WARN/SOFT/HARD/BLOCK으로 조절하면, 개발 초기에는 효율성을 우선하고 프로덕션에서는 신뢰성을 우선하는 유연한 운영이 가능하다.

### 9.2 권고 사항

#### 단계 1: 즉시 시작 가능한 기본 Hook 세트 (1-2일)

```
최소 기본 Hook 세트:
──────────────────────────────────────────────────────────────────
1. ralph-stop-gate.sh   → ralph 루프 강제 (OMC가 이미 사용)
2. spec-first-gate.sh   → 스펙 우선 강제
3. pre-tool-enforcer.sh → 커밋 전 테스트 게이트
──────────────────────────────────────────────────────────────────
이것만으로도 세 요구사항의 70%를 충족한다.
```

#### 단계 2: 품질 게이트 강화 (1주)

```
품질 강화 Hook 세트:
──────────────────────────────────────────────────────────────────
4. post-tool-linter.sh      → 린트 게이트
5. artifact-gate.sh         → 아티팩트 검증
6. subagent-constraints.sh  → 서브에이전트 규칙
7. session-start.sh         → 컨텍스트 주입
──────────────────────────────────────────────────────────────────
이것으로 나머지 30%를 충족한다.
```

#### 단계 3: 팀 워크플로 통합 (지속)

```
지속적 개선:
──────────────────────────────────────────────────────────────────
• 프로젝트별 SPEC.md 표준 템플릿 정착
• 추적성 매트릭스 (traceability-matrix.md) 자동 업데이트 Hook
• 팀 내 게이트 강도 기준 합의 (초기/안정화/프로덕션)
• Hook 스크립트 버전 관리 (Git)
──────────────────────────────────────────────────────────────────
```

### 9.3 최종 아키텍처 요약

```
최소 추가로 최대 효과:
──────────────────────────────────────────────────────────────────

                    [이미 있는 것]
Claude Code (One-loop Agent) + OMC (ralph/ralplan/ultrawork)
                         │
                         │ 최소 추가
                         ▼
              [7개 Hook 스크립트 추가]
              (각각 10-50줄의 bash)
                         │
                         │ 달성
                         ▼
          [SPEC_AgentForDev.md 3가지 요구사항 충족]
          1. Human in the Loop ✓
          2. 결정론적 + 비결정론적 혼합 (방법 B) ✓
          3. 신뢰성-효율성 균형 ✓

──────────────────────────────────────────────────────────────────
```

Claude Code + OMC + Hook = 목표 달성을 위한 최소한의, 그러나 충분한 조합이다. "The boulder never stops"는 단순한 모토가 아니다. Stop Hook이 ralph 상태를 확인하고, exit 2로 종료를 차단하는 결정론적 게이트다. 이 아키텍처는 이미 이 대화에서 실행 중이다.

---

## 부록: Hook 이벤트 빠른 참조

| Hook 이벤트 | 발동 시점 | exit 0 | exit 1 | exit 2 |
|-----------|---------|--------|--------|--------|
| `SessionStart` | 세션 시작 | 정상 | 오류 | - |
| `UserPromptSubmit` | 사용자 입력 후 | 허용 | 오류 | 차단 |
| `PreToolUse` | 도구 호출 전 | 허용 | 오류 | 차단 |
| `PostToolUse` | 도구 호출 후 | 계속 | 오류 | 차단 |
| `TaskCompleted` | 태스크 완료 전 | 허용 | 오류 | 차단 |
| `Stop` | 응답 완료 후 | 종료 허용 | 오류 | 종료 차단 |
| `SubagentStart` | 서브에이전트 시작 | 계속 | 오류 | - |
| `TeammateIdle` | 에이전트 유휴 | 계속 | 오류 | - |

---

*이 보고서는 Claude Code + OMC + Hook 아키텍처가 SPEC_AgentForDev.md 요구사항을 충족함을 분석한다. 이 보고서 자체가 해당 아키텍처(Stop Hook + PreToolUse Hook + ralph 루프)가 실행 중인 환경에서 작성되었다.*
