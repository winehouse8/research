# Clock Canvas DB 그래프 쿼리 전략 보고서

작성일: 2026-03-27
방법론: RALPLAN 컨센서스 (Planner-Architect-Critic 3자 합의, 2 iteration)

---

## Executive Summary

Clock Canvas DB는 MongoDB에 저장된 **트리+그래프 하이브리드** 구조다. 이 데이터는 철학적으로 Neo4j Cypher가 다루는 Property Graph와 동일하지만, 실무적으로는 Canvas 고유의 복잡한 관계 해상도 로직(특히 클럭 경로 추적) 때문에 Cypher 표준만으로는 커버가 불완전하다.

**결론**: Cypher 트랜스파일러(사용자의 1번 안) 대신, 검증된 Python executor 위에 그래프 탐색 헬퍼를 추가하는 **Option D**가 최소 비용(400-500 LOC)으로 전체 커버리지(11/11 쿼리)를 달성하는 최선의 전략이다.

---

## 1. Clock Canvas DB 데이터 구조

### 1.1 저장 형태

MongoDB 문서 하나에 모든 아이템이 **flat array**(`items[]`)로 저장된다.

```
MongoDB Document: "ClockCMU__e8d4a276-..."
├── _id: "ClockCMU__e8d4a276-..."
├── itemType: "ClockCMU"
└── items: [    ← 3,005개 아이템이 평면 배열로 존재
      { id, pid, itemType, properties, _mappers, ... },
      { id, pid, itemType, properties, _mappers, ... },
      ...
   ]
```

### 1.2 아이템 타입 분포 (CMU_CPU_SS 예시, 3,005개)

| 카테고리 | 주요 타입 | 개수 | 역할 |
|---|---|---|---|
| 레지스터 | SFRField, SFR, SFRParam | 962, 341, 54 | SFR 레지스터 맵 |
| 다이어그램 노드 | ClockGate, ClockFreqmon, ClockExternalCLKSource | 37, 29, 23 | 캔버스 위의 클럭 컴포넌트 |
| 핵심 컴포넌트 | ClockDivider, ClockMultiplexer, ClockPLLCtrl, ClockPLL | 9, 9, 8, 8 | 분주기, 먹스, PLL |
| 연결 | Connection, Input, Output | 221, 193, 196 | 노드 간 클럭 신호 경로 |
| 참조 | Label, LabelRef | 29, 65 | 다이어그램 간 클럭 신호 브릿지 |
| 뷰/메타 | NodeMetaView | 258 | 캔버스 좌표 (x, y) |
| 확장 제어 | ClockEXTCTRL* (PWRDOWN, THROTTLE, EDGESYNC, CUSTOM) | 92, 55, 9, ... | 컴포넌트 부가 기능 |

### 1.3 아이템 계층 (트리 구조)

```
ClockCMU (루트, 1개)
├── ConfigurationFolder        ← 주파수 설정 프리셋
├── SFRBlock                   ← 레지스터 블록
│   └── SFR (341개)
│       └── SFRField (962개)   ← 개별 비트필드
├── ClockDiagramFolder
│   └── ClockDiagram (캔버스)
│       ├── ClockExternalCLKSource (23)  ← 외부 클럭 소스
│       ├── ClockPLLCtrl (8)             ← PLL 컨트롤러
│       │   └── ClockPLL (8)             ← PLL 인스턴스
│       ├── ClockMultiplexer (9)         ← 클럭 먹스
│       ├── ClockDivider (9)             ← 분주기
│       │   └── ClockDividerEXT          ← 확장 제어
│       ├── ClockGate (37)               ← 클럭 게이트
│       ├── ClockFreqmon (29)            ← 주파수 모니터
│       ├── Connection (221)             ← 노드 간 연결선
│       ├── Label (29)                   ← 라벨 (다이어그램 간 브릿지)
│       ├── LabelRef (65)                ← 라벨 참조
│       └── ClockDFTOCCBuffer (9)        ← DFT 버퍼
├── ClockCMUCtrl                ← CMU 전체 제어
├── ClockQChannelManager        ← Q-Channel 핸드셰이크
└── ClockEdgeSyncGroup          ← Edge Sync 그룹
```

---

## 2. 6가지 관계 메커니즘 (REF-01 ~ REF-06)

