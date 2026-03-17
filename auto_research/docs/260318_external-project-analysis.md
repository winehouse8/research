# 외부 프로젝트 분석 보고서 — Helios & autoresearch-at-home

**작성일**: 2026-03-18
**목적**: 자율 연구 에이전트 생태계 설계(260317_final-strategy-report.md)와 유사한 문제를 다루는 두 오픈소스 프로젝트를 분석하고, 우리 설계와의 접점·차이·교훈을 정리

---

## 요약 (두괄식 핵심)

| 항목 | Helios (snoglobe) | autoresearch-at-home (mutable-state-inc) |
|---|---|---|
| **한 줄 요약** | 자율 ML 실험 에이전트 — SSH로 원격 GPU를 조종하며 밤새 실험을 돌리는 오케스트레이터 | 분산 자율 연구 스웜 — 여러 에이전트가 `train.py`를 변이시키며 val_bpb를 공동 최적화 |
| **핵심 문제** | "train→wait→check→tweak 루프를 어떻게 자동화할까?" | "여러 에이전트가 같은 연구 문제를 어떻게 협업할까?" |
| **우리 연구와 겹침** | 장기기억 (ContextGate 체크포인트), SQLite+WAL | 지식 축적 (insight/hypothesis 공유), 평가 (val_bpb) |
| **우리 연구에 없는 것** | Sleep/Wake 트리거, SSH 원격 실행, TUI | VRAM 티어 시스템, SETI@home 분산 협업 |
| **우리가 갖고 있지만 이들에게 없는 것** | 선택압(pairwise 비교), MAP-Elites 다양성, PageRank 중요도, L0/L1/L2 계층 메모리 | 동일 |

**핵심 결론**: 두 프로젝트 모두 "자율 연구 에이전트"를 구현하지만, **진화적 메커니즘(선택압·다양성·도태)이 없다**. 우리 설계의 3원칙(평가압력·다양성 보존·상태 명시성)은 이 두 프로젝트가 갖지 못한 고유한 차별점이다.

---

## 1. Helios — 자율 ML 실험 오케스트레이터

**GitHub**: https://github.com/snoglobe/helios
**언어**: TypeScript (Node.js 20+)
**기술 스택**: Ink TUI, better-sqlite3, ssh2, Anthropic Claude Agent SDK, OpenAI Codex SDK

### 1.1 프로젝트 목적

Helios는 **무인 야간 ML 실험**을 자동화한다. 사용자가 고수준 연구 목표를 주면 (예: "125M GPT를 TinyStories에서 loss < 1.0까지 훈련"), LLM 에이전트가 스스로:

1. 훈련 스크립트를 작성하고
2. SSH로 원격 GPU 머신에 실험을 배포하고
3. stdout에서 메트릭을 실시간 파싱하고
4. 결과를 비교하여 다음 실험을 계획하고
5. 목표 달성 또는 중단까지 무한 반복한다

Andrej Karpathy의 `autoresearch` 컨셉에서 영감을 받았지만, TUI 인터페이스, 멀티머신 SSH, 영속 메모리, sleep/wake 트리거, 멀티 프로바이더 지원, AgentHub 협업까지 갖춘 완전체 시스템이다.

### 1.2 핵심 아키텍처 & 아이디어

#### (1) Agent-as-Orchestrator with Tool-Use Loop

실험 로직을 하드코딩하지 않는다. LLM 에이전트에게 **37개 도구**(원격 실행, 파일 조작, 메트릭 조회, 메모리 관리, 웹 검색 등)를 제공하고 모델이 스스로 결정한다.

```
목표 수신 → 실험 계획 → 도구로 실행 → 결과 모니터링 → 다음 실험 계획 → 반복
```

#### (2) ContextGate — 컨텍스트 윈도우 관리 ⭐

장기 실행의 핵심 문제 해결. 토큰 사용량이 모델 한계의 ~68%에 도달하면:

1. 모델에게 현재 대화의 "gist" 요약을 작성하게 함
2. gist를 영속 메모리 트리에 저장
3. 대화 히스토리를 리셋
4. 메모리 트리에서 브리핑을 재구성하여 새 컨텍스트에 주입

