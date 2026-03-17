# 메모리 시스템 명세

`core/memory.py`가 구현하는 L0/L1/L2 계층적 메모리 로딩, annotation 주입, 논문 저장을 기술합니다.

---

## paper_id(): 결정론적 ID 생성

```python
def paper_id(claim: str, l1_summary: str) -> str:
    content = claim + l1_summary
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
```

SHA-256 해시를 앞 16자리(64비트)로 잘라 ID로 사용합니다.

### 왜 `content[:500]`이 아닌 `claim + l1_summary`인가

`content[:500]` 방식은 같은 토픽의 논문들이 유사한 도입부를 공유할 때 충돌 위험이 있습니다. `claim`은 논문의 핵심 주장이고 `l1_summary`는 ~2000 토큰 분량의 요약이므로, 두 필드를 합치면 내용이 다른 논문이 같은 ID를 가질 확률이 사실상 0에 가깝습니다. 또한 동일한 논문을 두 번 저장하면 자동으로 같은 ID가 생성되어 중복 삽입을 방지합니다.

---

## save_paper(): 논문 저장

```python
def save_paper(conn: sqlite3.Connection, paper: dict) -> str
```

`paper` 딕셔너리 키: `claim`, `l0_summary`, `l1_summary`, `l2_content`, `evidence_sources`, `assumptions`, `topic_tag`, `perspective`, `source_uri`.

### 처리 순서

1. `paper_id(claim, l1_summary)`로 ID 계산
2. `SELECT id FROM papers WHERE id = ?`로 중복 확인 — 이미 존재하면 즉시 기존 ID 반환
3. Popper 반증 가능성 게이트 실행 (아래 참조)
4. `INSERT INTO papers` — `fitness=0.5`, `status='active'`로 초기화
5. `audit_chain`에 `event_type='first_seen'`, `previous_state=NULL`, `new_state='active'` 기록
6. `conn.commit()` 후 ID 반환

### Popper 반증 가능성 게이트

```python
if not assumptions or assumptions in ("None stated", "This is a placeholder paper."):
    logger.warning(f"Popper gate: paper '{paper['claim'][:60]}' has weak/missing assumptions")
```

`assumptions` 필드가 비어 있거나 의미 없는 값이면 경고를 출력합니다. 저장 자체는 막지 않지만, 반증 불가능한 주장은 진화 생태계에서 품질이 낮다는 신호로 취급됩니다. 에이전트가 논문을 생성할 때 구체적인 전제 조건을 명시하도록 유도하는 소프트 게이트입니다.

---

## build_session_context(): 세션 컨텍스트 조립

```python
def build_session_context(
    conn: sqlite3.Connection,
    topic: str,
    session_id: str,
    max_tokens: int = 4000,
) -> str
```

에이전트가 새 세션을 시작할 때 이전 지식을 토큰 예산 내에서 주입합니다.

### 처리 파이프라인

```
1. annotation 주입 (Context Hub)
        ↓
2. L0 스캔: 해당 토픽 전체 논문 조회 (fitness DESC)
        ↓
3. 상위 3편 선택 + 랜덤 2편 선택
        ↓
4. L0 개요 섹션 작성
        ↓
5. L1 로드: 토큰 예산 내에서 선택 논문 상세 컨텍스트 추가
        ↓
6. 조립된 문자열 반환
```

### 1단계: annotation 주입 (Context Hub 패턴)

```python
annotations = conn.execute(
    """SELECT a.content, a.tags, a.created_at, p.claim
       FROM annotations a
       JOIN papers p ON a.paper_id = p.id
       WHERE p.topic_tag = ?
       ORDER BY a.created_at DESC
       LIMIT 5""",
    (topic,),
).fetchall()
```

해당 토픽의 최신 annotation 5건을 컨텍스트 맨 앞에 `## Previous Session Discoveries` 섹션으로 배치합니다. 세션이 달라도 이전에 발견한 인사이트가 자동으로 이어집니다.

