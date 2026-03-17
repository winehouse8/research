# GPT-5-mini, GPT-4o-mini vs 24GB GPU 오픈소스 최강 모델 성능 비교
## 멀티턴 에이전틱·코딩 유즈케이스 중심 분석

**작성일: 2026년 3월 9일**
**분석 기준: 2026년 3월 최신 벤치마크 데이터**

---

## 목차

1. [보고서 개요](#1-보고서-개요)
2. [비교 대상 모델 소개](#2-비교-대상-모델-소개)
   - 2.1 [OpenAI 소형 모델군](#21-openai-소형-모델군-gpt-5-mini-gpt-4o-mini-gpt-41-mini)
   - 2.2 [24GB GPU 오픈소스 모델군](#22-24gb-gpu-오픈소스-모델군)
3. [사양 및 비용 비교](#3-사양-및-비용-비교)
4. [범용 벤치마크 비교 (MMLU, GPQA, MATH, AIME)](#4-범용-벤치마크-비교)
5. [코딩 성능 비교 (HumanEval, SWE-bench, LiveCodeBench, Aider)](#5-코딩-성능-비교)
6. [멀티턴 에이전틱 성능 비교](#6-멀티턴-에이전틱-성능-비교)
   - 6.1 [도구 사용/함수 호출 (BFCL)](#61-도구-사용함수-호출-bfcl)
   - 6.2 [실제 소프트웨어 엔지니어링 (SWE-bench)](#62-실제-소프트웨어-엔지니어링-swe-bench)
   - 6.3 [에이전틱 태스크 (GAIA)](#63-에이전틱-태스크-gaia)
   - 6.4 [멀티턴 에이전틱 성능 종합](#64-멀티턴-에이전틱-성능-종합)
   - 6.5 [에이전틱 성능 격차 (AgentBench)](#65-에이전틱-성능-격차-agentbench)
   - 6.6 [실제 컴퓨터 사용 에이전트 (OSWorld / WebArena)](#66-실제-컴퓨터-사용-에이전트-성능-추이-osworld--webarena)
7. [용도별 추천](#7-용도별-추천)
   - 7.1 [API 과금 방식 (OpenAI 모델 선택 가이드)](#71-api-과금-방식-openai-모델-선택-가이드)
   - 7.2 [로컬 실행 (24GB GPU 모델 선택 가이드)](#72-로컬-실행-24gb-gpu-모델-선택-가이드)
8. [트레이드오프 분석: API vs 로컬](#8-트레이드오프-분석-api-vs-로컬)
9. [결론](#9-결론)
10. [참고 자료](#10-참고-자료)

---

## 1. 보고서 개요

### 1.1 작성 배경

2026년 3월 현재, LLM 생태계는 두 가지 큰 축으로 발전하고 있다.

1. **API 기반 상용 모델**: OpenAI GPT-5-mini, GPT-4.1-mini 등 소형 모델이 비용 효율적 에이전트 파이프라인의 핵심으로 부상
2. **로컬 실행 오픈소스 모델**: Qwen3-32B, GLM-4.7-Flash 등이 소비자 GPU(24GB VRAM)에서 상용 모델에 필적하는 성능을 제공

본 보고서는 이 두 진영을 **멀티턴 에이전틱 코딩** 유즈케이스에 초점을 맞춰 종합 비교한다. 핵심 질문은 다음과 같다:

> **"RTX 3090/4090 단일 GPU(24GB VRAM)로 GPT-5-mini 또는 GPT-4.1-mini 수준의 에이전틱 코딩 성능을 로컬에서 달성할 수 있는가?"**

### 1.2 분석 범위

- **OpenAI 모델**: GPT-5-mini (2025.08), GPT-4.1-mini (2025.04), GPT-4o-mini (2024.07)
- **24GB GPU 오픈소스**: Qwen3-32B, Qwen3-30B-A3B, GLM-4.7-Flash, DeepSeek-R1-Distill-Qwen-32B, Qwen2.5-Coder-32B, Mistral Small 3.2, Phi-4-Reasoning
- **벤치마크**: SWE-bench Verified, LiveCodeBench, HumanEval, BFCL, GAIA, AIME, GPQA Diamond

### 1.3 핵심 결론 미리보기

| 영역 | API 최강 (OpenAI mini) | 24GB GPU 최강 | 승자 |
|------|----------------------|--------------|------|
| SWE-bench Verified | GPT-4.1-mini 23.6% | GLM-4.7-Flash **59.2%** (Full: 73.8%) | **오픈소스** (2.5~3.1배) |
| LiveCodeBench | GPT-4.1-mini Aider 31.6% | GLM-4.7-Flash **84.9%** | **오픈소스** (2.7배) |
| HumanEval | GPT-4o-mini 87.2% | GLM-4.7 **94.2%** | **오픈소스** |
| AIME 2025 수학 추론 | GPT-5-mini **91.1%** | GLM-4.7-Flash 91.6% | **동급** |
| 도구 호출 (BFCL) | GPT-5-mini 55.5 | GLM-4.5 FC **70.85%** (1위) | **오픈소스** |
| 비용 (월간 추정) | $50-500+/월 | GPU 전기세 ~$30/월 | **오픈소스** |

> *Qwen3.5-122B-A10B는 24GB 단일 GPU 경계선. **24GB 적합 모델 중에서는 Qwen3-32B의 BFCL-V3 72.8이 최강.
> ***GLM-4.7 Full(358B MoE)은 서버급. GLM-4.7-Flash(30B MoE)가 24GB GPU 실행 가능. DeepSeek V3/R1은 함수 호출 미지원으로 에이전틱 파이프라인 제한적.

---

## 2. 비교 대상 모델 소개

### 2.1 OpenAI 소형 모델군 (GPT-5-mini, GPT-4o-mini, GPT-4.1-mini)

#### GPT-4o-mini (2024년 7월)

GPT-4o 패밀리의 경량화 모델로, 2024년 출시 당시 가장 비용 효율적인 OpenAI 모델이었다.

| 항목 | 사양 |
|------|------|
| 출시일 | 2024년 7월 18일 |
| 컨텍스트 창 | 128,000 토큰 |
| 최대 출력 | 16,384 토큰 |
| 지식 컷오프 | 2023년 10월 |
| 멀티모달 | 텍스트 + 이미지 |
| 추론 모드 | 없음 |
| API 입력 가격 | $0.15/1M 토큰 |
| API 출력 가격 | $0.60/1M 토큰 |

**강점**: 검증된 안정성, 가장 저렴한 가격대(GPT-4.1-nano 제외), 폭넓은 호환성
**약점**: 에이전틱 코딩 성능 한계(Aider Polyglot 18.2%), 컨텍스트 128K 제한

#### GPT-4.1-mini (2025년 4월)

GPT-4.1 패밀리의 경량 모델로, 에이전틱 워크플로와 코딩에 특화하여 설계되었다. GPT-4o-mini 대비 대부분의 벤치마크에서 우위를 보인다.

| 항목 | 사양 |
|------|------|
| 출시일 | 2025년 4월 14일 |
| 컨텍스트 창 | 1,047,576 토큰 (~1M) |
| 최대 출력 | 32,768 토큰 |
| 지식 컷오프 | 2024년 5~6월 |
| 멀티모달 | 텍스트 + 이미지 |
| 추론 모드 | 없음 (추론 단계 없이 빠른 응답) |
| API 입력 가격 | $0.40/1M 토큰 |
| API 출력 가격 | $1.60/1M 토큰 |
| 캐시 할인 | 75% |

**강점**: 1M 컨텍스트, Aider Polyglot 31.6%(GPT-4o-mini 대비 73.6% 향상), 강화된 지시 따르기, diff 형식 준수율 대폭 개선
**약점**: GPT-4o-mini 대비 2.7배 비싼 가격, SWE-bench 23.6%로 실제 엔지니어링 과제에서 제한적

#### GPT-5-mini (2025년 8월)

GPT-5 패밀리의 경량화 모델로, 내장 추론 능력을 보유한 최신 OpenAI 소형 모델이다.

| 항목 | 사양 |
|------|------|
| 출시일 | 2025년 8월 7일 |
| 컨텍스트 창 | 400,000 토큰 |
| 최대 출력 | 128,000 토큰 |
| 지식 컷오프 | 2024년 5월 |
| 멀티모달 | 텍스트 + 이미지 |
| 추론 모드 | **있음** (내장) |
| API 입력 가격 | $0.25/1M 토큰 |
| API 출력 가격 | $2.00/1M 토큰 |

**강점**: AIME 2025 91.1%(고난도 수학에서 질적 도약), GPQA Diamond 82.3%, 내장 추론, 128K 출력
**약점**: 컨텍스트 400K(GPT-4.1-mini 1M 대비 축소), SWE-bench/LiveCodeBench 공개 점수 부재

#### GPT-4.1-nano (참고)

| 항목 | 사양 |
|------|------|
| 출시일 | 2025년 4월 14일 |
| 컨텍스트 창 | ~1M 토큰 |
| API 입력 가격 | $0.10/1M (최저가) |
| Aider Polyglot | 9.8% |
| AIME 2024 | 29.4% |

GPT-4.1 패밀리의 최경량 모델. 분류, 자동완성 등 단순 태스크에 최적화. 에이전틱 코딩에는 비권장.

---

### 2.2 24GB GPU 오픈소스 모델군

#### Qwen3-32B (Alibaba, 2025년 4월)

| 항목 | 사양 |
|------|------|
| 파라미터 | 32B (Dense) |
| Q4_K_M VRAM | ~19.8GB |
| 컨텍스트 창 | 128K (YaRN 확장 가능) |
| 라이선스 | Apache 2.0 |
| 도구 사용 | 지원 |
| 추론 모드 | Thinking/Non-Thinking 통합 |
| AIME 2025 | 79.1% |
| BFCL-V3 도구 호출 | 72.8 |

24GB GPU에서 Q4_K_M으로 실행 가능한 Dense 모델 중 범용 최강. 추론 모드와 일반 모드를 상황에 따라 전환할 수 있어 유연성이 매우 높다.

#### GLM-4.7 / GLM-4.7-Flash / GLM-5 계열 (Zhipu AI / Z.ai)

GLM-4.7 계열은 풀 모델과 경량 Flash 변형이 구분된다. 24GB GPU에서 실행 가능한 것은 **GLM-4.7-Flash**이며, GLM-4.7 Full과 GLM-5는 서버급 모델이다.

| 모델 | 출시 | 파라미터 | SWE-bench | HumanEval | 비고 |
|------|------|---------|-----------|-----------|------|
| **GLM-4.7 Full** | 2025년 12월 | 358B MoE | **73.8%** | **94.2%** | 서버급, 24GB 불가 |
| **GLM-4.7-Flash** | 2026년 1월 | 30B/3B 활성 MoE | **59.2%** | — | 24GB GPU 가능 |
| **GLM-5** | 2026년 2월 | 744B | **77.8%** | — | Chatbot Arena ELO 1451 (1위) |

#### GLM-4.7-Flash (Zhipu AI, 2026년 1월) — 24GB GPU 실행 가능

| 항목 | 사양 |
|------|------|
| 파라미터 | 30B 총 / 3B 활성 (MoE) |
| Q4_K_M VRAM | ~8GB |
| FP16 VRAM | ~24GB (경계선) |
| 컨텍스트 창 | 128K |
| 라이선스 | 오픈소스 |
| 도구 사용 | 지원 (tau2-Bench 79.5) |
| SWE-bench Verified | **59.2%** |
| LiveCodeBench v6 | 64.0 |
| AIME 2025 | 91.6 |

2026년 1월 출시된 MoE 모델. **SWE-bench 59.2%는 24GB GPU 실행 가능 모델 중 세계 최고**로, 실제 GitHub 이슈 해결 능력에서 GPT-4.1-mini(23.6%)를 2.5배 상회한다. 상위 모델인 GLM-4.7 Full(73.8%)과 GLM-5(77.8%)는 서버급이지만, Flash 변형만으로도 GPT-4.1 full(54.6%)을 상회한다.

#### Qwen3-30B-A3B (Alibaba, 2025년 4월)

| 항목 | 사양 |
|------|------|
| 파라미터 | 30.5B 총 / 3.3B 활성 (MoE) |
| Q4_K_M VRAM | ~8GB |
| 추론 속도 | ~196 tok/s (RTX 4090) |
| AIME 2025 | 81.4% |
| 라이선스 | Apache 2.0 |

MoE 구조 덕분에 8GB VRAM만으로도 실행 가능. RTX 4090에서 196 tok/s의 경이적 속도를 기록한다.

#### DeepSeek-R1-Distill-Qwen-32B (DeepSeek, 2025년 1월)

| 항목 | 사양 |
|------|------|
| 파라미터 | 32B (Dense) |
| Q4_K_M VRAM | ~20GB |
| AIME 2024 | 72.6% |
| MATH-500 | 94.3% |
| LiveCodeBench | 57.2% |
| 라이선스 | MIT |

DeepSeek-R1(671B)의 추론 능력을 32B에 증류한 모델. 수학·추론 특화 최강.

#### Qwen2.5-Coder-32B (Alibaba, 2024년 9월)

| 항목 | 사양 |
|------|------|
| 파라미터 | 32B (Dense) |
| Q4_K_M VRAM | ~20GB |
| HumanEval | **92.7%** |
| 40+ 프로그래밍 언어 | 지원 |
| 라이선스 | Apache 2.0 |

HumanEval 92.7%로 GPT-4o와 동등한 코딩 성능. 24GB GPU에서 실행 가능한 코딩 특화 최강 모델.

#### Mistral Small 3.2 (Mistral AI, 2025년 6월)

| 항목 | 사양 |
|------|------|
| 파라미터 | 24B (Dense) |
| Q4_K_M VRAM | ~14GB |
| 컨텍스트 창 | 130K |
| HumanEval Plus Pass@5 | 92.90% |
| IFEval 지시 따르기 | 84.78% |
| 라이선스 | Apache 2.0 |

130K 컨텍스트와 강화된 함수 호출 기능으로 에이전트 파이프라인에 적합.

#### Phi-4-Reasoning (Microsoft, 2025년 4월)

| 항목 | 사양 |
|------|------|
| 파라미터 | 14B (Dense) |
| Q4_K_M VRAM | ~8.5GB |
| AIME 2025 | DeepSeek-R1(671B) 동급 |
| 컨텍스트 창 | 16K |
| 라이선스 | MIT |

14B 파라미터로 671B 모델에 필적하는 추론 성능. 소형 추론 특화 최강.

---

## 3. 사양 및 비용 비교

### 3.1 OpenAI 모델 API 가격 비교

| 모델 | 입력 ($/1M 토큰) | 출력 ($/1M 토큰) | 캐시 할인 | 컨텍스트 창 | 최대 출력 |
|------|-----------------|-----------------|---------|-----------|---------|
| GPT-4.1-nano | **$0.10** | $0.40 | 75% | ~1M | 32K |
| GPT-4o-mini | $0.15 | $0.60 | 미확인 | 128K | 16K |
| GPT-5-mini | $0.25 | $2.00 | 미확인 | 400K | 128K |
| GPT-4.1-mini | $0.40 | $1.60 | 75% | ~1M | 32K |
| GPT-4.1 (full) | $2.00 | $8.00 | 75% | ~1M | 32K |
| GPT-5 (full) | $1.25 | $10.00 | 미확인 | 400K | 128K |

#### 월간 비용 추정 (에이전틱 코딩 시나리오)

에이전틱 코딩 워크플로에서는 멀티턴 대화로 인해 토큰 사용량이 급증한다. 하루 8시간 코딩 에이전트 운영 기준:

| 시나리오 | 일일 토큰 사용 | GPT-4o-mini 월비용 | GPT-4.1-mini 월비용 | GPT-5-mini 월비용 |
|---------|-------------|------------------|------------------|------------------|
| 경량 사용 (10회 세션) | 입력 5M + 출력 1M | ~$41 | ~$108 | ~$97 |
| 중간 사용 (30회 세션) | 입력 15M + 출력 3M | ~$122 | ~$324 | ~$293 |
| 고강도 사용 (100회 세션) | 입력 50M + 출력 10M | ~$405 | ~$1,080 | ~$975 |

### 3.2 오픈소스 모델 VRAM 요구사항 및 비용

| 모델 | 파라미터 | FP16 VRAM | Q8 VRAM | Q4_K_M VRAM | 24GB 적합 | 구조 |
|------|---------|----------|---------|------------|---------|------|
| Phi-4-Reasoning | 14B | ~28GB | ~14GB | ~8.5GB | 여유 | Dense |
| Qwen3-14B | 14B | ~28GB | ~14GB | ~9GB | 여유 | Dense |
| DeepSeek-R1-Distill-14B | 14B | ~28GB | ~14GB | ~9GB | 여유 | Dense |
| **Qwen3-30B-A3B** | 30B(3.3B 활성) | ~22GB | ~11GB | **~8GB** | **여유 (MoE)** | MoE |
| **GLM-4.7-Flash** | 30B(3B 활성) | ~24GB | ~12GB | **~8GB** | **적합 (MoE)** | MoE |
| Mistral Small 3.2 | 24B | ~48GB | ~24GB | ~14GB | 적합 | Dense |
| Qwen2.5-32B | 32B | ~64GB | ~32GB | ~18GB | 적합 | Dense |
| **Qwen3-32B** | 32B | ~64GB | ~32GB | **~19.8GB** | **적합** | Dense |
| Qwen2.5-Coder-32B | 32B | ~64GB | ~32GB | ~20GB | 적합 | Dense |
| DeepSeek-R1-Distill-32B | 32B | ~64GB | ~32GB | ~20GB | 적합 | Dense |
| Llama 3.3 70B | 70B | ~140GB | ~70GB | ~40GB | 불가 | Dense |

#### 로컬 실행 비용 (RTX 4090 기준)

| 항목 | 비용 |
|------|------|
| GPU 구매비 | RTX 4090 ~$1,600 (1회) |
| 전기세 (24시간 운영) | ~$30-50/월 (450W TDP 기준) |
| 전기세 (업무 시간만) | ~$10-15/월 |
| API 비용 | **$0** |
| 데이터 프라이버시 | **완전 로컬** |

---

## 4. 범용 벤치마크 비교

### 4.1 지식 이해 (MMLU, GPQA Diamond)

| 모델 | 유형 | MMLU | GPQA Diamond | 비고 |
|------|------|------|-------------|------|
| GPT-5-mini | API | N/A | **82.3%** | 추론 내장 |
| GPT-4.1-mini | API | **87.5%** | 65.0% | 1M 컨텍스트 |
| GPT-4o-mini | API | 82.0% | N/A | 기준선 |
| GPT-4.1-nano | API | 80.1% | 50.3% | 최경량 |
| Llama 3.3 70B | 로컬(경계) | **86.0%** | N/A | 단일 24GB 불가 |
| Phi-4 | 로컬 | **84.8%** | N/A | 14B 최강 |
| Qwen3-32B | 로컬 | ~84% | N/A | 32B Dense |
| Qwen2.5-72B | 로컬(불가) | 86.1% | N/A | 단일 24GB 불가 |
| Qwen3-30B-A3B | 로컬 | 81.4% | N/A | MoE 효율 |
| Qwen3-14B | 로컬 | 81.1% | N/A | — |
| GLM-4.7-Flash | 로컬 | N/A | **75.2** | MoE |
| Mistral Small 3.2 | 로컬 | 80.5% | 46.1% | 24B |

**분석:**
- MMLU에서는 GPT-4.1-mini(87.5%)가 24GB 오픈소스 모델(Qwen3-32B ~84%, Phi-4 84.8%)을 약간 상회
- GPQA Diamond(대학원 수준)에서는 GPT-5-mini(82.3%)가 압도적이나, GLM-4.7-Flash(75.2%)도 상당한 수준
- **결론**: 범용 지식에서는 API 모델이 약간 우세하나, 격차가 3-5%p 수준으로 크지 않음

### 4.2 수학 추론 (MATH, AIME)

| 모델 | 유형 | AIME 2024 | AIME 2025 | MATH-500 | 비고 |
|------|------|----------|----------|---------|------|
| **GPT-5-mini** | API | N/A | **91.1%** | N/A | 추론 내장 |
| GPT-4.1-mini | API | 49.6% | 40.2% | N/A | 비추론 모델 |
| GPT-4.1-nano | API | 29.4% | N/A | N/A | 최경량 |
| **GLM-4.7-Flash** | 로컬 | N/A | **91.6** | N/A | MoE, 8GB |
| **Qwen3-30B-A3B** | 로컬 | N/A | **81.4%** | N/A | MoE, 8GB |
| **Qwen3-32B** | 로컬 | N/A | **79.1%** | N/A | Dense |
| **Qwen3-14B** | 로컬 | N/A | **76.3%** | **96.1%** | Reasoning 모드 |
| **DeepSeek-R1-Distill-32B** | 로컬 | **72.6%** | N/A | **94.3%** | 추론 특화 |
| DeepSeek-R1-Distill-14B | 로컬 | 69.7% | N/A | 93.9% | 경량 추론 |
| Phi-4-Reasoning | 로컬 | R1-671B 동급 | R1-671B 동급 | N/A | 14B |
| Phi-4 | 로컬 | N/A | N/A | 80.4% | 기본 |

**분석:**
- AIME 2025에서 GPT-5-mini(91.1%)와 GLM-4.7-Flash(91.6%)가 **사실상 동급**
- GPT-4.1-mini(40.2%)는 오픈소스 대비 현저히 낮음 (추론 모드 미지원)
- MATH-500에서 Qwen3-14B Reasoning(96.1%)과 DeepSeek-R1-Distill-32B(94.3%)가 최고 수준
- **결론**: 수학·추론에서는 24GB 오픈소스가 GPT-4.1-mini를 크게 상회하며, GPT-5-mini와도 동급

---

## 5. 코딩 성능 비교

### 5.1 HumanEval (함수 단위 코드 생성)

| 모델 | 유형 | HumanEval Pass@1 | 비고 |
|------|------|-----------------|------|
| **GLM-4.7** | 서버급 | **94.2%** | 비교 대상 중 최고 (Full 모델) |
| **Qwen2.5-Coder-32B** | 로컬 | **92.7%** | 코딩 특화, 24GB 가능 |
| Mistral Small 3.2 | 로컬 | 92.90% (Pass@5) | Pass@5 기준 |
| Llama 3.3 70B | 로컬(경계) | 88.4% | 단일 24GB 불가 |
| GPT-4o-mini | API | 87.2% | 0-shot |
| GPT-4.1-mini | API | ~90% 추정 | 공식 미공개 |
| Phi-4 | 로컬 | 82.6% | 14B |

**분석:**
- **GLM-4.7 Full(94.2%)이 비교 모델 중 HumanEval 최고** (서버급, 24GB 불가)
- 24GB GPU 실행 가능 모델 중에서는 Qwen2.5-Coder-32B(92.7%)가 최강
- GPT-4o-mini(87.2%) 대비 오픈소스가 5-7%p 우위
- GPT-4.1-mini는 공식 HumanEval 점수 미공개이나 ~90% 추정
- **결론**: 함수 단위 코드 생성에서는 오픈소스(GLM-4.7, Qwen2.5-Coder-32B)가 API mini 모델을 명확히 상회

### 5.2 SWE-bench Verified (실제 GitHub 이슈 해결)

SWE-bench Verified는 실제 오픈소스 프로젝트의 GitHub 이슈를 LLM이 자동으로 해결하는 능력을 평가한다. **에이전틱 코딩 능력의 가장 현실적인 척도**.

| 모델/에이전트 | 유형 | SWE-bench Verified | 비고 |
|-------------|------|------------------|------|
| GLM-5 (744B) | 서버급 | **77.8%** | Chatbot Arena ELO 1451 (1위) |
| TRAE Agent (2025.06) | 에이전트 | **75.2%** | 역대 최고 (해당 시점) |
| GPT-5 (full) | API | 74.9% | 플래그십 |
| **GLM-4.7 Full** | **서버급** | **73.8%** | 358B MoE, 24GB 불가 |
| DeepSeek V3.2 | API/서버 | 67.8% | 서버급 |
| **GLM-4.7-Flash** | **로컬(24GB)** | **59.2%** | **24GB GPU 최강** |
| GPT-4.1 (full) | API | 54.6% | 플래그십 |
| Qwen2.5 기반 에이전트 | 로컬/API | ~47% | 추정 |
| GPT-4o | API | 33.2% | 이전 세대 |
| GPT-4.5 | API | 28.0% | — |
| **GPT-4.1-mini** | **API** | **23.6%** | **mini 최강** |

**핵심 인사이트:**

```
GLM-4.7-Flash (24GB 로컬)  ████████████████████████████████  59.2%
GPT-4.1 (full, API)        ███████████████████████████       54.6%
GPT-4.1-mini (API)         ████████████                      23.6%

→ 24GB GPU 오픈소스가 GPT-4.1 full API 모델을 상회!
→ GPT-4.1-mini 대비 2.5배 성능!
```

**분석:**
- GLM-4.7-Flash(59.2%)는 GPT-4.1-mini(23.6%)의 **2.5배** 성능
- 더 나아가, GPT-4.1 full 모델(54.6%)보다도 **4.6%p 높음**
- 이는 8GB VRAM(Q4)에서 실행 가능한 모델이 $2.00/1M 입력 API를 상회한다는 의미
- **결론**: 실제 소프트웨어 엔지니어링에서 24GB GPU 로컬 실행이 API mini 모델을 압도

### 5.3 LiveCodeBench Pass@1 (경쟁 코딩, 2026년 3월)

| 모델 | 유형 | LiveCodeBench Pass@1 | 비고 |
|------|------|---------------------|------|
| Gemini 3 Pro | API | **91.7%** (SOTA) | 최고 성능 |
| Gemini 3 Flash (Reasoning) | API | 90.8% | — |
| DeepSeek V3.2 | API/서버 | 89.6% | — |
| Kimi K2.5 | API/서버 | 85.0% | 단일 24GB 불가 |
| **GLM-4.7-Flash** | **로컬(24GB)** | **84.9%** | **24GB 최강** |
| **Qwen3.5-27B** | **로컬(24GB)** | **80.7%** | 24GB 적합 |
| DeepSeek-R1-Distill-Llama-70B | 로컬(경계) | 57.5% | 오프로드 필요 |
| Qwen2.5-72B | 로컬(불가) | 55.5% | 단일 불가 |
| **GPT-4.1-mini** (Aider) | **API** | **31.6%** | Aider Polyglot |
| Qwen2.5-Coder-32B | 로컬 | 31.4% | 2407-2409 기간 |
| **GPT-4o-mini** (Aider) | **API** | **18.2%** | Aider Polyglot |

> 주의: GPT-4.1-mini와 GPT-4o-mini의 수치는 Aider Polyglot 벤치마크(코드 diff 정확도)이며, LiveCodeBench와 직접 비교 시 주의 필요. 하지만 전체적인 코딩 역량의 상대적 위치를 보여준다.

**분석:**
- GLM-4.7-Flash의 LiveCodeBench 84.9%는 Kimi K2.5(85.0%)에 근접하는 놀라운 수준
- 24GB GPU에서 실행 가능한 모델 중 LiveCodeBench 80%+ 달성 모델 존재
- GPT-4.1-mini의 Aider Polyglot 31.6%는 코딩 diff 정확도 기준으로, 실제 코딩 능력의 한계를 보여줌

### 5.4 Aider Polyglot (코드 diff 정확도, 다중 언어)

| 모델 | 유형 | Aider Polyglot | 변화 |
|------|------|---------------|------|
| GPT-5 (full) | API | **88.0%** | 플래그십 |
| GPT-4.1 (full) | API | 52.9% | — |
| **GPT-4.1-mini** | API | **31.6%** | GPT-4o-mini 대비 +73.6% |
| **GPT-4o-mini** | API | **18.2%** | 기준선 |
| GPT-4.1-nano | API | 9.8% | 최경량 한계 |

**OpenAI mini 계열 Aider 성능 진화:**

```
GPT-4.1-nano     █████                   9.8%
GPT-4o-mini      █████████               18.2%
GPT-4.1-mini     ████████████████        31.6%
GPT-4.1 (full)   ██████████████████████████  52.9%
GPT-5 (full)     ████████████████████████████████████████████  88.0%
```

### 5.5 코딩 벤치마크 종합 비교표

| 벤치마크 | GPT-4o-mini | GPT-4.1-mini | GPT-5-mini | Qwen2.5-Coder-32B | GLM-4.7 Full | GLM-4.7-Flash | Qwen3-32B |
|---------|------------|-------------|-----------|------------------|------------|-------------|----------|
| HumanEval | 87.2% | ~90% 추정 | N/A | **92.7%** | **94.2%** | N/A | N/A |
| Aider Polyglot | 18.2% | 31.6% | N/A | 73.7 | N/A | N/A | N/A |
| SWE-bench Verified | N/A | 23.6% | N/A | N/A | **73.8%** | **59.2%** | N/A |
| LiveCodeBench | N/A | N/A | N/A | 31.4%* | **84.9%** | **84.9%** | 70.7+ |
| LiveCodeBench v6 | N/A | N/A | N/A | N/A | **64.0** | **64.0** | N/A |

> *Qwen2.5-Coder-32B의 LiveCodeBench 31.4%는 2024년 7-9월 기간 데이터. 이후 업데이트에서 향상 가능.
> GLM-4.7 Full(358B MoE)은 서버급으로 24GB GPU 실행 불가. GLM-4.7-Flash(30B/3B 활성)가 24GB GPU 실행 가능 버전.

---

## 6. 멀티턴 에이전틱 성능 비교

에이전틱(Agentic) 성능은 LLM이 도구를 사용하고, 멀티턴 대화를 통해 복잡한 과제를 해결하는 능력을 의미한다. 이는 단순 벤치마크를 넘어서 실제 코딩 에이전트, AI 어시스턴트, 자동화 파이프라인에서의 실용적 성능을 반영한다.

### 6.1 도구 사용/함수 호출 (BFCL)

BFCL(Berkeley Function Calling Leaderboard)은 직렬, 병렬, 멀티턴 인터랙션 등 다양한 시나리오에서 함수 호출 능력을 평가한다.

> ⚠️ **[중요] DeepSeek 함수 호출 미지원**: DeepSeek-Coder-V2, DeepSeek V3, DeepSeek R1은 **공식적으로 함수 호출(function calling)을 지원하지 않는다.** 이는 LangGraph, AutoGen, CrewAI 등 에이전틱 프레임워크에서의 활용을 근본적으로 제한하며, GAIA 리더보드에서도 제외되는 원인이다. 에이전틱 파이프라인에 DeepSeek 계열을 고려할 경우, 프롬프트 기반 툴 호출 워크어라운드가 필요하며 신뢰성이 크게 낮아진다.

#### BFCL 전체 순위 (2025~2026 기준)

| 순위 | 모델 | BFCL 점수 | 버전 | 비고 |
|------|------|---------|------|------|
| **1** | **GLM-4.5 FC** | **70.85%** | 최신 | 전체 1위 |
| 2 | Claude Opus 4.1 | 70.36% | 최신 | 2위 |
| 3 | Claude Sonnet 4 | 70.29% | 최신 | 3위 |
| 7 | GPT-5 | 59.22% | 최신 | — |
| — | Llama 3.3-70B | **77.3%** | v2 (0-shot) | v2 기준 |
| — | Llama 3.1-405B | 81.1% | v2 | — |
| — | **DeepSeek V3/R1** | **미지원** | — | **함수 호출 공식 미지원** |
| — | **DeepSeek-Coder-V2** | **제한적** | — | **공식 미지원 선언** |

> 버전 주의: BFCL v2와 최신 버전은 평가 방식이 다르므로 직접 수치 비교에 주의.

#### BFCL-V4 (2026년 3월 기준, OpenAI 계열)

| 모델 | 유형 | BFCL-V4 점수 | 비고 |
|------|------|------------|------|
| Qwen3.5-122B-A10B | 로컬(경계)* | **72.2** | 24GB 경계 |
| **GPT-5-mini** | API | **55.5** | 추론 내장 |
| **GPT-4.1-mini** | API | **~52** | 추정 |

> *Qwen3.5-122B-A10B는 활성 파라미터 10B이므로 Q4 기준 ~25GB로 24GB 경계선

#### BFCL-V3 (24GB 적합 모델)

| 모델 | 유형 | BFCL-V3 도구 호출 | 24GB VRAM |
|------|------|----------------|---------|
| **Qwen3-32B** | 로컬 | **72.8** | ~19.8GB (Q4) |
| GLM-4.7-Flash | 로컬 | 79.5 (tau2-Bench) | ~8GB (Q4) |
| Mistral Small 3.2 | 로컬 | 강화됨 (수치 미공개) | ~14GB (Q4) |

**분석:**
- **GLM-4.5 FC가 BFCL 전체 1위(70.85%)**로 함수 호출 전문화 모델의 효과를 입증
- 24GB GPU에서 Qwen3-32B의 BFCL-V3 72.8은 GPT-5-mini의 BFCL-V4 55.5를 상회
- 단, BFCL 버전 차이(V3 vs V4)로 직접 비교에 주의 필요
- GLM-4.7-Flash의 tau2-Bench 79.5는 에이전트 도구 사용에서 최강급
- **DeepSeek 계열은 함수 호출 미지원으로 에이전틱 파이프라인에서 사실상 배제**

#### 도구 사용 기능 지원 비교

| 기능 | GPT-4o-mini | GPT-4.1-mini | GPT-5-mini | Qwen3-32B | GLM-4.7-Flash | Mistral Small 3.2 | DeepSeek V3/R1 |
|------|------------|-------------|-----------|----------|-------------|-----------------|--------------|
| 함수 호출 | 지원 | 지원 | 지원 | 지원 | 지원 | 지원 | **미지원** |
| 병렬 호출 | 지원 | 지원 | 지원 | 지원 | 미확인 | 지원 | **미지원** |
| JSON 모드 | 지원 | 지원 | 지원 | 지원 | 지원 | 지원 | 제한적 |
| 구조화 출력 | 지원 | 지원 | 지원 | 지원 | 지원 | 지원 | 제한적 |
| 추론 모드 | 없음 | 없음 | **있음** | **있음** | 있음 | 없음 | **있음** |
| 에이전트 적합성 | 양호 | 우수 | 우수 | 우수 | 우수 | 양호 | **제한** |

### 6.2 실제 소프트웨어 엔지니어링 (SWE-bench)

SWE-bench Verified는 에이전틱 코딩의 "금본위" 벤치마크이다. 실제 GitHub 이슈를 받아 코드를 수정하고 테스트를 통과시키는 전체 프로세스를 평가한다.

#### 전체 모델 SWE-bench Verified 순위 (2026년 3월)

| 순위 | 모델/에이전트 | SWE-bench Verified | 24GB 실행 | 비고 |
|------|-------------|------------------|---------|------|
| 1 | GLM-5 (744B) | **77.8%** | 불가 (서버급) | Chatbot Arena ELO 1451 |
| 2 | TRAE Agent | **75.2%** | N/A | 에이전트 시스템 |
| 3 | GPT-5 (full) | 74.9% | 불가 | $1.25/$10.00 |
| **4** | **GLM-4.7 Full** | **73.8%** | **불가 (358B MoE)** | 서버급 |
| 5 | DeepSeek V3.2 | 67.8% | 불가 | API/서버 |
| **6** | **GLM-4.7-Flash** | **59.2%** | **가능 (8GB Q4)** | **24GB GPU 최강, 무료** |
| 7 | GPT-4.1 (full) | 54.6% | 불가 | $2.00/$8.00 |
| 8 | Qwen2.5 기반 에이전트 | ~47% | 일부 가능 | — |
| 9 | GPT-4o | 33.2% | 불가 | — |
| 10 | GPT-4.5 | 28.0% | 불가 | — |
| **11** | **GPT-4.1-mini** | **23.6%** | **불가 (API)** | **$0.40/$1.60** |

#### 24GB GPU 실행 가능 모델의 SWE-bench 비교

```
GLM-4.7-Flash      ██████████████████████████████  59.2%  (Q4: 8GB)
Qwen3-Coder 계열    ███████████████████████████████████  69.6%  (별도 Coder 변형)
Qwen2.5 에이전트     ████████████████████████  ~47%   (추정)
GPT-4.1-mini (API)  ████████████  23.6%             (참고: API 모델)
```

**핵심 인사이트:**
1. GLM-4.7-Flash(24GB 실행 가능)는 $2/1M 토큰의 GPT-4.1 full보다도 SWE-bench에서 높은 점수
2. 24GB GPU의 8GB VRAM만으로 GPT-4.1-mini의 2.5배 성능 달성
3. GLM-4.7 Full(73.8%, 서버급)은 GPT-5 full(74.9%)에 근접하며, GLM-5(77.8%)는 이를 이미 초과
4. Qwen3-Coder 계열(69.6%)까지 포함하면 24GB GPU에서도 GPT-5 full(74.9%) 근접 가능

### 6.3 에이전틱 태스크 (GAIA)

GAIA는 멀티스텝 추론, 도구 사용, 멀티모달 처리를 종합 평가하는 에이전틱 벤치마크이다.

| 모델 | GAIA 성능 | 비고 |
|------|---------|------|
| GPT-4o-mini (with tools) | ~34.5% (165개 중 57개 해결) | 비용 ~$5 |
| GPT-4.1 계열 | GPT-4o-mini 대비 크게 향상 | OpenAI 공식 발표 |
| GPT-5 (full) | 최상위 | — |

**GAIA 관련 OpenAI 에이전틱 개선 사항 (GPT-4.1 계열):**
- 불필요한 파일 변경: 9%(GPT-4o) -> 2%(GPT-4.1)
- diff 형식 준수율 대폭 향상
- 멀티턴 일관성 향상
- 지시 따르기 신뢰성 향상

**분석:**
- GAIA에서는 GPT-4.1 계열이 멀티턴 에이전틱 태스크에서 GPT-4o 대비 크게 향상
- 24GB 오픈소스 모델의 GAIA 공식 점수는 부재하나, SWE-bench 및 도구 호출 성능에서 유추 시 경쟁력 있음
- GLM-4.7-Flash의 tau2-Bench 79.5는 에이전트 도구 사용에서 상용 모델과 경쟁 가능한 수준

### 6.4 멀티턴 에이전틱 성능 종합

| 평가 항목 | GPT-4o-mini | GPT-4.1-mini | GPT-5-mini | GLM-4.7-Flash | Qwen3-32B | Qwen2.5-72B | Qwen2.5-32B |
|---------|------------|-------------|-----------|-------------|----------|------------|------------|
| SWE-bench | N/A | 23.6% | N/A | **59.2%** | N/A | N/A | N/A |
| 도구 호출 (BFCL) | N/A | ~52 | 55.5 | 79.5 (tau2) | **72.8** | N/A | N/A |
| MT-bench (/10) | ~8.5 추정 | N/A | N/A | N/A | N/A | **9.35** | **9.20** |
| 멀티턴 안정성 | 보통 | 우수 | 우수 | 우수 | 우수 | 우수 | 우수 |
| 코드 diff 정확도 | 18.2% | 31.6% | N/A | N/A | N/A | N/A | N/A |
| 지시 따르기 | N/A | 84.1% | N/A | N/A | N/A | N/A | N/A |
| 추론 모드 | 없음 | 없음 | 있음 | 있음 | 있음 | 없음 | 없음 |
| 컨텍스트 창 | 128K | 1M | 400K | 128K | 128K | 128K | 128K |

> **MT-bench 참고**: Qwen2.5-72B(9.35)와 Qwen2.5-32B(9.20)은 멀티턴 대화 품질에서 최고 수준의 오픈소스 성능을 보인다. MT-bench는 8개 범주(수학, 코딩, 추론, 역할극 등)의 멀티턴 대화를 GPT-4가 10점 만점으로 평가하는 벤치마크로, 대화 일관성 및 지시 따르기 능력의 척도다.

### 6.5 에이전틱 성능 격차 (AgentBench)

AgentBench(ICLR 2024)는 OS 제어, 데이터베이스, 웹 쇼핑, 웹 브라우징 등 8개 환경에서 LLM 에이전트의 종합적인 멀티턴 상호작용 능력을 측정한다.

#### 오픈소스 vs 상용 모델 에이전틱 격차

| 모델 유형 | AgentBench 평균 점수 | 비고 |
|---------|------------------|------|
| **상용 모델** (GPT-4 등) | **2.32** | House Holding 78% 성공률 |
| **오픈소스 평균** (≤70B) | **0.51** | 상용 대비 **4.5배 낮음** |
| 최고 오픈소스 (CodeLlama-34B, 2024년 기준) | 0.96 | GPT-3.5-turbo에도 미치지 못함 |

```
상용 모델 (GPT-4 등)    ██████████████████████████████  2.32
오픈소스 평균 (≤70B)    ███                             0.51
오픈소스 최고           ██████                          0.96

→ 2024년 기준 에이전틱 태스크에서 상용-오픈소스 격차가 4.5배
→ 2025~2026년 Qwen2.5, GLM-4.7 등장으로 이 격차가 빠르게 좁혀지는 중
```

**맥락**: 2024년 AgentBench 기준 격차는 컸으나, 2025~2026년 GLM-4.7(SWE-bench 73.8%), Qwen2.5-Coder-32B(SWE-bench ~47%) 등의 등장으로 에이전틱 태스크에서 오픈소스가 빠르게 추격 중이다. 특히 코딩 에이전트(SWE-bench) 영역에서는 오픈소스가 상용 mini 모델을 역전했다.

### 6.6 실제 컴퓨터 사용 에이전트 성능 추이 (OSWorld / WebArena)

에이전틱 AI의 실제 컴퓨터 및 웹 조작 능력은 2023~2026년 사이 급격히 향상되었다.

#### OSWorld (실제 컴퓨터 태스크, Ubuntu/Windows/macOS)

OSWorld는 369개의 실제 컴퓨터 태스크(파일 관리, 앱 제어, 멀티스텝 업무)를 수행하는 멀티모달 에이전트 성능을 평가한다.

| 모델/에이전트 | 성공률 | 시점 | 비고 |
|------------|--------|------|------|
| 인간 기준 | 72.4% | — | 기준선 |
| **GPT-4o (vanilla)** | **12.2%** | **2024** | **기준선** |
| OpenAI CUA | 32.6% | 2024 | 50-step |
| Claude 3.7 | 28.0% | 2025.02 | 100-step |
| Agent S2 (Claude 3.7 기반) | 34.5% | 2025 | 오픈소스 에이전트 |
| **GPT-5.1** | **61.4%** | **2025** | — |
| **GPT-5.4** | **75.0%** | **2025** | **인간 수준 초과** |

```
GPT-4o (2024)    ███████           12.2%   ← 시작점
GPT-5.1 (2025)   █████████████████████████████████████████████  61.4%
GPT-5.4 (2025)   ████████████████████████████████████████████████████  75.0%
인간 기준         ████████████████████████████████████████████████  72.4%

→ 2년 만에 GPT-4o 12.2% → GPT-5.4 75.0%: 인간 수준 초과
```

> 오픈소스 24GB 모델들(GPT-4o-mini, Qwen2.5 등)은 멀티모달 제약 또는 성능 미달로 OSWorld 공식 측정값 없음. 이 영역에서는 아직 최신 상용 모델이 우위.

#### WebArena (실제 웹 브라우징 에이전트)

WebArena는 전자상거래, 소셜 포럼, 코드 저장소 등 4개 도메인의 812개 웹 태스크로 구성된다.

| 에이전트/모델 | 성공률 | 시점 | 비고 |
|------------|--------|------|------|
| **GPT-4 (vanilla)** | **~14%** | **2023** | **초기 기준선** |
| OpenAI Operator | 49.0% | 2025 | — |
| Gemini 2.5 Pro | 54.8%+ | 2025 | — |
| **IBM CUGA** | **61.7%** | **2025.02** | **단일 에이전트 SOTA** |

```
2023년  ████                    14%
2025년  ████████████████████████████████████████  61.7%

→ WebArena 성공률: 2년 만에 14% → 61.7% (4.4배 향상)
```

**분석**: OSWorld와 WebArena 모두 2023~2025년 사이 에이전틱 AI의 성공률이 극적으로 향상되었다. 그러나 이 영역은 아직 대형 상용 모델의 영역이며, 24GB GPU 오픈소스 모델은 주로 코딩 에이전트(SWE-bench) 영역에서 경쟁력을 확보하고 있다.

---

## 7. 용도별 추천

### 7.1 API 과금 방식 (OpenAI 모델 선택 가이드)

API를 통해 OpenAI 모델을 사용하는 경우, 용도에 따른 최적 선택:

#### 7.1.1 비용 최우선, 단순 태스크

| 추천 | 모델 | 이유 |
|------|------|------|
| 1순위 | **GPT-4.1-nano** | $0.10/1M 최저가, 1M 컨텍스트, 분류/자동완성 최적 |
| 2순위 | GPT-4o-mini | $0.15/1M, 검증된 안정성 |

#### 7.1.2 범용 코딩 에이전트 (중간 비용)

| 추천 | 모델 | 이유 |
|------|------|------|
| 1순위 | **GPT-4.1-mini** | Aider 31.6%, 1M 컨텍스트, 강화된 diff 준수 |
| 2순위 | GPT-5-mini | 내장 추론, GPQA 82.3%, 더 나은 추론 |

#### 7.1.3 고난도 수학/추론

| 추천 | 모델 | 이유 |
|------|------|------|
| 1순위 | **GPT-5-mini** | AIME 2025 91.1%, 내장 추론 |
| 비추천 | GPT-4.1-mini | AIME 40.2%로 추론 한계 |

#### 7.1.4 장문 컨텍스트 처리 (코드베이스 분석)

| 추천 | 모델 | 이유 |
|------|------|------|
| 1순위 | **GPT-4.1-mini** | **1M 토큰 컨텍스트**, 32K 출력 |
| 2순위 | GPT-5-mini | 400K 컨텍스트, 128K 출력 |

#### 7.1.5 OpenAI 모델 선택 플로우차트

```
시작
  │
  ├─ 비용이 가장 중요? ─────────── YES ──→ GPT-4.1-nano ($0.10/1M)
  │                                         │
  │                                         ├─ 코딩이 필요? → YES → GPT-4o-mini ($0.15/1M)
  │                                         └─ 분류/태깅만? → GPT-4.1-nano 유지
  │
  ├─ 추론/수학 필요? ────────────── YES ──→ GPT-5-mini ($0.25/1M)
  │
  ├─ 1M 컨텍스트 필요? ──────────── YES ──→ GPT-4.1-mini ($0.40/1M)
  │
  └─ 코딩 에이전트 범용? ─────────── YES ──→ GPT-4.1-mini ($0.40/1M)
```

### 7.2 로컬 실행 (24GB GPU 모델 선택 가이드)

RTX 3090/4090(24GB VRAM)에서 로컬 실행하는 경우:

#### 7.2.1 코딩 에이전트 / SWE 엔지니어링

| 순위 | 모델 | VRAM | 핵심 성능 | 이유 |
|------|------|------|---------|------|
| **1** | **GLM-4.7-Flash** | 8GB (Q4) / 24GB (FP16) | SWE-bench **59.2%** | 에이전틱 코딩 최강 |
| 2 | Qwen2.5-Coder-32B | 20GB (Q4) | HumanEval **92.7%** | 코드 생성 특화 |
| 3 | Qwen3-32B | 19.8GB (Q4) | 범용 코딩 + 추론 | 유연성 |

#### 7.2.2 수학/과학 추론

| 순위 | 모델 | VRAM | 핵심 성능 | 이유 |
|------|------|------|---------|------|
| **1** | **DeepSeek-R1-Distill-Qwen-32B** | 20GB (Q4) | AIME 72.6%, MATH 94.3% | 추론 특화 최강 |
| 2 | Qwen3-14B (Reasoning) | 9GB (Q4) | AIME 76.3%, MATH 96.1% | 경량 추론 |
| 3 | Phi-4-Reasoning | 8.5GB (Q4) | R1-671B 동급 | 초경량 추론 |

#### 7.2.3 범용 (대화 + 코딩 + 추론)

| 순위 | 모델 | VRAM | 이유 |
|------|------|------|------|
| **1** | **Qwen3-32B** | 19.8GB (Q4) | 추론/일반 모드 전환, Apache 2.0 |
| 2 | Mistral Small 3.2 | 14GB (Q4) | 130K 컨텍스트, 강화된 함수 호출 |
| 3 | Qwen2.5-32B | 18GB (Q4) | 안정적 범용 |

#### 7.2.4 고속 추론 / 실시간 응답

| 순위 | 모델 | VRAM | 속도 | 이유 |
|------|------|------|------|------|
| **1** | **Qwen3-30B-A3B** | 8GB (Q4) | **196 tok/s** | MoE 효율 최고 |
| 2 | GLM-4.7-Flash | 8GB (Q4) | ~95 tok/s | MoE, SWE-bench 겸비 |
| 3 | Phi-4 (Q4) | 8.5GB (Q4) | 빠름 | 소형, 저지연 |

#### 7.2.5 에이전트 도구 사용 / 함수 호출

| 순위 | 모델 | VRAM | 핵심 성능 | 이유 |
|------|------|------|---------|------|
| **1** | **GLM-4.7-Flash** | 8GB (Q4) | tau2-Bench 79.5 | 에이전트 도구 최강 |
| 2 | Qwen3-32B | 19.8GB (Q4) | BFCL-V3 72.8 | 도구 호출 + 범용 |
| 3 | Mistral Small 3.2 | 14GB (Q4) | 강화된 FC | 구조화 출력 |

#### 7.2.6 로컬 모델 선택 플로우차트

```
시작
  │
  ├─ SWE 코딩 에이전트? ─────────── YES ──→ GLM-4.7-Flash (8-24GB)
  │
  ├─ 코드 생성 특화? ─────────────── YES ──→ Qwen2.5-Coder-32B (20GB)
  │
  ├─ 수학/추론 특화? ─────────────── YES ──→ DeepSeek-R1-Distill-32B (20GB)
  │                                          │
  │                                          └─ VRAM 제한? → Phi-4-Reasoning (8.5GB)
  │
  ├─ 속도 최우선? ────────────────── YES ──→ Qwen3-30B-A3B (8GB, 196 tok/s)
  │
  ├─ 도구 사용 에이전트? ──────────── YES ──→ GLM-4.7-Flash (8GB)
  │
  └─ 범용 + 유연성? ──────────────── YES ──→ Qwen3-32B (19.8GB)
```

---

## 8. 트레이드오프 분석: API vs 로컬

### 8.1 성능 비교 매트릭스

| 평가 차원 | API (OpenAI mini) | 로컬 (24GB GPU) | 승자 |
|---------|-----------------|---------------|------|
| **SWE-bench Verified** | GPT-4.1-mini: 23.6% | GLM-4.7-Flash: **59.2%** | **로컬** (2.5x) |
| **LiveCodeBench** | GPT-4.1-mini Aider: 31.6% | GLM-4.7-Flash: **84.9%** | **로컬** (2.7x) |
| **HumanEval** | GPT-4o-mini: 87.2% | GLM-4.7: **94.2%** (Qwen2.5-Coder: 92.7%) | **로컬** |
| **AIME 2025** | GPT-5-mini: **91.1%** | GLM-4.7-Flash: 91.6 | **동급** |
| **GPQA Diamond** | GPT-5-mini: **82.3%** | GLM-4.7-Flash: 75.2 | **API** |
| **MMLU** | GPT-4.1-mini: **87.5%** | Qwen3-32B: ~84% | **API** (소폭) |
| **도구 호출** | GPT-5-mini: 55.5 (BFCL-V4) | Qwen3-32B: 72.8 (BFCL-V3) | 조건부 |
| **컨텍스트 창** | GPT-4.1-mini: **1M** | Qwen3-32B: 128K | **API** |
| **추론 속도** | GPT-5-mini: ~200 tok/s | Qwen3-30B-A3B: **196 tok/s** | **동급** |

### 8.2 비용 비교

#### 시나리오: 개인 개발자, 일일 8시간 에이전틱 코딩

| 항목 | API (GPT-4.1-mini) | API (GPT-5-mini) | 로컬 (RTX 4090) |
|------|-------------------|-----------------|-----------------|
| 초기 투자 | $0 | $0 | ~$1,600 (GPU) |
| 월간 비용 (중간 사용) | ~$324 | ~$293 | ~$15 (전기) |
| 연간 비용 | ~$3,888 | ~$3,516 | ~$1,780 (첫해) / ~$180 (이후) |
| 2년 총비용 | ~$7,776 | ~$7,032 | ~$1,960 |
| **3년 총비용** | **~$11,664** | **~$10,548** | **~$2,140** |
| 데이터 프라이버시 | 서버 전송 | 서버 전송 | **완전 로컬** |
| 인터넷 필요 | 필수 | 필수 | **불필요** |

#### 시나리오: 팀 (5인), 고강도 사용

| 항목 | API (GPT-4.1-mini) | 로컬 (RTX 4090 x5) |
|------|-------------------|-------------------|
| 초기 투자 | $0 | ~$8,000 |
| 월간 비용 | ~$5,400 | ~$75 (전기) |
| 연간 비용 | ~$64,800 | ~$8,900 (첫해) / ~$900 (이후) |
| **3년 총비용** | **~$194,400** | **~$10,700** |

### 8.3 비기능적 트레이드오프

| 차원 | API | 로컬 | 승자 |
|------|-----|------|------|
| **설정 복잡도** | 간단 (API 키) | 복잡 (GPU, 드라이버, 모델 다운로드) | **API** |
| **데이터 프라이버시** | 서버 전송 필요 | 완전 로컬 처리 | **로컬** |
| **가용성** | OpenAI 인프라 의존 | 자체 하드웨어 | **로컬** |
| **확장성** | 무제한 (비용 비례) | GPU 수에 제한 | **API** |
| **최신 모델** | 즉시 접근 | 모델 다운로드/변환 필요 | **API** |
| **커스터마이징** | 제한적 (fine-tuning) | 자유 (LoRA, 양자화 등) | **로컬** |
| **오프라인 사용** | 불가 | 가능 | **로컬** |
| **레이턴시** | 네트워크 지연 + 서버 큐 | GPU 직접 실행 | **로컬** |
| **규제/보안** | 데이터 유출 우려 | 에어갭 환경 가능 | **로컬** |

### 8.4 핵심 트레이드오프 결론

```
┌──────────────────────────────────────────────────────────┐
│                    API vs 로컬 판단 기준                    │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  API를 선택해야 하는 경우:                                  │
│  ✓ 1M+ 컨텍스트 창이 필수적 (코드베이스 전체 분석)            │
│  ✓ 초기 투자 없이 빠르게 시작해야 하는 경우                   │
│  ✓ 사용량이 매우 낮은 경우 (월 $50 이하)                     │
│  ✓ 최신 플래그십 성능이 필요한 경우 (GPT-5 full 등)          │
│                                                          │
│  로컬을 선택해야 하는 경우:                                  │
│  ✓ 에이전틱 코딩이 핵심 유즈케이스 (SWE-bench 중시)          │
│  ✓ 월 $100 이상 API 비용 발생 예상                         │
│  ✓ 데이터 프라이버시/보안이 중요 (금융, 의료, 군사)           │
│  ✓ 오프라인 환경에서 사용해야 하는 경우                       │
│  ✓ 장기적 비용 절감이 필요한 경우 (3년 기준 5-10x 절감)      │
│  ✓ GPU를 이미 보유하고 있는 경우                            │
│                                                          │
│  하이브리드 전략 (최적):                                    │
│  ✓ 코딩 에이전트: 로컬 GLM-4.7-Flash / Qwen3-32B          │
│  ✓ 장문 분석: API GPT-4.1-mini (1M 컨텍스트)              │
│  ✓ 고난도 추론: 로컬 DeepSeek-R1-Distill-32B              │
│  ✓ 플래그십 필요 시: API GPT-5 full / Claude Opus         │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

---

## 9. 결론

### 9.1 핵심 발견

본 보고서의 분석을 통해 도출된 핵심 결론은 다음과 같다:

#### 발견 1: 에이전틱 코딩에서 24GB GPU 오픈소스가 API mini 모델을 압도

- SWE-bench Verified 기준: GLM-4.7-Flash(59.2%) vs GPT-4.1-mini(23.6%) = **2.5배 격차**
- 이는 단순히 "비슷한 수준"이 아니라, 로컬 모델이 API mini 모델을 **질적으로 초월**하는 수준
- GLM-4.7-Flash는 GPT-4.1 full($2.00/1M 입력)보다도 높은 SWE-bench 점수를 8GB VRAM으로 달성
- GLM-4.7 Full(73.8%, 서버급)과 GLM-5(77.8%)는 GPT-5 full(74.9%)과 동등 또는 초과

#### 발견 2: 수학/추론에서는 GPT-5-mini와 오픈소스가 동급

- AIME 2025: GPT-5-mini 91.1% vs GLM-4.7-Flash 91.6
- GPT-5-mini의 내장 추론 능력은 강력하나, 오픈소스도 이미 동일 수준에 도달
- GPT-4.1-mini(AIME 40.2%)는 오픈소스 대비 현저히 낮음 (추론 모드 미지원)

#### 발견 3: 컨텍스트 창에서만 API가 확실한 우위

- GPT-4.1-mini의 1M 컨텍스트는 현재 24GB 오픈소스(대부분 128K)로 대체 불가
- 대규모 코드베이스 전체 분석 등 장문 컨텍스트가 필수적인 경우 API가 유리
- 단, 대부분의 에이전틱 코딩 태스크는 128K 이내에서 처리 가능

#### 발견 4: 비용 효율성에서 로컬이 압도적

- 월 $100 이상 API 사용 시 RTX 4090 투자가 6개월 내 회수
- 3년 기준 로컬이 API 대비 **5-10배 저렴**
- 데이터 프라이버시, 오프라인 사용 등 부가 가치까지 고려하면 격차 확대

#### 발견 5: MoE 아키텍처가 소비자 GPU 생태계를 변혁

- GLM-4.7-Flash, Qwen3-30B-A3B 등 30B 총 파라미터 / 3B 활성 MoE 모델이 8GB VRAM으로 실행 가능
- 이전에는 32B Dense 모델이 24GB GPU의 한계였으나, MoE로 인해 8GB GPU에서도 고성능 달성
- RTX 4090에서 Qwen3-30B-A3B가 196 tok/s를 기록하며, API 수준의 속도 제공

#### 발견 6: DeepSeek 함수 호출 미지원 — 에이전틱 파이프라인의 결정적 장벽

- DeepSeek-Coder-V2, DeepSeek V3, DeepSeek R1은 **공식적으로 함수 호출을 지원하지 않음**
- 이로 인해 LangGraph, AutoGen, CrewAI 등 주요 에이전틱 프레임워크에서 활용이 근본적으로 제한됨
- GAIA 리더보드에서도 DeepSeek 계열은 제외됨
- 코딩 성능(HumanEval 90.2%, LiveCodeBench 43.4%)은 우수하나, 에이전틱 유즈케이스에서는 사용 시 주의 필요
- **단순 코드 생성에는 유용하나, 에이전틱 파이프라인 구축에는 적합하지 않음**

#### 발견 7: 에이전틱 AI의 급격한 성장 — 코딩 에이전트가 가장 빠른 성숙

- AgentBench 기준 2024년 오픈소스(0.51) vs 상용(2.32)의 4.5배 격차가 2025~2026년 빠르게 좁혀짐
- OSWorld: GPT-4o 12.2%(2024) → GPT-5.4 75.0%(2025)로 인간 수준 초과
- WebArena: 14%(2023) → 61.7%(2025)로 4.4배 향상
- 단, 컴퓨터/웹 조작 영역은 여전히 대형 상용 모델 우위; 24GB 오픈소스의 경쟁력은 코딩 에이전트 영역에 집중

#### 발견 8: 함수 호출 특화 모델의 부상

- GLM-4.5 FC가 BFCL 전체 1위(70.85%)를 차지하며 함수 호출 전문화의 효과 입증
- Llama 3.3 70B도 BFCL v2에서 77.3%로 강력한 함수 호출 성능 보유
- 함수 호출 지원 여부가 에이전틱 모델 선택의 1차 필터가 됨

### 9.2 최종 추천 요약

#### 에이전틱 코딩 에이전트 구축 시

| 조건 | 추천 | 이유 |
|------|------|------|
| 24GB GPU 보유 | **GLM-4.7-Flash** | SWE-bench 59.2%, 8GB 실행, 도구 사용 최강 |
| 24GB GPU 보유 + 범용 | **Qwen3-32B** | 추론/코딩/대화 통합, BFCL 72.8 |
| GPU 없음, 빠른 시작 | **GPT-4.1-mini** | 1M 컨텍스트, Aider 31.6%, API 즉시 사용 |
| GPU 없음, 추론 필요 | **GPT-5-mini** | AIME 91.1%, 내장 추론, 128K 출력 |
| 비용 최소화 | **GPT-4.1-nano** 또는 RTX 4090 투자 | 상황에 따라 판단 |

#### 에이전틱 모델 선택 시 주의사항

| 모델 | 에이전틱 적합성 | 이유 |
|------|-------------|------|
| GLM-4.7-Flash | **최우수** | SWE-bench 59.2%, 함수 호출 지원, 8GB 실행 |
| Qwen3-32B | **우수** | BFCL 72.8, 범용 에이전트 |
| GPT-4.1-mini | **우수** | 1M 컨텍스트, 안정적 함수 호출 |
| Mistral Small 3.2 | **양호** | 함수 호출 지원, 130K 컨텍스트 |
| Llama 3.3 70B | **양호** | BFCL 77.3%, 단 24GB 단일 GPU 불가 |
| **DeepSeek V3/R1** | **제한** | **함수 호출 미지원 — 에이전틱 파이프라인 비권장** |
| **DeepSeek-Coder-V2** | **제한** | **함수 호출 공식 미지원** |

#### 한 줄 요약

```
24GB GPU가 있다면 → GLM-4.7-Flash + Qwen3-32B 조합이 최강
API만 사용한다면 → GPT-4.1-mini (코딩) + GPT-5-mini (추론) 조합이 최적
하이브리드 전략  → 코딩은 로컬, 장문 분석은 API, 이것이 2026년의 정답
DeepSeek 사용 시 → 코드 생성은 가능하나 에이전틱 파이프라인(함수 호출)에는 비권장
```

### 9.3 향후 전망

2026년 3월 현재, LLM 생태계의 주요 트렌드:

1. **MoE 아키텍처의 대중화**: 소비자 GPU에서 실행 가능한 고성능 MoE 모델이 계속 등장할 전망
2. **SWE-bench 경쟁 가속**: GLM-4.7-Flash(59.2%) 이후 24GB GPU에서 70%+ 달성 모델 출현 예상; GLM-5(77.8%)는 이미 서버급에서 달성
3. **API 가격 하락 압력**: 오픈소스의 성능 향상이 API 가격에 하방 압력을 가할 것
4. **Qwen3.5 시리즈**: Qwen3.5-35B-A3B(262K 컨텍스트)가 24GB 경계선에서 새로운 선택지 제공
5. **하이브리드 아키텍처**: 로컬 + API를 결합한 에이전트 프레임워크가 표준이 될 전망
6. **함수 호출 지원 표준화**: DeepSeek 계열의 함수 호출 미지원 문제가 다음 세대에서 해결될 전망; 함수 호출은 에이전틱 모델의 필수 요건으로 자리잡음
7. **컴퓨터 사용 에이전트 급성장**: OSWorld 12.2%→75.0%, WebArena 14%→61.7%의 추이로 볼 때, 2026년 말 로컬 모델의 컴퓨터 조작 에이전트 진입 예상
8. **함수 호출 특화 모델**: GLM-4.5 FC(BFCL 1위)처럼 특정 에이전틱 능력에 특화된 경량 모델이 증가할 전망

---

## 10. 참고 자료

### OpenAI 공식 자료

- [Introducing GPT-4.1 in the API | OpenAI](https://openai.com/index/gpt-4-1/) - GPT-4.1 패밀리 공식 발표 (2025.04)
- [GPT-4o mini: advancing cost-efficient intelligence | OpenAI](https://openai.com/index/gpt-4o-mini-advancing-cost-efficient-intelligence/) - GPT-4o-mini 공식 발표 (2024.07)
- [Introducing GPT-5 | OpenAI](https://openai.com/index/introducing-gpt-5/) - GPT-5/GPT-5-mini 공식 발표 (2025.08)
- [OpenAI API Pricing](https://openai.com/api/pricing/) - 공식 가격 페이지

### 오픈소스 모델 공식 자료

- [Qwen3 Technical Report (arXiv, 2025.05)](https://arxiv.org/pdf/2505.09388) - Qwen3 전체 시리즈 공식 보고서
- [Qwen2.5-Coder Technical Report (arXiv)](https://arxiv.org/html/2409.12186v3) - Qwen2.5-Coder 공식 보고서
- [DeepSeek-R1 Technical Report (arXiv)](https://arxiv.org/html/2501.12948v1) - DeepSeek-R1 공식 보고서
- [Phi-4-Reasoning Technical Report (Microsoft)](https://www.microsoft.com/en-us/research/wp-content/uploads/2025/04/phi_4_reasoning.pdf)
- [GLM-5 공식 블로그 (Z.ai)](https://z.ai/blog/glm-5) - GLM-5 및 GLM-4.7-Flash 발표

### 모델 카드 (HuggingFace)

- [Qwen/Qwen3-32B](https://huggingface.co/Qwen/Qwen3-32B)
- [deepseek-ai/DeepSeek-R1-Distill-Qwen-32B](https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-32B)
- [zai-org/GLM-4.7-Flash](https://huggingface.co/zai-org/GLM-4.7-Flash)
- [microsoft/phi-4](https://huggingface.co/microsoft/phi-4)
- [mistralai/Mistral-Small-3.2-24B-Instruct-2506](https://huggingface.co/mistralai/Mistral-Small-3.2-24B-Instruct-2506)

### 벤치마크 리더보드

- [LiveCodeBench Leaderboard](https://livecodebench.github.io/leaderboard.html) - 코딩 리더보드
- [SWE-bench Results](https://www.swebench.com/viewer.html) - 소프트웨어 엔지니어링 벤치마크
- [Open LLM Leaderboard (HuggingFace)](https://huggingface.co/open-llm-leaderboard) - 오픈소스 LLM 공식 리더보드
- [Artificial Analysis LLM Leaderboard](https://artificialanalysis.ai/leaderboards/models) - 종합 분석 리더보드
- [AIME 2025 Benchmark Leaderboard](https://artificialanalysis.ai/evaluations/aime-2025)

### 벤치마크 분석 및 가격 비교

- [GPT-4.1 mini: Pricing, Context Window, Benchmarks | llm-stats.com](https://llm-stats.com/models/gpt-4.1-mini-2025-04-14)
- [GPT-5 mini: Pricing, Context Window, Benchmarks | llm-stats.com](https://llm-stats.com/models/gpt-5-mini-2025-08-07)
- [GPT-4.1 mini - Intelligence, Performance & Price Analysis | Artificial Analysis](https://artificialanalysis.ai/models/gpt-4-1-mini)
- [Best Local LLMs for 24GB VRAM (LocalLLM.in)](https://localllm.in/blog/best-local-llms-24gb-vram)
- [GLM-4.7-Flash Review (llm-stats.com)](https://llm-stats.com/blog/research/glm-4.7-flash-launch)

### 심층 분석 기사

- [GPT-4.1 Released: Benchmarks, Performance | Helicone](https://www.helicone.ai/blog/gpt-4.1-full-developer-guide)
- [GPT-4.1: Features, Access, GPT-4o Comparison | DataCamp](https://www.datacamp.com/blog/gpt-4-1)
- [Mistral Small 3.1 vs 3.2 Comparison | VentureBeat](https://venturebeat.com/ai/mistral-just-updated-its-open-source-small-model-from-3-1-to-3-2-heres-why)
- [Kimi K2.5 Tech Blog (kimi.com)](https://www.kimi.com/blog/kimi-k2-5)
- [Home GPU LLM Leaderboard | Awesome Agents](https://awesomeagents.ai/leaderboards/home-gpu-llm-leaderboard/)

### 에이전틱 벤치마크 자료

- [10 AI agent benchmarks | Evidently AI](https://www.evidentlyai.com/blog/ai-agent-benchmarks)
- [GAIA: The LLM Agent Benchmark | Towards Data Science](https://towardsdatascience.com/gaia-the-llm-agent-benchmark-everyones-talking-about/)
- [HAL: GAIA Leaderboard](https://hal.cs.princeton.edu/gaia)
- [SWE-bench Verified | OpenAI](https://openai.com/index/introducing-swe-bench-verified/)
- [AgentBench: Evaluating LLMs as Agents (THUDM)](https://github.com/THUDM/AgentBench) - 8개 환경 에이전트 벤치마크
- [OSWorld: Benchmarking Multimodal Agents](https://os-world.github.io/) - 컴퓨터 사용 에이전트 벤치마크
- [WebArena: A Realistic Web Environment for Building Agents](https://webarena.dev/) - 웹 브라우징 에이전트 벤치마크
- [Berkeley Function Calling Leaderboard (BFCL)](https://gorilla.cs.berkeley.edu/leaderboard.html) - 함수 호출 리더보드
- [DeepSeek Function Calling Limitation (DeepSeek-Coder-V2 논문)](https://arxiv.org/html/2406.11931v1) - 함수 호출 미지원 근거

---

*본 보고서는 2026년 3월 9일 기준 공개된 벤치마크 데이터와 기술 문서를 바탕으로 작성되었습니다. AI 모델 생태계는 빠르게 변화하므로, 최신 수치는 위 리더보드 링크에서 직접 확인하시기 바랍니다. 일부 벤치마크 점수는 제3자 분석에 의존하며, 벤치마크 버전 차이(BFCL-V3 vs V4, LiveCodeBench 버전 등)로 인해 직접 비교에 주의가 필요합니다.*
