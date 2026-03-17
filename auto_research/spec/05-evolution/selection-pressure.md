# 선택압 — `comparisons` 테이블과 PageRank

## 핵심 원리

선택압은 `comparisons(winner, loser, created_at)` 테이블 하나로 구현됩니다. 에이전트가 "좋은 논문을 고르는 것"이 아니라, 비교에서 지는 논문이 자연스럽게 도태되는 구조입니다.

> "에이전트가 좋은 논문을 쓰도록 하는 것이 아니라, 나쁜 논문이 자연스럽게 도태되는 생태계를 설계하는 것." — 최종 전략 보고서

---

## PageRank 알고리즘

### 그래프 방향

`comparisons` 테이블의 각 행이 유향 엣지를 만듭니다.

```
loser → winner
```

loser가 winner에게 "표를 주는" 방향입니다. 중요한 논문을 많이 이긴 논문이 더 많은 표를 받습니다.

```python
G = networkx.DiGraph()
for row in comparisons:
    G.add_edge(row["loser"], row["winner"])

pagerank_scores = networkx.pagerank(G)
```

### "많은 강한 논문을 이긴 논문 = 중요한 논문"

단순 승률(`wins / total_matches`)은 상대의 강도를 무시합니다. PageRank는 재귀적으로 계산되므로, 강한 논문을 이긴 기록이 약한 논문을 이긴 기록보다 더 높은 fitness를 만들어 냅니다. 학술 인용 분석에서 중요한 논문에 인용될수록 가중치가 높아지는 것과 같은 원리입니다.

### Fitness 정규화

PageRank 점수를 [0, 1] 범위로 정규화합니다.

```python
max_score = max(scores.values())
min_score = min(scores.values())
fitness = (score - min_score) / (max_score - min_score)
```

비교 기록이 없는 신규 논문은 초기값 `0.5`를 유지합니다.

---

## Rival 선택 전략

```python
# select_rival(conn, topic)
# 70% 확률: 현재 챔피언(fitness 최고 논문)
# 30% 확률: 랜덤 active 논문
```

| 선택 유형 | 확률 | 목적 |
|-----------|------|------|
| 챔피언 | 70% | 챔피언에게 도전하여 검증 압력 유지 |
| 랜덤 | 30% | 탐색 (SGD의 노이즈 주입과 같은 역할) |

챔피언 고정 비교만 하면 챔피언 주변으로만 비교가 집중되어 다른 논문들이 비교 기회를 얻지 못합니다. 30% 랜덤 선택이 전체 생태계를 골고루 탐색합니다.

---

## Complementary 논문 — 상호 강화

`complementary`로 분류된 두 논문은 경쟁하지 않고 서로를 강화합니다.

```python
# comparisons 테이블에 두 행 삽입
INSERT INTO comparisons (winner, loser) VALUES (paper_a.id, paper_b.id)
INSERT INTO comparisons (winner, loser) VALUES (paper_b.id, paper_a.id)
```

PageRank 계산 시 두 논문 모두 상대방으로부터 표를 받습니다. 독립 복제 연구가 서로의 신뢰도를 높이는 실제 학계 원리를 반영합니다.

---

## Position Bias 제거

opposing 논문 비교 시 순서 편향을 제거합니다.

```
순방향 (A first, B second) → judge 결과 r1
역방향 (B first, A second) → judge 결과 r2

r1 == r2 → 만장일치, comparisons에 기록
r1 != r2 → position bias 감지, 기록 없음
```

만장일치 비율이 낮으면 비교 프롬프트 또는 claim 분류 로직을 점검해야 합니다.
