# Auto Research Ecosystem v2 — 기술 명세서

**지식이 축적되고 경쟁하고 진화하는 자율 연구 생태계의 전체 기술 명세.**

---

## 이 문서를 읽는 법

이 `spec/` 디렉토리는 Auto Research Ecosystem v2의 전체 구현을 **계층적으로** 정리한 기술 명세서입니다.

### 읽는 순서

1. **지금 이 파일** (`spec/summary.md`)을 먼저 읽어 전체 구조를 파악합니다
2. 관심 있는 폴더로 들어갑니다
3. 해당 폴더의 **`summary.md`를 먼저** 읽어 해당 파트의 개요와 파일 목록을 확인합니다
4. 필요한 세부 문서를 읽습니다

### 구조

```
spec/
├── summary.md                    ← 지금 읽고 있는 파일 (전체 개요)
│
├── 01-architecture/              ← 시스템 설계 철학과 전체 구조
│   ├── summary.md                ← 이 폴더의 개요
│   ├── overview.md               ← 시스템 전체 구조, 데이터 흐름, ASCII 다이어그램
│   ├── principles.md             ← 3대 설계 원칙 + 과학철학 3종 조합
│   └── tech-stack.md             ← 기술 스택 선택/불선택 근거, 비용 추정
│
├── 02-core/                      ← SQLite 스키마, 메모리, 피트니스 엔진
│   ├── summary.md                ← 이 폴더의 개요
│   ├── schema.md                 ← 5개 테이블, 인덱스, 트리거, WAL 설정
│   ├── memory-system.md          ← L0/L1/L2 계층 로딩, annotation, SHA-256 ID
│   └── fitness-system.md         ← PageRank, MAP-Elites, lifecycle 상태 전환
│
├── 03-agents/                    ← 3개 LLM 에이전트 + SDK 통합
│   ├── summary.md                ← 이 폴더의 개요
│   ├── sdk-integration.md        ← Claude Agent SDK + OMC 플러그인 통합
│   ├── research-agent.md         ← 논문 생성 (sonnet, WebSearch/WebFetch)
│   ├── compare-agent.md          ← Pairwise 비교 (haiku, position bias 제거)
│   └── reflector-agent.md        ← Annotation 추출 (haiku, 결정론적 분리)
│
├── 04-main-loop/                 ← while True 무한 연구 루프
│   ├── summary.md                ← 이 폴더의 개요
│   ├── lifecycle.md              ← 5단계 사이클, async 구조, 시그널 처리
│   └── cold-start.md             ← 시드 데이터, LLM 자동 생성, seed_data.py
│
└── 05-evolution/                 ← 진화적 메커니즘
    ├── summary.md                ← 이 폴더의 개요
    ├── selection-pressure.md     ← PageRank 자연선택, comparisons 그래프
    ├── diversity.md              ← MAP-Elites 격자, lifecycle 상태 전환
    └── epistemology.md           ← 포퍼 + 베이즈 + 라카토슈 통합
```

---

## 폴더별 요약

### 01-architecture — 아키텍처 개요

시스템의 전체 설계 철학과 구조를 다룹니다. **"나쁜 논문이 자연스럽게 도태되는 생태계를 설계하는 것"** 이라는 핵심 원칙부터 시작하여, 3대 설계 원칙(평가압력, 다양성 보존, 상태 명시성), 데이터 흐름 다이어그램, 기술 스택 선택 근거를 담고 있습니다.

**처음 이 프로젝트를 접하는 사람은 여기부터 읽으세요.**

### 02-core — 코어 인프라

SQLite 스키마(5개 테이블), L0/L1/L2 계층적 메모리 시스템, PageRank 피트니스 엔진 등 핵심 인프라를 명세합니다. 데이터 모델을 이해하려면 `schema.md`, 메모리 로딩 방식을 이해하려면 `memory-system.md`, 진화 엔진을 이해하려면 `fitness-system.md`를 읽으세요.

### 03-agents — 에이전트 모듈

3개 LLM 에이전트(research, compare, reflector)의 역할, 모델 선택, 프롬프트 구조, SDK 통합 방식을 명세합니다. Claude Agent SDK 사용 패턴과 oh-my-claudecode 플러그인 연동 방식을 `sdk-integration.md`에서 확인할 수 있습니다.

### 04-main-loop — 메인 루프

`autoresearch_v2.py`의 while True 무한 루프 구조를 명세합니다. 5단계 사이클(컨텍스트 → 생성 → 비교 → 반성 → 갱신), asyncio 기반 비동기 구조, 시그널 핸들링, 콜드 스타트 시딩 방식을 다룹니다.

### 05-evolution — 진화 메커니즘

연구 생태계의 진화적 메커니즘을 과학철학과 연결하여 명세합니다. PageRank 기반 자연선택, MAP-Elites 다양성 보존, 포퍼-베이즈-라카토슈 3종 인식론 통합이 실제 코드에서 어떻게 구현되는지 설명합니다.

---

## 소스 코드와의 매핑

| 명세 파일 | 대응 소스 코드 |
|-----------|---------------|
| `01-architecture/overview.md` | 전체 프로젝트 구조 |
| `01-architecture/tech-stack.md` | `requirements.txt`, `agents/_sdk.py` |
| `02-core/schema.md` | `core/schema.sql`, `core/__init__.py` |
| `02-core/memory-system.md` | `core/memory.py` |
| `02-core/fitness-system.md` | `core/fitness.py` |
| `03-agents/sdk-integration.md` | `agents/_sdk.py` |
| `03-agents/research-agent.md` | `agents/research_agent.py` |
| `03-agents/compare-agent.md` | `agents/compare_agent.py` |
| `03-agents/reflector-agent.md` | `agents/reflector_agent.py` |
| `04-main-loop/lifecycle.md` | `autoresearch_v2.py` |
| `04-main-loop/cold-start.md` | `autoresearch_v2.py`, `seed_data.py` |
| `05-evolution/selection-pressure.md` | `core/fitness.py`, `agents/compare_agent.py` |
| `05-evolution/diversity.md` | `core/fitness.py` |
| `05-evolution/epistemology.md` | `agents/research_agent.py`, `agents/compare_agent.py`, `core/memory.py` |

---

## 핵심 수치

- **테이블**: 5개 (papers, comparisons, edges, annotations, audit_chain)
- **에이전트**: 3개 (research/sonnet, compare/haiku, reflector/haiku)
- **품질 강제**: 3개 Stop Hook (Mini-Ralph 패턴, MAX_STOP_RETRIES=3)
- **사이클 추적**: Trial ID (`YYYYMMDDHHMMSS_HASH`) + per-trial 로그 파일
- **사이클당 비용**: ~$0.036
- **연구 질문 기반**: `--prompt` 인자로 에이전트의 North Star 지정 가능
- **테스트**: `tests/test_integration.py` — schema, memory, fitness 통합 테스트

---

*이 명세서는 `docs/260317_final-strategy-report.md` 전략 보고서의 구현 결과물입니다.*
