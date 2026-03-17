# 다양성 보존 — MAP-Elites

## 원리

전역 순위로만 경쟁하면 가장 강한 논문이 빠르게 생태계를 지배하고, 소수 관점은 도태됩니다. MAP-Elites는 논문을 2차원 격자에 배치하여 각 셀 내에서만 경쟁하도록 합니다.

---

## 2차원 격자 구조

```
축 1: topic_tag   (연구 주제, 예: agentic_memory)
축 2: perspective (관점, 4종 고정)
```

| | empirical | theoretical | applied | critical |
|---|---|---|---|---|
| agentic_memory | 셀 (1,1) | 셀 (1,2) | 셀 (1,3) | 셀 (1,4) |
| llm_performance | 셀 (2,1) | 셀 (2,2) | 셀 (2,3) | 셀 (2,4) |

각 셀은 독립적인 생존 경쟁 공간입니다. empirical 논문은 다른 empirical 논문과만 경쟁합니다.

---

## 4개 Perspective 정의

| Perspective | 의미 | 예시 |
|-------------|------|------|
| `empirical` | 실험·측정·관찰 기반 | "91% 토큰 절감을 측정했다" |
| `theoretical` | 원리·모델·증명 기반 | "PageRank가 중요도를 재귀적으로 정의한다" |
| `applied` | 구현·실용성 기반 | "SQLite WAL로 충분하다" |
| `critical` | 한계·반론·철학적 분석 | "이 접근의 근본적 한계는..." |

---

## 셀당 최대 보존 수

각 셀에서 `active` + `foundational` 상태의 논문이 최대 3개를 초과하면 fitness가 가장 낮은 논문을 `archived`로 전환합니다.

```python
# update_map_elites(conn, topic) 내부 로직
for (topic_tag, perspective), papers in cells.items():
    active_papers = [p for p in papers if p["status"] in ("active", "foundational")]
    if len(active_papers) > 3:
        # fitness 오름차순 정렬 후 초과분을 archived로
        to_archive = sorted(active_papers, key=lambda p: p["fitness"])[:len(active_papers) - 3]
        for paper in to_archive:
            if paper["status"] != "foundational":  # foundational은 보호
                conn.execute("UPDATE papers SET status = 'archived' WHERE id = ?", (paper["id"],))
```

---

## Foundational 논문 보호

`foundational` 상태 논문은 MAP-Elites 초과 시에도 `archived`로 전환되지 않습니다. 생태계의 핵심 지식 기반을 보호합니다.

---

## Lifecycle 상태 전환

| 전환 | 조건 |
|------|------|
| `active` → `foundational` | fitness > 0.7 이고 비교에서 5승 이상 |
| `active` → `contested` | 최근 5회 비교 중 3패 이상 |
| `active` / `contested` → `archived` | MAP-Elites 셀 초과 (foundational 제외) |

`archived` 상태는 삭제가 아닙니다. DB에 보존되며 `audit_chain`으로 언제 왜 archived됐는지 추적 가능합니다.

> **참고**: `contested → active` 역전환은 현재 구현되어 있지 않습니다. contested 상태의 논문은 MAP-Elites에서 archived되거나 그대로 유지됩니다.

```
active:       경쟁 중인 일반 논문
foundational: 검증된 핵심 논문 (보호)
contested:    최근 성적 부진 논문
archived:     도태된 논문 (보존됨)
```

---

## 다양성 보존의 효과

MAP-Elites 없이 전역 순위로만 관리하면 empirical 관점의 강한 논문이 theoretical, applied, critical 관점을 모두 밀어낼 수 있습니다. 셀 분리로 각 관점에서 최소 1개의 생존자가 보장되어 연구 생태계가 단일 서술로 수렴하지 않습니다.
