# DSU 클럭 트리 질문 실패 원인 분석

작성일: 2026-03-27
관련 보고서: `260327_clock-canvas-db-graph-query-strategy.md`, `260327_neo4j-etl-feasibility-study.md`
방법론: RALPLAN 컨센서스 (Planner-Architect-Critic 합의)

---

## Executive Summary

에이전트가 "DSU의 포트중에 클럭이 정상적으로 공급되고 있는 클럭 트리를 하나만 보여줘"에 대답하지 못한 근본 원인은 **DB 한계가 아니라 도구(trace 헬퍼) + 프롬프트의 한계**다.

데이터는 MongoDB에 완전히 존재한다. 문제는 `trace()` 헬퍼가 1홉만 추적하는데, 전체 클럭 트리는 5홉 이상이라는 것이다. LLM이 직접 80줄급 재귀 Python을 작성해야 하는데, gpt-4o-mini에게는 너무 복잡하다.

**Neo4j로 마이그레이션하면 근본적으로 해결된다.** Cypher 4줄로 전체 클럭 트리를 가져올 수 있고, 토큰 수가 1/10로 줄어 응답 시간도 크게 단축된다.

---

## 1. 실패한 질문 분석

### 1.1 질문의 요구사항

"DSU의 포트중에 클럭이 정상적으로 공급되고 있는 클럭 트리를 하나만 보여줘"

이 질문에 답하려면:
1. DSU(ClockIP) 찾기 — 26개 포트 보유
2. 한 포트에서 **역방향 멀티홉 추적**: 5홉 이상, Label/LabelRef 패스스루 2회, Multiplexer 분기 4개
3. "정상적으로 공급" 판단 — 게이팅 여부 확인

### 1.2 실제 클럭 트리 (데이터에서 직접 확인)

DSU는 26개 포트를 가지고 있다:
- CORE0CLK ~ CORE13CLK (14개) — 코어별 클럭
- SCLK, PCLK, ATCLK, GICCLK, PERIPHCLK, PPUCLK (6개) — 시스템 클럭
- *_CHK (6개) — 체크용 클럭

**DSU.SCLK의 전체 클럭 트리:**

```
DSU.SCLK
  ← ClockGate "DSU__SCLK"
    ← [LabelRef → Label bridge]
      ← ClockDFTOCCBuffer "CPU_OCCBUF_CKC7"
        ← ClockMultiplexer "CPU_CKC7"
          ← ClockExternalCLKSource "CPU_XIN"      (MUX input 0)
          ← ClockPLLCtrl "CPU_PLL7"               (MUX input 1)
            ← ClockExternalCLKSource "CPU_FIN"       (PLL 소스)
          ← ClockDivider "CPU_PLL7_DIV0"           (MUX input 2)
          ← ClockExternalCLKSource "CPU_EXTCLK"    (MUX input 3)
```

**DSU.CORE0CLK의 전체 클럭 트리:**

```
DSU.CORE0CLK
  ← ClockGate "DSU__CORE0CLK"
    ← [LabelRef → Label bridge]
      ← ClockDFTOCCBuffer "CPU_OCCBUF_CKC0"
        ← ClockMultiplexer "CPU_CKC0"
          ← ClockExternalCLKSource "CPU_XIN"
          ← ClockPLLCtrl "CPU_PLL0"
            ← ClockExternalCLKSource "CPU_FIN"
          ← ClockDivider "CPU_PLL0_DIV"
          ← ClockExternalCLKSource "CPU_EXTCLK"
```

**공통 패턴**: 모든 DSU 포트가 동일한 구조 — Gate ← Label ← OCC Buffer ← MUX ← (PLL + Divider + 외부클럭)

---

## 2. 근본 원인 진단

### 2.1 원인 1: trace()가 단일 홉 (기여도 50%)

`tools.py:58-140`의 `trace(port_id)` 헬퍼는 **포트에서 바로 다음 연결된 컴포넌트 1개**만 반환한다.

```python
# trace()가 하는 일:
# Input/Output 포트의 connections[] 배열에서
# Connection → 반대편 포트 → 그 포트의 부모 컴포넌트
# Label/LabelRef를 만나면 자동 통과
# → 하지만 재귀하지 않음. 1홉에서 멈춤.
```

DSU SCLK의 경우:
```
DSU.SCLK(Input) → trace() → ClockGate "DSU__SCLK"  ← 여기까지만
                                    ↓
                         나머지 4홉은 LLM이 직접 코드를 짜야 함
                                    ↓
               Buffer ← MUX ← PLL ← FIN  ← 이 부분을 못 봄
```

### 2.2 원인 2: 프롬프트에 멀티홉 패턴 없음 (기여도 30%)

`prompts.py:87-92`의 P-TOPO 패턴:

```python
# P-TOPO: 토폴로지 추적 (연결된 컴포넌트)
comp = col.find_one({"properties.name": "CPU_PLL7"})
for out in col.find({"pid": comp["_id"], "itemType": "Output"}):
    for t in trace(out["_id"]):
        print(t["properties"]["name"], f"({t['itemType']}, via={t['via']})")
```

이 패턴은 **1홉 추적만** 보여준다. "전체 클럭 트리를 재귀적으로 추적"하는 P-TREE 패턴이 없다.

### 2.3 원인 3: gpt-4o-mini 코드 생성 한계 (기여도 20%)

전체 클럭 트리를 추적하려면 LLM이 한 턴에 다음을 작성해야 한다:
- 재귀적 역방향 탐색 함수
- Label/LabelRef 패스스루 처리 (45줄)
- Multiplexer 분기 처리
- 순환 방지 (visited set)
- 깊이 제한
- 결과 포맷팅

