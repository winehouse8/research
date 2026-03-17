# 피트니스 시스템 명세

`core/fitness.py`가 구현하는 PageRank 피트니스 계산, lifecycle 상태 전환, MAP-Elites 다양성 유지를 기술합니다.

---

## 개요

두 가지 진화 메커니즘이 협력합니다.

| 메커니즘 | 함수 | 목적 |
|----------|------|------|
| PageRank 피트니스 | `calculate_fitness()` | "강한 논문을 많이 이긴 논문이 중요하다" |
| MAP-Elites 다양성 | `update_map_elites()` | topic × perspective 셀별로 다양성을 보존 |

lifecycle 상태 전환(`update_lifecycle_states()`)은 두 메커니즘의 결과를 반영하여 논문의 상태를 갱신합니다.

---

## calculate_fitness(): PageRank 피트니스

```python
def calculate_fitness(conn: sqlite3.Connection, topic: str) -> None
```

해당 토픽의 모든 논문 fitness를 재계산합니다.

### 그래프 구성 방향: loser → winner

```python
G.add_edge(comp["loser"], comp["winner"])
```

엣지가 패자에서 승자로 향합니다. PageRank는 들어오는 링크가 많을수록 높은 점수를 줍니다. 따라서 많은 논문에 패배를 안긴 논문일수록 높은 PageRank를 받습니다. "강한 논문들을 꺾은 논문"에 높은 점수를 부여하는 의도를 정확히 표현합니다.

```python
pr = nx.pagerank(G, alpha=0.85, max_iter=100)
```

- `alpha=0.85`: 표준 감쇠 계수(damping factor). 85% 확률로 링크를 따라가고 15%는 임의 점프합니다.
- `max_iter=100`: 최대 반복 횟수.

### convergence 실패 시 fallback

```python
except nx.PowerIterationFailedConvergence:
    pr = {}
    for pid in paper_ids:
        wins = ...  # SELECT COUNT(*) WHERE winner = pid
        total = ...  # SELECT COUNT(*) WHERE winner = pid OR loser = pid
        pr[pid] = wins / max(total, 1)
```

PageRank 수렴에 실패하면 단순 승률(wins / total)로 대체합니다. 그래프가 특이한 구조(강한 사이클 등)일 때도 시스템이 중단되지 않습니다.

### 정규화

```python
normalized = (score - min_pr) / pr_range
```

min-max 정규화로 모든 점수를 [0, 1] 범위로 변환합니다. 논문이 2편 미만이거나 비교 결과가 없으면 함수는 조기 반환합니다(fitness 미변경).

---

## update_lifecycle_states(): 상태 전환

```python
def update_lifecycle_states(conn: sqlite3.Connection, topic: str) -> None
```

모든 전환은 `audit_chain`에 기록됩니다.

### active → foundational

```sql
WHERE p.status = 'active' AND p.fitness > 0.7
AND (SELECT COUNT(*) FROM comparisons WHERE winner = p.id) > 5
```

조건: fitness > 0.7 **AND** 누적 승리 수 > 5.

높은 fitness만으로는 부족합니다. 충분한 비교(5회 이상 승리)를 거쳐 검증된 논문만 foundational로 승격됩니다. foundational 논문은 MAP-Elites에서 아카이브 대상에서 보호됩니다.

### active → contested

```sql
AND (SELECT COUNT(*) FROM (
    SELECT CASE WHEN loser = p.id THEN 1 ELSE 0 END as was_loss
    FROM comparisons
    WHERE winner = p.id OR loser = p.id
    ORDER BY created_at DESC LIMIT 5
) WHERE was_loss = 1) >= 3
```

조건: 가장 최근 5회 비교(승리+패배 모두 포함) 중 3회 이상 패배.

최근 성과를 기준으로 판단합니다. 오래된 승리 이력이 있어도 최근 3연패 이상이면 contested가 됩니다. contested 논문은 MAP-Elites에서 아카이브될 수 있습니다.

---