### 2단계: L0 스캔

`archived`를 제외한 모든 논문의 `id`, `claim`, `l0_summary`, `fitness`, `status`, `perspective`를 `fitness DESC`로 조회합니다. L0 필드만 읽으므로 전체 논문이 많아도 빠릅니다.

### 3단계: 논문 선택

- 상위 fitness 논문 최대 3편 (`top_papers = all_papers[:3]`)
- 나머지에서 랜덤 최대 2편 (`random.sample(remaining, min(2, len(remaining)))`)

랜덤 선택은 fitness가 낮은 논문도 컨텍스트에 포함시켜 탐색(exploration)을 유지합니다.

### 4단계: L0 개요 섹션

모든 논문을 한 줄씩 나열합니다. 선택된 논문은 `★` 마커로 표시됩니다.

```
★ [empirical] (fitness=0.87) 트랜스포머 어텐션은 희소할수록 효율적이다...
  [theoretical] (fitness=0.42) 어텐션 복잡도는 O(n²)이다...
```

### 5단계: L1 로드 (토큰 예산 관리)

```python
token_count = sum(len(part.split()) for part in parts)

for pid in selected_ids:
    if token_count >= max_tokens:
        break
    ...
    block_tokens = len(block.split())
    if token_count + block_tokens <= max_tokens:
        parts.append(block)
        token_count += block_tokens
```

단어 수를 토큰의 근사치로 사용합니다. 각 L1 블록을 추가하기 전에 예산 초과 여부를 확인하므로, `max_tokens`를 넘는 블록은 추가하지 않습니다. 기본값은 4000 토큰입니다.

L1 블록 형식:
```
### [perspective] claim
Fitness: 0.87
Assumptions: ...전제 조건...
...l1_summary 본문...
```

---

## save_annotation(): 세션 발견 기록

```python
def save_annotation(
    conn: sqlite3.Connection,
    paper_id_val: str,
    session_id: str,
    content: str,
    tags: list,
) -> str
```

에이전트가 세션 중 특정 논문에 대해 발견한 내용을 저장합니다. `tags`는 JSON 직렬화하여 저장합니다. 반환값은 `uuid4().hex[:16]` 형식의 annotation ID입니다.

annotation은 삭제되지 않으며, `build_session_context()`가 다음 세션에서 자동으로 로드합니다.

---

## search_papers(): SQL LIKE 검색

```python
def search_papers(conn: sqlite3.Connection, query_text: str, topic: str) -> list
```

`claim`과 `l0_summary` 컬럼에 대해 SQL LIKE 검색을 수행합니다.

```sql
WHERE topic_tag = ? AND status != 'archived'
  AND (claim LIKE ? OR l0_summary LIKE ?)
ORDER BY fitness DESC
LIMIT 10
```

### 벡터 임베딩을 사용하지 않는 이유

전략 보고서에 따르면 L0 + LLM 필터링으로 충분합니다. 벡터 임베딩은 외부 모델 의존성과 저장 비용을 추가하지만, 이 시스템에서 검색 요청은 LLM이 이미 토픽을 알고 있는 상태에서 키워드로 보완 정보를 찾는 용도입니다. SQL LIKE로 후보를 추리고 LLM이 관련성을 판단하는 방식이 더 단순하고 충분합니다.

결과는 `fitness DESC`로 정렬하여 중요도가 높은 논문을 먼저 반환합니다. 최대 10건으로 제한합니다.

---

## get_paper(): 단일 논문 조회

```python
def get_paper(conn: sqlite3.Connection, pid: str) -> Optional[dict]
```

ID로 논문 한 편을 조회합니다. `SELECT *`로 l2_content를 포함한 모든 필드를 반환합니다. 논문이 없으면 `None`을 반환합니다. L2 전문이 필요한 심층 읽기 단계에서 사용합니다.
