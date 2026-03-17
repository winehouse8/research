# 에이전트 자율 연구 생태계 설계 — 논의 정리 보고서

**작성일**: 2026-03-17
**기반**: v1(`260317_agent-ecosystem-minimal.md`) + v2(`260317_agent-ecosystem-minimal-v2.md`) + 이후 심화 논의
**목적**: 메인 이슈, 사고 진전, 현재 남은 문제 정리

---

## 1. 핵심 설계 결정 — 사고 진전 기록

### 1.1 그래프 DB의 역할 재정의

**초기 혼동**: 그래프 DB를 논문 간 관계 탐색과 검색 인프라로 동시에 쓰려 했다.

**결론**:
- 그래프 DB = **발견된 관계의 정리장** (확인된 것만 기록)
- 검색(discovery) = **topic_tag SQL 필터 → L0 요약 LLM 판단** (그래프 아님)

```
역할 분리:
  "관련 논문 찾기"    → SQL 필터 + LLM 관련성 판단
  "관계 기록/전파"    → 그래프 (supports/contradicts/defeats 엣지)
  "중요도 계산"       → PageRank (그래프 기반)
```

**핵심 통찰**: 그래프가 불완전해도(E를 놓쳐도) 문제없다. 그래프는 완전성을 약속하지 않는다. 발견한 관계만 기록한다. 발견은 별도 탐색 메커니즘이 담당한다.

---

### 1.2 임베딩 벡터 검색의 포기

**초기 제안**: 새 논문 추가 시 FAISS/sqlite-vss로 ANN 검색.

**반론(사용자)**: 임베딩 성능이 안 좋다. 100개 L0 요약을 LLM에 먹여서 자연어로 질의하는 게 더 정확하다는 보고가 많다.

**결론**: 임베딩 인프라 없이 작동:
```
전체 N개
  → topic_tag SQL 필터 (비용: 0)
  → L0 요약 M개 → LLM 일괄 전달 → 관련성 판단
  → 상위 K개 → L1 로드 → 실제 작업
```

**한계**: N이 매우 커지면(topic당 2000+) L0 전체 LLM 전달이 느려진다. 이 임계점 전까지는 현재 설계로 충분.

---

### 1.3 평가압력의 최소화

**초기 설계(v1)**: evaluations 테이블에 judge_model, rubric, score, verdict 등 저장.

**문제 제기**: ralph 루프마다 새로 태어나는 에이전트 → "누가 평가했나"는 의미 없다.

**결론**: 평가 결과는 오직 하나의 사실만 필요:

```sql
CREATE TABLE comparisons (
    winner     TEXT REFERENCES papers(id),
    loser      TEXT REFERENCES papers(id),
    created_at TEXT
);
-- 전부. agent_id, judge_score, relation_type 없음.
```

`fitness = wins / total_matches` — comparisons 테이블에서 파생.

---

### 1.4 반박 논문 = 생성 전략, 평가 메커니즘 아님

**초기 혼동**: "피어리뷰"와 "반박 논문" 두 경로를 별도로 설계해야 하나?

**결론**: 인프라 관점에서 동일하다.
```
피어리뷰:  새 논문 B가 기존 논문 A와 pairwise 비교 → B 이김
반박 논문: "A를 반박하는 논문을 써라"로 생성된 C가 A와 pairwise 비교 → C 이김
```

생성 프롬프트만 다를 뿐, 평가 메커니즘은 동일. 별도 처리 불필요.

---

### 1.5 비교 가능성 문제 — claim 정규화

**문제 제기**: 두 논문이 반드시 대립하지 않는다. 같은 결론에 다른 근거일 수도, 아예 다른 각도를 다룰 수도 있다.

**해결**: 논문 포맷에 `claim` 필드(핵심 주장 한 문장) 추가.

```
비교 전 분류:
  claim이 반대인 경우  → pairwise 대결 (더 합리적인 쪽 승)
  claim이 같은 경우   → 근거 대결 (더 강한 근거 쪽 fitness 상승)
  claim이 무관한 경우  → 대결 없음, 다른 MAP-Elites 셀에 공존
```

보완 논문(같은 결론, 다른 근거)은 둘 다 fitness 상승. 실제 학계처럼 독립 복제가 두 논문을 강화.

---

### 1.6 평가 기준의 단순화

**초기 rubric**: 주장 명확성, 근거 구체성, 반박 가능성, 새로운 연결 발견 등 4~6개 축.

**결론**: 근거 형태(데이터/실험/논리/역사)를 우리가 규정하지 않는다.

```
judge 프롬프트 (한 문장):
"제시된 근거가 결론을 실제로 지지하는가?"
```

에이전트가 스스로 근거 전략을 발견하게 한다:
- 초기: 인터넷 글 인용
- 중기: 코드 실험 수행
- 후기: ??? (에이전트가 발견할 새 방법)

AlphaGo 원리: "이기면 좋다"만 정의하면 전략은 에이전트가 찾는다.

---

### 1.7 라카토슈 보정

