# 개발 단계 상태머신: Claude Code Hook 기반 결정론적 개발 워크플로우 설계

> 작성일: 2026-03-03
> 대상: Claude Code + OMC(OhMyClaudeCode) 기반 프로젝트
> 목적: TDD 및 양방향 추적성(Bidirectional Traceability)을 보장하는 결정론적 개발 단계 관리 시스템 설계

---

## 목차

1. [서론](#1-서론)
2. [상태 파일 설계](#2-상태-파일-설계)
3. [단계 전환 게이트](#3-단계-전환-게이트)
4. [E2E 버그 처리 방법론](#4-e2e-버그-처리-방법론)
5. [훅 구현 가이드](#5-훅-구현-가이드)
6. [OMC 상태와 충돌 없는 설계](#6-omc-상태와-충돌-없는-설계)
7. [완전한 설정](#7-완전한-설정-claudesettingsjson)
8. [결론 및 구현 우선순위](#8-결론-및-구현-우선순위)

---

## 1. 서론

### 1.1 왜 별도의 `dev-phase-state.json`이 필요한가?

Claude Code와 OMC(OhMyClaudeCode)를 함께 사용하는 환경에서는 두 가지 종류의 상태 관리가 동시에 필요하다.

**OMC 상태** (`.omc/state/`):
- ralph, ultrawork, ralplan 등 OMC 에이전트의 실행 상태
- 태스크 목록, 현재 실행 중인 에이전트, 세션 메타데이터
- "어떤 에이전트가 어떤 태스크를 실행하고 있는가?"를 추적

**개발 단계 상태** (`.claude/dev-phase-state.json`):
- 소프트웨어 개발 방법론 단계 (IDLE → SPEC → TESTCASE → CODING → TEST → DONE)
- 요구사항, 테스트케이스, 코드 아티팩트 간의 추적성 매트릭스
- "우리가 개발 방법론의 어느 단계에 있는가?"를 추적

이 두 상태를 분리하는 핵심 이유는 다음과 같다:

1. **생명주기가 다르다**: OMC 상태는 ralph 세션이 시작되고 끝날 때마다 초기화될 수 있지만, 개발 단계 상태는 여러 ralph 세션을 걸쳐 지속되어야 한다. 예를 들어, CODING 단계 도중 ralph가 취소되더라도 우리는 여전히 CODING 단계에 머물러야 한다.

2. **책임이 다르다**: OMC는 "에이전트 오케스트레이션"을 담당하고, 개발 단계 상태는 "개발 방법론 준수 강제"를 담당한다. 이 둘을 혼합하면 각각의 관심사가 흐려진다.

3. **결합도를 낮출 수 있다**: 개발 단계 게이트 시스템은 OMC 없이도 독립적으로 작동해야 한다. 사용자가 직접 Claude Code와 대화하는 경우에도 동일한 단계 제약이 적용되어야 한다.

4. **취소 안전성**: `/oh-my-claudecode:cancel` 명령은 `.omc/state/` 파일만 정리한다. `.claude/dev-phase-state.json`은 ralph 취소 후에도 보존되어 개발 단계의 연속성을 보장한다.

### 1.2 개발 단계 개요

본 시스템은 다음 6가지 개발 단계를 정의한다:

| 단계 | 설명 | 주요 산출물 |
|------|------|------------|
| `IDLE` | 초기 상태, 새 개발 사이클 대기 중 | 없음 |
| `SPEC` | 요구사항 명세 작성 단계 | `docs/spec.md`, REQ-XXX 요구사항 목록 |
| `TESTCASE` | 테스트케이스 설계 단계 | `tests/TC-XXX_*.py`, 추적성 매트릭스 |
| `CODING` | 구현 코드 작성 단계 | `src/` 하위 구현 파일, REQ-XXX 주석 |
| `TEST` | 테스트 실행 및 검증 단계 | 테스트 결과 보고서, 커버리지 리포트 |
| `DONE` | 완료 상태 | 최종 추적성 매트릭스 |

각 단계 전환은 반드시 게이트(Gate) 검사를 통과해야 한다. 게이트는 결정론적(파일 존재 여부, grep 검사 등) 검사와 LLM 컨텍스트 주입(프롬프트 가이드)의 두 종류로 구성된다.

### 1.3 핵심 설계 원칙

**원칙 1: OMC는 "어떻게 실행하는가"를 관리하고, 개발 단계는 "어느 방법론 단계인가"를 관리한다.**

OMC의 ralph는 태스크를 분해하고 서브에이전트에 위임하는 오케스트레이션 계층이다. 개발 단계 상태머신은 그 위에서 동작하는 방법론 계층이다. 두 계층은 서로의 내부를 수정하지 않고, 읽기만 허용하는 방향으로 협력한다.

**원칙 2: 게이트는 결정론적이어야 한다.**

LLM은 비결정론적이다. 따라서 단계 전환 게이트의 핵심 검사는 파일 시스템, grep, 테스트 실행과 같은 결정론적 수단으로 구현해야 한다. LLM은 컨텍스트 주입을 통해 "올바른 방향"을 안내하는 역할만 한다.

**원칙 3: TDD(테스트 주도 개발)를 강제한다.**

구현 코드(CODING)는 반드시 테스트케이스(TESTCASE) 이후에 작성된다. E2E 버그가 발견되면 코드 직접 수정이 아니라 누락된 테스트케이스 작성으로 사이클이 재진입한다.

**원칙 4: 양방향 추적성을 자동화한다.**

모든 코드 아티팩트는 REQ-XXX(요구사항 ID)와 TC-XXX(테스트케이스 ID)를 포함해야 한다. 훅 시스템이 이를 자동으로 추적하여 `traceability` 섹션을 최신 상태로 유지한다.

---

## 2. 상태 파일 설계

### 2.1 파일 위치 및 접근 규칙

- **위치**: `.claude/dev-phase-state.json`
- **소유자**: 개발 단계 훅 시스템
- **읽기**: 모든 훅, OMC stop-gate에서 읽기 허용
- **쓰기**: `dev-phase-transition-gate.sh`, `dev-phase-artifact-tracker.sh`만 쓰기 허용
- **동시성**: `flock`을 이용한 파일 잠금으로 병렬 서브에이전트 충돌 방지

### 2.2 전체 JSON 스키마

다음은 CODING 단계 진행 중인 상태의 완전한 예시이다:

```json
{
  "phase": "CODING",
  "cycle": {
    "number": 1,
    "type": "development",
    "started_at": "2026-03-03T09:00:00Z",
    "regression_trigger": null
  },
  "requirements": [
    { "id": "REQ-001", "title": "사용자 로그인", "file": "docs/spec.md", "status": "approved" },
    { "id": "REQ-002", "title": "비밀번호 재설정", "file": "docs/spec.md", "status": "approved" }
  ],
  "test_cases": [
    { "id": "TC-001", "req_id": "REQ-001", "file": "tests/test_login.py", "status": "written" },
    { "id": "TC-002", "req_id": "REQ-002", "file": "tests/test_reset.py", "status": "written" }
  ],
  "code_artifacts": [
    { "file": "src/auth/login.py", "req_ids": ["REQ-001"], "tc_ids": ["TC-001"], "status": "implemented" }
  ],
  "test_results": [],
  "traceability": {
    "req_to_tc": { "REQ-001": ["TC-001"], "REQ-002": ["TC-002"] },
    "tc_to_code": { "TC-001": ["src/auth/login.py"] },
    "code_to_test": { "src/auth/login.py": ["TC-001"] },
    "coverage_pct": 50.0,
    "uncovered_reqs": ["REQ-002"]
  },
  "gates_passed": ["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9"],
  "history": [
    { "from": "IDLE", "to": "SPEC", "at": "2026-03-03T09:00:00Z", "triggered_by": "user_prompt" },
    { "from": "SPEC", "to": "TESTCASE", "at": "2026-03-03T10:00:00Z", "gates_checked": ["G1","G2","G3","G4"] },
    { "from": "TESTCASE", "to": "CODING", "at": "2026-03-03T11:00:00Z", "gates_checked": ["G5","G6","G7","G8","G9"] }
  ]
}
```

### 2.3 각 필드 설명

**`phase`** (string): 현재 개발 단계. `IDLE | SPEC | TESTCASE | CODING | TEST | DONE` 중 하나.

**`cycle`** (object): 현재 개발 사이클 메타데이터.
- `number`: 사이클 번호 (1부터 시작, 회귀 시 증가)
- `type`: 사이클 유형. `development | regression | hotfix | spec-regression` 중 하나.
- `started_at`: ISO 8601 UTC 타임스탬프
- `regression_trigger`: 회귀 사이클인 경우 원인 정보, 아니면 `null`

**`requirements`** (array): SPEC 단계에서 추출된 요구사항 목록.
- `id`: REQ-XXX 형식의 고유 식별자
- `title`: 요구사항 제목
- `file`: 스펙 파일 경로
- `status`: `draft | approved | deprecated` 중 하나

**`test_cases`** (array): TESTCASE 단계에서 작성된 테스트케이스 목록.
- `id`: TC-XXX 형식의 고유 식별자
- `req_id`: 연결된 REQ-XXX ID
- `file`: 테스트 파일 경로
- `status`: `written | passing | failing | skipped` 중 하나

**`code_artifacts`** (array): CODING 단계에서 작성된 구현 파일 목록.
- `file`: 구현 파일 경로
- `req_ids`: 이 파일이 구현하는 요구사항 ID 목록
- `tc_ids`: 이 파일을 검증하는 테스트케이스 ID 목록
- `status`: `implemented | tested | refactored` 중 하나

**`test_results`** (array): TEST 단계에서 실행된 테스트 결과 목록.

**`traceability`** (object): 양방향 추적성 매트릭스.
- `req_to_tc`: 요구사항 → 테스트케이스 매핑
- `tc_to_code`: 테스트케이스 → 코드 파일 매핑
- `code_to_test`: 코드 파일 → 테스트케이스 매핑 (역방향)
- `coverage_pct`: 전체 요구사항 커버리지 퍼센트
- `uncovered_reqs`: 테스트케이스가 없는 요구사항 ID 목록

**`gates_passed`** (array): 현재까지 통과한 게이트 ID 목록.

**`history`** (array): 단계 전환 이력 (감사 추적용).

### 2.4 초기 상태 (IDLE)

새 프로젝트의 초기 상태:

```json
{
  "phase": "IDLE",
  "cycle": {
    "number": 0,
    "type": null,
    "started_at": null,
    "regression_trigger": null
  },
  "requirements": [],
  "test_cases": [],
  "code_artifacts": [],
  "test_results": [],
  "traceability": {
    "req_to_tc": {},
    "tc_to_code": {},
    "code_to_test": {},
    "coverage_pct": 0.0,
    "uncovered_reqs": []
  },
  "gates_passed": [],
  "history": []
}
```

---

## 3. 단계 전환 게이트

### 3.1 상태머신 다이어그램

```
IDLE ──→ SPEC ──(G1-G4)──→ TESTCASE ──(G5-G9)──→ CODING ──(G10-G15)──→ TEST ──(G16-G20)──→ DONE
                                                                                                │
                                                                               (E2E 버그 발견)  │
                                          TESTCASE ←──────────────────── REGRESSION ←──────────┘
```

IDLE 상태에서 SPEC으로의 전환은 사용자 프롬프트로 시작되며 게이트 없이 진행된다. 이후 각 단계 전환은 해당 단계의 게이트 그룹을 모두 통과해야 한다.

회귀(REGRESSION) 경로는 DONE 상태에서 버그 발견 시 TESTCASE(또는 SPEC, CODING)로 복귀하는 경로이다. 별도의 REGRESSION 단계 없이 `cycle.type` 필드로 구분한다.

### 3.2 게이트 매트릭스 (G1-G20)

#### G1-G4: SPEC → TESTCASE 전환 게이트

| 게이트 | 단계 전환 | 유형 | 검사 내용 | 훅 이벤트 | 구현 방법 |
|--------|----------|------|----------|----------|----------|
| G1 | SPEC→TESTCASE | 결정론적 | `docs/spec.md` 또는 `SPEC.md` 파일이 존재하는가? | PreToolUse:TaskUpdate | `test -f docs/spec.md \|\| test -f SPEC.md` |
| G2 | SPEC→TESTCASE | 결정론적 | 스펙 파일에 `REQ-[0-9]+` 형식의 ID가 포함되어 있는가? | PreToolUse:TaskUpdate | `grep -qE 'REQ-[0-9]+'` |
| G3 | SPEC→TESTCASE | 결정론적 | 각 요구사항에 인수 조건(Acceptance Criteria) 섹션이 있는가? | PreToolUse:TaskUpdate | `grep -c '###.*Acceptance\|승인 기준\|인수 조건'` |
| G4 | SPEC→TESTCASE | LLM | LLM 컨텍스트 주입: "spec 완성 확인" 프롬프트 제공 | SessionStart | `dev-phase-context-injector.sh` |

**G1 상세**: 스펙 파일의 존재 여부를 확인한다. `docs/spec.md`, `SPEC.md`, `docs/requirements.md` 등을 허용한다.

**G2 상세**: 스펙 파일 내에 `REQ-001`, `REQ-002` 형식의 요구사항 ID가 최소 1개 이상 존재해야 한다. ID가 없으면 TESTCASE 단계로 진입할 수 없다.

**G3 상세**: 각 요구사항 항목에 "### Acceptance Criteria", "인수 조건", 또는 "승인 기준" 섹션이 포함되어 있어야 한다. 인수 조건이 없는 요구사항은 테스트케이스 작성의 기준이 될 수 없다.

**G4 상세**: LLM에 현재 단계가 SPEC임을 주입하고, 다음 단계(TESTCASE)로 넘어가기 전 스펙이 완성되었는지 확인하도록 유도하는 프롬프트를 제공한다.

#### G5-G9: TESTCASE → CODING 전환 게이트

| 게이트 | 단계 전환 | 유형 | 검사 내용 | 훅 이벤트 | 구현 방법 |
|--------|----------|------|----------|----------|----------|
| G5 | TESTCASE→CODING | 결정론적 | `tests/` 디렉토리가 존재하고 테스트 파일이 있는가? | PreToolUse:TaskUpdate | `ls tests/*.py 2>/dev/null \|\| ls tests/*.test.js` |
| G6 | TESTCASE→CODING | 결정론적 | 각 REQ-XXX에 대응하는 TC-XXX가 있는가? | PreToolUse:TaskUpdate | 추적성 매트릭스 검사 |
| G7 | TESTCASE→CODING | 결정론적 | 테스트 파일에 실제 테스트 함수가 있는가? | PreToolUse:TaskUpdate | `grep -rE 'def test_\|it\(\|test\('` |
| G8 | TESTCASE→CODING | 결정론적 | `traceability_matrix.md`가 갱신되었는가? | PreToolUse:TaskUpdate | 파일 존재 및 최신성 확인 |
| G9 | TESTCASE→CODING | LLM | LLM 프롬프트 주입: "어느 REQ를 구현할지 명시" | SessionStart | `dev-phase-context-injector.sh` |

**G5 상세**: `tests/` 디렉토리가 존재하고, Python의 경우 `test_*.py` 또는 `*_test.py`, JavaScript의 경우 `*.test.js` 또는 `*.spec.js` 형식의 파일이 하나 이상 있어야 한다.

**G6 상세**: `dev-phase-state.json`의 `requirements` 배열과 `test_cases` 배열을 비교하여 커버되지 않은 요구사항이 없는지 확인한다. 미커버 요구사항이 있으면 게이트 실패.

**G7 상세**: 테스트 파일 내에 `def test_`, `it(`, `test(`, `describe(` 등 실제 테스트 함수가 존재해야 한다. 빈 파일이나 플레이스홀더만 있으면 게이트 실패.

**G8 상세**: `traceability_matrix.md` 또는 동등한 추적성 문서가 존재해야 한다. 이 파일에는 REQ↔TC 매핑이 표로 정리되어 있어야 한다.

**G9 상세**: CODING 단계로 넘어갈 때 LLM에 "어느 요구사항(REQ-XXX)을 구현할 것인지 명시하고, 각 구현 함수에 추적성 ID를 포함하라"는 컨텍스트를 주입한다.

#### G10-G15: CODING → TEST 전환 게이트

| 게이트 | 단계 전환 | 유형 | 검사 내용 | 훅 이벤트 | 구현 방법 |
|--------|----------|------|----------|----------|----------|
| G10 | CODING→TEST | 결정론적 | `src/` 디렉토리에 구현 파일이 존재하는가? | PreToolUse:TaskUpdate | `find src/ -name '*.py' -o -name '*.ts'` |
| G11 | CODING→TEST | 결정론적 | 구현 파일에 REQ-XXX 추적성 ID 주석이 있는가? | PreToolUse:Bash (commit gate) | `grep -rE 'REQ-[0-9]+'` |
| G12 | CODING→TEST | 결정론적 | 린트 검사를 통과하는가? | PreToolUse:Bash | `eslint src/ \|\| pylint src/` |
| G13 | CODING→TEST | 결정론적 | 단위 테스트가 모두 통과하는가? | PreToolUse:Bash | `npm test \|\| pytest` |
| G14 | CODING→TEST | 결정론적 | 각 TC-XXX가 구현 파일과 연결되어 있는가? | 추적성 검사 | `traceability.tc_to_code` 검사 |
| G15 | CODING→TEST | LLM | LLM 프롬프트 주입: "테스트 실행 후 결과 보고" | SessionStart | `dev-phase-context-injector.sh` |

**G10 상세**: `src/` 또는 프로젝트의 메인 소스 디렉토리에 구현 파일이 존재해야 한다. 파일 확장자는 프로젝트 언어에 따라 `.py`, `.ts`, `.js`, `.java` 등을 허용한다.

**G11 상세**: 모든 구현 파일에 `# REQ-001`, `// REQ-001` 형식의 추적성 주석이 있어야 한다. 커밋 게이트(`dev-phase-commit-gate.sh`)가 git commit 시점에 이를 강제한다.

**G12 상세**: 프로젝트의 린터 설정에 따라 ESLint, Pylint, Flake8 등을 실행하여 오류가 없어야 한다. 경고는 허용하되 오류(exit code 1 이상)는 게이트 실패.

**G13 상세**: `npm test`, `pytest`, `mvn test` 등 프로젝트의 테스트 실행 명령이 성공해야 한다. 테스트가 하나라도 실패하면 CODING 단계를 유지한다.

**G14 상세**: `dev-phase-state.json`의 `traceability.tc_to_code` 매핑을 검사하여 모든 TC-XXX가 하나 이상의 구현 파일과 연결되어 있어야 한다.

**G15 상세**: TEST 단계로 전환 시 LLM에 "전체 테스트를 실행하고 결과를 보고하라. 실패한 테스트가 있으면 원인을 분석하라"는 컨텍스트를 주입한다.

#### G16-G20: TEST → DONE 전환 게이트

| 게이트 | 단계 전환 | 유형 | 검사 내용 | 훅 이벤트 | 구현 방법 |
|--------|----------|------|----------|----------|----------|
| G16 | TEST→DONE | 결정론적 | 모든 단위 테스트가 통과하는가? | Stop 게이트 | `pytest --tb=no -q` 종료코드 확인 |
| G17 | TEST→DONE | 결정론적 | 코드 커버리지가 80% 이상인가? | Stop 게이트 | `pytest --cov \|\| nyc` 결과 파싱 |
| G18 | TEST→DONE | 결정론적 | `traceability_matrix.md`의 완전성 (REQ↔TC↔코드↔테스트 전체) | Stop 게이트 | 4방향 매핑 완전성 검사 |
| G19 | TEST→DONE | 결정론적 | 미커버 요구사항(`uncovered_reqs`)이 없는가? | Stop 게이트 | `traceability.uncovered_reqs` 배열 길이 검사 |
| G20 | TEST→DONE | LLM | LLM 프롬프트 주입: "최종 추적성 검토" | SessionStart | `dev-phase-context-injector.sh` |

**G16 상세**: 단위 테스트 전체가 통과해야 DONE 상태로 전환 가능하다. Stop 훅에서 검사하여 미통과 시 계속 작업을 강제한다.

**G17 상세**: 코드 커버리지 측정 도구(pytest-cov, nyc, JaCoCo 등)를 실행하여 전체 커버리지가 80% 이상이어야 한다. 이 임계값은 프로젝트에 따라 조정 가능하다.

**G18 상세**: 추적성 매트릭스의 4가지 방향(REQ→TC, TC→코드, 코드→테스트, 테스트→REQ)이 모두 완전히 연결되어 있어야 한다. 고아(orphan) 아티팩트가 없어야 한다.

**G19 상세**: `dev-phase-state.json`의 `traceability.uncovered_reqs` 배열이 비어 있어야 한다. 테스트케이스가 없는 요구사항이 하나라도 있으면 DONE 불가.

**G20 상세**: DONE 상태로 전환 전 LLM에 최종 추적성 검토를 수행하고, 모든 REQ-XXX가 TC-XXX와 구현 코드에 연결되어 있음을 확인하라는 컨텍스트를 주입한다.

---

## 4. E2E 버그 처리 방법론

### 4.1 시나리오

다음 상황을 가정한다:

1. 모든 단계가 완료되어 `phase: "DONE"` 상태
2. 담당자가 수동으로 E2E 테스트를 실행하여 버그를 발견
3. 담당자가 Claude에게 "E2E 테스트 실패: 세션 만료 후 로그인 페이지 리다이렉트 누락"이라고 보고
4. ralph(또는 Claude)가 버그 수정을 시작

### 4.2 버그 처리 결정 트리

```
버그 원인 분석
├── 요구사항이 불명확했다
│   └── SPEC으로 복귀 (cycle.type = "spec-regression")
├── 테스트케이스가 E2E 시나리오를 누락 [기본]
│   └── TESTCASE로 복귀 (cycle.type = "regression")
└── 단순 구현 버그 (요구사항 명확, TC 존재)
    └── CODING으로 복귀 (cycle.type = "hotfix")
```

**판단 기준**:

- `spec-regression`: 요구사항 문서에 해당 시나리오가 언급되지 않았거나, 모호하게 기술되어 있는 경우. 예: "세션 관리" 요구사항이 아예 없는 경우.

- `regression` (기본값): 요구사항은 존재하지만, 해당 E2E 시나리오에 대한 테스트케이스가 없는 경우. TDD 원칙상 이 경우가 대부분의 E2E 버그에 해당한다. 테스트가 없었기 때문에 버그가 검출되지 않은 것이다.

- `hotfix`: 요구사항도 존재하고, TC도 존재하며, TC도 현재 통과하고 있지만, 특정 엣지 케이스에서 구현이 잘못된 경우. 이 경우만 CODING 단계로 직접 복귀한다.

### 4.3 기본 접근: TDD 우선 (TESTCASE 재진입)

세션 만료 리다이렉트 버그의 경우, 대부분 "세션 만료 시 리다이렉트" 시나리오에 대한 테스트케이스가 없었기 때문에 발생한다. 따라서 기본 처리 흐름은 다음과 같다:

**7단계 워크플로우**:

**1단계**: 상태 전환 (DONE → TESTCASE)
```
새 사이클 시작: cycle.number = 2, cycle.type = "regression"
```

**2단계**: 새 TC-XXX 작성 (E2E 시나리오를 단위 테스트로)
```python
# TC-003: REQ-001 세션 만료 리다이렉트
# regression_trigger: E2E 테스트에서 발견된 세션 만료 처리 누락
def test_session_expired_redirect():
    """세션 만료 시 /login으로 리다이렉트되어야 한다."""
    client = create_test_client()
    client.set_session(expired=True)
    response = client.get("/dashboard")
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"
```

**3단계**: G5-G9 게이트 통과 확인
- G5: `tests/` 디렉토리에 새 파일 존재 ✓
- G6: REQ-001에 대한 TC-003 추가됨 ✓
- G7: 테스트 함수 `test_session_expired_redirect` 존재 ✓
- G8: `traceability_matrix.md` 갱신 ✓
- G9: LLM 컨텍스트 주입 ✓

→ CODING 단계로 전환

**4단계**: 버그 수정 (구현 코드 수정)
```python
# src/auth/session.py
# REQ-001: 사용자 인증 관리 (TC-001, TC-003)

def check_session_validity(request):
    """세션 유효성 검사. 만료 시 로그인 페이지로 리다이렉트."""
    if is_session_expired(request.session):
        return redirect("/login")  # 이 부분이 누락되어 있었음
    return None
```

**5단계**: TC-003 통과 확인
```bash
pytest tests/test_login.py::test_session_expired_redirect -v
# PASSED
```

**6단계**: G10-G20 게이트 통과 → DONE 상태로 전환

**7단계**: 추적성 매트릭스 갱신
```
traceability_matrix.md 업데이트:
REQ-001 ← TC-001 (기존), TC-003 (신규)
TC-003 ← src/auth/session.py (신규 연결)
```

### 4.4 TESTCASE 재진입을 선택하는 이유 (CODING 직접 재진입 대비)

CODING 단계로 직접 재진입하는 것이 더 빠르게 느껴질 수 있지만, TDD 관점에서 TESTCASE 재진입이 옳다:

1. **TDD 원칙**: "버그 = 누락된 테스트케이스". 테스트가 먼저 실패해야 구현의 방향이 생긴다. TC-003 없이 코드를 수정하면 나중에 같은 버그가 재발해도 검출이 안 된다.

2. **추적성 확보**: 새 TC-XXX를 먼저 작성함으로써 `REQ ← TC ← fix commit` 연결고리가 생긴다. CODING 직접 재진입 시 추적성이 끊어진다.

3. **별도 REGRESSION 단계 불필요**: `cycle.type` 필드가 `regression`임을 나타내기 때문에 상태머신에 별도의 REGRESSION 노드를 추가할 필요가 없다. 기존 TESTCASE→CODING→TEST→DONE 흐름을 재사용하면서 사이클 번호와 유형으로 구분한다.

4. **문서화 자동화**: 훅이 회귀 사이클의 트리거 정보를 자동으로 기록하므로, 나중에 "이 TC-003은 왜 추가되었는가?"에 대한 답이 상태 파일에 있다.

### 4.5 회귀 사이클 중 상태 JSON

```json
{
  "phase": "TESTCASE",
  "cycle": {
    "number": 2,
    "type": "regression",
    "started_at": "2026-03-03T15:00:00Z",
    "regression_trigger": {
      "source": "human_e2e",
      "description": "로그인 후 세션 만료 시 리다이렉트 누락",
      "reported_at": "2026-03-03T14:55:00Z"
    }
  }
}
```

---

## 5. 훅 구현 가이드

모든 훅 스크립트는 `.claude/hooks/` 디렉토리에 위치하며 실행 권한(`chmod +x`)이 필요하다.

### 5.1 훅 1: `dev-phase-context-injector.sh` (SessionStart)

세션 시작 시 현재 개발 단계를 LLM 컨텍스트에 주입하는 훅이다. G4, G9, G15, G20에 해당하는 LLM 가이드 역할을 한다.

```bash
#!/bin/bash
# 세션 시작 시 현재 개발 단계를 LLM 컨텍스트에 주입
STATE_FILE=".claude/dev-phase-state.json"
[ ! -f "$STATE_FILE" ] && exit 0

PHASE=$(jq -r '.phase // "IDLE"' "$STATE_FILE")
CYCLE_NUM=$(jq -r '.cycle.number // 1' "$STATE_FILE")
CYCLE_TYPE=$(jq -r '.cycle.type // "development"' "$STATE_FILE")
UNCOVERED=$(jq -r '.traceability.uncovered_reqs | join(", ")' "$STATE_FILE" 2>/dev/null || echo "없음")

case "$PHASE" in
  SPEC)     CONSTRAINT="스펙 문서(SPEC.md)만 작성할 수 있습니다. 테스트 코드나 구현 코드 작성 금지." ;;
  TESTCASE) CONSTRAINT="테스트케이스만 작성할 수 있습니다. 각 TC는 반드시 REQ-XXX ID를 참조해야 합니다." ;;
  CODING)   CONSTRAINT="구현 코드만 작성할 수 있습니다. 각 함수에 # REQ-XXX 추적성 ID를 포함하세요." ;;
  TEST)     CONSTRAINT="테스트 실행과 결과 분석만 허용됩니다. 구현 수정 금지." ;;
  DONE)     CONSTRAINT="모든 단계 완료. 새 기능은 /ralph로 새 사이클을 시작하세요." ;;
  *)        CONSTRAINT="개발 단계가 초기화되지 않았습니다." ;;
esac

CONTEXT="[개발 단계 게이트 시스템]
현재 단계: ${PHASE} (사이클 #${CYCLE_NUM}, 유형: ${CYCLE_TYPE})
제약사항: ${CONSTRAINT}
미커버 요구사항: ${UNCOVERED}
추적성: 모든 산출물에 REQ-XXX 및 TC-XXX ID를 포함하세요."

printf '%s' "$CONTEXT" | jq -Rs '{"additionalContext": .}'
```

**동작 원리**:
- `jq -Rs`는 다중 줄 문자열을 JSON 문자열로 변환한다.
- `{"additionalContext": ...}` 형식은 Claude Code SessionStart 훅이 LLM 컨텍스트에 추가하는 표준 형식이다.
- 파일이 없으면 (`exit 0`) 아무것도 출력하지 않고 정상 종료한다.

### 5.2 훅 2: `dev-phase-write-gate.sh` (PreToolUse on Write/Edit)

파일 쓰기 시 현재 단계에서 허용된 경로인지 검사하는 훅이다. G1, G5, G10 등의 결정론적 단계 제약을 물리적으로 강제한다.

```bash
#!/bin/bash
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // ""')
STATE_FILE=".claude/dev-phase-state.json"
PHASE=$(jq -r '.phase // "IDLE"' "$STATE_FILE" 2>/dev/null || echo "IDLE")

case "$PHASE" in
  SPEC)
    if ! echo "$FILE_PATH" | grep -qE '^(docs/spec|SPEC|docs/requirements)'; then
      printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"SPEC 단계: 스펙 파일만 작성 가능합니다. 요청 파일: %s"}}\n' "$FILE_PATH"
      exit 0
    fi ;;
  TESTCASE)
    if ! echo "$FILE_PATH" | grep -qE '^tests/'; then
      echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"TESTCASE 단계: tests/ 디렉토리만 작성 가능합니다."}}'
      exit 0
    fi ;;
  CODING)
    if echo "$FILE_PATH" | grep -qE '^tests/'; then
      echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"CODING 단계: 테스트 파일 수정 금지. 구현 코드만 작성하세요."}}'
      exit 0
    fi ;;
  TEST)
    if ! echo "$FILE_PATH" | grep -qE '\.(log|json|xml|html)$|test.result'; then
      echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"TEST 단계: 테스트 결과 파일만 작성 가능합니다."}}'
      exit 0
    fi ;;
esac
```

**주의사항**:
- IDLE과 DONE 상태는 제약 없이 통과시킨다 (case문에 없으므로 기본 통과).
- `permissionDecision: "deny"`는 Claude Code PreToolUse 훅의 표준 거부 형식이다.
- `permissionDecisionReason`은 LLM에게 왜 거부되었는지 설명하여 자기 수정을 유도한다.

### 5.3 훅 3: `dev-phase-commit-gate.sh` (PreToolUse on Bash)

`git commit` 명령 실행 시 추적성 ID 존재 여부와 테스트 통과 여부를 검사하는 훅이다. G11, G12, G13에 해당한다.

```bash
#!/bin/bash
INPUT=$(cat)
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // ""')

if echo "$CMD" | grep -qE 'git\s+commit'; then
  STATE_FILE=".claude/dev-phase-state.json"
  PHASE=$(jq -r '.phase // "IDLE"' "$STATE_FILE" 2>/dev/null)

  if [ "$PHASE" = "CODING" ]; then
    CHANGED=$(git diff --cached --name-only 2>/dev/null | grep -E '\.(py|ts|js|java)$')
    for file in $CHANGED; do
      if ! grep -qE 'REQ-[0-9]+' "$file" 2>/dev/null; then
        echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"추적성 ID 없음: ${file}에 # REQ-XXX 주석을 추가하세요.\"}}"
        exit 0
      fi
    done
  fi

  if ! (npm test --silent 2>/dev/null || python -m pytest -q 2>/dev/null); then
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"커밋 게이트: 테스트가 통과해야 커밋할 수 있습니다."}}'
    exit 0
  fi
fi
```

**동작 원리**:
1. Bash 도구의 명령이 `git commit`을 포함하는지 확인한다.
2. CODING 단계인 경우, 스테이징된 소스 파일에 `REQ-[0-9]+` 패턴이 있는지 검사한다.
3. 패턴이 없는 파일이 발견되면 해당 파일명과 함께 거부 메시지를 반환한다.
4. 추적성 검사 통과 후에도 테스트 실행 결과를 확인하여 실패 시 커밋을 거부한다.

**언어 감지**: `npm test`와 `pytest` 모두 시도하여 실패하면 거부한다. 하나라도 성공하면 통과.

### 5.4 훅 4: `dev-phase-transition-gate.sh` (PreToolUse on TaskUpdate/Bash)

단계 전환 요청을 감지하고 적절한 게이트 검사를 실행하는 핵심 훅이다. 상태머신의 심장부에 해당한다.

```bash
#!/bin/bash
# dev-phase-transition-gate.sh
# 단계 전환 요청 감지 및 게이트 검사 실행

INPUT=$(cat)
STATE_FILE=".claude/dev-phase-state.json"
PHASE=$(jq -r '.phase // "IDLE"' "$STATE_FILE" 2>/dev/null || echo "IDLE")

# 단계 전환 요청 감지 (bash 명령 또는 특정 패턴)
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // ""')
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // ""')

# 전환 요청 여부 확인 함수
detect_transition_request() {
  local from_phase="$1"
  case "$from_phase" in
    SPEC)
      echo "$CMD" | grep -qiE 'phase.*testcase|testcase.*phase|단계.*전환|전환.*testcase' && echo "TESTCASE"
      ;;
    TESTCASE)
      echo "$CMD" | grep -qiE 'phase.*coding|coding.*phase|단계.*전환|전환.*coding' && echo "CODING"
      ;;
    CODING)
      echo "$CMD" | grep -qiE 'phase.*test|test.*phase|단계.*전환|전환.*test' && echo "TEST"
      ;;
    TEST)
      echo "$CMD" | grep -qiE 'phase.*done|done.*phase|단계.*완료|완료.*done' && echo "DONE"
      ;;
  esac
}

# G1-G4 게이트 검사 (SPEC → TESTCASE)
run_spec_to_testcase_gates() {
  # G1: 스펙 파일 존재 확인
  if ! (test -f "docs/spec.md" || test -f "SPEC.md" || test -f "docs/requirements.md"); then
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"[G1 실패] 스펙 파일이 없습니다. docs/spec.md 또는 SPEC.md를 먼저 작성하세요."}}'
    return 1
  fi

  # G2: REQ-XXX ID 확인
  SPEC_FILE=""
  for f in "docs/spec.md" "SPEC.md" "docs/requirements.md"; do
    [ -f "$f" ] && SPEC_FILE="$f" && break
  done
  if ! grep -qE 'REQ-[0-9]+' "$SPEC_FILE" 2>/dev/null; then
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"[G2 실패] 스펙 파일에 REQ-XXX 형식의 요구사항 ID가 없습니다."}}'
    return 1
  fi

  # G3: 인수 조건 확인
  REQ_COUNT=$(grep -cE '^##+ REQ-[0-9]+' "$SPEC_FILE" 2>/dev/null || echo 0)
  AC_COUNT=$(grep -cE '인수 조건|Acceptance Criteria|승인 기준' "$SPEC_FILE" 2>/dev/null || echo 0)
  if [ "$AC_COUNT" -lt "$REQ_COUNT" ]; then
    echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"[G3 실패] 일부 요구사항에 인수 조건이 없습니다. 요구사항: ${REQ_COUNT}개, 인수 조건: ${AC_COUNT}개\"}}"
    return 1
  fi

  # 모든 게이트 통과 → 상태 전환
  transition_phase "SPEC" "TESTCASE" "G1,G2,G3,G4"
  return 0
}

# G5-G9 게이트 검사 (TESTCASE → CODING)
run_testcase_to_coding_gates() {
  # G5: tests/ 디렉토리 및 테스트 파일 확인
  if ! (ls tests/test_*.py 2>/dev/null || ls tests/*.test.js 2>/dev/null || ls tests/*.spec.ts 2>/dev/null) | grep -q .; then
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"[G5 실패] tests/ 디렉토리에 테스트 파일이 없습니다."}}'
    return 1
  fi

  # G6: REQ↔TC 추적성 확인
  UNCOVERED=$(jq -r '.traceability.uncovered_reqs | length' "$STATE_FILE" 2>/dev/null || echo 0)
  if [ "$UNCOVERED" -gt 0 ]; then
    UNCOVERED_LIST=$(jq -r '.traceability.uncovered_reqs | join(", ")' "$STATE_FILE")
    echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"[G6 실패] 다음 요구사항에 테스트케이스가 없습니다: ${UNCOVERED_LIST}\"}}"
    return 1
  fi

  # G7: 실제 테스트 함수 존재 확인
  if ! grep -rqE 'def test_|it\(|describe\(' tests/ 2>/dev/null; then
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"[G7 실패] 테스트 파일에 실제 테스트 함수가 없습니다. def test_ 또는 it() 함수를 작성하세요."}}'
    return 1
  fi

  # G8: traceability_matrix.md 존재 확인
  if ! test -f "traceability_matrix.md" && ! test -f "docs/traceability_matrix.md"; then
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"[G8 실패] traceability_matrix.md가 없습니다. REQ↔TC 매핑 표를 작성하세요."}}'
    return 1
  fi

  # 모든 게이트 통과 → 상태 전환
  transition_phase "TESTCASE" "CODING" "G5,G6,G7,G8,G9"
  return 0
}

# 상태 파일 업데이트 함수
transition_phase() {
  local from="$1"
  local to="$2"
  local gates="$3"
  local now
  now=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  exec 200>".claude/.dev-phase.lock"
  flock -x 200

  jq --arg from "$from" --arg to "$to" --arg at "$now" --arg gates "$gates" '
    .phase = $to |
    .gates_passed += ($gates | split(",")) |
    .history += [{"from": $from, "to": $to, "at": $at, "gates_checked": ($gates | split(","))}]
  ' "$STATE_FILE" > /tmp/dev-state.tmp && mv /tmp/dev-state.tmp "$STATE_FILE"

  flock -u 200
}

# 전환 요청 처리
TARGET=$(detect_transition_request "$PHASE")
if [ -n "$TARGET" ]; then
  case "${PHASE}_${TARGET}" in
    SPEC_TESTCASE)   run_spec_to_testcase_gates ;;
    TESTCASE_CODING) run_testcase_to_coding_gates ;;
    *)
      echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"현재 단계(${PHASE})에서 ${TARGET}로의 직접 전환은 지원되지 않습니다.\"}}"
      ;;
  esac
fi
```

**핵심 설계 포인트**:
- 전환 요청은 Bash 명령 또는 자연어 패턴으로 감지한다.
- 각 단계 전환별로 독립적인 게이트 검사 함수를 갖는다.
- 상태 파일 업데이트는 `flock`과 atomic rename으로 동시성을 보장한다.

### 5.5 훅 5: `dev-phase-stop-gate.sh` (Stop)

Claude Code 세션 종료 시 개발 단계가 완료되지 않았으면 계속 작업을 강제하는 훅이다. OMC와 통합된 종료 방지 로직을 포함한다.

```bash
#!/bin/bash
DEV_STATE=".claude/dev-phase-state.json"
OMC_STATE=".omc/state/ralph-state.json"

PHASE=$(jq -r '.phase // "IDLE"' "$DEV_STATE" 2>/dev/null || echo "IDLE")
OMC_ACTIVE=$(jq -r '.active // false' "$OMC_STATE" 2>/dev/null || echo "false")

# OMC 활성 시 OMC의 persistent-mode 훅이 처리하도록 위임
if [ "$OMC_ACTIVE" = "true" ]; then
  exit 0
fi

# 개발 단계가 중간이면 계속 작업 강제
if [ "$PHASE" != "DONE" ] && [ "$PHASE" != "IDLE" ]; then
  MSG="개발 단계(${PHASE})가 완료되지 않았습니다. 다음 단계 게이트를 통과하거나 /cancel로 중단하세요."
  printf '{"continue": true, "reason": "%s"}\n' "$MSG"
fi
```

**OMC 위임 로직**:
- OMC ralph가 활성 상태이면 OMC의 자체 Stop 훅이 세션 지속을 관리한다.
- 개발 단계 Stop 훅은 ralph 비활성 상태에서만 직접 개입한다.
- 두 시스템이 동시에 "continue"를 요청해도 Claude Code는 둘 다 존중한다.

### 5.6 훅 6: `dev-phase-artifact-tracker.sh` (PostToolUse on Write)

파일 작성 후 자동으로 추적성 매트릭스를 갱신하는 훅이다. 개발자가 수동으로 상태 파일을 업데이트하지 않아도 된다.

```bash
#!/bin/bash
INPUT=$(cat)
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // ""')
STATE_FILE=".claude/dev-phase-state.json"
[ ! -f "$STATE_FILE" ] && exit 0
[ ! -f "$FILE" ] && exit 0

exec 200>".claude/.dev-phase.lock"
flock -x 200

REQ_IDS=$(grep -oE 'REQ-[0-9]+' "$FILE" 2>/dev/null | sort -u | jq -R . | jq -s .)
TC_IDS=$(grep -oE 'TC-[0-9]+' "$FILE" 2>/dev/null | sort -u | jq -R . | jq -s .)
PHASE=$(jq -r '.phase' "$STATE_FILE")

if [ "$PHASE" = "CODING" ] && [ "$(echo "$REQ_IDS" | jq 'length')" -gt 0 ]; then
  jq --arg file "$FILE" --argjson reqs "$REQ_IDS" --argjson tcs "$TC_IDS" \
    '.code_artifacts += [{"file": $file, "req_ids": $reqs, "tc_ids": $tcs, "status": "implemented"}]' \
    "$STATE_FILE" > /tmp/dev-state.tmp && mv /tmp/dev-state.tmp "$STATE_FILE"
fi

flock -u 200
```

**자동 추적 원리**:
1. PostToolUse 이벤트에서 작성된 파일 경로를 받는다.
2. 파일 내용에서 `REQ-[0-9]+`와 `TC-[0-9]+` 패턴을 모두 추출한다.
3. CODING 단계이고 REQ ID가 있으면 `code_artifacts` 배열에 항목을 추가한다.
4. `flock`으로 동시 쓰기를 방지하고, atomic rename으로 파일 일관성을 보장한다.

**한계**: 파일이 여러 번 수정되면 `code_artifacts`에 중복 항목이 생길 수 있다. 이를 방지하려면 `jq`에 `del(.code_artifacts[] | select(.file == $file))` 후 다시 추가하는 upsert 로직을 사용한다.

### 5.7 훅 7: `dev-phase-subagent-injector.sh` (SubagentStart)

ultrawork 등 서브에이전트가 시작될 때 현재 개발 단계 제약을 주입하는 훅이다. 메인 에이전트와 서브에이전트가 동일한 단계 제약을 받도록 보장한다.

```bash
#!/bin/bash
STATE_FILE=".claude/dev-phase-state.json"
[ ! -f "$STATE_FILE" ] && exit 0
PHASE=$(jq -r '.phase // "IDLE"' "$STATE_FILE")
echo "{\"additionalContext\": \"[서브에이전트 제약] 현재 개발 단계: ${PHASE}. 이 단계의 산출물만 작성 가능. 모든 파일에 REQ-XXX 추적성 ID 포함 필수.\"}"
```

**필요성**: ultrawork는 독립적인 컨텍스트에서 실행되는 서브에이전트를 생성한다. 메인 세션의 `SessionStart` 컨텍스트가 서브에이전트에 자동으로 전달되지 않기 때문에 `SubagentStart` 훅으로 별도 주입이 필요하다.

---

## 6. OMC 상태와 충돌 없는 설계

### 6.1 소유권 분리 (Ownership Separation)

두 시스템은 완전히 분리된 디렉토리를 소유한다:

```
프로젝트 루트/
├── .omc/
│   └── state/
│       ├── ralph-state.json      ← OMC 전용 (ralph, ultrawork, ralplan)
│       ├── ultrawork-state.json
│       └── session.json
└── .claude/
    ├── dev-phase-state.json      ← 개발 단계 전용
    ├── .dev-phase.lock           ← 개발 단계 잠금 파일
    ├── hooks/                    ← 개발 단계 훅 스크립트
    └── settings.json             ← Claude Code 훅 설정
```

**규칙**:
- OMC 컴포넌트(ralph, ultrawork, ralplan)는 `.claude/dev-phase-state.json`을 절대 수정하지 않는다.
- 개발 단계 훅은 `.omc/state/`를 읽을 수 있지만 절대 수정하지 않는다.
- 각 시스템은 자신의 디렉토리에만 쓰기 권한을 갖는 것으로 간주한다.

### 6.2 읽기는 양방향 허용 (Cross-reads Allowed)

단방향 쓰기, 양방향 읽기 원칙:

```
                  ┌─────────────────────────────────────────┐
                  │            읽기 허용                     │
                  │                                         │
  OMC 상태         │   dev-phase-stop-gate.sh               │  개발 단계 상태
  .omc/state/  ──→│   OMC ralph 활성 여부 읽기             │──→ .claude/dev-phase-state.json
                  │                                         │
                  └─────────────────────────────────────────┘

  OMC 상태 쓰기: OMC 전용
  개발 단계 상태 쓰기: 개발 단계 훅 전용
```

구체적 예: `dev-phase-stop-gate.sh`가 `.omc/state/ralph-state.json`을 읽어 OMC가 활성 상태인지 확인하고, 활성 상태이면 자신의 stop 로직을 건너뛴다. 이렇게 두 시스템이 충돌 없이 협력한다.

### 6.3 동시 쓰기 안전 (Concurrent Write Safety)

ultrawork 등 병렬 서브에이전트가 동시에 `dev-phase-state.json`을 수정하려 할 때의 안전 장치:

**flock 기반 상호 배제**:
```bash
exec 200>".claude/.dev-phase.lock"
flock -x 200          # 배타적 잠금 획득 (블로킹)
# ... 상태 파일 수정 ...
flock -u 200          # 잠금 해제
```

**Atomic 갱신**:
```bash
jq '...' "$STATE_FILE" > /tmp/dev-state.tmp  # 임시 파일에 먼저 씀
mv /tmp/dev-state.tmp "$STATE_FILE"           # atomic rename으로 교체
```

`mv`(rename)는 같은 파일시스템 내에서 원자적(atomic) 연산이다. 따라서 다른 프로세스가 읽는 시점에 항상 완전한 JSON을 보게 된다. 불완전한 JSON이 노출되는 시간 창이 없다.

### 6.4 `/cancel` 명령 안전성

`/oh-my-claudecode:cancel` 명령의 동작:

```
/oh-my-claudecode:cancel 실행
  ↓
.omc/state/ralph-state.json 초기화   ← OMC 상태만 정리
.omc/state/session.json 정리         ← OMC 상태만 정리
  ↓
.claude/dev-phase-state.json         ← 영향 없음, 보존됨!
```

**의도적 설계**: 사용자가 ralph를 취소해도 개발 단계 상태는 보존된다. 예를 들어, CODING 단계에서 ralph가 취소되면 다음 ralph 세션이 시작될 때도 여전히 CODING 단계로 인식하여 CODING 단계 제약이 계속 적용된다.

이 동작이 원치 않는 경우(개발 단계도 리셋하고 싶은 경우)는 별도의 명령으로 `dev-phase-state.json`을 IDLE로 초기화해야 한다.

---

## 7. 완전한 설정 (`.claude/settings.json`)

다음은 모든 훅이 등록된 완전한 `settings.json`이다:

```json
{
  "hooks": {
    "SessionStart": [
      {"type": "command", "command": "./.claude/hooks/dev-phase-context-injector.sh"}
    ],
    "PreToolUse": [
      {"type": "command", "command": "./.claude/hooks/dev-phase-write-gate.sh",
       "matchers": [{"tool_name": "Write"}, {"tool_name": "Edit"}]},
      {"type": "command", "command": "./.claude/hooks/dev-phase-commit-gate.sh",
       "matchers": [{"tool_name": "Bash"}]},
      {"type": "command", "command": "./.claude/hooks/dev-phase-transition-gate.sh",
       "matchers": [{"tool_name": "TaskUpdate"}, {"tool_name": "Bash"}]}
    ],
    "PostToolUse": [
      {"type": "command", "command": "./.claude/hooks/dev-phase-artifact-tracker.sh",
       "matchers": [{"tool_name": "Write"}, {"tool_name": "Edit"}]}
    ],
    "SubagentStart": [
      {"type": "command", "command": "./.claude/hooks/dev-phase-subagent-injector.sh"}
    ],
    "Stop": [
      {"type": "command", "command": "./.claude/hooks/dev-phase-stop-gate.sh"}
    ]
  }
}
```

### 7.1 훅 이벤트 매핑 요약

| 훅 이벤트 | 스크립트 | 게이트 | 목적 |
|----------|---------|-------|------|
| `SessionStart` | `dev-phase-context-injector.sh` | G4, G9, G15, G20 | LLM 단계 인식 주입 |
| `PreToolUse (Write/Edit)` | `dev-phase-write-gate.sh` | G1, G5, G10 물리적 강제 | 단계별 파일 쓰기 제한 |
| `PreToolUse (Bash)` | `dev-phase-commit-gate.sh` | G11, G12, G13 | 커밋 시 추적성 및 테스트 검사 |
| `PreToolUse (TaskUpdate/Bash)` | `dev-phase-transition-gate.sh` | G1-G9 통합 | 단계 전환 게이트 엔진 |
| `PostToolUse (Write/Edit)` | `dev-phase-artifact-tracker.sh` | 자동화 | 추적성 매트릭스 자동 갱신 |
| `SubagentStart` | `dev-phase-subagent-injector.sh` | 서브에이전트 | 서브에이전트 단계 제약 |
| `Stop` | `dev-phase-stop-gate.sh` | G16-G19 | 완료 전 종료 방지 |

### 7.2 설치 체크리스트

```bash
# 1. 훅 디렉토리 생성
mkdir -p .claude/hooks

# 2. 모든 훅 스크립트 복사
cp hooks/*.sh .claude/hooks/

# 3. 실행 권한 부여
chmod +x .claude/hooks/*.sh

# 4. jq 설치 확인 (필수 의존성)
which jq || brew install jq || apt-get install -y jq

# 5. 초기 상태 파일 생성
cat > .claude/dev-phase-state.json << 'EOF'
{
  "phase": "IDLE",
  "cycle": {"number": 0, "type": null, "started_at": null, "regression_trigger": null},
  "requirements": [],
  "test_cases": [],
  "code_artifacts": [],
  "test_results": [],
  "traceability": {"req_to_tc": {}, "tc_to_code": {}, "code_to_test": {}, "coverage_pct": 0.0, "uncovered_reqs": []},
  "gates_passed": [],
  "history": []
}
EOF

# 6. settings.json 설정 (이미 존재하면 hooks 섹션 병합)
# .claude/settings.json에 위 훅 설정 추가
```

---

## 8. 결론 및 구현 우선순위

### 8.1 구현 우선순위 표

| 우선순위 | 훅 스크립트 | 구현 노력 | 영향도 | 비고 |
|---------|-----------|---------|-------|------|
| 1 | `dev-phase-transition-gate.sh` | 중 | 핵심 | 상태머신의 핵심 게이트 엔진. 이것 없이는 단계 전환 불가 |
| 2 | `dev-phase-context-injector.sh` | 낮 | 높음 | LLM이 현재 단계를 인식하게 하는 컨텍스트 주입 |
| 3 | `dev-phase-stop-gate.sh` | 낮 | 높음 | OMC와 통합된 종료 방지. 단계 완료 전 세션 종료를 막음 |
| 4 | `dev-phase-write-gate.sh` | 낮 | 높음 | 물리적으로 단계 위반 파일 쓰기를 방지 |
| 5 | `dev-phase-init-gate.sh` | 낮 | 중 | 첫 번째 사용 시 자동으로 IDLE 상태 파일 초기화 |
| 6 | `dev-phase-artifact-tracker.sh` | 중 | 중 | 추적성 매트릭스 자동화. 수동 관리 부담 제거 |
| 7 | `dev-phase-commit-gate.sh` | 낮 | 중 | 커밋 시 추적성 ID 및 테스트 통과 확인 |
| 8 | `dev-phase-subagent-injector.sh` | 낮 | 낮 | ultrawork 서브에이전트 사용 시에만 필요 |
| 9 | `dev-phase-completion-gate.sh` | 낮 | 낮 | G16-G20 방어적 중복 검사 (stop-gate의 보완) |

### 8.2 단계별 도입 전략

**Phase A (즉시 도입, 1-2일)**:
- 우선순위 1-2 훅 구현
- 기본 상태 파일 초기화 스크립트 작성
- `SessionStart` 컨텍스트 주입 검증

**Phase B (단기, 1주)**:
- 우선순위 3-4 훅 구현
- 실제 프로젝트에서 SPEC→TESTCASE 전환 테스트
- 게이트 실패 메시지 다듬기

**Phase C (중기, 2-3주)**:
- 우선순위 5-7 훅 구현
- 자동 추적성 매트릭스 생성 검증
- 회귀 사이클 시나리오 E2E 테스트

**Phase D (장기, 선택)**:
- 우선순위 8-9 훅 구현
- ultrawork 통합 테스트
- 커버리지 리포트 자동화

### 8.3 핵심 설계 원칙 요약

1. **결정론적 게이트 우선**: LLM 판단에 의존하지 않고 파일 시스템, grep, 테스트 결과로 게이트를 결정한다.

2. **소유권 분리 엄수**: `.omc/`와 `.claude/`는 각 시스템의 단독 쓰기 영역이다. 교차 쓰기는 절대 허용하지 않는다.

3. **TDD 강제**: 버그 수정도 테스트케이스 작성으로 시작한다. CODING 단계 직접 재진입은 `hotfix` 유형으로만 허용하며, 추적성이 확보된 경우에 한한다.

4. **추적성 자동화**: 개발자가 수동으로 추적성 매트릭스를 관리하지 않도록 훅이 자동으로 수집한다.

5. **cancel 안전성**: OMC ralph 취소가 개발 단계 상태에 영향을 주지 않도록 파일 소유권을 분리한다.

6. **동시성 안전**: `flock`과 atomic rename으로 병렬 서브에이전트 환경에서도 상태 파일이 손상되지 않는다.

### 8.4 최종 결언

Claude Code + OMC + `dev-phase-state.json`은 결정론적 개발 방법론(TDD, 양방향 추적성, 단계별 게이트)과 비결정론적 LLM 에이전트를 조합하는 최소한의, 그러나 완전한 시스템이다.

LLM은 본질적으로 비결정론적이다. 동일한 입력에 대해 항상 같은 출력을 보장할 수 없다. 따라서 소프트웨어 개발의 품질을 LLM의 "좋은 판단"에만 의존하는 것은 위험하다. 본 시스템은 그 간극을 결정론적 훅 게이트로 메운다:

- LLM이 단계를 벗어난 파일을 작성하려 해도 → `PreToolUse` 훅이 막는다.
- LLM이 테스트 없이 커밋하려 해도 → `PreToolUse` Bash 훅이 막는다.
- LLM이 게이트를 통과하지 않고 단계를 건너뛰려 해도 → `dev-phase-transition-gate.sh`가 막는다.
- 세션을 조기에 종료하려 해도 → `Stop` 훅이 막는다.

LLM의 역할은 이 결정론적 울타리 안에서 창의적이고 효율적으로 코드를 작성하는 것이다. 울타리(게이트 시스템)는 방법론적 정확성을 보장하고, LLM(Claude Code)은 구현 속도와 품질을 제공한다. 두 요소의 조합이 신뢰할 수 있는 자율 개발 시스템의 기반이 된다.

---

*본 문서는 2026-03-03 기준 claude-sonnet-4-6 모델 환경에서의 Claude Code Hook API를 기반으로 작성되었습니다.*