→ **우리 설계의 L0/L1/L2와 같은 문제(토큰 폭발)를 다른 전략으로 해결**. Helios는 모델 생성 gist + 트리 브라우징, 우리는 중요도 기반 계층적 로딩.

#### (3) 가상 파일시스템 메모리

메모리를 트리 구조로 관리:
```
/goal                          ← 연구 목표
/best                          ← 최고 결과
/experiments/01-train-gpt      ← 실험 기록
/observations/cosine-helps     ← 관찰 메모
```

각 노드에 `gist`(한 줄 요약)와 `content`(전문)가 있다. SQLite `memory_nodes` 테이블에 세션별로 저장.

→ 사실상 **2단계 메모리**(gist = L0/L1, content = L2)이지만, 명시적 계층화는 아니고 중요도 기반 로딩도 없다.

#### (4) Sleep/Wake 트리거 시스템 ⭐

에이전트가 "sleep" 도구를 호출하면 조합 가능한(composable) 트리거 표현식으로 대기:

```
(process_exit AND metric("loss") < 1.0) OR timer(7200)
```

AND/OR 트리를 1초 주기로 폴링. 트리거 발화 시 경과 시간, 만족 조건, 활성 태스크 상태, 최신 메트릭을 포함한 풍부한 컨텍스트로 에이전트를 깨운다.

→ **우리 설계에는 없는 기능**. 연구 루프가 코드 실험을 포함하는 Phase 3에서 유사한 메커니즘이 필요할 수 있다.

#### (5) 멀티머신 SSH 원격 실행

모든 연산은 SSH로 원격 머신에서 수행. `MetricCollector`가 로그 파일을 tail하며 `key=value` 패턴을 정규식으로 파싱. 하이퍼파라미터 sweep 시 라운드 로빈으로 머신 분배.

#### (6) AgentHub 멀티 에이전트 협업

Git 유사 프로토콜: 여러 Helios 에이전트가 실험 번들을 push/fetch하고, 메시지 보드로 소통하며, 서로의 작업을 기반으로 발전.

### 1.3 주요 컴포넌트

| 모듈 | 역할 |
|---|---|
| `src/core/orchestrator.ts` | 중앙 에이전트 루프: 세션 관리, LLM 호출, 도구 실행, 체크포인트 |
| `src/core/state-machine.ts` | 에이전트 생명주기: idle → active → sleeping/waiting/error |
| `src/memory/memory-store.ts` | 가상 파일시스템 메모리 (SQLite 백엔드) |
| `src/memory/context-gate.ts` | 토큰 모니터링, 체크포인트 트리거, 브리핑 재구성 |
| `src/memory/experiment-tracker.ts` | 실험 자동 기록 (`/experiments/`에 메모리 노드 생성) |
| `src/metrics/store.ts` | SQLite 기반 시계열 메트릭 저장 |
| `src/metrics/analyzer.ts` | 선형 회귀 추세 분석 (감소/정체/증가/불안정) |
| `src/scheduler/trigger-scheduler.ts` | 조합 가능한 트리거 평가 (AND/OR 트리) |
| `src/tools/compare-runs.ts` | 두 실험의 메트릭 비교 (단순 델타) |
| `src/tools/sweep.ts` | 하이퍼파라미터 그리드 서치 + 멀티머신 분배 |
| `src/hub/client.ts` | Git형 멀티 에이전트 협업 프로토콜 |
| `src/skills/bundled/` | Markdown 프롬프트 템플릿 (discover, paper, ablation, writeup, consult) |

### 1.4 강점

- **정교한 Sleep/Wake**: AND/OR 조합 트리거로 불필요한 폴링 없이 효율적 대기
- **ContextGate**: API 응답의 실제 `input_tokens`를 사용한 정확한 체크포인트 판단
- **가상 파일시스템 메모리**: gist/content 분리로 효율적 브라우징
- **멀티머신 오케스트레이션**: 노트북에서 원격 GPU 클러스터 제어
- **37개 도구**: 연구 워크플로우 전체를 커버하는 포괄적 도구셋
- **멀티 프로바이더**: Claude와 OpenAI 간 교차 상담 가능

