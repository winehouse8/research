# Clock Canvas DB → Neo4j ETL 가능성 심층 조사

작성일: 2026-03-27
선행 보고서: `260327_clock-canvas-db-graph-query-strategy.md` (Option E 상세 조사)

---

## Executive Summary

**결론: 기술적으로 완전히 가능하다. 그리고 생각보다 깨끗하게 매핑된다.**

Clock Canvas DB의 3,005개 아이템 + 6가지 관계는 Neo4j Property Graph로 **1:1 매핑**이 가능하다. ETL 후에는 현재 80줄짜리 Python 패스스루 로직(`trace()`)이 Cypher 한 줄로 대체된다. 가장 복잡한 관계인 REF-03(Connection 토폴로지)도 ETL 시점에 **가상 엣지로 사전 해상도(pre-resolve)**하면 Cypher `MATCH (a)-[:CLOCK_SIGNAL*1..10]->(b)`로 자유 탐색이 가능하다.

**핵심 트레이드오프:**
- ETL 1회 비용: ~300-400 LOC Python 스크립트
- 얻는 것: 네이티브 Cypher 쿼리, 경로 탐색 `O(관계수)`, Label 패스스루 자동화
- 잃는 것: Neo4j 인프라 필요 (Docker 1개), MongoDB↔Neo4j 동기화 부담

---

## 1. 실제 데이터 정밀 분석 결과

### 1.1 데이터 규모

| 항목 | CMU_CPU_SS (1개 CMU) | 추정 전체 SoC |
|---|---|---|
| 아이템 수 | 3,005 | ~30,000-100,000 (CMU 10-30개) |
| Connection (엣지) | 221 | ~2,000-7,000 |
| Label/LabelRef | 29/65 | ~300-2,000 |
| SFR/SFRField | 341/962 | ~3,000-10,000 |
| _mapper 엔트리 | 3,652 | ~30,000-100,000 |

**Neo4j 관점**: 이 규모는 Neo4j에게 **매우 작은** 그래프다. Neo4j는 수십억 노드도 처리한다. 성능은 전혀 문제가 되지 않는다.

### 1.2 아이템 공통 필드 (모든 아이템이 가짐)

```
{
  "id":       "760c552a-...",        ← 고유 ID → Neo4j node ID
  "pid":      "88e28c1b-...",        ← 부모 ID → :HAS_CHILD 엣지
  "itemType": "ClockDiagram",        ← Neo4j Label
  "title":    "CD_CPU_SS",           ← 표시명
  "domain":   "Clock",               ← 도메인 (항상 "Clock")
  "module":   "e8d4a276-...",        ← 소속 CMU ID
  "_type":    "design",              ← 항상 "design"
  "_mappers": [...],                 ← REF-04 매퍼 배열
  "_sync":    {},                    ← 동기화 메타 (비어있음)
  "mirroredChildren": [],            ← 미러 (비어있음)
  "properties": { ... }             ← 타입별 속성
}
```

### 1.3 Connection의 실제 해상도 체인 (REF-03)

실제 데이터에서 확인한 연결 토폴로지:

```
ClockExternalCLKSource "CPU_EXTCLK"
  └→ Output (key=CLK_OUTPUT, port)
       └→ Connection (sourceOutput→targetInput)
            └→ Input (key=CLK_INPUT, port)
                 └→ Label "CPU_EXTCLK" (브릿지)
                      └→ LabelRef (다이어그램 내 여러 곳에서 참조)
                           └→ Input of next node...
```

**실제 토폴로지 분포** (CMU_CPU_SS, 221개 Connection):