**추가**: 순수 "합리적인가?"만으로는 Verbosity bias 문제 있음.

라카토슈의 진보/퇴행 구분을 rubric에 미세 추가:
```
반박에 새로운 예측/검증 방법으로 응답 → 진보적 프로그램 (+보너스)
반박에 "그 소스가 틀렸다"로만 응답    → 퇴행적 프로그램 (-페널티)
```

---

### 1.8 소스 신뢰도 평가의 한계와 재설계

**초기 제안**: URL 기반 점수 (arxiv=0.80, nature=0.90 등).

**문제 제기**: 근거 없는 자의적 숫자. 방법론 약함.

**결론**: 점수 없이 원문 발췌를 judge에게 직접 전달.

```json
"evidence_sources": [
  {
    "title": "IEA World Energy Outlook 2025",
    "url": "...",
    "citation_count": 847,      ← Semantic Scholar API (객관적 데이터)
    "key_excerpt": "OPEC+ 감산 지속 시 2026년 공급 부족 예상..."
  }
]
```

judge는 점수 없이 원문을 읽고 스스로 판단. 가장 단순하고 방어 가능한 방법.

방어 가능한 신뢰도 신호 (쓸 수 있을 때만):
- **Citation count**: Semantic Scholar API — 객관적
- **저널 SJR/JIF**: 외부 공인 DB — 객관적
- **예측 트랙레코드**: Q1형 질문에서 과거 정확도 — 가장 직접적

---

### 1.9 과학철학 무기

**결론**: 포퍼 단독은 부족. 세 가지 조합:

| 역할 | 철학 |
|---|---|
| 게이트키퍼 (진입 필터) | **포퍼**: 반증 불가능한 주장은 생태계 제외 |
| 주 엔진 (확률 업데이트) | **베이즈**: 실험 없이 evidence 기반 신뢰도 갱신 |
| 평가 기준 (진보/퇴행) | **라카토슈**: 새 예측 제시 vs 땜질만 하는가 |

사회과학/예측 질문에서의 반증: 과거 데이터가 실험을 대체 (역사적 반례, 모델 백테스팅).

---

## 2. 현재 확정된 최소 설계

### 2.1 데이터 스키마

```sql
CREATE TABLE papers (
    id                   TEXT PRIMARY KEY,  -- SHA-256(content[:500])
    claim                TEXT NOT NULL,     -- 핵심 주장 한 문장
    l0_summary           TEXT,              -- 50토큰, 필터용
    l1_summary           TEXT,              -- 2000토큰, 추론용
    l2_content           TEXT,              -- 전문, on-demand
    evidence_sources     TEXT,              -- JSON: [{title, url, citation_count, excerpt}]
    assumptions          TEXT,              -- 성립 조건
    fitness              REAL DEFAULT 0.5,
    status               TEXT DEFAULT 'active',  -- active | archived
    topic_tag            TEXT,
    perspective          TEXT,
    created_at           TEXT
);

CREATE TABLE comparisons (
    winner     TEXT REFERENCES papers(id),
    loser      TEXT REFERENCES papers(id),
    created_at TEXT
);
```

### 2.2 에이전트 구조

```
research_agent:
  입력: topic, 상위 fitness 3개(L1) + 랜덤 2개(L1)
  도구: web_search, read_url, (bash — Q4~Q7용)
  출력: papers 테이블에 새 논문 추가

pair_compare_agent:
  입력: 같은 topic_tag의 두 논문 (claim 기준 대립/보완/직교 분류 후)
  도구: 없음 (읽기만)
  출력: comparisons 테이블에 (winner, loser) 기록
```

### 2.3 루프

```python
while True:
    # 1. 컨텍스트 구성
    top_papers = db.query("fitness 상위 3개 + 랜덤 2개 WHERE topic=?")

    # 2. 새 논문 생성 (or 반박 논문 생성 확률 30%)
    new_paper = research_agent(topic, context=top_papers)
    db.save(new_paper)

    # 3. 비교 대상 선택
    rival = select_rival(db, new_paper.claim, new_paper.topic_tag)

    # 4. claim 분류 → 비교 방식 결정
    relation = classify(new_paper.claim, rival.claim)
    if relation == "직교":
        pass  # 비교 없음, 둘 다 공존
    else:
        winner = pair_compare_agent(new_paper, rival, relation)
        db.save_comparison(winner, loser)
        db.update_fitness(recompute_from_comparisons)
```

### 2.4 judge 프롬프트

```
대립인 경우:
  "A와 B 중 어느 주장이 제시된 근거에 의해 더 잘 지지되는가?
   근거의 형태(데이터/실험/논리/역사)는 무관하다.
   단, 반박에 새로운 예측으로 응답한 쪽을 더 높이 평가한다."

보완인 경우:
  "A와 B가 같은 결론을 주장하는데, 어느 쪽 근거가 더 강한가?"
```

---

## 3. 연구 주제별 적용 가능성