이 데이터의 핵심은 **6가지 서로 다른 방식으로 아이템 간 관계를 표현**한다는 것이다.

### REF-01: 트리 (부모-자식)

```json
{ "id": "760c552a-...", "pid": "88e28c1b-...", "itemType": "ClockDiagram" }
                                  ↑ 부모 ID
```

- 모든 아이템이 `pid`(parent id)와 `id`를 가짐
- `pid`로 부모를 찾고, `id`로 자식을 찾는 트리 구조
- **Cypher 매핑: 쉬움** — `(:Parent)-[:HAS_CHILD]->(:Child)`

### REF-02: 속성 참조 (크로스 문서 FK)

```json
{
  "itemType": "ClockPLLCtrl",
  "properties": {
    "plltype": "063602d0-9e41-491c-bbbe-9d81fb40b665"  ← 다른 문서의 아이템 UUID
  }
}
```

- 속성값이 다른 아이템의 UUID를 가리킴
- 크로스 문서 참조 가능 (예: `plltype`은 InputClockFolder 문서의 `InputClockPLL` 참조)
- 확인된 참조 속성들: `plltype`, `refCLK`, `PCLK`, `unifiedModule`, `hardeningCLKCOMP`, `selectedConfiguration`, `itemLabel`
- **Cypher 매핑: 중간** — FK 조인 필요

### REF-03: Connection 토폴로지 (클럭 경로)

```
[ClockPLLCtrl] → Output(port) → Connection → Input(port) → [ClockDivider]
                  ↑ sourceOutput    ↑ 중간 아이템    ↑ targetInput
```

```json
// Connection 아이템
{
  "itemType": "Connection",
  "properties": {
    "sourceOutput": "f913eaf4-...",  ← Output 아이템의 UUID
    "targetInput": "54965d87-...",   ← Input 아이템의 UUID
    "type": "origin"
  }
}

// Output 아이템 (포트)
{
  "itemType": "Output",
  "properties": {
    "key": "CLK_OUTPUT",
    "socket": "CLK",
    "connections": ["edb30eac-..."],  ← Connection UUID 배열
    "position": "RIGHT"
  }
}
```

- 노드 간 직접 연결이 아니라 **Output → Connection → Input → 부모 노드** 3홉 경유
- **Label/LabelRef 패스스루**: 다이어그램 경계를 넘는 클럭 신호는 Label→LabelRef로 투명하게 전달
- 이 로직만 ~80줄의 Python 코드 필요
- **Cypher 매핑: 어려움** — 3-5홉 해상도 + Label 패스스루가 Cypher 단순 엣지 모델에 맞지 않음

### REF-04: 매퍼 동기화 (_mappers)

```json
{
  "itemType": "ClockCMUCtrl",
  "_mappers": [
    { "type": "ITEM_NAME", "sid": "71c591e2-...", "tid": "9c4da7b8-..." },
    { "type": "ITEM_PROP", "sid": "...", "tid": "..." }
  ]
}
```

- `_mappers` 배열로 아이템 간 양방향 동기화 관계 표현
- 매퍼 타입 3종: `ITEM_NAME` (이름 동기화), `ITEM_PROP` (속성 동기화), `SFR_PARAM_VALUE` (SFR 파라미터 값 동기화)
- CMU 데이터에서 1,915개 아이템이 매퍼를 가짐
- **Cypher 매핑: 중간** — 배열 내 sub-object 구조라 Cypher 확장 함수 필요

### REF-05: SFR 링크 (itemRef)

```json
{
  "itemType": "SFR",
  "properties": {
    "itemRef": "9c4da7b8-...",  ← 이 SFR이 속한 컴포넌트
    "name": "CTRL_CONTROLLER__CMU_CPU_SS",
    "spec": "{\"fields\":[...]}"
  }
}
```

- SFR/SFRField가 `itemRef`로 자신이 소속된 클럭 컴포넌트를 역참조
- **Cypher 매핑: 쉬움** — `(:SFR)-[:BELONGS_TO]->(:Component)`

### REF-06: hotData 임베디드 (JSON 문자열 참조)

```json
{
  "itemType": "SFR",
  "properties": {
    "spec": "{\"name\":\"CTRL_DIVIDER\",\"fields\":[{\"name\":\"SFR_DIVRATIO\",\"index\":0,\"size\":4}],\"mappers\":{\"P_WIDTH_DIVRATIO\":\"maxDivRatioWidth\"}}"
  }
}
```

