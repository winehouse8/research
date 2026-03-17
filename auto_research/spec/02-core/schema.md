# SQLite 스키마 명세

`core/schema.sql`이 정의하는 5개 테이블, 인덱스, 트리거, PRAGMA 설정을 기술합니다.

---

## 테이블 개요

| 테이블 | 역할 |
|--------|------|
| `papers` | 논문/보고서 본체. L0/L1/L2 계층 필드 보유 |
| `comparisons` | 쌍비교 결과. 선택 압력(selection pressure)의 원천 |
| `edges` | 지식 관계 그래프. Phase 2 연기 |
| `annotations` | 세션 발견 메모. Context Hub 패턴 |
| `audit_chain` | append-only 불변 감사 기록 |

---

## papers

논문 한 편의 모든 데이터를 담는 중심 테이블입니다.

```sql
CREATE TABLE IF NOT EXISTS papers (
    id              TEXT PRIMARY KEY,
    claim           TEXT NOT NULL,
    l0_summary      TEXT,
    l1_summary      TEXT,
    l2_content      TEXT,
    evidence_sources TEXT,
    assumptions     TEXT,
    fitness         REAL DEFAULT 0.5,
    status          TEXT DEFAULT 'active',
    topic_tag       TEXT,
    perspective     TEXT,
    expires_at      TEXT,
    created_at      TEXT,
    source_uri      TEXT
);
```

### L0 / L1 / L2 계층 필드

| 필드 | 토큰 규모 | 용도 |
|------|-----------|------|
| `l0_summary` | ~50 토큰 | 빠른 관련성 필터링. L0 스캔 단계에서 전체 논문을 훑을 때 사용 |
| `l1_summary` | ~2000 토큰 | 추론·계획 컨텍스트. 세션 컨텍스트 조립 시 토큰 예산 내에서 로드 |
| `l2_content` | 전문 | 심층 읽기용. 필요할 때만 온디맨드 로드하여 토큰 낭비 방지 |

### 나머지 컬럼

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | TEXT PK | SHA-256(claim + l1_summary)의 앞 16자리 hex |
| `claim` | TEXT NOT NULL | 논문의 핵심 주장. 한 문장 |
| `evidence_sources` | TEXT | JSON 배열. `[{title, url, citation_count, excerpt}]` 형식 |
| `assumptions` | TEXT | 주장이 성립하는 전제 조건. Popper 반증 가능성 게이트의 입력값 |
| `fitness` | REAL | PageRank 기반 중요도 점수. 초기값 0.5, 범위 [0, 1] |
| `status` | TEXT | `active` \| `contested` \| `foundational` \| `archived` |
| `topic_tag` | TEXT | MAP-Elites 셀 주소의 첫 번째 축. 주제 분류 키 |
| `perspective` | TEXT | MAP-Elites 셀 주소의 두 번째 축. `empirical` \| `theoretical` \| `applied` \| `critical` |
| `expires_at` | TEXT | TTL 기반 재검토 기한. NULL이면 만료 없음 |
| `source_uri` | TEXT | 논문 생성 경로 감사용 (OpenViking DRR 패턴) |

---

## comparisons

쌍비교(pairwise comparison) 결과를 기록합니다. 피트니스 계산의 유일한 원천입니다.

```sql
CREATE TABLE IF NOT EXISTS comparisons (
    winner      TEXT REFERENCES papers(id),
    loser       TEXT REFERENCES papers(id),
    created_at  TEXT
);
```

### 3컬럼만 사용하는 이유

`agent_id`, `reason`, `score` 같은 컬럼을 두지 않습니다. 비교 결과에서 "누가 평가했나"는 의미가 없기 때문입니다. 피트니스는 비교 결과의 패턴(누가 누구를 얼마나 많이 이겼나)에서 PageRank로 계산되며, 평가자 정보는 이 계산에 영향을 주지 않습니다. 최소한의 컬럼으로 쓰기 경합을 줄이고 테이블을 단순하게 유지합니다.

---

## edges

논문 간 지식 관계 그래프입니다.

```sql
CREATE TABLE IF NOT EXISTS edges (
    id          TEXT PRIMARY KEY,
    src         TEXT REFERENCES papers(id),
    dst         TEXT REFERENCES papers(id),
    relation    TEXT,   -- supports|contradicts|extends|derived_from|depend_on
    strength    REAL DEFAULT 1.0,
    created_at  TEXT,
    valid_until TEXT    -- NULL = still valid
);
```

### Phase 2 연기 사유

edges 테이블은 스키마만 정의되어 있고 실제로 채워지지 않습니다. 현재 시스템은 비교(comparisons) 기반 PageRank로 충분한 선택 압력을 확보합니다. 엣지 추출에는 LLM 호출 비용이 발생하며, 관계 그래프의 유용성은 논문이 충분히 축적된 이후에 검증해야 합니다. 이에 따라 엣지 인덱스도 함께 연기됩니다(스키마 주석: `edges indexes deferred to Phase 2`).