## update_map_elites(): 다양성 유지

```python
def update_map_elites(conn: sqlite3.Connection, topic: str) -> None
```

MAP-Elites 그리드는 `topic_tag × perspective`로 셀을 구분합니다. 각 셀 내에서만 경쟁합니다.

### 셀별 처리 로직

```python
cell_papers = conn.execute(
    """SELECT id, fitness, status FROM papers
       WHERE topic_tag = ? AND perspective = ?
         AND status IN ('active', 'contested', 'foundational')
       ORDER BY fitness DESC""",
    (topic, perspective),
).fetchall()

if len(cell_papers) <= 1:
    continue  # 최소 1편 보장

if len(cell_papers) > 3:
    for paper in cell_papers[3:]:  # 4위 이하
        if paper["status"] in ("active", "contested"):
            # archived로 전환
```

- 셀당 최대 3편을 유지합니다.
- 4위 이하 논문 중 `active` 또는 `contested` 상태만 아카이브합니다.
- `foundational` 논문은 아카이브 대상에서 제외됩니다(`status in ("active", "contested")` 조건).
- 셀에 논문이 1편 이하이면 건드리지 않습니다.

### foundational 보호

`foundational` 논문은 fitness 순위에 관계없이 아카이브되지 않습니다. 충분한 검증을 거쳐 승격된 논문을 섣불리 제거하지 않도록 설계되었습니다.

---

## get_champion(): 최고 fitness 논문 반환

```python
def get_champion(conn: sqlite3.Connection, topic: str) -> dict
```

```sql
SELECT * FROM papers
WHERE topic_tag = ? AND status IN ('active', 'foundational')
ORDER BY fitness DESC LIMIT 1
```

토픽에서 fitness가 가장 높은 `active` 또는 `foundational` 논문 1편을 반환합니다. 해당 논문이 없으면 빈 딕셔너리를 반환합니다. `contested`와 `archived` 논문은 챔피언 후보에서 제외됩니다.

---

## select_rival(): 경쟁 상대 선택

```python
def select_rival(conn: sqlite3.Connection, topic: str) -> dict
```

새 논문의 비교 상대를 선택합니다.

```python
if random.random() < 0.7:
    rival = get_champion(conn, topic)
    if rival:
        return rival

# fallback: 랜덤 active 논문
papers = conn.execute(
    """SELECT * FROM papers
       WHERE topic_tag = ? AND status IN ('active', 'contested', 'foundational')
       ORDER BY RANDOM() LIMIT 1""",
    (topic,),
).fetchone()
```

- 70% 확률: 챔피언(최고 fitness 논문)을 상대로 지정
- 30% 확률: 랜덤 논문 선택

### SGD-inspired 탐색

확률적 경사 하강법(SGD)에서 착안했습니다. 대부분의 경우 가장 강한 상대(챔피언)에 도전하여 선택 압력을 높이고, 30%는 약한 논문과도 비교하여 탐색 공간을 유지합니다. 챔피언이 없을 때는 랜덤 선택으로 자동 fallback합니다.

---

## _log_audit(): 감사 기록 헬퍼

```python
def _log_audit(
    conn: sqlite3.Connection,
    paper_id: str,
    event_type: str,
    previous_state: str,
    new_state: str,
    created_at: str,
    agent_id: str = "system",
) -> None
```

`audit_chain`에 단일 레코드를 삽입합니다. `update_lifecycle_states()`와 `update_map_elites()`가 상태를 변경할 때마다 호출합니다.

`id`는 `uuid4().hex[:16]`으로 생성합니다. `agent_id` 기본값은 `"system"`입니다. `conn.commit()`은 호출하지 않으며, 호출자가 일괄 커밋합니다.

### event_type 값

| 값 | 발생 시점 |
|----|-----------|
| `first_seen` | `save_paper()`에서 신규 논문 저장 시 |
| `status_changed` | lifecycle 전환 (active→foundational, active→contested) |
| `archived` | MAP-Elites에서 아카이브 처리 시 |