- SFR의 `spec` 속성에 JSON 문자열로 필드 정의, 파라미터 매퍼 등이 임베딩
- 중첩 깊이 최대 2단계
- `JSON.parse()` 후 내부 참조 해석 필요
- **Cypher 매핑: 어려움** — JSON 문자열 파싱은 Cypher 표준에 없음

### 관계 메커니즘 요약

| REF | 관계 | 저장 방식 | Cypher 매핑 |
|---|---|---|---|
| REF-01 | 트리 | `pid` → `id` | 쉬움 |
| REF-02 | 속성 FK | 속성값 = UUID | 중간 |
| REF-03 | 연결 토폴로지 | Connection + Input/Output + Label/LabelRef | **어려움** |
| REF-04 | 매퍼 동기화 | `_mappers[]{type, sid, tid}` | 중간 |
| REF-05 | SFR 링크 | `itemRef` = UUID | 쉬움 |
| REF-06 | 임베디드 JSON | `spec` 문자열 내 참조 | **어려움** |

---

## 3. "Neo4j Cypher로 커버되는가?" 분석

### 3.1 철학적 호환성: YES

Clock Canvas DB는 Property Graph의 4대 요소를 모두 갖추고 있다:

| Property Graph 요소 | Clock Canvas 대응 |
|---|---|
| 노드 (vertices) | 각 아이템 (3,005개) |
| 엣지 (edges) | Connection(221), pid관계, UUID참조, _mappers |
| 속성 (properties) | `properties` 객체 |
| 레이블 (labels) | `itemType` 필드 (45+ 종류) |
| 방향성 (directed) | sourceOutput→targetInput, pid→id |

### 3.2 실무적 호환성: PARTIAL

| REF 타입 | Cypher 표현 가능? | 난이도 | 비고 |
|---|---|---|---|
| REF-01 (트리) | `MATCH (p)-[:HAS_CHILD]->(c)` | 쉬움 | 완벽 매핑 |
| REF-02 (속성 FK) | `MATCH (a)-[:REFERENCES]->(b)` | 중간 | 크로스문서 조인 필요 |
| REF-03 (토폴로지) | `MATCH (a)-[:CONNECTS_TO]->(b)` | **어려움** | 실제로는 3-5홉 해상도 필요. Label/LabelRef 패스스루 80줄 로직을 가상 엣지로 추상화해야 함 |
| REF-04 (매퍼) | Cypher 확장 함수 필요 | 중간 | 표준에서 벗어남 |
| REF-05 (SFR 링크) | `MATCH (s:SFR)-[:BELONGS_TO]->(c)` | 쉬움 | 완벽 매핑 |
| REF-06 (hotData) | Cypher 확장 함수 필요 | **어려움** | JSON 문자열 파싱은 Cypher 표준 밖 |

### 3.3 핵심 문제: REF-03 (Connection 토폴로지)

Clock Canvas의 핵심 가치인 **"클럭 경로 추적"**이 Cypher 표준과 가장 맞지 않는 부분이다.

```
Cypher의 엣지 모델:     (A)-[:CONNECTS_TO]->(B)    ← 단순

Canvas의 실제 연결:     Node → Output(port) → Connection(중간) → Input(port) → Node
                        + Label → LabelRef (다이어그램 간 투명 패스스루)
                        = 3~5홉 해상도 로직
```

이 로직을 Cypher로 표현하면:
- `OPTIONAL MATCH` 체인 + `CASE` 표현식이 필요
- 또는 가상 엣지 `[:CONNECTS_TO]`를 만들되, 내부적으로 80줄 해상도 함수 실행
- 어느 쪽이든 **"LLM이 Cypher를 이미 잘 생성한다"는 장점이 상쇄**됨

---

## 4. 쿼리 전략 Options 비교

### 4.1 평가 대상 Options

| Option | 설명 | LOC | 인프라 |
|---|---|---|---|
| A | Cypher → Canvas DB 트랜스파일러 | 800-1200 | 없음 |
| B | JSON 쿼리 DSL → Canvas DB 함수 | 400-600 | 없음 |
| C | Cypher-like 서브셋 + Canvas 확장 | — | — |
| **D** | **Python 헬퍼 라이브러리 확장** | **400-500** | **없음** |
| E | Neo4j ETL (실제 그래프 DB) | 300-500 + Neo4j | Neo4j 서버 |