### 1.5 한계

- **선택압·평가 시스템 없음**: 실험 비교는 단순 메트릭 델타. 체계적 평가 프레임워크 부재
- **세션 간 지식 축적 없음**: 메모리가 세션에 묶임. 세션 간 지식 이전 메커니즘 부재
- **다양성 보존 없음**: 탐욕적(greedy) "개선만 보존" 전략. 다양한 해를 탐색·보존하는 메커니즘 없음
- **그래프·중요도 없음**: 메모리가 트리이지 그래프가 아님. 지식 간 관계나 중요도 스코어링 없음
- **선형 실험 진행**: 순차적 또는 소규모 병렬 sweep. 인구 기반(population-based) 접근 없음

---

## 2. autoresearch-at-home — 분산 자율 연구 스웜

**GitHub**: https://github.com/mutable-state-inc/autoresearch-at-home
**언어**: Python 3.10
**기술 스택**: PyTorch (CUDA), Flash Attention 3 (kernels 라이브러리), Ensue Network API, rustbpe

### 2.1 프로젝트 목적

Andrej Karpathy의 `autoresearch` 포크로, **SETI@home 모델**을 연구에 적용한다. 핵심 아이디어:

- LLM 에이전트가 `train.py`(신경망 훈련 스크립트)를 자율적으로 수정
- 5분간 실험을 실행하고 val_bpb(validation bits-per-byte)를 측정
- 결과를 공유 저장소(Ensue)에 게시
- 여러 에이전트가 서로의 결과를 참조하며 집단적으로 최적화

**즉시적 과제**: 고정 5분 예산 내에서 GPT 스타일 LM의 사전훈련 레시피 최적화
**더 큰 비전**: 단일 PhD 학생이 아닌, 자율 에이전트로 구성된 "연구 커뮤니티" 에뮬레이션

### 2.2 핵심 아키텍처 & 아이디어

#### (1) Single-File-as-Genome ⭐

전체 모델 정의, 옵티마이저, 훈련 루프가 `train.py` 한 파일에 존재. 에이전트의 "변이"는 이 파일을 편집하는 것. "적합도 함수"는 불변인 `prepare.py`의 `evaluate_bpb()`.

```
변이 가능:  train.py (모델 아키텍처, 하이퍼파라미터, 옵티마이저)
불변:       prepare.py (데이터 로더, 평가 함수, 토크나이저)
```

→ **깔끔한 관심사 분리**: 에이전트는 훈련 방법만 바꿀 수 있고, 평가 방법은 바꿀 수 없다. 게이밍 방지.

#### (2) 고정 시간 예산 (300초)

모든 실험이 정확히 5분 벽시계(wall-clock) 시간 동안 실행. 결과를 실험 간에 비교 가능하게 만든다. (단, 하드웨어 간 비교는 VRAM 티어로 해결)

#### (3) Ensue 기반 공유 메모리 ⭐

모든 협업이 Ensue(ensue-network.ai)라는 서드파티 KV 저장소를 통해 이루어진다:

```
@autoresearch-at-home/results/    ← 실험 결과 (train.py 소스 포함)
@autoresearch-at-home/claims/     ← 실험 선점 (중복 방지)
@autoresearch-at-home/hypotheses/ ← 다음 실험 제안
@autoresearch-at-home/insights/   ← 실험에서 얻은 통찰
@autoresearch-at-home/best/       ← 글로벌/티어별 최고 결과
```

시맨틱 검색을 통한 유사 실험 탐색 지원. 네트워크 실패 시 솔로 모드로 graceful degradation.

#### (4) VRAM 티어 시스템

GPU VRAM을 자동 감지하여 small/medium/large/xl로 분류. 티어별 최고 결과를 별도 추적하여 **4090 에이전트가 H100 결과에 좌절하지 않도록** 공정한 비교 제공.

#### (5) 의무적 지식 공유 프로토콜

매 실험 후 3가지를 반드시 게시:
1. **결과**: 메트릭 + 전체 `train.py` 소스
2. **통찰**: 결과가 왜 그렇게 나왔는지에 대한 추론
3. **가설**: 다른 에이전트를 위한 다음 실험 제안