| 소스 → 타겟 | 개수 | 의미 |
|---|---|---|
| LabelRef → ClockMultiplexer | 36 | 라벨에서 먹스로 입력 |
| LabelRef → ClockGate | 36 | 라벨에서 게이트로 입력 |
| ClockGate → ClockIP | 36 | 게이트에서 IP로 출력 |
| ClockGate → ClockQChannelManager | 28 | 게이트에서 QCH로 |
| ClockExternalCLKSource → ClockFreqmon | 20 | 외부클럭에서 주파수모니터로 |
| ClockPLLCtrl → ClockDivider | 9 | PLL에서 분주기로 |
| ClockDivider → Label | 9 | 분주기에서 라벨로 (브릿지) |
| ClockMultiplexer → ClockDFTOCCBuffer | 9 | 먹스에서 DFT버퍼로 |
| ClockDFTOCCBuffer → Label | 9 | DFT버퍼에서 라벨로 |
| LabelRef → ClockPLLCtrl | 8 | 라벨에서 PLL로 |
| ClockPLLCtrl → Label | 8 | PLL에서 라벨로 |
| ClockPLLCtrl → ClockFreqmon | 8 | PLL에서 주파수모니터로 |
| ClockExternalCLKSource → Label | 3 | 외부클럭에서 라벨로 |

---

## 2. Neo4j 스키마 설계

### 2.1 노드 매핑

**원칙**: 모든 아이템 → Neo4j 노드. `itemType` → Neo4j Label.

```cypher
// 모든 아이템이 공통 속성을 가짐
CREATE (n:ClockDivider {
  uid:      "760c552a-...",       // MongoDB id
  title:    "CPU_PLL0_DIV",
  module:   "e8d4a276-...",       // 소속 CMU
  domain:   "Clock",

  // properties 객체를 flatten
  name:              "CPU_PLL0_DIV",
  maxDivRatioWidth:  4,
  divRatioInitValue: 0,
  clkEn:             false,
  ECC:               false,
  SDCPath:           "/CMU_CPU_SS/...",
  nodeID:            "abc123",
  nodeType:          "ITDADIVIDER"
})
```

**특수 처리가 필요한 타입:**

| 타입 | 처리 | 이유 |
|---|---|---|
| Connection | **노드로 만들지 않음** → 엣지로 변환 | 중간 매개체일 뿐 |
| Input/Output | **노드로 만들지 않음** → 포트 정보를 엣지 속성으로 | 중간 매개체 |
| NodeMetaView | **노드로 만들지 않음** → 부모 노드에 x,y 속성 병합 | 뷰 메타데이터 |
| Label | 노드로 생성 (브릿지 역할) | 다이어그램 간 연결에 핵심 |
| LabelRef | 노드로 생성 | Label과 쌍으로 동작 |

### 2.2 엣지 매핑 (6개 REF 타입)

#### REF-01: HAS_CHILD (트리)

```cypher
// pid → id 관계
CREATE (parent)-[:HAS_CHILD]->(child)

// 예시
MATCH (cmu:ClockCMU {uid: "e8d4a276-..."})
MATCH (folder:ClockDiagramFolder {uid: "88e28c1b-..."})
CREATE (cmu)-[:HAS_CHILD]->(folder)
```

**ETL**: `pid`로 부모를 찾아 엣지 생성. 단순. ~2,800개 엣지.

#### REF-02: REFERENCES (속성 FK)

```cypher
// 속성값이 UUID인 경우 → 엣지로 변환
CREATE (pllctrl)-[:REFERENCES {prop: "plltype"}]->(inputPLL)
CREATE (cmu)-[:REFERENCES {prop: "refCLK"}]->(label)
CREATE (divider)-[:REFERENCES {prop: "unifiedModule"}]->(freqmon)

// 크로스 문서도 가능 (InputClockFolder의 아이템도 노드로 생성)
```

**확인된 UUID 참조 속성:**

| itemType | 속성 | 타겟 타입 | 크로스 문서? |
|---|---|---|---|
| ClockCMU | `refCLK` | Label | 아니오 |
| ClockCMU | `PCLK` | (외부) | 예 |
| ClockPLLCtrl | `plltype` | InputClockPLL | **예** |
| ClockPLL | `plltype` | InputClockPLL | **예** |
| ClockDivider | `unifiedModule` | ClockFreqmon 등 | 아니오 |
| ClockDivider | `hardeningCLKCOMP` | InputClockCLKComp | **예** |
| ClockMultiplexer | `unifiedModule` | ClockFreqmon 등 | 아니오 |
| ClockMultiplexer | `hardeningCLKCOMP` | InputClockCLKComp | **예** |
| LabelRef | `itemLabel` | Label | 아니오 |
| SFR | `itemRef` | ClockCMUCtrl 등 | 아니오 |
| SFRField | `itemRef` | ClockCMUCtrl 등 | 아니오 |
| ConfigurationFolder | `selectedConfiguration` | (외부) | 예 |

