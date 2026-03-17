# 에이전트 메모리 & 지식저장소 SOTA 보고서

> 작성일: 2026-03-16
> 목적: autoresearch Ralph 루프에서 쌓이는 실험 결과를 효율적으로 관리하기 위한 지식저장소 설계

---

## 1. 핵심 문제 정의

### 현재 autoresearch의 메모리 구조

```
실험 1회 → results.tsv에 한 줄 추가
다음 실험 → results.tsv 전체 읽기 (N줄 × 토큰 = O(N) 비용)
100회 실험 후 → 매 실험마다 수백 줄 전체 로딩 = 토큰 낭비
```

**두 가지 핵심 문제:**
1. **토큰 효율**: 매 이터레이션마다 전체 실험 기록을 읽는 건 낭비
2. **지식 통합**: 100번의 실험에서 "이 방향은 항상 안 된다"는 패턴을 누적 학습할 수 없음

---

## 2. 2026 SOTA: 에이전트 메모리 연구 현황

### 2.1 학술 논문 주요 성과

#### A-MEM (NeurIPS 2025, arxiv:2502.12110)
**Zettelkasten 원칙을 에이전트 메모리에 적용**

- 새 메모리 추가 시 contextual description, keywords, tags를 포함한 구조화된 노트 생성
- **핵심**: 새 메모리가 기존 메모리의 contextual representation을 동적으로 업데이트
- 6개 foundation model에서 기존 SOTA 대비 일관된 성능 향상
- GitHub: [agiresearch/A-mem](https://github.com/agiresearch/A-mem)

#### Synapse (arxiv:2601.02744, 2026)
**에피소딕-시맨틱 메모리를 동적 연관 그래프로 통합**

- 불연속적 사실들을 동적 그래프로 연결, 비관련 노이즈 필터링
- LoCoMo 벤치마크 SOTA: **멀티홉 추론 정확도 +23%, 토큰 소비 -95%** (전체 컨텍스트 방식 대비)
- Spreading Activation 메커니즘으로 관련 메모리만 선택적 활성화

#### Agentic Memory (arxiv:2601.01885, 2026)
**에이전트가 직접 LTM/STM을 관리하는 통합 프레임워크**

- 메모리 작업(저장/검색/업데이트/요약/삭제)을 **도구 호출(tool call)로 노출**
- 에이전트가 "무엇을 언제 저장할지" 자율 결정
- autoresearch에 직접 적용 가능한 패턴

#### MAGMA (arxiv:2601.03236, 2026)
**멀티에이전트용 Multi-Graph 기반 메모리 아키텍처**

- 에이전트별 프라이빗 그래프 + 공유 글로벌 그래프 이중 구조
- 멀티에이전트 동시 접근 시 충돌 방지 메커니즘 내장

#### MIRIX (2026)
**6계층 특화 메모리 모듈**

| 모듈 | 역할 |
|------|------|
| Core Memory | 항상 로딩되는 핵심 컨텍스트 |
| Episodic Memory | 특정 사건/실험 기록 |
| Semantic Memory | 일반화된 지식 |
| Procedural Memory | 검증된 절차/방법론 |
| Resource Memory | 파일/코드 위치 |
| Knowledge Vault | 핵심 발견 영구 보존 |

#### RAG 기반 메모리 (검색 증강 접근법)

**패턴**: 전체 메모리를 로딩하지 않고, 쿼리와 관련된 메모리만 벡터 유사도 검색으로 선택적 로딩

- **원리**: 실험 기록을 벡터 임베딩으로 저장 → 새 실험 시 "비슷한 과거 실험" top-k만 로딩
- **대표 구현**: Mem0의 벡터 저장소, GraphRAG (Microsoft 2025), HippoRAG (2025)
- **autoresearch 적용 예시**:
  ```python
  # 현재 아이디어와 유사한 과거 실험만 로딩
  similar = memory.search("attention window size 변경", top_k=5)
  # → 5개 실험만 컨텍스트에 포함 (전체 100개 대신)
  ```
- **토큰 효율**: 관련 k개만 로딩 → O(k) 고정비용 (k=5~10이면 수십 토큰)
- **단점**: 임베딩 모델 필요, 초기 설정 비용, 검색 실패 시 관련 정보 누락 가능

---

### 2.2 상용 에이전트 메모리 시스템 비교

| 시스템 | 방식 | 토큰 효율 | 멀티에이전트 | 자체 호스팅 | autoresearch 적합성 |
|--------|------|-----------|-------------|-------------|---------------------|
| **Mem0** | 벡터+그래프 하이브리드 | **-80% 토큰** | ✓ | ✓ (오픈소스) | 높음 |
| **Zep** | 시간적 지식 그래프 | 중간 | ✓ | ✓ | 중간 |
| **Letta/MemGPT** | OS 메모리 계층 모방 | 중간 | △ | ✓ | 중간 |
| **LangMem** | LangChain 통합 | 중간 | ✓ | ✓ | 중간 |

**Mem0**
- 장점: 50,000+ 개발자 사용, -80% 토큰, `agent_id`로 멀티에이전트 격리, 오픈소스
- 단점: 클라우드 사용 시 레이턴시 추가, 로컬 자체 호스팅 시 Redis+벡터DB 인프라 필요, 소규모 실험에 과도할 수 있음

**Zep**
- 장점: 시간적 지식 그래프로 "사실이 시간에 따라 어떻게 변했는지" 추적, 엔티티/관계 모델링 강력
- 단점: 엔터프라이즈 라이선스 비용 높음, 초기 설정 복잡도 높음, 단순 실험 로그 관리에는 과도한 인프라

**Letta/MemGPT**
- 장점: OS 메모리 계층 모방, 개발자가 메모리 블록을 직접 편집 가능, 투명한 메모리 관리
- 단점: 단일 에이전트 가정으로 설계됨 → 멀티에이전트 공유 상태 관리 어려움(△), 메모리 계층 전환 오버헤드

---

## 3. Obsidian/Notion vs 에이전트 전용 저장소

### 3.1 Obsidian

**장점:**
- 로컬 퍼스트: 데이터가 로컬 Markdown 파일 → 에이전트가 파일시스템으로 직접 접근 가능
- 2026년 현재 AI 에이전트용 플러그인(Obsidian Skills) 등장
- 쌍방향 링크 + 그래프 뷰 = 지식 연결 가시화
- 무료, 오프라인 가능

**단점:**
- **멀티 에이전트 동시 쓰기 불가** (파일 잠금 없음 → race condition)
- API 없음, 에이전트가 파일시스템으로만 접근
- 구조화된 쿼리 불가 (grep 수준)
- 자동 압축/요약 기능 없음

**autoresearch 적합성: 낮음**
단일 인간 사용자의 PKM(개인 지식 관리)에는 최적이지만, 자율 에이전트 루프에는 부적합.

### 3.2 Notion

**장점:**
- 데이터베이스 기능: 필터링, 정렬, 뷰 다양
- 2025년 9월부터 Notion AI Agents 내장
- API 제공 (HTTP REST)

**단점:**
- **클라우드 의존**: 오프라인 불가, API 레이트 리밋
- 비용: Business Plan $20/월
- 멀티에이전트 동시 수정 시 충돌 가능성
- 실험 로그 수백 줄 쿼리는 API 비용 증가

**autoresearch 적합성: 낮음~중간**
협업 시각화에는 좋으나, 고빈도 에이전트 루프에는 레이트 리밋 및 비용 문제.

### 3.3 실익 판단: Obsidian/Notion을 쓰면 좋은 경우

```
인간이 실험 결과를 시각적으로 탐색할 때 → Obsidian/Notion 적합
에이전트가 자율적으로 고빈도 CRUD 할 때 → 에이전트 전용 저장소 적합
```

**결론: 두 계층 분리 권장**
- 에이전트 내부 루프 → 가벼운 파일 기반 저장소
- 인간 리뷰 → Obsidian/Notion으로 export

---

## 4. autoresearch에 최적화된 지식저장소 설계

### 4.1 핵심 원칙

> **"매 이터레이션에 필요한 최소 정보만 로딩하고, 중요한 발견은 압축해서 영구 보존한다"**

Synapse의 -95% 토큰 절감 원리를 autoresearch에 적용:
- **항상 로딩**: 핵심 요약 (~300 토큰)
- **필요시 로딩**: 전체 실험 기록 (쿼리 기반)
- **영구 보존**: 검증된 핵심 발견

### 4.2 권장 파일 구조

```
autoresearch/
├── train.py               # 에이전트가 수정하는 파일 (기존)
├── prepare.py             # 수정 안 함 (기존)
├── program.md             # 에이전트 지침 (기존)
├── ralph.sh               # Ralph 루프 (기존)
├── results.tsv            # 전체 실험 로그 (기존, 건드리지 않음)
└── memory/
    ├── SUMMARY.md         # ★ 항상 로딩 (~300 토큰), 핵심 압축
    ├── INSIGHTS.md        # 검증된 발견 (영구 보존)
    └── FAILED.md          # 실패 방향 목록 (반복 방지)
```

### 4.3 각 파일 명세

#### `memory/SUMMARY.md` (매 이터레이션 필수 로딩)

```markdown
# 현재 상태 요약
- 총 실험: 47회 (keep: 12, discard: 31, crash: 4)
- 현재 최고 val_bpb: 0.9712 (커밋 a3f8c2d, LR 스케줄러 변경)
- 베이스라인 val_bpb: 0.9979
- 개선율: +2.67%

# 현재 유망한 방향
- Learning rate warmup 연장 효과 있음 (+0.008)
- GQA (Grouped Query Attention) 미탐색

# 주의: 이미 시도했으나 효과 없는 방향
→ FAILED.md 참조
```

#### `memory/INSIGHTS.md` (핵심 발견 영구 보존)

```markdown
# 검증된 발견 (여러 실험에서 재현됨)

## [검증됨] LR 0.03 → 0.04 개선
- 실험: b2c3d4e, f1e2d3c
- val_bpb 개선: 평균 +0.004
- 조건: depth=8, warmup 기본값

## [검증됨] RMSNorm이 LayerNorm보다 안정적
- 실험: 3개 독립 실험에서 재현
- 학습 초기 불안정성 감소
```

#### `memory/FAILED.md` (실패 방향 목록)

```markdown
# 시도해봤으나 효과 없음 (다시 시도하지 마세요)

- GeLU activation (기존 SiLU보다 나쁨, 실험 c3d4e5f)
- model width 2배 → OOM (d4e5f6g)
- weight decay 0.01 → 0.1 (오히려 악화, 실험 5개)
- attention dropout → 일관되게 악화
```

### 4.4 program.md에 메모리 지침 추가

실험 루프 Step 1을 다음과 같이 수정:

```markdown
1. **메모리 로딩** (항상):
   - `memory/SUMMARY.md` 읽기 → 현재 상태 파악
   - `memory/FAILED.md` 읽기 → 반복 방지
   - (필요시만) `results.tsv` 전체 읽기

...실험 수행...

8. **메모리 업데이트** (실험 후):
   - `memory/SUMMARY.md` 업데이트 (총 실험 수, 현재 최고값)
   - 중요한 발견이면 `memory/INSIGHTS.md`에 추가
   - 실패한 방향이면 `memory/FAILED.md`에 추가
```

### 4.5 토큰 비교

| 방식 | 이터레이션당 토큰 (100회 시점) |
|------|-------------------------------|
| 기존 (results.tsv 전체 읽기) | ~3,000 토큰 |
| **제안 (SUMMARY.md만)** | **~300 토큰** |
| 절감률 | **-90%** |

---

## 5. 멀티 에이전트 확장 시 CRUD 설계

### 5.1 단일 에이전트 (현재 autoresearch) → 파일 기반으로 충분

```bash
# 에이전트가 직접 파일 편집
memory/SUMMARY.md  # 매 실험 후 업데이트
memory/INSIGHTS.md # 중요 발견 시 append
memory/FAILED.md   # 실패 시 append
```

### 5.2 멀티 에이전트 (여러 GPU 동시 실행)

MAGMA 및 Collaborative Memory 연구의 권장 패턴:

```
에이전트 A (GPU 0) ─┐
에이전트 B (GPU 1) ─┤→ 공유 메모리 허브 → 글로벌 INSIGHTS
에이전트 C (GPU 2) ─┘    (충돌 방지 필요)
```

**충돌 방지 옵션:**

| 방식 | 난이도 | 설명 |
|------|--------|------|
| **파일 잠금 + append-only** | 쉬움 | `flock`으로 쓰기 직렬화, 읽기는 자유 |
| **SQLite** | 쉬움 | WAL 모드로 동시 읽기, 쓰기 직렬화 |
| **Mem0 (오픈소스)** | 중간 | `agent_id`별 격리, 공유 메모리 API |
| **MCP memory service** | 중간 | REST API, concurrent-safe, 자동 백업 |

**권장 (멀티 에이전트 최소 구현):**

```python
# memory_hub.py - SQLite 기반 간단한 공유 메모리
import sqlite3
import threading

DB_PATH = "memory/hub.db"
lock = threading.Lock()

def log_experiment(agent_id, val_bpb, description, status):
    with lock:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            INSERT INTO experiments (agent_id, val_bpb, description, status, ts)
            VALUES (?, ?, ?, ?, datetime('now'))
        """, (agent_id, val_bpb, description, status))
        conn.commit()

def get_best(n=5):
    conn = sqlite3.connect(DB_PATH)
    return conn.execute("""
        SELECT agent_id, val_bpb, description
        FROM experiments WHERE status='keep'
        ORDER BY val_bpb ASC LIMIT ?
    """, (n,)).fetchall()

def get_failed_directions():
    conn = sqlite3.connect(DB_PATH)
    return conn.execute("""
        SELECT DISTINCT description FROM experiments
        WHERE status IN ('discard','crash')
    """).fetchall()
```

---

## 6. OpenClaw의 메모리 아키텍처 — 실전 참고

> OpenClaw(Claude Code)는 에이전트 메모리 문제를 이미 실전에서 해결하고 있다. 이 설계를 autoresearch에 적용할 수 있다.

### 6.1 OpenClaw 2계층 메모리

OpenClaw의 공식 설계 원칙: **"파일이 진실의 원천이다. 모델은 디스크에 쓴 것만 기억한다."**

```
memory/
├── YYYY-MM-DD.md   ← 일별 로그 (단기, append-only)
│   오늘 + 어제 것만 세션 시작 시 자동 로딩
└── MEMORY.md       ← 장기 기억 (큐레이션된 핵심 사실)
    "작고 조용하게 유지. 시간이 지나도 참이길 바라는 것만."
```

**핵심 도구:**
- `memory_search` — 벡터 임베딩 기반 시맨틱 검색 (BM25 키워드 + 유사도 하이브리드)
- `memory_get` — 특정 파일 직접 읽기

**자동 압축 전 플러시(Auto-flush before compaction):**
컨텍스트 압축 직전 자동으로 silent agentic turn을 실행해 중요 내용을 daily note에 기록. 이것이 **메멘토 문제의 핵심 해결책** — Claude Code가 꺼지기 직전에 스스로 메모를 남긴다.

### 6.2 OpenClaw 메모리 생태계 (2026)

| 도구 | 방식 | 특징 |
|------|------|------|
| **Mem0 for OpenClaw** | 벡터+그래프 | 30초 설치, 세션 간 영속 기억, [공식 블로그](https://mem0.ai/blog/mem0-memory-for-openclaw) |
| **ClawVault** | Markdown-native | Obsidian 연동, 세션 체크포인트/복구, [GitHub](https://github.com/Versatly/clawvault) |
| **openclaw-memory-sync** | Obsidian 동기화 | OpenClaw ↔ Obsidian vault 양방향 싱크, [GitHub](https://github.com/YearsAlso/openclaw-memory-sync) |
| **Memori Plugin** | 자동 recall+capture | 멀티에이전트 게이트웨이 통합 (2026-03-13 출시) |
| **memsearch (Milvus)** | 오픈소스 추출판 | OpenClaw 메모리 시스템을 독립 라이브러리로 추출 |

### 6.3 autoresearch에 그대로 적용하는 방법

OpenClaw의 설계를 ralph 루프에 직접 이식:

```
memory/
├── YYYY-MM-DD.md   → 당일 실험 로그 (오늘 것만 자동 로딩)
└── MEMORY.md       → 장기 기억 (SUMMARY.md와 동일한 역할)
```

**program.md 지침 예시:**

```markdown
## 메모리 관리

시작 시:
1. `memory/MEMORY.md` 읽기 (핵심 상태, ~300토큰)
2. `memory/$(date +%Y-%m-%d).md` 읽기 (오늘 실험 로그)

종료 시 반드시:
1. `memory/$(date +%Y-%m-%d).md`에 이번 실험 결과 append
2. 중요한 발견이면 `memory/MEMORY.md` 업데이트
```

**OpenClaw 방식의 핵심 교훈:**
- 일별 파일 분리 → 오늘/어제만 로딩하면 토큰 고정
- MEMORY.md는 "작게 유지" — 모든 것을 쓰지 말 것
- **자동 압축 직전 저장** 패턴을 ralph.sh에 구현 가능:

```bash
# ralph.sh 개선안: 압축 전 메모리 저장 훅
trap 'echo "저장 중..." && claude -p "memory/MEMORY.md를 오늘 실험 결과로 업데이트해라"' EXIT
```

---

## 7. 권장 도입 순서

### Phase 1: 즉시 적용 (파일 기반, 0 의존성)

```bash
mkdir memory
touch memory/SUMMARY.md memory/INSIGHTS.md memory/FAILED.md
```

`program.md`에 메모리 로딩/업데이트 지침 추가.
→ **토큰 -90%, 구현 시간 30분**

### Phase 2: 멀티 에이전트 확장 시

SQLite WAL 모드 공유 DB 또는 Mem0 오픈소스 도입.

### Phase 3: 장기 운영 시

Zep (시간적 지식 그래프) 또는 A-MEM 방식 도입으로 실험 패턴을 자동으로 연결.

---

## 7. 최종 권장사항 요약

| 질문 | 답 |
|------|-----|
| Obsidian/Notion 쓸 것인가? | 인간 리뷰용으로만. 에이전트 루프 내부에는 부적합 |
| 가장 단순한 해결책은? | `memory/SUMMARY.md` 파일 하나 추가 |
| 토큰 절감 목표치 | -90% (300토큰 vs 3000토큰) |
| 멀티에이전트 최소 구현 | SQLite WAL |
| 장기 SOTA 방향 | A-MEM (Zettelkasten) + Synapse (그래프 + -95% 토큰) |

---

## 참고 자료

- [A-MEM: Agentic Memory for LLM Agents](https://arxiv.org/abs/2502.12110) (NeurIPS 2025)
- [Synapse: Episodic-Semantic Memory via Spreading Activation](https://arxiv.org/html/2601.02744v1) (2026)
- [Agentic Memory: Unified LTM/STM](https://arxiv.org/abs/2601.01885) (2026)
- [MAGMA: Multi-Graph Agentic Memory](https://arxiv.org/html/2601.03236v1) (2026)
- [Multi-Agent Memory: Computer Architecture Perspective](https://arxiv.org/html/2603.10062) (2026)
- [Collaborative Memory: Multi-User with Access Control](https://arxiv.org/html/2505.18279v1)
- [Mem0: Production-Ready Long-Term Memory](https://arxiv.org/pdf/2504.19413)
- [Mem0 vs Zep vs LangMem vs MemoClaw 비교](https://dev.to/anajuliabit/mem0-vs-zep-vs-langmem-vs-memoclaw-ai-agent-memory-comparison-2026-1l1k)
- [Graph Memory for AI Agents (Mem0 Blog)](https://mem0.ai/blog/graph-memory-solutions-ai-agents)
- [Letta: Benchmarking AI Agent Memory](https://www.letta.com/blog/benchmarking-ai-agent-memory)
- [ICLR 2026 MemAgents Workshop](https://openreview.net/pdf?id=U51WxL382H)
