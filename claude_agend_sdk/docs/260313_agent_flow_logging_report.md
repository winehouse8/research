# OpenAI Agents SDK + 로컬 모델 에이전트 플로우 로깅 & 자동 프롬프트 개선 보고서

> **목적**: 멀티턴 에이전트 플로우(컨텍스트·툴 호출·결과)를 로깅하고, 이를 기반으로 다른 에이전트가 자동으로 프롬프트를 개선하는 아키텍처 조사
> **작성일**: 2026-03-13

---

## 목차

1. [핵심 결론](#1-핵심-결론)
2. [OpenAI Agents SDK 내장 Tracing 시스템](#2-openai-agents-sdk-내장-tracing-시스템)
3. [OpenAI 플랫폼 traces GUI — 에이전트가 읽을 수 있나?](#3-openai-플랫폼-traces-gui--에이전트가-읽을-수-있나)
4. [로컬 모델 사용 시 Tracing 문제 및 해결](#4-로컬-모델-사용-시-tracing-문제-및-해결)
5. [외부 관찰성 도구 비교](#5-외부-관찰성-도구-비교)
6. [자동 프롬프트 개선 에이전트 구현 패턴](#6-자동-프롬프트-개선-에이전트-구현-패턴)
7. [추천 아키텍처](#7-추천-아키텍처)
8. [빠른 시작 코드](#8-빠른-시작-코드)

---

## 1. 핵심 결론

| 질문 | 답변 |
|------|------|
| 에이전트 플로우를 구조화해서 로깅할 수 있나? | ✅ SDK 내장 `TracingProcessor` 커스텀 구현으로 가능 |
| OpenAI traces GUI 데이터를 에이전트가 읽을 수 있나? | ❌ GUI 전용, 읽기 API 없음 |
| 로컬 모델에서 tracing 작동하나? | ✅ SDK 레이어는 동작, OpenAI 업로드만 실패 (해결책 있음) |
| 트레이스를 다른 에이전트가 읽어 프롬프트 개선 가능? | ✅ MLflow/Phoenix/Langfuse 모두 Python API로 읽기 가능 |
| 가장 적합한 도구 조합은? | **Phoenix (자기주도형) 또는 MLflow (쿼리 강력)** |

---

## 2. OpenAI Agents SDK 내장 Tracing 시스템

### 2.1 내부 아키텍처

```
Agent 실행
    │
TraceProvider          ← Span/Trace 객체 생성, contextvars로 비동기 중첩 관리
    │
BatchTraceProcessor    ← 스레드 안전 큐(8192), 배치 128개, 5초 지연
    │
BackendSpanExporter    ← HTTP POST → platform.openai.com/traces (기본값)
```

### 2.2 자동으로 캡처되는 이벤트 (11가지 Span 타입)

| 이벤트 | Span 타입 | 캡처되는 데이터 |
|--------|-----------|-----------------|
| `Runner.run()` 전체 | `Trace` | workflow 이름, group_id, metadata |
| 각 에이전트 활성화 | `AgentSpanData` | agent 이름, tools 목록, handoffs 목록 |
| **각 LLM 호출** | `GenerationSpanData` | **전체 메시지 히스토리(input), LLM 응답(output), 토큰 수, 모델명** |
| **각 툴 호출** | `FunctionSpanData` | **툴 이름, 입력 인자, 반환값** |
| 에이전트 핸드오프 | `HandoffSpanData` | from_agent, to_agent |
| 가드레일 체크 | `GuardrailSpanData` | 가드레일 이름, 발동 여부 |
| MCP 툴 목록 | `MCPListToolsSpanData` | 서버 이름, 툴 목록 |

### 2.3 `TracingProcessor` 인터페이스 (커스텀 구현 가능)

```python
from agents.tracing import TracingProcessor, Trace, Span
import abc

class TracingProcessor(abc.ABC):

    def on_trace_start(self, trace: Trace) -> None: ...  # trace 시작
    def on_trace_end(self, trace: Trace) -> None: ...    # trace 완료 ← 여기서 저장

    def on_span_start(self, span: Span) -> None: ...     # span 시작
    def on_span_end(self, span: Span) -> None: ...       # span 완료 ← 핵심 훅

    def shutdown(self) -> None: ...      # 앱 종료 시 플러시
    def force_flush(self) -> None: ...   # 즉시 처리 강제
```

### 2.4 Span 데이터 구조 (가장 중요한 2가지)

#### `GenerationSpanData` — LLM 호출 전체 내용

```python
span.span_data.input    # list[dict] — LLM에 보낸 전체 메시지 배열
# 예시:
# [
#   {"role": "system", "content": "You are a helpful assistant..."},
#   {"role": "user",   "content": "2+2는?"},
#   {"role": "assistant", "content": "4입니다.", "tool_calls": [...]}
# ]

span.span_data.output   # list[dict] — LLM 응답
span.span_data.model    # str — "gpt-4o", "llama3.2:8b" 등
span.span_data.usage    # {"input_tokens": 123, "output_tokens": 45}
span.span_data.model_config  # temperature, max_tokens 등
```

#### `FunctionSpanData` — 툴 호출 결과

```python
span.span_data.name    # str — 툴 이름 (예: "search_web", "run_code")
span.span_data.input   # str — 직렬화된 인자 (예: '{"query": "...", "limit": 5}')
span.span_data.output  # Any — 툴 반환값
```

### 2.5 `add_trace_processor` vs `set_trace_processors`

```python
from agents import add_trace_processor, set_trace_processors

# 방법 A: 기존 OpenAI 업로드 유지하면서 추가 (둘 다 받음)
add_trace_processor(my_custom_processor)

# 방법 B: OpenAI 업로드 완전 대체 (내 처리기만 실행)
set_trace_processors([my_custom_processor])
```

---

## 3. OpenAI 플랫폼 traces GUI — 에이전트가 읽을 수 있나?

**결론: ❌ 불가능. GUI 전용이다.**

- `platform.openai.com/traces` 는 읽기 전용 웹 UI
- OpenAI 공개 API에 traces 조회 엔드포인트 없음
- SDK는 POST(쓰기)만 하고 GET(읽기) 경로 없음
- ZDR(Zero Data Retention) 정책 조직은 tracing 자체가 비활성화됨

**→ 에이전트가 트레이스를 읽으려면 프로세스 내에서 직접 캡처해야 함.**

---

## 4. 로컬 모델 사용 시 Tracing 문제 및 해결

### 문제

```python
# Ollama 등 로컬 모델 사용 시:
client = OpenAI(base_url="http://localhost:11434/v1", api_key="dummy")
# → SDK tracing 자체는 정상 작동
# → 단, 기본 BatchTraceProcessor가 platform.openai.com에 POST → 401 에러 발생
```

### 해결책 3가지

```python
# 옵션 1: OpenAI tracing 완전 비활성화 (가장 단순)
from agents import set_tracing_disabled
set_tracing_disabled(True)

# 옵션 2: 모델은 로컬, 트레이스만 OpenAI에 업로드
from agents import set_tracing_export_api_key
set_tracing_export_api_key("sk-your-openai-key")  # 모델 호출은 로컬로

# 옵션 3: 트레이스를 완전히 로컬 파일/DB로만 저장 (권장)
from agents import set_trace_processors
from agents.tracing import BatchTraceProcessor
set_trace_processors([BatchTraceProcessor(my_local_file_exporter)])
```

---

## 5. 외부 관찰성 도구 비교

### 5.1 비교표

| 도구 | pip 설치 | OpenAI Agents SDK | **에이전트가 읽기 가능** | 자체 호스팅 | 무료 | 로컬 모델 |
|------|---------|-------------------|------------------------|-------------|------|-----------|
| **Arize Phoenix** | `arize-phoenix` + `openinference-instrumentation-openai-agents` | ✅ (v8.13+) | ✅ `get_spans_dataframe()` | ✅ 완전 무료 | ✅ 무제한 | ✅ Ollama 공식 지원 |
| **MLflow** | `mlflow[genai]` | ✅ `autolog()` | ✅ SQL DSL `search_traces()` | ✅ 순수 OSS | ✅ 완전 무료 | ✅ Ollama 공식 문서화 |
| **Langfuse** | `langfuse` + `openinference-instrumentation-openai-agents` | ✅ | ✅ `api.trace.get()` | ✅ Docker | ✅ | ✅ |
| **AgentOps** | `agentops` | ✅ | ✅ REST API | ✅ (app 자체 호스팅) | ✅ | ✅ |
| **Braintrust** | `braintrust[openai-agents]` | ✅ | ✅ REST API + BTQL | ❌ Enterprise만 | ✅ (Cloud) | ✅ |

### 5.2 Arize Phoenix — 상세

**자동화 프롬프트 개선 에이전트에 가장 적합**. 완전 자기주도형, 무료, Ollama 명시 지원.

```bash
pip install arize-phoenix openinference-instrumentation-openai-agents arize-phoenix-otel
pip install arize-phoenix-client  # 읽기용 경량 패키지
```

```python
# 트레이스 수집
from phoenix.otel import register
from openinference.instrumentation.openai_agents import OpenAIAgentsInstrumentor

tracer_provider = register(project_name="my-agent", auto_instrument=True)
OpenAIAgentsInstrumentor().instrument(tracer_provider=tracer_provider)

# 에이전트가 트레이스 읽기 (나중에 개선 에이전트에서 사용)
from phoenix.client import Client
from phoenix.client.types.spans import SpanQuery

client = Client(endpoint="http://localhost:6006")

# LLM 호출만 필터
df = client.spans.get_spans_dataframe(
    project_identifier="my-agent",
    query=SpanQuery().where("span_kind == 'LLM'")
)
# df: pandas DataFrame — 컬럼에 input, output, latency, model_name 등 포함
```

### 5.3 MLflow — 상세

**가장 강력한 쿼리 DSL**. SQL-like 필터로 에러 케이스만 추출하기 쉬움.

```bash
pip install 'mlflow[genai]' openai
mlflow server --host 0.0.0.0 --port 5000  # 로컬 서버
```

```python
import mlflow
mlflow.set_tracking_uri("http://localhost:5000")
mlflow.openai.autolog()  # OpenAI Agents SDK 자동 계측

# Ollama와도 동작
client = OpenAI(base_url="http://localhost:11434/v1", api_key="dummy")

# 에러 케이스만 조회
failed_traces = mlflow.search_traces(
    filter_string="status = 'ERROR'",
    return_type="dataframe"
)

# 특정 에이전트의 최근 100개
traces = mlflow.search_traces(
    filter_string="name LIKE 'researcher%'",
    order_by=["attributes.timestamp_ms DESC"],
    max_results=100,
    return_type="dataframe"
)
```

---

## 6. 자동 프롬프트 개선 에이전트 구현 패턴

핵심 파이프라인:

```
[에이전트 실행] → [트레이스 로깅] → [개선 에이전트가 읽음] → [프롬프트 개선] → [재실행]
```

### 6.1 패턴 A: SDK 내장 Custom TracingProcessor (외부 의존성 없음)

```python
import json
from typing import Any
from agents import set_trace_processors, Agent, Runner
from agents.tracing import TracingProcessor, TracingExporter, BatchTraceProcessor, Trace, Span

class JsonlTraceLogger(TracingExporter):
    """모든 span을 JSONL 파일에 저장"""

    def __init__(self, path: str = "traces.jsonl"):
        self._path = path

    def export(self, items: list) -> None:
        with open(self._path, "a", encoding="utf-8") as f:
            for item in items:
                data = item.export()
                if data:
                    f.write(json.dumps(data, ensure_ascii=False) + "\n")

# 설정: OpenAI 업로드 없이 로컬 파일만
exporter = JsonlTraceLogger("agent_traces.jsonl")
set_trace_processors([BatchTraceProcessor(exporter)])

# 에이전트 실행 (트레이스 자동 캡처)
agent = Agent(name="ResearchAgent", instructions="...")
result = await Runner.run(agent, "어시스턴트야, X를 조사해줘")
```

저장된 JSONL 파일 구조:
```jsonl
{"object":"trace.span","id":"span_abc","trace_id":"trace_xyz","span_data":{"type":"generation","input":[{"role":"system","content":"..."},{"role":"user","content":"..."}],"output":[{"role":"assistant","content":"..."}],"model":"llama3.2:8b","usage":{"input_tokens":150,"output_tokens":80}}}
{"object":"trace.span","id":"span_def","trace_id":"trace_xyz","span_data":{"type":"function","name":"search_web","input":"{\"query\":\"AI safety\"}","output":"[{\"title\":\"...\"}]"}}
```

### 6.2 패턴 B: 개선 에이전트가 트레이스를 읽고 프롬프트를 자동 수정

```python
import json
from openai import AsyncOpenAI

async def prompt_improvement_agent(traces_file: str, current_instructions: str) -> str:
    """트레이스를 읽고 프롬프트를 개선하는 에이전트"""

    # 1. 트레이스 읽기
    traces = []
    with open(traces_file) as f:
        for line in f:
            span = json.loads(line)
            sd = span.get("span_data", {})
            if sd.get("type") == "generation":
                traces.append({
                    "messages_sent": sd.get("input", []),
                    "model_response": sd.get("output", []),
                    "tokens": sd.get("usage", {}),
                })
            elif sd.get("type") == "function":
                traces.append({
                    "tool_called": sd.get("name"),
                    "tool_input": sd.get("input"),
                    "tool_output": sd.get("output"),
                })

    # 2. 개선 에이전트에게 전달
    client = AsyncOpenAI(base_url="http://localhost:11434/v1", api_key="dummy")

    response = await client.chat.completions.create(
        model="qwen3.5:9b",  # 로컬 고성능 모델
        messages=[
            {
                "role": "system",
                "content": """당신은 AI 에이전트의 프롬프트를 개선하는 전문가입니다.
에이전트의 실행 트레이스를 보고 어떤 프롬프트 지시가 잘못되었는지 파악하여
개선된 프롬프트를 작성합니다."""
            },
            {
                "role": "user",
                "content": f"""현재 에이전트 지시문:
```
{current_instructions}
```

실행 트레이스 (최근 {len(traces)}개):
```json
{json.dumps(traces[:10], ensure_ascii=False, indent=2)}
```

문제점을 분석하고 개선된 지시문을 ``` 블록 안에 작성해주세요.
분석 포인트:
1. 에이전트가 불필요한 툴을 호출했는가?
2. LLM 응답이 지시문의 의도와 어긋났는가?
3. 컨텍스트가 불충분하게 제공되었는가?
4. 특정 도메인 지식이 프롬프트에 빠져있는가?"""
            }
        ]
    )

    # 3. 개선된 프롬프트 추출
    content = response.choices[0].message.content
    start = content.find("```") + 3
    end = content.rfind("```")
    if start < end:
        return content[start:end].strip()
    return content.strip()

# 사용
improved_prompt = await prompt_improvement_agent(
    traces_file="agent_traces.jsonl",
    current_instructions="당신은 리서치 에이전트입니다. 사용자의 질문에 답하세요."
)
print(f"개선된 프롬프트:\n{improved_prompt}")
```

### 6.3 패턴 C: Phoenix + 자동 평가 루프

```python
import phoenix as px
from phoenix.client import Client
from phoenix.evals import run_evals, llm_classify

# Phoenix 서버 시작
px.launch_app()
client = Client()

# 1단계: 에이전트 실행 (트레이스 자동 수집)
from phoenix.otel import register
from openinference.instrumentation.openai_agents import OpenAIAgentsInstrumentor
register(project_name="my-agent", auto_instrument=True)
OpenAIAgentsInstrumentor().instrument()

# ... 에이전트 실행 ...

# 2단계: 실패 케이스 추출
failed_spans = client.spans.get_spans_dataframe(
    project_identifier="my-agent",
    query=SpanQuery().where("span_kind == 'LLM'")
)

# 출력 품질이 낮은 것만 필터 (자체 평가기 추가 가능)
poor_spans = failed_spans[failed_spans["attributes.llm.token_count.completion"] < 50]

# 3단계: 개선 에이전트에 전달
for _, span in poor_spans.iterrows():
    input_msgs = span["attributes.llm.input_messages"]
    output_msg = span["attributes.llm.output_messages"]
    # → 개선 에이전트 호출
```

### 6.4 패턴 D: GEPA와 연동 (고급 자동화)

GEPA (ICLR 2026 Oral, arXiv:2507.19457)를 OpenAI Agents SDK와 연동하려면:

```python
# gepa는 자체 GEPAAdapter 인터페이스 구현 필요
# OpenAI Agents SDK trace → GEPA reflective_dataset 포맷으로 변환

def traces_to_gepa_format(spans: list[dict]) -> list[dict]:
    """SDK trace → GEPA ASI 형식 변환"""
    records = []
    for span in spans:
        sd = span.get("span_data", {})
        if sd.get("type") == "generation":
            input_text = "\n".join(
                f"{m['role']}: {m.get('content', '')}"
                for m in (sd.get("input") or [])
            )
            output_text = "\n".join(
                f"{m['role']}: {m.get('content', '')}"
                for m in (sd.get("output") or [])
            )
            records.append({
                "Inputs": input_text,
                "Generated Outputs": output_text,
                "Feedback": "평가자가 여기에 피드백 추가",  # 별도 평가 필요
            })
    return records
```

---

## 7. 추천 아키텍처

### 시나리오별 추천

#### Case 1: 가장 단순하게 시작하고 싶다 (외부 서버 없음)

```
OpenAI Agents SDK
    → set_trace_processors([BatchTraceProcessor(JsonlTraceLogger("traces.jsonl"))])
    → traces.jsonl 파일에 모든 span 저장
    → 개선 에이전트가 파일 읽어서 분석
```

**장점**: 의존성 없음, 즉시 시작 가능
**단점**: 검색/필터링 직접 구현 필요

#### Case 2: 자체 서버 + 강력한 쿼리 (권장)

```
OpenAI Agents SDK
    → openinference-instrumentation-openai-agents
    → Arize Phoenix (로컬 Docker)
    → phoenix-client로 에이전트가 트레이스 쿼리
    → 개선 에이전트 → 재실행
```

```bash
# 설치
pip install arize-phoenix openinference-instrumentation-openai-agents arize-phoenix-otel arize-phoenix-client

# Phoenix 서버 실행
docker run -p 6006:6006 arizephoenix/phoenix
# 또는
python -m phoenix.server.main serve
```

**장점**: GUI도 있고 프로그래매틱 쿼리도 있음, 완전 무료, Ollama 명시 지원
**단점**: Docker 또는 Python 서버 필요

#### Case 3: 데이터 과학 친화적 (MLflow 이미 사용 중이라면)

```
OpenAI Agents SDK
    → mlflow.openai.autolog()
    → mlflow server (로컬)
    → mlflow.search_traces(filter_string="status='ERROR'")
    → 실패 케이스 DataFrame → 개선 에이전트
```

**장점**: SQL-like 쿼리 강력, pandas DataFrame 바로 반환, Ollama 공식 문서화
**단점**: MLflow 서버 별도 구동 필요

### 전체 시스템 흐름

```
┌─────────────────────────────────────────────────────────┐
│                   에이전트 실행 계층                      │
│                                                         │
│  Agent A  ──→  Agent B  ──→  Agent C                   │
│   (툴 호출)    (핸드오프)    (최종 응답)                  │
└──────────────────────┬──────────────────────────────────┘
                       │ TracingProcessor
                       ▼
┌─────────────────────────────────────────────────────────┐
│                   트레이스 저장 계층                      │
│                                                         │
│  [JSONL 파일] 또는 [Phoenix/MLflow 서버]                 │
│                                                         │
│  각 Span: type, input, output, tool_name, timestamps    │
└──────────────────────┬──────────────────────────────────┘
                       │ Python API 읽기
                       ▼
┌─────────────────────────────────────────────────────────┐
│                 개선 에이전트 계층                        │
│                                                         │
│  1. 실패/저품질 트레이스 필터                             │
│  2. "왜 틀렸나" 분석 (로컬 LLM: Qwen3.5-9B 등)          │
│  3. 개선된 프롬프트 생성                                  │
│  4. 원래 에이전트의 instructions 업데이트                 │
│  5. 재실행 → 결과 비교                                   │
└─────────────────────────────────────────────────────────┘
```

---

## 8. 빠른 시작 코드

### 완전한 예제: 로컬 모델 + 자동 트레이스 로깅 + 개선 에이전트

```python
"""
완전한 예제: OpenAI Agents SDK + 로컬 모델 (Ollama) + 자동 프롬프트 개선
"""
import json
import asyncio
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI
from agents import Agent, Runner, set_trace_processors, function_tool
from agents.tracing import TracingExporter, BatchTraceProcessor

# ─── 1. 트레이스 로거 구현 ───────────────────────────────────────────────────

class InMemoryTraceLogger(TracingExporter):
    """메모리에 트레이스 저장 (파일로도 동시 저장)"""

    def __init__(self, log_file: str = "traces.jsonl"):
        self.spans: list[dict] = []
        self.log_file = Path(log_file)

    def export(self, items: list) -> None:
        with self.log_file.open("a", encoding="utf-8") as f:
            for item in items:
                data = item.export()
                if data:
                    self.spans.append(data)
                    f.write(json.dumps(data, ensure_ascii=False) + "\n")

    def get_llm_calls(self) -> list[dict]:
        """LLM 호출 span만 반환"""
        return [
            s for s in self.spans
            if s.get("span_data", {}).get("type") == "generation"
        ]

    def get_tool_calls(self) -> list[dict]:
        """툴 호출 span만 반환"""
        return [
            s for s in self.spans
            if s.get("span_data", {}).get("type") == "function"
        ]

# 트레이스 로거 등록 (OpenAI 업로드 없이 로컬만)
trace_logger = InMemoryTraceLogger("my_agent_traces.jsonl")
set_trace_processors([BatchTraceProcessor(trace_logger)])

# ─── 2. 에이전트 정의 ───────────────────────────────────────────────────────

LOCAL_BASE_URL = "http://localhost:11434/v1"

@function_tool
def search_web(query: str) -> str:
    """웹 검색 (더미 구현)"""
    return f"검색 결과: '{query}'에 대한 결과입니다."

@function_tool
def calculate(expression: str) -> str:
    """계산기"""
    try:
        return str(eval(expression))
    except Exception as e:
        return f"계산 오류: {e}"

agent = Agent(
    name="ResearchAgent",
    instructions="""당신은 리서치 에이전트입니다. 사용자의 질문에 답하세요.""",  # ← 개선 대상
    tools=[search_web, calculate],
    model="ollama/llama3.2:8b",  # 로컬 모델
)

# ─── 3. 에이전트 실행 ───────────────────────────────────────────────────────

async def run_agent_with_logging(questions: list[str]):
    """여러 질문을 실행하고 트레이스 수집"""
    results = []
    for q in questions:
        print(f"\n[실행] {q}")
        result = await Runner.run(agent, q)
        results.append(result.final_output)
        print(f"[응답] {result.final_output[:100]}...")
    return results

# ─── 4. 개선 에이전트 ───────────────────────────────────────────────────────

async def improve_prompt_with_agent(
    current_instructions: str,
    trace_logger: InMemoryTraceLogger,
) -> str:
    """로컬 LLM이 트레이스를 분석해 프롬프트 개선"""

    llm_calls = trace_logger.get_llm_calls()
    tool_calls = trace_logger.get_tool_calls()

    # 분석용 요약 생성
    analysis_data = []
    for span in llm_calls[:5]:  # 최근 5개만
        sd = span["span_data"]
        msgs = sd.get("input", [])
        resp = sd.get("output", [])
        analysis_data.append({
            "system_prompt": next((m["content"] for m in msgs if m["role"] == "system"), ""),
            "user_message": next((m["content"] for m in msgs if m["role"] == "user"), ""),
            "assistant_response": next((m.get("content", "") for m in resp), ""),
            "tool_calls_made": [t["span_data"]["name"] for t in tool_calls[:3]],
        })

    client = AsyncOpenAI(base_url=LOCAL_BASE_URL, api_key="dummy")

    response = await client.chat.completions.create(
        model="qwen3.5:9b",  # 개선용 고성능 로컬 모델
        messages=[
            {
                "role": "system",
                "content": "당신은 AI 에이전트 프롬프트 최적화 전문가입니다."
            },
            {
                "role": "user",
                "content": f"""현재 에이전트 지시문:
```
{current_instructions}
```

실행 트레이스 분석 ({len(llm_calls)}개 LLM 호출, {len(tool_calls)}개 툴 호출):
```json
{json.dumps(analysis_data, ensure_ascii=False, indent=2)}
```

다음 기준으로 분석하고 개선된 지시문을 ``` 블록에 작성해주세요:
1. 에이전트가 불필요한 툴을 호출했나?
2. 응답이 사용자 의도와 맞지 않는 경우가 있나?
3. 도메인 지식이나 구체적 지시가 부족한가?
4. 응답 형식 지시가 명확한가?"""
            }
        ]
    )

    content = response.choices[0].message.content
    # ``` 블록 추출
    start = content.find("```") + 3
    end = content.rfind("```")
    if 0 < start < end:
        # 언어 지정자 제거 (```python 등)
        extracted = content[start:end].strip()
        first_newline = extracted.find("\n")
        if first_newline > 0 and not extracted[:first_newline].startswith(" "):
            extracted = extracted[first_newline:].strip()
        return extracted
    return content.strip()

# ─── 5. 메인 루프 ─────────────────────────────────────────────────────────

async def main():
    questions = [
        "파이썬의 GIL이 뭔가요?",
        "2024년 노벨 물리학상 수상자는?",
        "123 * 456을 계산해주세요.",
    ]

    # 실행 1: 현재 프롬프트로 실행
    print("=== 1차 실행 ===")
    await run_agent_with_logging(questions)

    print(f"\n[트레이스] LLM 호출 {len(trace_logger.get_llm_calls())}회, 툴 호출 {len(trace_logger.get_tool_calls())}회 캡처됨")

    # 개선 에이전트 실행
    print("\n=== 프롬프트 개선 에이전트 실행 ===")
    improved = await improve_prompt_with_agent(
        agent.instructions,
        trace_logger
    )
    print(f"개선된 프롬프트:\n{improved}")

    # 에이전트 업데이트 후 재실행
    agent.instructions = improved
    trace_logger.spans.clear()  # 트레이스 초기화

    print("\n=== 2차 실행 (개선된 프롬프트) ===")
    await run_agent_with_logging(questions)

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 참고 자료

### OpenAI Agents SDK 공식
- [Tracing 공식 문서](https://openai.github.io/openai-agents-python/tracing/)
- [TracingProcessor 인터페이스 소스](https://github.com/openai/openai-agents-python/blob/main/src/agents/tracing/processor_interface.py)
- [SpanData 타입 소스](https://github.com/openai/openai-agents-python/blob/main/src/agents/tracing/span_data.py)

### 관찰성 도구
- [Arize Phoenix GitHub](https://github.com/Arize-ai/phoenix)
- [Phoenix: OpenAI Agents 지원 릴리즈 (2025.03.14)](https://arize.com/docs/phoenix/release-notes/03.14.2025-openai-agents-instrumentation)
- [MLflow: OpenAI Agents 트레이싱](https://mlflow.org/docs/latest/genai/tracing/integrations/listing/openai-agent/)
- [MLflow: Ollama 트레이싱](https://mlflow.org/docs/latest/genai/tracing/integrations/listing/ollama/)
- [Langfuse: OpenAI Agents 통합](https://langfuse.com/integrations/frameworks/openai-agents)
- [openinference-instrumentation-openai-agents (PyPI)](https://pypi.org/project/openinference-instrumentation-openai-agents/)

### 자동 프롬프트 개선
- [GEPA GitHub](https://github.com/gepa-ai/gepa) — 트레이스 기반 프롬프트 최적화 (ICLR 2026 Oral)
- [GEPA arXiv](https://arxiv.org/abs/2507.19457)