**ETL**: 속성값이 UUID 패턴이면 → `REFERENCES` 엣지 생성. ~500-1000개.

#### REF-03: CLOCK_SIGNAL (연결 토폴로지) — 핵심

**현재 MongoDB에서의 해상도 (80줄 Python)**:
```
Output.connections[] → Connection.id
  → Connection.targetInput → Input.id
    → Input의 부모(pid) = 타겟 노드
      → 타겟이 Label이면 → Label.labelRefs[] → LabelRef 각각
        → LabelRef의 부모 다이어그램에서 Output 찾아서 재귀...
```

**Neo4j에서의 해상도 (ETL 시 사전 해상도)**:

ETL 시점에 Connection 체인을 풀어서 **직접 엣지**를 생성한다:

```cypher
// 사전 해상도된 클럭 신호 엣지
CREATE (src:ClockPLLCtrl)-[:CLOCK_SIGNAL {
  connection_id: "edb30eac-...",
  source_port:   "CLK_OUTPUT",
  target_port:   "CLK_INPUT"
}]->(tgt:ClockDivider)

// Label 패스스루도 사전 해상도
CREATE (label:Label)-[:LABEL_BRIDGE]->(labelref:LabelRef)
CREATE (src_node)-[:CLOCK_SIGNAL]->(label)
CREATE (labelref)-[:CLOCK_SIGNAL]->(tgt_node)
```

**ETL 후 Cypher 쿼리:**

```cypher
// "PLL0에서 CPU IP까지 클럭 경로 추적" — 현재 80줄 Python이 이 한 줄로!
MATCH path = (pll:ClockPLLCtrl {name: "CPU_PLL0"})
             -[:CLOCK_SIGNAL*1..10]->
             (ip:ClockIP)
RETURN path

// "ClockGate가 3개 이상인 경로 찾기"
MATCH path = (start)-[:CLOCK_SIGNAL*]->(end)
WHERE size([n IN nodes(path) WHERE n:ClockGate]) >= 3
RETURN path

// "Label로 연결된 다이어그램 간 클럭 경로"
MATCH path = (a)-[:CLOCK_SIGNAL*]->(b)
WHERE any(n IN nodes(path) WHERE n:Label)
RETURN path
```

**ETL 알고리즘:**

```python
def resolve_connections(items):
    """Connection → CLOCK_SIGNAL 직접 엣지 변환"""
    id_map = {i['id']: i for i in items}
    edges = []

    for conn in items:
        if conn['itemType'] != 'Connection':
            continue

        # Output → Connection → Input 해상도
        src_output = id_map.get(conn['properties']['sourceOutput'])
        tgt_input = id_map.get(conn['properties']['targetInput'])
        if not src_output or not tgt_input:
            continue

        src_node = id_map.get(src_output['pid'])  # Output의 부모 = 소스 노드
        tgt_node = id_map.get(tgt_input['pid'])    # Input의 부모 = 타겟 노드

        edges.append({
            'type': 'CLOCK_SIGNAL',
            'from': src_node['id'],
            'to': tgt_node['id'],
            'props': {
                'connection_id': conn['id'],
                'source_port': src_output['properties'].get('key', ''),
                'target_port': tgt_input['properties'].get('key', ''),
            }
        })

    return edges  # Label/LabelRef는 별도 LABEL_BRIDGE 엣지로 처리
```

**CLOCK_SIGNAL 엣지 수**: 221개 (Connection 1:1)
**LABEL_BRIDGE 엣지 수**: 65개 (LabelRef 1:1)

#### REF-04: MAPS_TO (매퍼)