→ 실패한 실험도 게시하여 **중복 실험 방지**. 결과뿐 아니라 **추론도 공유**한다는 점이 독특.

#### (6) 중복 방지 (Claiming)

실험 시작 전 `claim_experiment()` 호출:
- 해시 기반 정확 매칭 + 시맨틱 유사도 검사 (임계값 0.92)
- 15분 TTL (실험이 완료되지 않으면 클레임 만료)
- 경쟁 조건 처리: write → 2초 대기 → re-read, 가장 빠른 `created_at` 우선

### 2.3 주요 컴포넌트

| 파일 | 역할 | 수정 가능 |
|---|---|---|
| `prepare.py` (390줄) | 데이터 다운로드, BPE 토크나이저 훈련, 데이터로더, 평가 함수 | ❌ |
| `train.py` (630줄) | GPT 아키텍처, MuonAdamW 옵티마이저, 훈련 루프 | ✅ (에이전트가 편집) |
| `coordinator.py` (~1300줄) | Ensue API 통합, 실험 선점, 결과 게시, 스웜 분석 | 인프라 |
| `program.md` | 솔로 모드 에이전트 지시문 (시스템 프롬프트) | 지시문 |
| `collab.md` | 협업 모드 프로토콜 명세 | 지시문 |

**train.py의 현재 아키텍처** (에이전트들이 진화시키는 "게놈"):
- RMS 정규화, RoPE, Flash Attention 3
- 슬라이딩 윈도우 어텐션 (SSSL 패턴)
- Value 임베딩 (ResFormer 방식) + 입력 의존 게이팅
- MuonAdamW 하이브리드 옵티마이저
- ReluSquared 활성화 함수
- ~50M 파라미터 (8 레이어, 768차원)

### 2.4 강점

- **극단적 단순성**: 전체 시스템이 ~2400줄 Python, 4개 파일. DB 없음, 메시지 브로커 없음
- **완전 재현성**: 모든 결과에 전체 `train.py` 소스 포함
- **하드웨어 공정성**: VRAM 티어로 동급 하드웨어 내 비교
- **지식 축적**: 의무적 insight/hypothesis 게시로 추론까지 공유
- **내결함성**: 모든 네트워크 호출에 try/except, 실패 시 솔로 모드
- **깨끗한 평가/변이 분리**: 불변 evaluate_bpb() vs 가변 train.py

### 2.5 한계

- **선택압 없음**: "현재 최고보다 낮은가?" 이진 판단. pairwise 비교, 순위, 다양성 없음
- **메모리 계층 없음**: Ensue의 플랫 KV 저장소. L0/L1/L2 계층화 없음
- **단일 목적 최적화**: val_bpb 하나만 추적. 다목적 Pareto 프론티어 없음
- **서드파티 의존**: Ensue 서비스 중단 시 협업 기능 상실
- **구조화된 파라미터 추적 없음**: 실험 설명이 자유 텍스트. "LR을 0.001→0.04로 변경"이 구조화되지 않음
- **컨텍스트 윈도우 제한**: 에이전트 수·결과 수 증가 시 THINK 단계에서 토큰 폭발 가능

---

## 3. 비교 분석 — 세 시스템의 교차 비교

### 3.1 핵심 메커니즘 비교표