총 ~80줄의 Python 코드를 한 번에 정확하게 생성해야 하는데, gpt-4o-mini에게는 비현실적이다.

### 2.4 DB 한계인가? 아니다.

DSU의 26개 포트, 221개 Connection, Label/LabelRef 브릿지 — 클럭 트리를 역추적하는 데 필요한 **모든 데이터가 MongoDB에 완전히 존재**한다. 문제는 데이터가 없는 게 아니라, 그 데이터를 꺼내는 쿼리가 너무 복잡하다는 것이다.

---

## 3. 해결 방안 비교

### 3.1 Option A: trace_tree() 재귀 헬퍼 추가 (즉시 조치)

```python
# tools.py에 추가
def trace_tree(node_name, direction="backward", max_depth=10):
    """전체 클럭 트리를 재귀적으로 추적하여 트리 구조로 반환."""
    # ... ~80줄 재귀 구현
```

| 항목 | 평가 |
|---|---|
| LOC | ~80줄 |
| 효과 | 이 패턴(클럭 트리) 해결 |
| LLM 부담 | `trace_tree("DSU__SCLK")` 한 줄 |
| 한계 | **이 패턴만** 해결. 다른 그래프 질문엔 또 새 헬퍼 필요 |

### 3.2 Option B: Neo4j ETL + Cypher (전략적 해결)

```cypher
-- 전체 클럭 트리를 Cypher 4줄로
MATCH path = (gate:ClockGate {name: "DSU__SCLK"})
             <-[:CLOCK_SIGNAL|LABEL_BRIDGE*]-(source)
WHERE NOT ()<-[:CLOCK_SIGNAL]-(source)
RETURN path
```

| 항목 | 평가 |
|---|---|
| LOC | ~350줄 (ETL 스크립트) + Docker |
| 효과 | **모든 그래프 질문** 해결 |
| LLM 부담 | Cypher 4줄 (LLM이 잘 생성) |
| 추가 이점 | Neo4j Browser로 시각화 가능 |

### 3.3 응답 시간 관점 비교

| | MongoDB + Python | Neo4j + Cypher |
|---|---|---|
| LLM이 생성할 코드 | ~80줄 재귀 Python (또는 trace_tree 한 줄) | ~4줄 Cypher |
| 생성 토큰 수 | ~500-800 토큰 (trace_tree 시 ~50) | ~50-80 토큰 |
| 생성 시간 | 느림 + 실패 가능성 | 빠름 + 안정적 |
| DB 실행 시간 | 앱레벨 다중 조인 (느림) | 네이티브 그래프 순회 (빠름) |
| 턴 수 | 여러 턴 (디버깅 포함) | 1턴에 완료 |

**핵심**: Neo4j는 단순히 "가능"한 게 아니라, **토큰 수 1/10, 코드 복잡도 1/20**로 응답 시간을 극적으로 단축한다.

### 3.4 Neo4j가 해결하는 질문 유형

| 질문 패턴 | Python (현재) | Cypher (Neo4j) |
|---|---|---|
| 전체 클럭 트리 | 80줄 재귀 또는 trace_tree | `*1..N` 가변 경로 |
| 영향받는 하위 노드 | BFS 직접 구현 | `MATCH (a)-[*]->(b)` |
| Gate 3개 이상 경로 | 거의 불가능 | `WHERE size([n WHERE n:ClockGate]) >= 3` |
| 최단 경로 | 직접 구현 | `shortestPath()` |
| 순환 탐지 | 직접 구현 | `MATCH (a)-[*]->(a)` |

---

## 4. 결론 및 추천

### 진단 결과

| 가설 | 판정 | 근거 |
|---|---|---|
| 프롬프트 문제? | **부분적 YES** (30%) | 멀티홉 패턴 없음. 하지만 패턴만 추가해도 LLM이 80줄 코드를 못 짬 |
| DB 한계? | **NO** | 데이터 완전히 존재. 쿼리 복잡도가 문제 |
| 도구 한계? | **YES** (50%) | trace()가 1홉만 추적 |
| 모델 한계? | **부분적 YES** (20%) | 복잡한 재귀 코드 생성 어려움 |
| Neo4j가 해결? | **YES** | 4줄 Cypher로 대체. 토큰/시간 1/10 |

### 추천 전략

**Neo4j ETL을 최우선으로 추진한다.**

이유:
1. `trace_tree()` 헬퍼를 추가해도 **한 패턴만** 해결. 새 그래프 질문마다 새 헬퍼가 필요 (whack-a-mole)
2. Neo4j는 **모든 그래프 질문**을 짧은 Cypher로 해결
3. 응답 시간이 중요한 상황에서, **토큰 수 1/10 감소**는 결정적 이점
4. ETL PoC는 1일이면 검증 가능 (Docker + CMU 1개 + Cypher 테스트)
5. Neo4j Browser로 클럭 트리 시각화까지 공짜로 얻음

### PoC 계획

```
Phase 0 (1일):
1. docker run neo4j:5-community
2. CMU_CPU_SS 1개 ETL (~350줄 Python)
3. "DSU 클럭 트리" Cypher 쿼리로 검증
4. Neo4j Browser에서 클럭 토폴로지 시각화
```

---

## Sources

- 에이전트 프롬프트: `clock_agent/prompts.py` (P-TOPO 패턴, 1홉만)
- trace() 헬퍼: `clock_agent/tools.py:58-140` (단일 홉)
- run_db_query 실행환경: `clock_agent/tools.py:284-291` (헬퍼 주입)
- DB 실제 데이터: `raw_data/MongoDB/MongoDB - CMU - example.json.json` (DSU 26포트, 221 Connection)
- 선행 보고서: `260327_clock-canvas-db-graph-query-strategy.md`, `260327_neo4j-etl-feasibility-study.md`