```cypher
// _mappers[]{type, sid, tid} → 엣지
CREATE (src)-[:MAPS_TO {mapper_type: "ITEM_NAME"}]->(tgt)
CREATE (src)-[:MAPS_TO {mapper_type: "ITEM_PROP"}]->(tgt)
CREATE (src)-[:MAPS_TO {mapper_type: "SFR_PARAM_VALUE"}]->(tgt)
```

**분포:**
- ITEM_NAME: 3,490개 (이름 동기화)
- SFR_PARAM_VALUE: 108개 (SFR 파라미터 값 동기화)
- ITEM_PROP: 54개 (속성 동기화)

**ETL**: `_mappers` 배열 순회, `sid`→`tid` 방향으로 엣지 생성. ~3,652개 엣지.

**주의**: mapper는 아이템 자체가 owner인데, `sid`→`tid` 방향이 실제 동기화 방향이다. owner는 엣지 속성으로 기록.

#### REF-05: BELONGS_TO (SFR 링크)

```cypher
// SFR.itemRef, SFRField.itemRef → 소속 컴포넌트
CREATE (sfr:SFR)-[:BELONGS_TO]->(ctrl:ClockCMUCtrl)
CREATE (field:SFRField)-[:BELONGS_TO]->(ctrl:ClockCMUCtrl)
```

**ETL**: `itemRef` 속성이 있으면 → `BELONGS_TO` 엣지. ~1,300개 (SFR 341 + SFRField 962).

#### REF-06: hotData (임베디드 JSON)

두 종류의 hotData가 있다:

**6a. SFR spec (JSON 문자열)**:
```json
{
  "spec": "{\"name\":\"CTRL_DIVIDER\",\"fields\":[...],\"mappers\":{...}}"
}
```

→ ETL 시 `spec`을 파싱하여:
- `fields[]`의 각 필드 정보를 SFRField 노드의 속성으로 보강
- `mappers{}`의 매핑 정보를 `PARAM_MAPS_TO` 엣지로 변환

**6b. Table hotData (PLL 파라미터 테이블)**:
```json
{
  "hotData": "[{\"SFR Name\":{\"value\":\"CTRL_PLL_STATUS\"},\"Offset\":{\"value\":\"0xc\"},...}]",
  "hotColHeader": "[\"SFR Name\",\"Offset\",\"Bit Field Name\",...]"
}
```

→ ETL 시 Table 내용을 별도 노드(`PLLParam`)로 변환하거나, InputClockPLL 노드에 속성으로 병합.

**ETL 복잡도**: 중간. JSON 파싱 + 구조 해석 필요. ~50줄.

### 2.3 전체 Neo4j 스키마 요약

```
[Node Labels]
:ClockCMU, :ClockDiagram, :ClockDiagramFolder, :ClockPLLCtrl, :ClockPLL,
:ClockDivider, :ClockMultiplexer, :ClockGate, :ClockFreqmon,
:ClockExternalCLKSource, :ClockIP, :ClockDFTOCCBuffer,
:ClockCMUCtrl, :ClockQChannelManager,
:Label, :LabelRef,
:SFRBlock, :SFR, :SFRField, :SFRParam,
:InputClockPLL, :InputClockCLKComp,
:ConfigurationFolder,
:ClockDividerEXT, :ClockPLLCtrlEXT, :ClockMultiplexerEXT,
:ClockGateEXT, :ClockFreqmonEXT, :ClockQChannelManagerEXT,
:ClockEXTCTRL* (EDGESYNC, PWRDOWN, THROTTLE, CUSTOM, EWAKEUP, SHORTSTOP, FREQMON, PEXTENDED)

[Edge Types]
:HAS_CHILD        ← REF-01 트리 (~2,800)
:REFERENCES        ← REF-02 속성 FK (~500-1,000)
:CLOCK_SIGNAL      ← REF-03 사전 해상도된 클럭 경로 (~221)
:LABEL_BRIDGE      ← REF-03 Label↔LabelRef 브릿지 (~65)
:MAPS_TO           ← REF-04 매퍼 동기화 (~3,652)
:BELONGS_TO        ← REF-05 SFR→컴포넌트 (~1,300)
:PARAM_MAPS_TO     ← REF-06 SFR spec 내 파라미터 매핑 (~100)

[총 노드 수]  ~2,700 (Connection/Input/Output/NodeMetaView 제외)
[총 엣지 수]  ~8,600
```

