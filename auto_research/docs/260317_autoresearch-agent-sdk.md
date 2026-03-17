# AutoResearch 고도화: claude -p vs Claude Agent SDK + 멀티에이전트 설계

> 작성일: 2026-03-17
> 목적: claude -p 기반 ralph 루프를 Claude Agent SDK 기반 Planner-Executor-Reflector 멀티에이전트로 업그레이드하는 방법 조사

---

## 목차

1. [핵심 질문: claude -p에서 oh-my-claude 스킬이 작동하는가?](#1-핵심-질문)
2. [Claude Agent SDK 개요](#2-claude-agent-sdk-개요)
3. [멀티에이전트 프레임워크 비교](#3-멀티에이전트-프레임워크-비교)
4. [Planner-Executor-Reflector 패턴](#4-planner-executor-reflector-패턴)
5. [선행 자율 연구 시스템](#5-선행-자율-연구-시스템)
6. [autoresearch에 최적화된 Agent SDK 아키텍처 설계](#6-autoresearch-최적화-설계)
7. [최종 권장 요약](#7-최종-권장-요약)

---

## 1. 핵심 질문

### Q: `claude -p`에서 oh-my-claude 플러그인의 /ralph, /ralplan 같은 스킬이 작동하는가?

**답: 작동하지 않는다.** 공식 문서에서 명확히 명시:

> "User-invoked skills like `/commit` and built-in commands are **only available in interactive mode**. In `-p` mode, describe the task you want to accomplish instead."
> — [Skills - Claude Code Docs](https://code.claude.com/docs/en/skills)

### 기술적 이유: claude -p와 인터랙티브 모드의 차이

| 기능 | 인터랙티브 모드 | claude -p |
|------|----------------|-----------|
| **스킬** (`/commit`, `/ralph` 등) | 작동 | **비활성화** (공식 명시) |
| **Built-in commands** | 작동 | **비활성화** (공식 명시) |
| **settings.json 훅** | 자동 로드 | `--setting-sources user,project` 명시 필요 |
| **MCP 서버** | 자동 로드 | `--mcp-config` 또는 `--setting-sources` 필요 |
| **`CLAUDECODE` 환경변수** | 설정됨 (`CLAUDECODE=1`) | 설정됨 (`CLAUDECODE=1`) — 모드 무관 |
| **플러그인** | 자동 작동 | `--setting-sources`로 로드 시 일부 가능 |
| **세션 라이프사이클** | SessionStart/End 훅 | 다르게 동작 |

**`CLAUDECODE` 환경변수 상세 설명**:
`CLAUDECODE=1`은 "현재 Claude Code 프로세스 내에서 실행 중임"을 나타내는 플래그이다. 인터랙티브 모드와 `-p` 모드 **모두에서 동일하게 설정**된다. 따라서 이 변수만으로는 두 모드를 구분할 수 없다.

**그렇다면 플러그인은 왜 `-p`에서 작동하지 않는가?**
`CLAUDECODE=1`이 설정되어 있어도 `-p` 모드에서 훅이 실행되지 않는 이유는 다음과 같다:
- **REPL 루프 부재**: 인터랙티브 모드는 입력-처리-출력을 반복하는 REPL(Read-Eval-Print Loop)이 있어서, 각 프롬프트 제출 시 `UserPromptSubmit` 훅이 트리거된다. `-p` 모드는 단일 프롬프트를 처리하고 종료하므로 REPL 루프 자체가 없다.
- **SessionStart/SessionEnd 훅**: 인터랙티브 세션이 시작/종료될 때 발생하는 생명주기 이벤트가 `-p` 모드에서는 다르게 처리된다. 플러그인이 이 이벤트에 의존한다면 작동하지 않는다.
- **스킬 시스템 비활성화**: `/ralph`, `/ralplan` 같은 슬래시 커맨드는 REPL 입력 파싱 단계에서 처리되는데, `-p` 모드는 이 파싱 단계를 거치지 않는다.

**근본적 이유**: oh-my-claude 같은 플러그인 시스템은 인터랙티브 세션의 REPL 루프에 통합되어 있다. `-p` 모드는 단발성 실행(one-shot)으로, 다음이 없다:
- 스킬 시스템의 REPL 상호작용
- SessionStart/SessionEnd 생명주기 훅
- 플러그인의 프롬프트 제출 훅(UserPromptSubmit)

### 현재 ralph.sh의 한계

```bash
# 현재 ralph.sh 방식
while true; do
    cat "$PROGRAM" | claude -p --allowedTools "Bash,Read,Write,Edit"
    sleep 5
done
```

**`--allowedTools` 옵션의 기술적 한계**:
- **도구 집합 고정**: 런타임 중 동적으로 변경 불가. 이터레이션마다 다른 도구가 필요해도 `--allowedTools`는 프로세스 시작 시 한 번만 지정된다.
- **허용 범위만 지정**: `--allowedTools`는 "허가 없이 사용 가능한 도구"를 지정할 뿐, 도구 집합 자체를 제한하는 `--tools`와 다르다. 즉, 목록에 없는 도구 호출 시 사용자 확인을 요청하거나 거부된다.
- **MCP 도구 불포함**: `--allowedTools`로 지정할 수 있는 도구는 내장 도구(Bash, Read 등)와 MCP 도구의 일부 패턴만이다. MCP 서버 자체를 로드하려면 `--mcp-config`가 별도로 필요하다.

**파이프(`|`) 입력 방식의 기술적 한계**:
```bash
cat program.md | claude -p --allowedTools "Bash,Read,Write,Edit"
```
- **단방향 단발성**: stdin으로 전달된 내용은 단일 프롬프트로 처리된다. 멀티턴 대화 컨텍스트(이전 메시지 참조) 불가능.
- **입력 크기 제한**: 파이프로 전달할 수 있는 텍스트 크기는 시스템 파이프 버퍼 한계와 Claude의 컨텍스트 창에 의해 제한된다. 매우 큰 `program.md`나 `results.tsv` 전체를 파이프로 전달 시 절단될 수 있다.
- **세션 재개 불가**: `--resume` 플래그를 통해 이전 세션을 재개할 수 있으나, 파이프로 스크립팅할 때 세션 ID를 추적하고 전달하는 것이 복잡하다.
- **출력 캡처만 가능**: stdout으로 받은 텍스트 출력만 다음 단계로 전달할 수 있다. 에이전트 내부 상태나 도구 호출 내역을 구조적으로 받을 수 없다(JSON 출력 모드 제외).

이 방식의 기능적 한계:
1. **스킬/훅 없음**: /ralph, /ralplan 같은 전문 에이전트 하니스 사용 불가
2. **서브에이전트 없음**: 플래너, 실행자, 반성자 역할 분리 불가
3. **단순 도구만 사용**: Bash, Read, Write, Edit만으로 모든 연구 수행
4. **메모리 수동 관리**: 에이전트가 직접 파일을 읽고 써야 함
5. **프로그램적 제어 불가**: 파이썬 코드로 루프 제어, 조건 분기, 병렬화 불가

**결론**: claude -p 기반 ralph 루프는 단순하지만 고도화의 한계가 있다. 전문 에이전트 패턴이 필요하다면 **Claude Agent SDK**가 해답이다.

---

## 2. Claude Agent SDK 개요

### 2.1 패키지 정보

| | Python | TypeScript/Node.js |
|--|--------|--------------------|
| **패키지명** | `claude-agent-sdk` | `@anthropic-ai/claude-agent-sdk` |
| **설치** | `pip install claude-agent-sdk` | `npm install @anthropic-ai/claude-agent-sdk` |
| **GitHub** | [anthropics/claude-agent-sdk-python](https://github.com/anthropics/claude-agent-sdk-python) | [anthropics/claude-agent-sdk-typescript](https://github.com/anthropics/claude-agent-sdk-typescript) |

> **이력**: 2025년 6월 "Claude Code SDK"로 출시 → 2025년 9월 "Claude Agent SDK"로 리네이밍 (코딩 에이전트 외에도 범용 사용). 구버전 `claude-code-sdk`는 deprecated.

### 2.2 claude -p vs Agent SDK: 근본적 차이

| 항목 | claude -p | Claude Agent SDK |
|------|-----------|-----------------|
| **인터페이스** | CLI 프로세스 | Python/TS 라이브러리 |
| **프로세스 모델** | 별도 OS 프로세스 spawning | In-process (동일 Python 런타임) |
| **훅** | shell command (settings.json) | Python 콜백 함수 (네이티브) |
| **출력** | stdout 텍스트/JSON | 구조화된 메시지 객체 스트림 |
| **서브에이전트** | 제한적 | `agents` 옵션으로 완전 지원 |
| **루프 제어** | shell while 루프 | Python for/while 루프 |
| **조건 분기** | bash if/elif | Python 완전 지원 |
| **병렬화** | 어려움 | `asyncio.gather` 즉시 사용 |
| **스킬** | 비활성화 | `setting_sources=["project"]` 시 가능 |
| **MCP** | `--mcp-config` 플래그 | `mcp_servers` 옵션 |

### 2.3 기본 사용 패턴 (Python)

```python
import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions

async def single_experiment():
    """한 번의 실험 루프"""
    async for message in query(
        prompt="""
results.tsv를 읽어 현재 상태를 파악하고,
train.py를 수정해 실험을 실행하고 결과를 기록하라.
""",
        options=ClaudeAgentOptions(
            allowed_tools=["Bash", "Read", "Write", "Edit"],
            permission_mode="acceptEdits",  # 파일 수정 자동 승인
        ),
    ):
        if hasattr(message, "result"):
            print(message.result)

asyncio.run(single_experiment())
```

### 2.4 서브에이전트 생성 API

`AgentDefinition`으로 서브에이전트를 정의하고, `allowed_tools`에 `"Agent"`를 반드시 포함해야 한다.

```python
from claude_agent_sdk import query, ClaudeAgentOptions, AgentDefinition

options = ClaudeAgentOptions(
    allowed_tools=["Read", "Bash", "Write", "Agent"],  # "Agent" 필수
    agents={
        "planner": AgentDefinition(
            description="실험 전략 수립 전문가. 다음 하이퍼파라미터를 결정할 때 사용.",
            prompt="당신은 ML 실험 플래너입니다. 다음 실험 설정을 JSON으로 출력하세요.",
            tools=["Read", "Grep"],
            model="haiku",   # 비용 절감: 계획은 haiku
        ),
        "executor": AgentDefinition(
            description="GPU 훈련 실행 전문가. 실제 훈련을 실행할 때 사용.",
            prompt="당신은 ML 훈련 실행자입니다. train.py를 수정하고 실행하세요.",
            tools=["Bash", "Write", "Read", "Edit"],
            model="sonnet",  # 실행은 sonnet
        ),
    }
)
```

**서브에이전트 3가지 생성 방법**:
1. **프로그래매틱** (권장): `agents={"name": AgentDefinition(...)}` 파라미터
2. **파일시스템 기반**: `.claude/agents/agent-name.md` 마크다운 파일
3. **내장 general-purpose**: `"Agent"` 도구만 추가하면 Claude가 자동으로 범용 서브에이전트 생성

**중요 제약**: 서브에이전트의 `tools`에 `"Agent"`를 포함할 수 없음 → **서브에이전트 중첩은 1단계만 가능**

### 2.5 내장 도구 전체 목록

| 도구 | 기능 |
|------|------|
| `Bash` | 터미널 명령, 스크립트, git 실행 |
| `Read` | 파일 읽기 |
| `Write` | 새 파일 생성 |
| `Edit` | 기존 파일 편집 |
| `Glob` | 파일 패턴 검색 |
| `Grep` | 파일 내용 정규식 검색 |
| `WebSearch` | 웹 검색 |
| `WebFetch` | 웹 페이지 파싱 |
| `AskUserQuestion` | 사용자에게 질문 |

autoresearch에 필요한 모든 도구(파일 수정, bash 실행)가 내장되어 있다.

---

## 3. 멀티에이전트 프레임워크 비교

### 3.1 autoresearch 적합성 기준

autoresearch의 핵심 요구사항:
1. **Bash 실행**: GPU 훈련 스크립트(`uv run train.py`) 실행
2. **파일 읽기/쓰기**: train.py 수정, results.tsv 업데이트
3. **이터레이션 루프 외부 제어**: 5분 × N회 반복, Python이 제어해야 함
4. **오버헤드 최소화**: 5분 실험에서 에이전트 오버헤드 < 30초

### 3.2 프레임워크별 상세 분석

#### Claude Agent SDK (Anthropic 공식) ★★★★★

```python
# bash/파일 I/O 내장, 루프 완전 제어
from claude_agent_sdk import query, ClaudeAgentOptions
import asyncio

async def autoresearch_sdk(iterations=100):
    for i in range(iterations):
        async for msg in query(
            prompt=f"iteration {i}: 다음 실험 수행",
            options=ClaudeAgentOptions(
                allowed_tools=["Bash", "Read", "Write", "Edit", "Agent"],
                agents={"planner": ..., "executor": ..., "reflector": ...}
            )
        ):
            pass  # 각 이터레이션이 독립 실행
```

- **장점**: bash/파일 I/O가 내장 도구, Python이 루프 완전 제어, Claude 최신 모델 네이티브, 서브에이전트 모델별 지정 가능
- **단점**: Anthropic API Key 필수(Claude 전용), 서브에이전트 중첩 1단계 제한, 비교적 신규 SDK

#### LangGraph (LangChain) ★★★★★

```python
# 상태 기계 기반, 오버헤드 최소, 모델 무관
from langgraph.graph import StateGraph, END

builder = StateGraph(dict)
builder.add_node("plan", planner_fn)
builder.add_node("execute", executor_fn)
builder.add_node("reflect", reflector_fn)
builder.add_conditional_edges("reflect", should_continue,
    {"continue": "plan", "end": END})
app = builder.compile()
result = app.invoke({"iteration": 0, ...})
```

- **장점**: 오버헤드 최소, 그래프로 워크플로우 명시적 설계, 모델 무관(Claude/GPT/로컬), MIT 라이선스
- **단점**: 초기 학습 곡선, 그래프 사전 설계 필요, LLM 호출 직접 구현

#### CrewAI ★★

```python
from crewai import Agent, Crew, Task, Process

crew = Crew(
    agents=[planner, executor, reflector],
    tasks=[plan_task, execute_task, reflect_task],
    process=Process.sequential,
)
```

- **장점**: 역할 기반 코드 가독성 높음, 빠른 프로토타이핑
- **단점**: 오버헤드 높음(LangGraph 대비 3배 느림, 토큰 56% 추가), 5분 실험 루프에 과도

#### AutoGen (Microsoft) ★★

- **주의**: 2025년 유지보수 모드로 전환. Microsoft Agent Framework로 이전 권장
- `max_round`로 루프 제어가 제한적, 대화 기록 누적으로 컨텍스트 급증

#### OpenAI Swarm → Agents SDK ★★★

- Swarm은 deprecated, OpenAI Agents SDK로 대체
- 이터레이션 루프를 LLM이 핸드오프로 제어 → 예측 불가
- OpenAI 모델 중심 (Claude 사용 시 별도 설정)

### 3.3 autoresearch 적합성 종합 비교

| 프레임워크 | Bash 실행 | 파일 I/O | 루프 외부 제어 | 오버헤드 | 추천도 |
|---|---|---|---|---|---|
| **Claude Agent SDK** | 내장 | 내장 | 완전 (Python) | 낮음 | ★★★★★ |
| **LangGraph** | subprocess 직접 | Python 직접 | 완전 (Python) | 최소 | ★★★★★ |
| **smolagents** | 코드 생성 실행 | 코드 생성 실행 | 완전 (Python) | 최소 | ★★★★ |
| **OpenAI Agents SDK** | function_tool 래핑 | function_tool 래핑 | LLM 핸드오프 | 낮음 | ★★★ |
| **AutoGen** | UserProxy 자동 | 코드 생성 | max_round 제한 | 중간 | ★★ |
| **CrewAI** | 커스텀 도구 필요 | 커스텀 도구 필요 | kickoff() 반복 | 높음 | ★★ |

---

## 4. Planner-Executor-Reflector 패턴

### 4.1 패턴의 역사와 출처

이 패턴은 단일 논문이 아닌 여러 연구가 수렴하여 형성된 아키텍처이다:

```
ReAct (Yao 2022)              Reflexion (Shinn 2023)
Thought→Action→Observation    자기 반성 언어적 피드백
         ↓                             ↓
Plan-and-Execute (LangChain 2023)
Planner ↔ Executor ↔ Replanner
         ↓
Planner-Executor-Reflector (현재 표준 패턴)
```

### 4.2 각 에이전트 역할 명세

| 에이전트 | 역할 | 입력 | 출력 |
|---|---|---|---|
| **Planner** | 고수준 전략, 실험 아이디어 선택, 우선순위 | 목표, 현재 최고 val_bpb, 실패 기록, 미탐색 방향 | 실험 설정 (어떤 하이퍼파라미터/아키텍처 변경) |
| **Executor** | train.py 수정, 학습 실행, 결과 수집 | 실험 설정, 현재 train.py | 수정된 train.py, val_bpb, vram, 실행 로그 |
| **Reflector** | 결과 분석, keep/discard 판단, 메모리 업데이트 | 실험 결과, 이전 기록 | keep/discard 결정, git 처리, memory/ 업데이트 |

### 4.3 autoresearch에 적용된 역할 매핑

```
Planner  → results.tsv/SUMMARY.md 읽기 + 미탐색 방향 선택 + 실험 계획 수립
           (어떤 하이퍼파라미터를 바꿀지, simplicity criterion 고려)

Executor → train.py 수정 + git commit + uv run train.py 실행 (5분)
           + run.log에서 val_bpb, peak_vram_mb 추출

Reflector→ 개선 여부 판단 (keep/discard/crash 분류)
           + results.tsv 업데이트
           + memory/SUMMARY.md, FAILED.md 업데이트
           + keep이면 commit 유지, discard면 git reset --hard HEAD~1
```

### 4.4 에이전트 간 통신 방식

한 이터레이션 내에서 Planner → Executor → Reflector 사이의 정보 전달은 두 채널로 이루어진다:

**채널 A: Python 변수를 통한 프롬프트 문자열 패싱 (단기, 이터레이션 내)**

```python
# autoresearch_sdk.py의 실제 흐름
plan = ""          # Planner 출력
exec_result = ""   # Executor 출력

# Phase 1: Planner → 출력을 plan 변수에 저장
async for msg in query(prompt="다음 실험 설계..."):
    if hasattr(msg, "result"):
        plan = msg.result  # "{"hypothesis": "GQA 적용", "change": "..."}"

# Phase 2: Executor → plan을 프롬프트에 주입, 출력을 exec_result에 저장
async for msg in query(prompt=f"다음 계획을 실행하라:\n{plan}"):
    if hasattr(msg, "result"):
        exec_result = msg.result  # "{"val_bpb": 0.9654, "status": "success"}"

# Phase 3: Reflector → exec_result를 프롬프트에 주입
async for msg in query(prompt=f"결과를 평가하라:\n{exec_result}"):
    pass
```

이 채널의 특징:
- 이터레이션 내에서만 유지됨 (다음 이터레이션에서는 초기화)
- 구조화된 JSON 문자열로 전달 (파싱 가능)
- 이전 에이전트의 전체 출력이 다음 에이전트의 프롬프트로 주입됨

**채널 B: 파일시스템 기반 공유 메모리 (장기, 이터레이션 간)**

```
memory/
├── SUMMARY.md   ← Planner가 읽고, Reflector가 쓴다
├── FAILED.md    ← Planner가 읽고 (HARD BLOCK 확인), Reflector가 쓴다
└── INSIGHTS.md  ← Reflector가 중요 발견 시 쓴다

results.tsv      ← Reflector가 쓰고, (필요 시) Planner가 읽는다
```

이 채널의 특징:
- 이터레이션이 종료되어도 영속 (다음 이터레이션에서 읽기 가능)
- 비동기 쓰기 가능 (파일 기반이므로 에이전트 재시작 후에도 유지)
- git 미추적 파일 → git reset이 일어나도 영향 없음

**두 채널의 역할 분리**:

| 채널 | 전달 정보 | 유효 범위 | 용도 |
|------|----------|----------|------|
| Python 변수 패싱 | 실험 계획, 실행 결과 | 이터레이션 내 | 에이전트 간 즉각적 정보 전달 |
| 파일시스템 공유 메모리 | 탐색 공간 지도, 실패 목록, 누적 결과 | 이터레이션 간 | 장기 학습 및 상태 유지 |

이 설계는 **블랙보드(Blackboard) 아키텍처 패턴**의 경량 구현이다 — 공유 메모리(memory/)에 모든 에이전트가 읽고 쓰고, 단기 조율은 직접 메시지 패싱으로 처리한다.

### 4.5 각 에이전트 전문 프롬프트 예시

```python
PLANNER_PROMPT = """
당신은 ML 연구 플래너입니다.

## 목표
val_bpb를 최소화하는 실험을 설계하라.

## 제약
- train.py만 수정 가능 (prepare.py 금지)
- 새 패키지 설치 불가 (pyproject.toml 내 도구만)
- 5분 시간 예산 내 완료되어야 함
- Simplicity criterion: 소폭 개선은 단순한 변경으로만

## 입력
1. memory/SUMMARY.md - 탐색 공간 지도 (시도된/미탐색 방향)
2. memory/FAILED.md - HARD/SOFT 블록 목록
3. results.tsv 최근 5개 - 최근 트렌드

## 출력 형식
```json
{
  "hypothesis": "어떤 아이디어를 시도하는가 (한 문장)",
  "change": "구체적으로 무엇을 바꾸는가",
  "rationale": "왜 이 실험이 개선을 가져올 것인가",
  "risk": "VRAM 증가, 발산 위험 등"
}
```
HARD BLOCK에 있는 방향은 절대 선택하지 마라.
"""

EXECUTOR_PROMPT = """
당신은 ML 훈련 실행자입니다.

## 역할
플래너가 제안한 실험을 train.py에 구현하고 실행하라.

## 절차
1. 현재 train.py 읽기
2. 플래너의 계획에 따라 최소한의 변경 적용
3. git commit -am "실험 설명"
4. uv run train.py > run.log 2>&1 (최대 10분)
5. grep "^val_bpb:\\|^peak_vram_mb:" run.log 로 결과 확인
6. 결과를 구조화된 형식으로 반환

## 출력 형식
```json
{
  "commit_hash": "a1b2c3d",
  "val_bpb": 0.9712,
  "peak_vram_mb": 45060,
  "status": "success|crash|timeout",
  "error": null
}
```
crash면 tail -n 50 run.log 로 원인 파악 후 포함.
"""

REFLECTOR_PROMPT = """
당신은 ML 실험 반성자입니다.

## 역할
실험 결과를 분석하고, 메모리를 업데이트하고, git 상태를 결정하라.

## 판단 기준
- keep: 현재 최고 val_bpb보다 개선됨
- discard: 개선 없음 또는 소폭 악화
- crash: 코드 실패, OOM, timeout

## 절차
1. 결과 해석 및 판단
2. 판단 *전에* memory/ 업데이트:
   - FAILED.md: crash → HARD BLOCK, discard → SOFT BLOCK (조건 명시)
   - SUMMARY.md: 시도된 방향 추가, 미탐색 방향에서 제거
3. 판단 후 git 처리:
   - keep → 그대로 (commit 유지)
   - discard/crash → git reset --hard HEAD~1
4. results.tsv에 한 줄 추가 (절대 commit하지 않음)

⚠️ 메모리 업데이트 → git reset 순서 엄수 (역순 금지)
"""
```

---

## 5. 선행 자율 연구 시스템

### 5.1 패턴 계보도

```
ReAct (Yao 2022, Google/Princeton)
Thought → Action → Observation 루프
                ↓
STOP (Zelikman 2023, Microsoft)          Reflexion (Shinn 2023)
재귀적 스캐폴드 자기 개선                  언어적 자기 반성
         ↓                                       ↓
AI Scientist v1 (Sakana 2024)         Plan-and-Execute (LangChain 2023)
4단계 순차 파이프라인                    Planner ↔ Executor ↔ Replanner
Researcher + Reviewer 에이전트
         ↓
AI Scientist v2 (Sakana 2025)
Experiment Progress Manager
Agentic Tree Search
         ↓
autoresearch (Karpathy 2026)
단일 에이전트 STOP-like 루프 (단순성 극대화)
```

### 5.2 AI Scientist v1/v2 (Sakana AI)

**v1 구조** (2024):
```
[Idea Generation] → [Experimental Iteration] → [Paper Write-up] → [Peer Review]
      ↑                        ↑                       ↑                |
  Semantic Scholar         experiment.py          LaTeX 자동 작성    LLM Reviewer
  신규성 검증             수정+실행+시각화                              피드백 루프
```

- 논문 1편당 비용: ~$15
- 단순 아이디어에서 논문 초안까지 완전 자동화

**v2 구조** (2025):
```
Experiment Progress Manager
        ↓
  Progressive Agentic Tree Search
  ├── Branch A → Experiment → Evaluate
  ├── Branch B → Experiment → Evaluate  ← 가지치기
  └── Branch C → Experiment → Evaluate
        ↓ (최선 브랜치)
  Replications (통계적 검증)
        ↓
  VLM Feedback Loop (시각화 품질 개선)
        ↓
  Paper Writing → Reviewer
```

- ICLR 워크샵에 3편 제출, 1편 수락
- 인간 작성 템플릿 코드 의존성 제거

**autoresearch와의 차이**:
| 항목 | AI Scientist | autoresearch |
|------|-------------|-------------|
| 목표 | 논문 작성 | val_bpb 최소화 |
| 에이전트 구조 | 멀티에이전트 파이프라인 | 단일 에이전트 |
| 복잡도 | 높음 | 최소 (630줄) |
| 비용 | ~$15/논문 | GPU 비용만 |
| 검증 | 피어 리뷰 LLM | 단일 메트릭 |

### 5.3 STOP (Self-Taught Optimizer)

autoresearch는 **STOP 패턴의 실용적 구현**이다:
- STOP: LM이 자신의 스캐폴딩 프로그램을 재귀적으로 개선
- autoresearch: 에이전트가 train.py(스캐폴드)를 반복 개선

```
STOP의 자기 개선 루프:
  스캐폴드 프로그램 → LM 여러 번 호출 → 최선 결과 반환 → 스캐폴드 개선 → 반복

autoresearch:
  train.py → 5분 학습 → val_bpb → train.py 개선 → 반복
```

---

## 6. autoresearch 최적화 설계

### 6.1 현재 ralph.sh → Agent SDK 업그레이드 아키텍처

```
현재:
ralph.sh
└── while true
    └── claude -p "program.md 내용" --allowedTools "Bash,Read,Write,Edit"
        └── 단일 에이전트가 모든 역할 수행

업그레이드 후:
autoresearch_sdk.py
└── for i in range(MAX_ITERATIONS)
    ├── Planner Agent (haiku): 전략 수립, 아이디어 선택
    ├── Executor Agent (sonnet): train.py 수정, 실행
    └── Reflector Agent (haiku/sonnet): 결과 분석, 메모리 업데이트, git 처리
```

### 6.2 완전 구현 코드 (Python, Claude Agent SDK)

```python
#!/usr/bin/env python3
"""
autoresearch_sdk.py — Claude Agent SDK 기반 autoresearch 루프
사용법: python autoresearch_sdk.py --tag mar17 --iterations 100
"""

import asyncio
import argparse
import json
import re
import subprocess
from pathlib import Path
from datetime import datetime
from claude_agent_sdk import query, ClaudeAgentOptions, AgentDefinition

# ── 레포 경로 ──────────────────────────────────────────────────────
REPO_DIR = Path(__file__).parent
RESULTS_TSV = REPO_DIR / "results.tsv"
MEMORY_DIR = REPO_DIR / "memory"
RUN_LOG = REPO_DIR / "run.log"

# ── 서브에이전트 정의 ──────────────────────────────────────────────

PLANNER = AgentDefinition(
    description="실험 전략 수립 전문가. 다음 실험 아이디어를 선택할 때 사용.",
    prompt="""당신은 ML 실험 플래너입니다.

목표: val_bpb를 최소화하는 다음 실험을 설계하라.

제약:
- train.py만 수정 가능 (prepare.py, results.tsv 수정 금지)
- 새 패키지 설치 불가
- Simplicity criterion: 소폭 개선 + 코드 복잡도 증가는 가치 없음

입력을 읽는 순서:
1. memory/SUMMARY.md (탐색 공간 지도)
2. memory/FAILED.md (HARD/SOFT 블록)

출력은 반드시 JSON:
{"hypothesis": "...", "change": "...", "rationale": "...", "risk": "..."}

HARD BLOCK에 있는 방향은 절대 선택하지 마라.
""",
    tools=["Read"],
    model="claude-haiku-4-5-20251001",
)

EXECUTOR = AgentDefinition(
    description="GPU 훈련 실행 전문가. train.py를 수정하고 실행할 때 사용.",
    prompt="""당신은 ML 훈련 실행자입니다.

절차:
1. train.py 읽기
2. 플래너 계획 적용 (최소 변경)
3. git commit -am "설명"
4. uv run train.py > run.log 2>&1 (최대 10분, 초과 시 kill)
5. grep "^val_bpb:\\|^peak_vram_mb:" run.log
6. 빈 출력이면 crash: tail -n 50 run.log

출력 JSON:
{"commit_hash": "a1b2c3d", "val_bpb": 0.9712, "peak_vram_mb": 45060,
 "status": "success|crash|timeout", "error": null}
""",
    tools=["Bash", "Read", "Write", "Edit"],
    model="claude-sonnet-4-6",
)

REFLECTOR = AgentDefinition(
    description="결과 분석 전문가. 실험 결과를 평가하고 메모리/git을 업데이트할 때 사용.",
    prompt="""당신은 ML 실험 반성자입니다.

판단 기준:
- keep: val_bpb가 현재 최고보다 낮음 (개선)
- discard: 개선 없거나 악화
- crash: 코드 실패, OOM, timeout

⚠️ 순서 엄수: 메모리 업데이트 → git 처리 (역순 금지)

절차:
1. memory/SUMMARY.md에서 현재 최고 val_bpb 읽기
2. 판단 결정
3. 메모리 업데이트 먼저:
   - crash → FAILED.md HARD BLOCK 추가 + SUMMARY.md 시도된 방향 추가
   - discard → FAILED.md SOFT BLOCK 추가 (조건 명시) + SUMMARY.md 업데이트
   - keep → SUMMARY.md 최고 val_bpb 갱신 + 시도된 방향 추가
4. git 처리:
   - keep: 그대로
   - discard/crash: git reset --hard HEAD~1
5. results.tsv에 한 줄 추가 (git add/commit 금지)

출력 JSON:
{"decision": "keep|discard|crash", "reason": "..."}
""",
    tools=["Read", "Write", "Edit", "Bash"],
    model="claude-haiku-4-5-20251001",
)

# ── 메모리 초기화 ────────────────────────────────────────────────

def init_memory():
    """memory/ 디렉토리와 초기 파일 생성"""
    MEMORY_DIR.mkdir(exist_ok=True)

    summary = MEMORY_DIR / "SUMMARY.md"
    if not summary.exists():
        summary.write_text("""# 탐색 공간 지도
## 시도된 방향
(실험 후 채워질 예정)

## 미탐색 방향
- GQA (Grouped Query Attention)
- Muon β2 파라미터 조정
- Dynamic batch size
- Cosine LR 스케줄링 주기 변경
- RMSNorm (LayerNorm 대체)
- ALiBi positional encoding

## 현재 최고 val_bpb: (베이스라인 후 기록)
## 베이스라인: (첫 실험 후 기록)
""")

    failed = MEMORY_DIR / "FAILED.md"
    if not failed.exists():
        failed.write_text("""# 실패 방향

## [HARD BLOCK] — 하드웨어/구조적 한계, 재시도 금지
(OOM, timeout 등 물리적 한계)

## [SOFT BLOCK] — 조건부 재시도 가능
(항목마다 반드시 [조건: ...] 태그 포함)
""")

    insights = MEMORY_DIR / "INSIGHTS.md"
    if not insights.exists():
        insights.write_text("# 검증된 발견 (여러 실험에서 재현됨)\n\n")


# ── 메인 루프 ────────────────────────────────────────────────────

async def run_autoresearch(tag: str, max_iterations: int):
    """Agent SDK 기반 autoresearch 루프"""

    print(f"autoresearch_sdk 시작: tag={tag}, max_iterations={max_iterations}")
    init_memory()

    # results.tsv 초기화
    if not RESULTS_TSV.exists():
        RESULTS_TSV.write_text("commit\tval_bpb\tmemory_gb\tstatus\tdescription\n")
        print("results.tsv 초기화 완료")

    for iteration in range(1, max_iterations + 1):
        start = datetime.now()
        print(f"\n{'='*60}")
        print(f"[{start.strftime('%H:%M:%S')}] === Iteration #{iteration} 시작 ===")

        try:
            # ── Phase 1: Planner ──────────────────────────────────
            print("[ Planner ] 실험 전략 수립 중...")
            plan = ""

            async for msg in query(
                prompt=f"""
Iteration {iteration}: memory/SUMMARY.md와 memory/FAILED.md를 읽고
다음 실험 전략을 JSON으로 출력하라.
results.tsv가 헤더만 있으면 (첫 실험) baseline 실행을 위해:
{{"hypothesis": "baseline", "change": "train.py 수정 없음", "rationale": "베이스라인 확립", "risk": "없음"}}
을 출력하라.
""",
                options=ClaudeAgentOptions(
                    allowed_tools=["Read", "Agent"],
                    agents={"planner": PLANNER},
                    permission_mode="acceptEdits",
                ),
            ):
                if hasattr(msg, "result"):
                    plan = msg.result

            print(f"  Plan: {plan[:150]}...")

            # ── Phase 2: Executor ─────────────────────────────────
            print("[ Executor ] train.py 수정 + 학습 실행 중...")
            exec_result = ""

            async for msg in query(
                prompt=f"""
다음 계획을 실행하라:
{plan}

train.py를 수정하고 실행하라. 결과를 JSON으로 출력하라.
""",
                options=ClaudeAgentOptions(
                    allowed_tools=["Bash", "Read", "Write", "Edit", "Agent"],
                    agents={"executor": EXECUTOR},
                    permission_mode="acceptEdits",
                ),
            ):
                if hasattr(msg, "result"):
                    exec_result = msg.result

            print(f"  Exec: {exec_result[:150]}...")

            # ── Phase 3: Reflector ────────────────────────────────
            print("[ Reflector ] 결과 분석 + 메모리 업데이트 중...")

            async for msg in query(
                prompt=f"""
Iteration {iteration} 실행 결과:
{exec_result}

결과를 평가하고, memory/를 업데이트하고, git을 처리하고, results.tsv에 기록하라.
""",
                options=ClaudeAgentOptions(
                    allowed_tools=["Read", "Write", "Edit", "Bash", "Agent"],
                    agents={"reflector": REFLECTOR},
                    permission_mode="acceptEdits",
                ),
            ):
                if hasattr(msg, "result"):
                    print(f"  Reflect: {msg.result[:150]}...")

        except Exception as e:
            print(f"  [ERROR] Iteration #{iteration} 실패: {e}")
            print("  30초 대기 후 재시도...")
            await asyncio.sleep(30)
            continue

        elapsed = (datetime.now() - start).total_seconds()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Iteration #{iteration} 완료 ({elapsed:.0f}초)")
        await asyncio.sleep(5)  # 다음 이터레이션 전 짧은 대기


# ── 진입점 ──────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agent SDK 기반 autoresearch")
    parser.add_argument("--tag", default=datetime.now().strftime("%b%-d").lower(),
                        help="실험 태그 (기본: 오늘 날짜)")
    parser.add_argument("--iterations", type=int, default=100,
                        help="최대 이터레이션 수 (기본: 100)")
    args = parser.parse_args()

    asyncio.run(run_autoresearch(tag=args.tag, max_iterations=args.iterations))
```

### 6.3 claude -p 방식과의 비교

```
방식 비교:

claude -p (현재 ralph.sh):
  while true:
    claude -p "$(cat program.md)" → 단일 에이전트 → 결과
    sleep 5

Agent SDK (업그레이드):
  for i in range(100):
    Plan  = await query(planner_agent)   # haiku (저비용)
    Exec  = await query(executor_agent)  # sonnet (실행력)
    Refl  = await query(reflector_agent) # haiku (분석)
    sleep 5
```

**주요 이점**:

| 항목 | claude -p | Agent SDK |
|------|-----------|-----------|
| 역할 분리 | 단일 에이전트가 모든 역할 | 전문 에이전트별 최적 프롬프트 |
| 비용 최적화 | 모든 작업에 동일 모델 | 작업별 haiku/sonnet/opus 선택 |
| 루프 제어 | shell while 루프 | Python 완전 제어 (에러 핸들링 포함) |
| 병렬화 | 어려움 | `asyncio.gather`로 즉시 가능 |
| 훅/플러그인 | 불가 | Python 콜백으로 완전 지원 |
| 장기기억 통합 | 에이전트가 수동 관리 | Reflector가 체계적 업데이트 |

### 6.4 LangGraph 대안 아키텍처

Claude API를 직접 사용하면서 LangGraph로 에이전트 흐름을 제어하는 방법:

```python
from langgraph.graph import StateGraph, END
from langchain_anthropic import ChatAnthropic
from typing import TypedDict

# 상태 정의
class AutoResearchState(TypedDict):
    plan: str
    exec_result: dict
    iteration: int
    should_stop: bool

# 각 노드는 ChatAnthropic을 직접 호출
llm_planner = ChatAnthropic(model="claude-haiku-4-5-20251001")
llm_executor = ChatAnthropic(model="claude-sonnet-4-6")
llm_reflector = ChatAnthropic(model="claude-haiku-4-5-20251001")

def planner_node(state: AutoResearchState) -> AutoResearchState:
    # 파일 I/O는 Python으로 직접
    summary = Path("memory/SUMMARY.md").read_text()
    failed = Path("memory/FAILED.md").read_text()
    plan = llm_planner.invoke(f"Plan next experiment:\n{summary}\n{failed}")
    return {**state, "plan": plan.content}

def executor_node(state: AutoResearchState) -> AutoResearchState:
    # train.py 수정은 LLM이 직접, bash 실행은 subprocess
    import subprocess
    result = subprocess.run(
        ["uv", "run", "train.py"],
        capture_output=True, text=True, timeout=600
    )
    val_bpb = re.search(r"val_bpb:\s+(\S+)", result.stdout)
    return {**state, "exec_result": {
        "stdout": result.stdout,
        "val_bpb": float(val_bpb.group(1)) if val_bpb else 0
    }}

def reflector_node(state: AutoResearchState) -> AutoResearchState:
    reflection = llm_reflector.invoke(
        f"Analyze: {state['exec_result']}, iteration: {state['iteration']}"
    )
    return {**state, "iteration": state["iteration"] + 1}

def should_continue(state: AutoResearchState) -> str:
    return "end" if state["should_stop"] or state["iteration"] >= 100 else "plan"

# 그래프 조립
builder = StateGraph(AutoResearchState)
builder.add_node("plan", planner_node)
builder.add_node("execute", executor_node)
builder.add_node("reflect", reflector_node)
builder.set_entry_point("plan")
builder.add_edge("plan", "execute")
builder.add_edge("execute", "reflect")
builder.add_conditional_edges("reflect", should_continue,
    {"plan": "plan", "end": END})

app = builder.compile()
result = app.invoke({"plan": "", "exec_result": {}, "iteration": 0, "should_stop": False})
```

### 6.5 세 가지 구현 방식 최종 비교

| 방식 | 복잡도 | 기능 | 비용 | 권장 케이스 |
|------|--------|------|------|------------|
| **claude -p ralph.sh** | 최소 | 기본 | 낮음 | 빠른 프로토타입, 하룻밤 실험 |
| **Claude Agent SDK** | 중간 | 최대 | 중간 | 전문 에이전트 역할 분리, 장기 실험 |
| **LangGraph + Anthropic API** | 중간 | 높음 | 낮음 | 모델 전환 필요 시, 커스텀 제어 |

---

## 7. 최종 권장 요약

### 핵심 답변

**Q: claude -p에서 oh-my-claude /ralph, /ralplan이 작동하는가?**
→ **작동하지 않는다**. 스킬은 인터랙티브 모드 전용. claude -p는 one-shot 단발성 실행이다.

**Q: claude -p의 한계를 어떻게 극복하는가?**
→ **Claude Agent SDK**로 업그레이드하면 Python 코드에서 서브에이전트를 직접 생성/제어할 수 있다.

### 즉시 시작하기

```bash
# 1. 설치
pip install claude-agent-sdk

# 2. autoresearch_sdk.py 위치: autoresearch/ 디렉토리에 저장

# 3. 실행
python autoresearch_sdk.py --tag mar17 --iterations 100

# 4. 백그라운드 실행 (tmux)
tmux new -s research
python autoresearch_sdk.py --tag mar17 --iterations 100
# Ctrl+B, D로 분리
```

### 권장 아키텍처 선택

```
목표: 빠른 밤새 실험 → 기존 ralph.sh 유지 (충분함)
목표: 전문 에이전트 역할 분리 → Claude Agent SDK
목표: 모델 독립, 최소 오버헤드 → LangGraph + API 직접 호출
목표: 논문 자동 작성까지 → AI Scientist 포크
```

---

## 참고 자료

### Claude Agent SDK
- [Agent SDK 개요](https://platform.claude.com/docs/en/agent-sdk/overview)
- [서브에이전트 가이드](https://platform.claude.com/docs/en/agent-sdk/subagents)
- [훅 가이드](https://platform.claude.com/docs/en/agent-sdk/hooks)
- [GitHub - claude-agent-sdk-python](https://github.com/anthropics/claude-agent-sdk-python)
- [GitHub - claude-agent-sdk-demos](https://github.com/anthropics/claude-agent-sdk-demos)

### claude -p
- [Headless/Programmatic 모드](https://code.claude.com/docs/en/headless)
- [CLI Reference](https://code.claude.com/docs/en/cli-reference)
- [Skills 문서](https://code.claude.com/docs/en/skills)

### 멀티에이전트 프레임워크
- [LangGraph 공식 사이트](https://langchain-ai.github.io/langgraph/)
- [CrewAI GitHub](https://github.com/crewAIInc/crewAI)
- [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/)
- [smolagents (HuggingFace)](https://github.com/huggingface/smolagents)

### 선행 자율 연구 시스템
- [AI Scientist (Sakana AI)](https://sakana.ai/ai-scientist/) — [GitHub](https://github.com/SakanaAI/AI-Scientist)
- [AI Scientist v2 arXiv:2504.08066](https://arxiv.org/abs/2504.08066) — [GitHub](https://github.com/SakanaAI/AI-Scientist-v2)
- [autoresearch (Karpathy)](https://github.com/karpathy/autoresearch)
- [STOP arXiv:2310.02304](https://arxiv.org/abs/2310.02304) — Microsoft
- [ReAct arXiv:2210.03629](https://arxiv.org/abs/2210.03629) — Google/Princeton
- [CAMEL arXiv:2303.17760](https://arxiv.org/abs/2303.17760) — NeurIPS 2023
- [Plan-and-Execute (LangChain)](https://blog.langchain.com/planning-agents/)
- [Reflection Agents (LangChain)](https://blog.langchain.com/reflection-agents/)
- [AgentRxiv](https://agentrxiv.github.io/)