| 질문 | 에이전트 직접 실험 | 현재 설계 강도 | 비고 |
|---|---|---|---|
| Q4. LLM 성능 | ✅ 코드 실행 | **최강** | 에이전트가 스스로 벤치마크 |
| Q5. 행렬 알고리즘 | ✅ 증명+코드 | **최강** | 수학적 증명 가능 |
| Q6. 에이전틱 메모리 | ✅ 구현+테스트 | **최강** | 메타: 우리 시스템 자체 |
| Q7. 로컬 LLM 챗봇 | ✅ 코드 실험 | **최강** | GPU 벤치마크 직접 실행 |
| Q1. 유가 예측 | ❌ | **중간** | 인터넷 검색 품질에 의존 |
| Q3. 역사연구 | ❌ | **중간** | 1차 사료 접근성에 의존 |
| Q2. 과학철학 | ❌ | **약함** | 순수 규범적 질문, 경험적 반증 불가 |

---

## 4. 현재 남은 이슈

### 🔴 미해결 (설계 필요)

**이슈 1: claim 분류의 신뢰성**
두 논문의 claim이 "대립/보완/직교"인지 자동 분류하는 것 자체가 LLM에 의존한다. 이 분류가 틀리면 잘못된 비교가 발생한다.
- 후보 해결: claim 분류를 별도 경량 LLM이 담당 + 불확실할 때 "직교"로 기본값

**이슈 2: topic_tag 자동 할당**
새 논문이 생성될 때 어떤 topic_tag를 붙이는가? 자동 할당 방법이 없으면 MAP-Elites 셀이 의미없어진다.
- 후보 해결: 사전 정의된 분류 체계 + LLM이 해당 논문을 분류

**이슈 3: 콜드 스타트**
시스템 시작 시 papers가 0개다. 초기 시드 논문을 어떻게 확보하나?
- 후보 해결: 관련 arXiv 논문 자동 수집으로 초기 papers 채우기

**이슈 4: 코드 실행 환경 격리**
Q4~Q7에서 에이전트가 직접 코드를 실행한다. 악성 코드 or 무한 루프 방지 필요.
- 후보 해결: Docker 격리, 타임아웃, 자원 제한

**이슈 5: 수렴 판단**
시스템이 언제 "충분히 탐색했다"고 판단하나? 현재 while True 루프는 무한히 돈다.
- 후보 해결: fitness 분포의 분산이 특정 임계값 이하로 떨어지면 수렴 판정

### 🟡 부분 해결 (구현 불확실)

**이슈 6: 인터넷 검색 품질 (Q1, Q3)**
read_url + web_search 도구를 쓰면 Q1, Q3에서 작동하지만, 인터넷 정보의 품질이 들쑥날쑥하다. URL 기반 신뢰도 점수는 방법론이 약하다.
- 현재 최선: citation_count (Semantic Scholar) + 원문 발췌를 judge에게 직접 전달

**이슈 7: rival 선택 전략**
새 논문의 비교 상대를 어떻게 선택하나? 항상 챔피언(fitness 최고)과 붙이면 초기 수렴이 빠를 수 있지만 다양성이 감소한다.
- 후보 해결: 70% 확률로 챔피언, 30% 확률로 랜덤 (SGD-inspired)

**이슈 8: MAP-Elites 셀 설계**
topic × perspective 2차원 격자인데, perspective 축을 어떻게 정의하나?
- 후보 해결: empirical / theoretical / applied / critical 4개로 고정

### 🟢 철학적 미해결 (수용하고 진행)

**이슈 9: 규범적 질문 (Q2)**
순수 철학적 질문은 이 시스템으로 잘 다루기 어렵다. pairwise 비교가 "더 정교하게 들리는 쪽"을 선택하는 경향이 있다. **이 한계는 수용하고, Q2형 질문은 시스템 범위 밖으로 설정한다.**

**이슈 10: 진리 vs 합리성**
이 시스템은 "진리"가 아닌 "현재 증거 기준으로 가장 반박하기 어려운 가설"을 찾는다. 이것이 실제 진리와 다를 수 있음을 사용자와 시스템 모두 인지해야 한다.

---

## 5. 다음 단계 추천

1. **즉시 가능**: Q6 (에이전틱 메모리) 주제로 소규모 파일럿 실행
   - papers 10개 수동 시드
   - research_agent + pair_compare_agent 루프 10 iteration
   - comparisons 결과와 fitness 변화 관찰

2. **단기**: topic_tag 자동 할당 + claim 자동 추출 구현

3. **중기**: 코드 실행 환경 격리 → Q4, Q5, Q7으로 확장

4. **장기**: 인터넷 검색 품질 개선 → Q1, Q3 커버리지 확장

---

## 참고 — 주요 설계 원칙 (오컴의 면도날)

> 평가압력 + 다양성 보존 + 상태 명시성

- 평가압력: `comparisons (winner, loser)` 테이블이 전부
- 다양성 보존: MAP-Elites 셀 + `archived` 상태 (삭제 없음)
- 상태 명시성: 모든 것이 SQLite에 명시적으로 기록됨