---

## 3. ETL 스크립트 설계

### 3.1 파이프라인

```
MongoDB Document
    │
    ▼
[1] items[] 로딩 + id_map 구축
    │
    ▼
[2] 노드 생성 (Connection, Input, Output, NodeMetaView 제외)
    │  - itemType → Neo4j Label
    │  - properties를 노드 속성으로 flatten
    │  - NodeMetaView의 x,y를 부모 노드에 병합
    │
    ▼
[3] REF-01 엣지: pid → HAS_CHILD
    │
    ▼
[4] REF-03 엣지: Connection 체인 해상도 → CLOCK_SIGNAL
    │  - Output.pid = 소스 노드, Input.pid = 타겟 노드
    │  - Label.labelRefs → LABEL_BRIDGE
    │
    ▼
[5] REF-02 엣지: UUID 속성 → REFERENCES
    │  - 알려진 UUID 속성: plltype, refCLK, PCLK, unifiedModule,
    │    hardeningCLKCOMP, itemLabel, selectedConfiguration
    │
    ▼
[6] REF-04 엣지: _mappers[] → MAPS_TO
    │
    ▼
[7] REF-05 엣지: itemRef → BELONGS_TO
    │
    ▼
[8] REF-06: spec JSON 파싱 → 속성 보강 + PARAM_MAPS_TO
    │
    ▼
[9] 크로스 문서 처리: InputClockFolder 로딩 → 노드 생성 → 엣지 연결
    │
    ▼
Neo4j Graph
```

### 3.2 LOC 추정

| 단계 | LOC | 비고 |
|---|---|---|
| MongoDB 로딩 + id_map | 20 | pymongo + dict comprehension |
| 노드 생성 (필터링 + flatten) | 50 | itemType 필터, properties flatten |
| REF-01 HAS_CHILD | 15 | pid 루프 |
| REF-03 CLOCK_SIGNAL | 60 | Connection 해상도 + Label/LabelRef |
| REF-02 REFERENCES | 30 | UUID 패턴 매칭 |
| REF-04 MAPS_TO | 20 | _mappers 루프 |
| REF-05 BELONGS_TO | 15 | itemRef 루프 |
| REF-06 hotData | 40 | JSON 파싱 + spec 해석 |
| 크로스 문서 처리 | 30 | InputClockFolder 로딩 |
| Neo4j 드라이버 + 배치 삽입 | 40 | neo4j-driver, UNWIND 배치 |
| 유틸/에러핸들링 | 30 | 로깅, 깨진 참조 처리 |
| **합계** | **~350** | |

### 3.3 핵심 ETL 코드 (의사 코드)