### 4.2 타겟 쿼리 11개

| # | 쿼리 | 필요 REF | 복잡도 |
|---|---|---|---|
| Q1 | "CMU_CPU_SS의 모든 ClockDivider 목록" | REF-01 | 낮음 |
| Q2 | "DIV_CPU의 분주비 설정값은?" | REF-01 + 속성 | 낮음 |
| Q3 | "PLL0에서 CPU IP까지 클럭 경로 추적" | REF-03 | 높음 |
| Q4 | "DIV_CPU의 SFR 레지스터 필드 목록" | REF-05 | 중간 |
| Q5 | "PLL0의 PLL 타입과 주파수 공식은?" | REF-02 | 중간 |
| Q6 | "DIV_CPU의 이름이 바뀌면 어디가 같이 바뀌나?" | REF-04 | 중간 |
| Q7 | "ClockGate가 3개 이상인 경로 찾기" | REF-03 멀티홉 | 높음 |
| Q8 | "PWRDOWN 기능이 활성화된 모든 노드" | REF-01 + 속성 | 중간 |
| Q9 | "Label로 연결된 다이어그램 간 클럭 경로" | REF-03 + Label | 높음 |
| Q10 | "PLL0의 출력 주파수가 변하면 영향받는 모든 하위 노드" | REF-02 + REF-03 | 높음 |
| Q11 | "DIV_CPU의 SFR spec에 정의된 파라미터 매퍼 목록" | REF-06 | 중간 |

### 4.3 Option별 평가

#### Option A: Cypher → Canvas DB 트랜스파일러

```
LLM → Cypher 생성 → AST 파싱 → Canvas DB API 호출로 변환
```

| 항목 | 평가 |
|---|---|
| 커버리지 | 6/11 (REF-03/04/06 쿼리에서 한계) |
| LOC | 800-1200 (Cypher 파서 서브셋 + 6개 REF 리졸버) |
| 장점 | LLM이 Cypher를 이미 잘 생성, 표준 문법, 풍부한 학습 자료 |
| 단점 | REF-03 Label 패스스루를 Cypher 엣지로 매핑 어려움, 파서 구현 비용 높음, Canvas 확장이 필요해지면 표준의 장점 상실 |
| 판정 | **3순위** — 단순 쿼리에는 좋지만 Canvas 핵심 기능에서 한계 |

#### Option B: JSON 쿼리 DSL → Canvas DB 함수

```json
{"from": "ClockDivider", "traverse": [{"ref": "REF-03", "depth": 5, "filter": {"itemType": "ClockGate"}}]}
```

| 항목 | 평가 |
|---|---|
| 커버리지 | 11/11 (Canvas 구조에 최적화) |
| LOC | 400-600 (JSON 스키마 + 6개 리졸버) |
| 장점 | Canvas 6개 REF 타입을 1급 시민으로 지원, 파서 불필요, 정적 분석 가능 |
| 단점 | LLM이 새 문법 학습 필요 (프롬프트 ~50줄 추가), 비표준, 유지보수 부담 |
| 판정 | **2순위** — Option D로 부족할 때의 대안 |

#### Option C: Cypher-like 서브셋 + Canvas 확장 (탈락)

| 항목 | 평가 |
|---|---|
| 탈락 사유 | Option A의 파서 비용 + Option B의 학습 비용을 동시에 부담하면서 어느 쪽의 장점도 완전히 얻지 못함 |

#### Option D: Python 헬퍼 라이브러리 확장 (추천)

```python
# 기존 run_db_query Python executor에 헬퍼 추가
follow(item_id, ref_type="connection")     # 단일 홉 탐색
paths(from_id, to_id, max_depth=10)        # 멀티홉 경로 탐색
mapper(item_id, mapper_type="ITEM_NAME")   # REF-04 전용
schema("ClockDivider")                      # 스키마 자기 발견
```

| 항목 | 평가 |
|---|---|
| 커버리지 | 11/11 (LLM이 Python으로 자유롭게 조합) |
| LOC | 400-500 (6개 REF 리졸버 + BFS 경로탐색 + 에러핸들링) |
| 장점 | 검증된 패턴 (70%→100% 정확도 달성 이력), 최소 인프라 비용, LLM이 Python을 가장 안정적으로 생성 |
| 단점 | 쿼리가 Python 코드 형태라 정적 분석 불가, 장기적으로 헬퍼 코드 누적 |
| 판정 | **1순위 (추천)** |