| 메커니즘 | 우리 설계 | Helios | autoresearch-at-home |
|---|---|---|---|
| **메모리 구조** | L0/L1/L2 계층 + SQLite | 가상 파일시스템 트리 (gist/content) | Ensue 플랫 KV + 시맨틱 검색 |
| **메모리 로딩** | 중요도 기반 계층적 로딩 (91% 절감) | 체크포인트 시 gist만 로딩 후 on-demand | 전체 로딩 (컨텍스트 윈도우 한계) |
| **선택압** | comparisons(winner, loser) pairwise | 없음 (LLM이 주관적 판단) | val_bpb > 현재 최고? 이진 판단 |
| **다양성 보존** | MAP-Elites (topic × perspective) | 없음 (탐욕적 보존) | VRAM 티어 (하드웨어 기반만) |
| **중요도 순위** | PageRank (비교 그래프) | 없음 (모든 메모리 동등) | 글로벌 최고 1개만 추적 |
| **지식 단위** | 논문 (claim + evidence + assumptions) | 메모리 노드 (gist + content) | train.py 소스 + 결과 메트릭 |
| **저장소** | SQLite + WAL | SQLite + WAL (better-sqlite3) | Ensue (클라우드 KV) |
| **세션 간 연속성** | SHA-256 ID + annotations | 세션별 격리 (글로벌 메모리 제한적) | Ensue에서 매번 읽기 |
| **에이전트 구조** | Planner-Executor-Reflector | 단일 에이전트 + 도구 루프 | 단일 에이전트 (program.md 지시) |
| **실행 환경** | Claude Agent SDK (Python) | TypeScript + Claude/OpenAI SDK | Python + LLM (implicit) |
| **코드 실행** | 계획 중 (Docker 격리) | SSH 원격 실행 | 로컬 GPU 직접 실행 |
| **협업** | 미설계 | AgentHub (git형 push/fetch) | Ensue (시맨틱 공유 메모리) |

### 3.2 문제 유형 비교

| 시스템 | 문제 유형 | 평가 방법 |
|---|---|---|
| **우리 설계** | B형 (진실 수렴) — 정답이 없는 연구 질문 | LLM-as-Judge pairwise + 라카토슈 보정 |
| **Helios** | A형 (정답 있음) — 메트릭 최소화/최대화 | 수치 메트릭 비교 (loss, accuracy 등) |
| **autoresearch-at-home** | A형 (정답 있음) — val_bpb 최소화 | 단일 스칼라 비교 |

→ **핵심 차이**: Helios와 autoresearch-at-home은 모두 **수치 메트릭 최적화**(A형)에 특화되어 있다. 우리 설계만이 **정답이 없는 B형 연구 질문**을 다룬다. 이것이 pairwise LLM-as-Judge, MAP-Elites, PageRank 같은 복잡한 메커니즘이 필요한 근본 이유다.

### 3.3 설계 철학 비교

```
Helios:              "단일 에이전트가 목표 달성할 때까지 실험을 자동화한다"
autoresearch-at-home: "여러 에이전트가 단일 메트릭을 향해 협업 최적화한다"
우리 설계:            "나쁜 지식이 자연스럽게 도태되는 생태계를 만든다"
```

- **Helios**: 에이전트 = 자동화 도구. 인간의 실험 루프를 대체.
- **autoresearch-at-home**: 에이전트 = 분산 작업자. Hill-climbing 최적화 스웜.
- **우리 설계**: 에이전트 = 생태계 구성원. 생성·경쟁·도태·진화하는 지식 생산 시스템.

---

## 4. 우리 설계에 대한 시사점 & 교훈

### 4.1 Helios에서 배울 점

| 교훈 | 상세 | 적용 가능 단계 |
|---|---|---|
| **ContextGate 패턴** | 토큰 68% 도달 시 자동 gist + 리셋 + 브리핑 재구성. 우리 L0/L1/L2와 보완적 — 장기 실행 시 동적 컨텍스트 관리에 참고 | Phase 2 |
| **Sleep/Wake 트리거** | 코드 실험(Q4~Q7)에서 훈련 완료 대기 시 유용. 조합 가능한 트리거 표현식 설계가 우수 | Phase 3 |
| **메트릭 자동 파싱** | stdout에서 `key=value` 패턴 자동 감지. 코드 실험 결과 수집에 적용 가능 | Phase 3 |
| **SQLite WAL + Prepared Statement Cache** | 동일 기술 스택이지만, Helios의 StmtCache 패턴을 참고할 가치 | Phase 1 |
| **가상 파일시스템 메모리** | 트리 구조로 gist/content 분리. 우리 L0/L1의 UI/디버깅 관점에서 참고 | Phase 2 |

### 4.2 autoresearch-at-home에서 배울 점