```python
from neo4j import GraphDatabase
from pymongo import MongoClient

def etl_cmu_to_neo4j(mongo_doc, neo4j_session):
    items = mongo_doc['items']
    id_map = {i['id']: i for i in items}

    # ── 노드 제외 대상 ──
    SKIP_TYPES = {'Connection', 'Input', 'Output', 'NodeMetaView'}

    # ── [2] 노드 생성 ──
    nodes = []
    for item in items:
        if item['itemType'] in SKIP_TYPES:
            continue
        props = {'uid': item['id'], 'title': item['title'],
                 'module': item['module'], 'domain': item['domain']}
        props.update(flatten_properties(item['properties']))
        nodes.append((item['itemType'], props))

    neo4j_session.run("""
        UNWIND $nodes AS n
        CALL apoc.create.node([n[0]], n[1]) YIELD node
        RETURN count(node)
    """, nodes=nodes)

    # ── [3] REF-01: HAS_CHILD ──
    parent_edges = [(i['pid'], i['id']) for i in items
                     if i['itemType'] not in SKIP_TYPES and i['pid'] in id_map]
    batch_create_edges(neo4j_session, parent_edges, 'HAS_CHILD')

    # ── [4] REF-03: CLOCK_SIGNAL (핵심!) ──
    for conn in items:
        if conn['itemType'] != 'Connection':
            continue
        src_out = id_map.get(conn['properties']['sourceOutput'])
        tgt_in = id_map.get(conn['properties']['targetInput'])
        if src_out and tgt_in:
            src_node_id = src_out['pid']
            tgt_node_id = tgt_in['pid']
            create_edge(neo4j_session, src_node_id, tgt_node_id,
                       'CLOCK_SIGNAL', {
                           'connection_id': conn['id'],
                           'source_port': src_out['properties'].get('key',''),
                           'target_port': tgt_in['properties'].get('key','')
                       })

    # ── [4b] Label ↔ LabelRef 브릿지 ──
    for label in items:
        if label['itemType'] != 'Label':
            continue
        for ref_id in label['properties'].get('labelRefs', []):
            create_edge(neo4j_session, label['id'], ref_id, 'LABEL_BRIDGE')

    # ── [5] REF-02: REFERENCES ──
    UUID_PROPS = {'plltype', 'refCLK', 'PCLK', 'unifiedModule',
                  'hardeningCLKCOMP', 'itemLabel', 'selectedConfiguration'}
    for item in items:
        for prop, val in item['properties'].items():
            if prop in UUID_PROPS and is_uuid(val):
                create_edge(neo4j_session, item['id'], val,
                           'REFERENCES', {'prop': prop})

    # ── [6] REF-04: MAPS_TO ──
    for item in items:
        for m in item.get('_mappers', []):
            create_edge(neo4j_session, m['sid'], m['tid'],
                       'MAPS_TO', {'mapper_type': m['type'], 'owner': item['id']})

    # ── [7] REF-05: BELONGS_TO ──
    for item in items:
        if 'itemRef' in item['properties']:
            create_edge(neo4j_session, item['id'],
                       item['properties']['itemRef'], 'BELONGS_TO')
```

---

## 4. ETL 후 Cypher 쿼리 예시

### 보고서의 11개 타겟 쿼리가 Cypher로 어떻게 바뀌는지:

#### Q1: "CMU_CPU_SS의 모든 ClockDivider 목록"

```cypher
// MongoDB: col.find({"pid": diagram_id, "itemType": "ClockDivider"})
// Neo4j:
MATCH (cmu:ClockCMU {name: "CMU_CPU_SS"})-[:HAS_CHILD*]->(d:ClockDivider)
RETURN d.name, d.maxDivRatioWidth, d.divRatioInitValue
```

#### Q3: "PLL0에서 CPU IP까지 클럭 경로 추적"

```cypher
// MongoDB: 80줄 trace() 함수 호출 + Label 패스스루 로직
// Neo4j:
MATCH path = (pll:ClockPLLCtrl {name: "CPU_PLL0"})
             -[:CLOCK_SIGNAL|LABEL_BRIDGE*1..10]->
             (ip:ClockIP)
RETURN [n IN nodes(path) | n.name + ":" + labels(n)[0]] AS clock_path
```

#### Q5: "PLL0의 PLL 타입과 주파수 공식"

```cypher
// MongoDB: 크로스 문서 조인 (CMU doc → InputClockFolder doc)
// Neo4j:
MATCH (pll:ClockPLLCtrl {name: "CPU_PLL0"})-[:REFERENCES {prop:"plltype"}]->(type:InputClockPLL)
RETURN type.name, type.formula
// 결과: PLL_0536, (($MDIV+$KDIV/Math.pow(2,16))*$FIN)/($PDIV*Math.pow(2,$SDIV))
```

#### Q6: "DIV_CPU의 이름이 바뀌면 어디가 같이 바뀌나?"

```cypher
// MongoDB: _mappers 배열 필터링 (현재 헬퍼 없음)
// Neo4j:
MATCH (d:ClockDivider {name: "CPU_PLL0_DIV"})<-[:MAPS_TO {mapper_type:"ITEM_NAME"}]-(src)
RETURN src.title, labels(src)[0] AS type
```

#### Q7: "ClockGate가 3개 이상인 경로 찾기"