검증 근거:
- 기존 에이전트가 8개 구조화 도구(70%) → Python executor(100%)로 진화한 이력
- `trace()` (82줄)와 `get_sfr()` (70줄)가 이미 이 패턴으로 동작 중
- 새 헬퍼는 기존 `local_vars` dict에 추가하면 됨 (tools.py:284-291)

#### Option E: Neo4j ETL

```
MongoDB → ETL 스크립트 → Neo4j → 네이티브 Cypher
```

| 항목 | 평가 |
|---|---|
| 커버리지 | 11/11 (네이티브 그래프 DB) |
| LOC | 300-500 (ETL 스크립트) + Neo4j 인프라 |
| 장점 | 가장 깨끗한 그래프 모델, REF-03도 실제 엣지로 변환하면 단순 Cypher로 탐색 가능, 유지보수 부담 flat |
| 단점 | Neo4j 서버 운영 필요, Canvas 변경 시 ETL 재실행, 데이터 동기화 문제 |
| 판정 | **4순위** — 마이그레이션 트리거 충족 시 재평가 |

### 4.4 최종 비교표

| 기준 | A (Cypher) | B (JSON DSL) | D (헬퍼) | E (Neo4j) |
|---|---|---|---|---|
| 커버리지 | 6/11 | 11/11 | 11/11 | 11/11 |
| LOC | 800-1200 | 400-600 | 400-500 | 300-500 + 인프라 |
| LLM 친화성 | 높음 (표준) | 중간 (학습 필요) | 높음 (Python) | 높음 (Cypher) |
| REF-03 처리 | 어려움 | 가능 | 가능 | 깨끗함 |
| 인프라 | 없음 | 없음 | 없음 | Neo4j |
| **추천 순위** | **3** | **2** | **1** | **4** |

---

## 5. 추천 전략: Option D 상세

### 5.1 헬퍼 함수 시그니처

```python
def follow(item_id: str, ref_type: str, **kwargs) -> list[dict]:
    """단일 홉 탐색.
    ref_type: 'children' | 'parent' | 'connection' | 'reference' | 'mapper' | 'sfr_link' | 'hotdata'
    kwargs: prop (REF-02 속성명), mapper_type (REF-04), direction (forward/backward)
    """

def paths(from_id: str, to_id: str = None, max_depth: int = 10,
          ref_types: list[str] = None, filter_type: str = None) -> list[list[dict]]:
    """멀티홉 경로 탐색. BFS 사용.
    to_id=None이면 도달 가능한 모든 노드 반환.
    ref_types로 사용할 관계 타입 제한 가능.
    visited set으로 순환 방지.
    """

def mapper(item_id: str, mapper_type: str = None) -> list[dict]:
    """REF-04 전용.
    _mappers에서 sid/tid로 연결된 아이템 반환.
    mapper_type: 'ITEM_NAME' | 'ITEM_PROP' | 'SFR_PARAM_VALUE' | None(전체)
    """

def schema(item_type: str) -> dict:
    """스키마 정의 반환.
    허용 속성, 자식 타입, 참조 타입, extend 정보 포함.
    """
```

### 5.2 LOC 추정 내역

| 헬퍼 | 예상 LOC | 근거 |
|---|---|---|
| `follow()` + REF 리졸버 6개 | 200-250 | REF-03만 80줄 (기존 trace 참고), 나머지 5개 각 20-30줄 |
| `paths()` | 60-80 | BFS + visited + depth limit + 필터 |
| `mapper()` | 30-40 | _mappers 배열 필터링 |
| `schema()` | 40-60 | 스키마 JSON 로딩 + 캐싱 |
| 에러 핸들링 + 유틸 | 40-60 | 깨진 참조, JSON 파싱 등 |
| **합계** | **400-500** | |

### 5.3 Known Risks