---

## annotations

에이전트가 세션 중 발견한 인사이트를 논문에 연결해 저장합니다.

```sql
CREATE TABLE IF NOT EXISTS annotations (
    id          TEXT PRIMARY KEY,
    paper_id    TEXT REFERENCES papers(id),
    session_id  TEXT,
    content     TEXT NOT NULL,
    tags        TEXT,           -- JSON array
    created_at  TEXT
);
```

### Context Hub 패턴

`build_session_context()`는 세션 시작 시 해당 토픽의 최신 annotation 5건을 컨텍스트 맨 앞에 주입합니다. 이를 통해 이전 세션에서 발견한 내용이 새 세션에 자동으로 이어집니다. 세션이 종료되어도 발견은 DB에 남아 다음 세션에서 재사용됩니다.

---

## audit_chain

모든 상태 변화를 append-only로 기록하는 불변 감사 테이블입니다.

```sql
CREATE TABLE IF NOT EXISTS audit_chain (
    id              TEXT PRIMARY KEY,
    paper_id        TEXT,
    event_type      TEXT,   -- first_seen|status_changed|evaluated|archived|revived
    previous_state  TEXT,
    new_state       TEXT,
    agent_id        TEXT,
    created_at      TEXT
);
```

### 불변성 보장: BEFORE UPDATE / DELETE 트리거

UPDATE와 DELETE 시도를 데이터베이스 레벨에서 차단합니다.

```sql
CREATE TRIGGER IF NOT EXISTS prevent_audit_update
BEFORE UPDATE ON audit_chain
BEGIN
    SELECT RAISE(ABORT, 'audit_chain is append-only: updates are not allowed');
END;

CREATE TRIGGER IF NOT EXISTS prevent_audit_delete
BEFORE DELETE ON audit_chain
BEGIN
    SELECT RAISE(ABORT, 'audit_chain is append-only: deletes are not allowed');
END;
```

애플리케이션 코드가 실수로 레코드를 수정하거나 삭제하려 해도 SQLite가 트랜잭션을 ABORT시킵니다. 논문 삭제 대신 `archived` 상태로 전환하는 설계와 짝을 이룹니다.

---

## 인덱스

| 인덱스 | 대상 컬럼 | 용도 |
|--------|-----------|------|
| `idx_papers_topic_status` | `papers(topic_tag, status)` | 토픽별 활성 논문 필터링 (L0 스캔, lifecycle 쿼리) |
| `idx_papers_fitness` | `papers(fitness DESC)` | 챔피언 조회, 상위 fitness 선택 |
| `idx_comparisons_winner` | `comparisons(winner)` | 승리 횟수 집계 |
| `idx_comparisons_loser` | `comparisons(loser)` | 패배 횟수 집계, contested 판별 |
| `idx_annotations_paper` | `annotations(paper_id)` | 논문별 annotation 조회 |

edges 인덱스는 Phase 2까지 생성하지 않습니다. 테이블이 비어 있는 상태에서 인덱스는 유지 비용만 발생시킵니다.

---

## WAL 모드 + busy_timeout=5000

```sql
PRAGMA journal_mode=wal;
PRAGMA busy_timeout=5000;
```

`journal_mode=wal`(Write-Ahead Logging)은 읽기와 쓰기를 동시에 허용합니다. 기본 DELETE 저널은 쓰기 시 읽기를 차단하지만 WAL은 읽기 스냅샷을 유지하므로, 세션 컨텍스트를 읽는 도중 비교 결과를 기록할 수 있습니다.

`busy_timeout=5000`은 다른 프로세스가 쓰기 잠금을 보유 중일 때 즉시 실패하는 대신 최대 5초간 재시도합니다. 단일 프로세스 운영이 기본이지만 향후 병렬 에이전트 확장 시 쓰기 경합을 무해하게 처리합니다.

두 PRAGMA는 `schema.sql` 파일 상단과 `init_db()` 함수 내부에서 모두 설정됩니다.

---

## init_db() 동작

`core/__init__.py`의 `init_db(db_path)` 함수가 DB 초기화를 담당합니다.

1. `os.makedirs(db_dir, exist_ok=True)` — 부모 디렉터리를 자동 생성합니다.
2. `sqlite3.connect(db_path)` — DB 파일이 없으면 새로 만듭니다.
3. `conn.row_factory = sqlite3.Row` — `row["column_name"]` 딕셔너리 스타일 접근을 활성화합니다.
4. PRAGMA 3종 설정: `journal_mode=wal`, `busy_timeout=5000`, `foreign_keys=ON`.
5. `schema.sql`을 읽어 `executescript()`로 실행합니다. `CREATE TABLE IF NOT EXISTS`이므로 기존 DB에 반복 실행해도 안전합니다.
6. `conn.commit()` 후 커넥션을 반환합니다. 커넥션 닫기는 호출자 책임입니다.