```cypher
// MongoDB: 불가능 (멀티홉 패턴 매칭)
// Neo4j:
MATCH path = (start)-[:CLOCK_SIGNAL|LABEL_BRIDGE*]->(end:ClockIP)
WHERE size([n IN nodes(path) WHERE n:ClockGate]) >= 3
RETURN path
LIMIT 10
```

#### Q9: "Label로 연결된 다이어그램 간 클럭 경로"

```cypher
// MongoDB: trace() + Label/LabelRef 패스스루 (가장 복잡한 로직)
// Neo4j:
MATCH path = (a)-[:CLOCK_SIGNAL*]->(label:Label)-[:LABEL_BRIDGE]->(lr:LabelRef)-[:CLOCK_SIGNAL*]->(b)
RETURN path
```

#### Q10: "PLL0의 출력 주파수가 변하면 영향받는 모든 하위 노드"

```cypher
// MongoDB: REF-02 + REF-03 복합 (매우 복잡)
// Neo4j:
MATCH (pll:ClockPLLCtrl {name: "CPU_PLL0"})
MATCH path = (pll)-[:CLOCK_SIGNAL|LABEL_BRIDGE*]->(downstream)
RETURN DISTINCT downstream.name, labels(downstream)[0] AS type
ORDER BY type, downstream.name
```

---

## 5. 인프라 요구사항

### 5.1 Neo4j 배포 옵션

| 옵션 | 비용 | 복잡도 | 적합성 |
|---|---|---|---|
| **Docker (추천)** | 무료 | 낮음 | `docker run neo4j:5-community` 한 줄 |
| Neo4j Desktop | 무료 | 최소 | 개발/탐색용 |
| Neo4j AuraDB Free | 무료 (제한) | 없음 | 클라우드, 200K 노드 제한 |
| Neo4j AuraDB Pro | 유료 | 없음 | 프로덕션 |

**추천**: Docker Community Edition. 이 규모(~3K 노드, ~9K 엣지)에서는 무료 버전으로 충분.

```bash
docker run -d \
  --name clock-canvas-neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/password \
  -v neo4j_data:/data \
  neo4j:5-community
```

### 5.2 동기화 전략

| 전략 | 복잡도 | 적합 시나리오 |
|---|---|---|
| **수동 ETL (추천)** | 낮음 | 설계 변경 후 수동으로 `python etl.py` 실행 |
| 이벤트 기반 | 중간 | MongoDB Change Stream → 실시간 동기화 |
| 주기적 배치 | 낮음 | cron으로 N분마다 전체 ETL |

**추천**: 수동 ETL. Clock Canvas 설계는 초 단위로 바뀌는 게 아니라, 설계 세션 단위로 바뀜. 설계 완료 후 한 번 ETL 실행하면 충분.

---

## 6. 가능성 판정 및 트레이드오프

### 6.1 가능성: 완전히 가능

| 검증 항목 | 결과 | 근거 |
|---|---|---|
| 모든 노드 매핑 가능? | **YES** | 45개 itemType → 45개 Neo4j Label |
| 모든 엣지 매핑 가능? | **YES** | 6개 REF 타입 → 7개 엣지 타입 |
| 크로스 문서 참조? | **YES** | InputClockFolder도 같은 그래프에 노드로 생성 |
| Connection 사전 해상도? | **YES** | sourceOutput→targetInput 체인을 직접 CLOCK_SIGNAL 엣지로 |
| Label/LabelRef 패스스루? | **YES** | LABEL_BRIDGE 엣지 + 가변 경로 탐색 |
| hotData 처리? | **YES** | JSON 파싱 후 속성 보강 또는 별도 노드 |
| 데이터 규모 문제? | **NO** | ~3K 노드는 Neo4j에게 극소 규모 |

### 6.2 Option D vs Option E 최종 비교