| 교훈 | 상세 | 적용 가능 단계 |
|---|---|---|
| **Single-File-as-Genome** | 변이 가능 영역과 불변 평가 영역의 깨끗한 분리. 우리 시스템에서도 에이전트가 수정할 수 있는 것/없는 것의 경계를 명확히 | Phase 1 |
| **의무적 지식 공유** | 모든 실험 후 결과 + 통찰 + 가설을 반드시 게시. 우리 reflector_agent의 annotation 생성에 비슷한 의무 프로토콜 적용 가능 | Phase 1 |
| **Graceful Degradation** | 네트워크 실패 시 솔로 모드로 계속 동작. 우리 시스템에서도 외부 API(Semantic Scholar 등) 실패 시 fallback 설계 필요 | Phase 1 |
| **VRAM 티어 = 환경별 공정 비교** | 하드웨어가 다르면 별도 리더보드. 우리 시스템에서 다른 LLM 모델로 생성된 논문 간 비교 시 유사한 "계층 분리" 참고 가능 | Phase 2 |
| **실험 선점 (Claiming)** | 시맨틱 유사도 기반 중복 방지. 다중 에이전트 병렬 실행 시 같은 주제에 대한 중복 연구 방지에 적용 가능 | Phase 3 |

### 4.3 우리 설계의 고유 강점 (두 프로젝트에 없는 것)

1. **평가압력 시스템**: pairwise LLM-as-Judge + position bias 제거 + 라카토슈 보정. 두 프로젝트 모두 체계적 평가 없음.
2. **MAP-Elites 다양성**: topic × perspective 격자에서 셀 내 경쟁. 두 프로젝트 모두 다양성 보존 메커니즘 없음.
3. **PageRank 중요도**: 비교 그래프 기반 중요도 순위. 두 프로젝트 모두 지식 간 관계나 중요도 스코어링 없음.
4. **B형 문제 대응**: 정답 없는 연구 질문에 대한 "반박 내성"으로 간접 평가. 두 프로젝트 모두 수치 메트릭 최적화에만 특화.
5. **구조화된 지식 스키마**: papers(claim, evidence, assumptions, fitness, status, topic_tag, perspective) + edges + annotations. 두 프로젝트의 메모리보다 훨씬 풍부한 구조.
6. **과학철학 3종 조합**: 포퍼(게이트키퍼) + 베이즈(신뢰도) + 라카토슈(진보/퇴행). 독자적 설계.

---

## 5. 통합 포지셔닝

```
┌──────────────────────────────────────────────────────────────────────────┐
│                    자율 연구 에이전트 스펙트럼                              │
│                                                                          │
│  단순 ◄─────────────────────────────────────────────────────────► 복잡   │
│                                                                          │
│  autoresearch     autoresearch-at-home      Helios         우리 설계     │
│  (Karpathy 원본)   (분산 스웜)             (오케스트레이터)  (진화 생태계)  │
│                                                                          │
│  while loop       + 협업 레이어            + 메모리/도구     + 선택압     │
│  + claude -p      + 중복 방지              + Sleep/Wake     + 다양성     │
│                   + 지식 공유              + SSH 실행       + PageRank   │
│                   + VRAM 티어              + TUI           + 도태/진화   │
│                                                                          │
│  ──── A형 문제 (수치 최적화) ──── │ ──── B형 문제 (진실 수렴) ────       │
└──────────────────────────────────────────────────────────────────────────┘
```

세 시스템은 같은 기원(Karpathy의 autoresearch)에서 출발하지만 다른 방향으로 진화했다:

- **autoresearch-at-home**: 수평 확장 (다수 에이전트 협업)
- **Helios**: 수직 심화 (단일 에이전트 역량 극대화)
- **우리 설계**: 메타 수준 진화 (지식 자체가 경쟁·도태·진화)

이들은 **보완적**이다. Helios의 인프라(SSH 실행, Sleep/Wake, 메트릭 파싱)와 autoresearch-at-home의 협업 패턴(지식 공유, 중복 방지)은 우리 설계의 Phase 3(코드 실험 + 다중 에이전트)에서 참고할 가치가 크다.

---

*분석 대상*:
- Helios: https://github.com/snoglobe/helios
- autoresearch-at-home: https://github.com/mutable-state-inc/autoresearch-at-home
- 기반 연구: `260317_final-strategy-report.md`
