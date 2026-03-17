# 콜드 스타트 — 자연 시작 및 `seed_data.py`

## 개요

메인 루프는 빈 DB에서도 자연스럽게 시작됩니다. 별도의 `cold_start()` 함수 없이, 첫 사이클부터 논문을 생성하고 자연스럽게 컬렉션을 키워나갑니다.

| 방법 | 위치 | 특성 |
|------|------|------|
| 자연 시작 (Natural Ramp-up) | `autoresearch_v2.py` 메인 루프 | 별도 시딩 없음, 첫 사이클부터 바로 시작 |
| 수동 시드 데이터 | `seed_data.py` | 결정론적, 오프라인 가능, agentic_memory 전용 |

---

## 자연 시작 (Natural Ramp-up)

`cold_start()` 함수는 제거되었습니다. 메인 루프가 빈 DB를 자연스럽게 처리합니다:

```python
# autoresearch_v2.py — cold_start가 아닌 자연 시작 방식
# No cold_start needed. The main loop handles empty DB gracefully:
# - Cycle 1: generates first paper, no rival → skips comparison
# - Cycle 2: generates second paper, first paper is rival → first comparison
# - Natural ramp-up, no garbage seed papers needed
```

### 동작 순서

```
Cycle 1: 첫 논문 생성 → rival 없음 → 비교 건너뜀
Cycle 2: 두 번째 논문 생성 → 첫 논문이 rival → 첫 비교 수행
Cycle 3+: 정상 사이클 (논문 생성 → 비교 → 반성 → 갱신)
```

### 시작 시 로그

```python
initial_count = conn.execute(
    "SELECT COUNT(*) as cnt FROM papers WHERE topic_tag = ?", (topic,)
).fetchone()["cnt"]
if initial_count == 0:
    logger.info("Starting from empty DB — first cycles will build up the paper collection naturally")
else:
    logger.info(f"Resuming with {initial_count} existing papers for '{topic}'")
```

### cold_start 제거 이유

- 시드 논문이 garbage paper(낮은 품질 placeholder)가 되는 문제 방지
- 메인 루프가 자연스럽게 빈 DB를 처리하므로 별도 시딩이 불필요
- 첫 사이클에서 rival이 없으면 비교를 건너뛰므로 에러 없이 동작

---

## `seed_data.py` — 수동 시드 데이터

`agentic_memory` 주제에 대한 10개의 수동 작성 논문을 포함합니다. 기존 연구 문서(`260317_*.md`)에서 핵심 주장을 추출하여 작성했습니다.

### 사용법

```bash
python seed_data.py --db db/knowledge.db --topic agentic_memory
```

이미 10개 이상 존재하면 건너뜁니다.

### 포함된 시드 논문 10개

| # | Claim 요약 | Perspective |
|---|------------|-------------|
| 1 | L0/L1/L2 계층 메모리로 토큰 91% 절감 (OpenViking) | empirical |
| 2 | SHA-256 콘텐츠 해시 ID로 세션 간 노드 재연결 (Wrkr) | theoretical |
| 3 | Pairwise LLM-as-Judge + A/B B/A 순서 교차로 position bias 제거 | applied |
| 4 | MAP-Elites topic×perspective 격자로 소수 관점 보호 | theoretical |
| 5 | SQLite BEFORE UPDATE/DELETE 트리거로 불변 감사 체인 구현 (Wrkr) | applied |
| 6 | 세션 annotation 자동 주입으로 전체 상태 직렬화 없이 연속성 확보 (Context Hub) | empirical |
| 7 | PageRank는 상대 강도를 가중하므로 단순 승률보다 중요도를 잘 반영 | theoretical |
| 8 | 각 Phase 직후 동기 write-back으로 중단 시 발견 손실 방지 (MiroFish) | applied |
| 9 | 포퍼-베이즈-라카토슈 3종 조합이 자동화 연구 평가의 완전한 인식론적 프레임워크 | critical |
| 10 | SQLite+WAL은 단일 프로세스 에이전트에 충분, 외부 DB 불필요 | empirical |

### 각 시드 논문의 구조

모든 시드 논문은 `papers` 테이블의 전체 필드를 포함합니다.

```python
{
    "claim":            "...",      # 핵심 주장 한 문장
    "l0_summary":       "...",      # ~50 토큰 요약
    "l1_summary":       "...",      # ~2000 토큰 상세 요약
    "l2_content":       "...",      # 전문 (플레이스홀더)
    "evidence_sources": [...],      # [{title, url, excerpt}]
    "assumptions":      "...",      # claim 성립 조건
    "topic_tag":        "agentic_memory",
    "perspective":      "...",      # empirical|theoretical|applied|critical
}
```

`save_paper(conn, paper)` 호출 시 SHA-256 기반 결정론적 ID가 생성됩니다. 동일한 시드 데이터로 시딩하면 항상 같은 ID가 생성됩니다.