| 기준 | D (Python 헬퍼) | E (Neo4j ETL) |
|---|---|---|
| **구현 LOC** | 400-500 | ~350 (ETL) + Docker |
| **REF-03 처리** | 80줄 imperative 코드 (유지보수 부담) | `MATCH -[:CLOCK_SIGNAL*]->` 한 줄 |
| **멀티홉 경로 탐색** | BFS 직접 구현 필요 | Cypher 네이티브 (최적화됨) |
| **패턴 매칭 (Q7)** | Python 루프로 구현 (어려움) | Cypher WHERE 절 (자연스러움) |
| **새 관계 타입 추가** | 헬퍼 함수 추가 (~30줄) | ETL에 엣지 타입 추가 (~10줄) |
| **인프라** | 없음 | Docker 1개 |
| **동기화** | 불필요 (MongoDB 직접 접근) | 수동 ETL 실행 필요 |
| **LLM 인터페이스** | Python 코드 생성 (검증됨) | Cypher 생성 (LLM이 잘 함) |
| **정적 분석/시각화** | 불가 | Neo4j Browser로 그래프 시각화 |
| **디버깅** | print 기반 | Neo4j Browser에서 인터랙티브 탐색 |

### 6.3 Neo4j의 숨겨진 장점: 시각화

Neo4j Browser (`localhost:7474`)에서 클럭 트리를 **시각적으로 탐색**할 수 있다. 이것은 Python 헬퍼로는 불가능한 가치다.

```cypher
// 전체 클럭 토폴로지 시각화
MATCH (n)-[r:CLOCK_SIGNAL|LABEL_BRIDGE]->(m)
RETURN n, r, m
```

→ PLL → Divider → MUX → Gate → IP 경로를 **그래프로 직접 눈으로 볼 수 있다**.

---

## 7. 추천 로드맵

### Phase 0: PoC (1일)

```
1. Docker로 Neo4j 실행
2. CMU_CPU_SS 1개만 ETL
3. 11개 타겟 쿼리를 Cypher로 실행해서 동작 확인
4. Neo4j Browser에서 클럭 토폴로지 시각화
```

**이 PoC만으로 "Option E가 실현 가능한가?"를 확정할 수 있다.**

### Phase 1: ETL 스크립트 완성 (2-3일)

```
1. 전체 CMU 문서 ETL
2. InputClockFolder 크로스 문서 ETL
3. 깨진 참조 처리 + 로깅
4. 인덱스 생성 (uid, name, itemType)
```

### Phase 2: 에이전트 통합 (2-3일)

```
1. run_db_query에 neo4j_session 주입
2. 또는 별도 run_cypher_query 도구 추가
3. prompts.py에 Cypher 쿼리 패턴 문서 추가
4. 11개 타겟 쿼리 자동화 테스트
```

---

## 8. 결론

**Neo4j ETL은 기술적으로 완전히 가능하며, 생각보다 매핑이 깨끗하다.**

가장 큰 장점은 REF-03(Connection 토폴로지)의 80줄 Python 패스스루 로직이 Cypher `[:CLOCK_SIGNAL|LABEL_BRIDGE*]`로 대체된다는 것이다. 멀티홉 경로 탐색, 패턴 매칭, 그래프 시각화가 공짜로 따라온다.

가장 큰 단점은 Docker 인프라 1개가 추가되고, MongoDB 변경 시 수동 ETL이 필요하다는 것이다.

**최종 추천**:
- **지금 바로 Phase 0 PoC를 실행**해서 실제로 동작하는지 확인
- PoC 성공 시, Option D(Python 헬퍼)를 건너뛰고 바로 Option E(Neo4j)로 가는 것도 합리적
- Option D와 E는 상호 배타적이지 않음 — D를 먼저 만들고 마이그레이션 트리거 충족 시 E로 전환하는 기존 전략도 유효

---

## Sources

- Clock Canvas CMU MongoDB export: `raw_data/MongoDB/MongoDB - CMU - example.json.json` (3,005 items)
- Clock Canvas InputClockFolder: `raw_data/MongoDB/MongoDB - InputClockFolder - example.json.json` (16 items)
- Clock Canvas 스키마: `raw_data/example/*.json` (8 schema files)
- Neo4j Cypher Manual: https://neo4j.com/docs/cypher-manual/current/
- Neo4j Python Driver: https://neo4j.com/docs/python-manual/current/
- 선행 보고서: `260327_clock-canvas-db-graph-query-strategy.md`