| 리스크 | 발생 조건 | 완화 전략 |
|---|---|---|
| 깨진 참조 체인 | Connection의 targetInput이 존재하지 않는 ID | `follow()`가 `None` 반환 + 경고 로그. `paths()`는 부분 경로 반환 |
| 순환 참조 | Label↔LabelRef 간 순환 | 모든 탐색 함수에 `visited` set. 기본 `max_depth=10` |
| 성능 저하 | REF-03 멀티홉이 MongoDB 앱레벨 조인으로 느림 | `pid`+`itemType` 복합 인덱스. 단일 CMU 내 탐색은 메모리 내 dict 변환 처리 |
| hotData 파싱 실패 | spec 필드가 malformed JSON | `json.loads()` try/catch, 실패 시 raw 문자열 반환 |
| 헬퍼 코드 누적 | 새 REF 타입 추가, 요구사항 증가 | 마이그레이션 트리거 (아래 참조) |

### 5.4 마이그레이션 트리거 (Option E 전환 조건)

다음 중 **하나라도 충족**되면 Option E (Neo4j ETL) 재평가:

1. `tools.py` 헬퍼 로직이 **800 LOC** 초과
2. **7번째 REF 타입**이 발견됨
3. 평균 쿼리 응답이 **5초** 초과

---

## 6. 수용 기준 및 검증 프로토콜

### 6.1 수용 기준

| # | 기준 | 측정 방법 |
|---|---|---|
| AC-1 | 11개 타겟 쿼리 중 8개 이상을 ≤3 LLM 턴으로 해결 | gpt-4o-mini, temperature=0, 각 쿼리 3회 독립 실행, 2/3 이상 성공 시 PASS |
| AC-2 | 6개 REF 타입 모두 탐색 함수 존재 | 각 REF 타입별 단위 테스트 1개 (Python assert) |
| AC-3 | 기존 46문항 테스트셋 회귀 없음 | `python scripts/eval_mc.py --all --split test` 기존 점수 이상 |
| AC-4 | Label/LabelRef 패스스루 동작 | Q9 전용 테스트: 다이어그램 간 경로가 Label을 투명하게 통과 |

### 6.2 Follow-ups

1. `pid` + `itemType` 복합 인덱스 확인/생성
2. 11개 타겟 쿼리 자동화 테스트 스크립트 작성
3. `prompts.py`에 `follow()`/`paths()`/`mapper()`/`schema()` 사용 패턴 문서 추가

---

## 7. ADR (Architecture Decision Record)

**Decision**: Option D — 기존 Python executor(`run_db_query`) 위에 그래프 탐색 헬퍼 라이브러리 구축

**Drivers**:
1. 검증된 아키텍처 패턴 (70%→100% 정확도 달성 이력)
2. 최소 인프라 비용 (새 DB 없음)
3. 11개 타겟 쿼리 전체 커버리지
4. LLM이 Python을 가장 안정적으로 생성 (Cypher보다 안정적)

**Alternatives Considered**:
- Option A (Cypher 트랜스파일러): REF-03/04/06 매핑 어려움, 800-1200 LOC, 6/11 커버리지 → 기각
- Option B (JSON DSL): Canvas 최적화 가능하나 LLM 학습 비용 → 대안으로 보류
- Option C (하이브리드): 양쪽 단점 결합 → 기각
- Option E (Neo4j ETL): 가장 깨끗하지만 인프라 부담 → 마이그레이션 트리거로 예약

**Why Chosen**:
- `trace()`와 `get_sfr()`가 이 패턴으로 100% 정확도 달성한 실적
- REF-03의 80줄 Label/LabelRef 패스스루 로직은 Cypher 표준에 맞지 않음
- 400-500 LOC로 6개 REF 타입 모두 커버

**Consequences**:
- tools.py가 ~850줄로 증가 (현재 350 + 500)
- 장기적으로 Option E 마이그레이션 가능성 있음
- 새 헬퍼 함수마다 prompts.py에 사용법 문서 추가 필요

---

## Sources

- Clock Canvas DB raw data: `db_search_agent/raw_data/example/*.json` (8개 스키마 파일)
- Clock Canvas DB MongoDB export: `db_search_agent/raw_data/MongoDB/` (CMU 3,005 아이템, InputClockFolder)
- 기존 에이전트 코드: `db_search_agent/clock_agent/tools.py` (trace, get_sfr, run_db_query)
- 에이전트 최적화 보고서: `db_search_agent/docs_test/1_agent-optimization-report.md`
- 데이터 관계 문서: `db_search_agent/docs_development/04-데이터-관계와-질의.md`
- 선행 연구: `docs/260327_agent-domain-knowledge-retrieval-best-method.md`
