# 기술 스택

전략 보고서(`docs/260317_final-strategy-report.md`) 섹션 7의 최종 기술 선택과 그 근거를 정리한다. 선택하지 않은 것들과 그 이유도 함께 기록한다.

---

## 선택한 기술

### Python 3.10+

**역할**: 메인 루프, 결정론적 상태 갱신, 비동기 조율

**선택 이유**:
- `asyncio`가 내장되어 LLM 비동기 호출과 동기 DB 연산을 같은 프로세스에서 혼용 가능
- `sqlite3`, `hashlib`이 내장 라이브러리. 추가 의존성 없음
- Claude Agent SDK가 Python 패키지로 제공됨

README에는 Python 3.9+로 명시되어 있으나, 전략 보고서는 Python 3.10+를 권장한다.

---

### claude-agent-sdk

**역할**: LLM 호출 인터페이스. 3개 에이전트 모두 사용.

**패키지**: `claude-agent-sdk>=0.1.49` (`requirements.txt`)

**핵심 사용 패턴**:

```python
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage

async for message in query(
    prompt=user_prompt,
    options=ClaudeAgentOptions(
        allowed_tools=["WebSearch", "WebFetch"],
        permission_mode="bypassPermissions",
        system_prompt=system,
        model="claude-sonnet-4-6",
        max_turns=15,
        **OMC_OPTS,
    ),
):
    if isinstance(message, ResultMessage):
        result_text = message.result or ""
```

`query()`는 async generator를 반환한다. `ResultMessage`가 최종 응답이다. 중간 메시지에서 도구 사용 현황을 로깅할 수 있다.

**Stop Hooks (HookMatcher)**:

```python
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage, HookMatcher

options=ClaudeAgentOptions(
    ...
    hooks={
        "Stop": [HookMatcher(matcher="*", hooks=[enforce_research_quality])]
    },
)
```

`HookMatcher`는 에이전트 Stop 이벤트에 Python 콜백을 등록합니다. 콜백이 `{"decision": "block", "reason": "..."}` 를 반환하면 에이전트가 중지하지 않고 추가 턴을 사용합니다. 이를 통해 SDK 레벨에서 출력 품질을 강제할 수 있습니다 (Mini-Ralph 패턴).

**모델별 역할 분배**:

| 에이전트 | 모델 | 이유 |
|----------|------|------|
| research_agent | `claude-sonnet-4-6` | 실제 웹 검색 + 논문 작성. 품질이 비용보다 중요 |
| compare_agent | `claude-haiku-4-5-20251001` | 반복 호출 많음 (사이클당 3회). 비용 최적화. max_turns=3 (Stop hook 허용) |
| reflector_agent | `claude-haiku-4-5-20251001` | annotation 추출. max_turns=3 (Stop hook 허용) |

**`claude -p`를 선택하지 않은 이유**:

`claude -p`는 one-shot이다. 스킬, 훅, 서브에이전트가 작동하지 않는다. Python 루프가 완전한 제어권을 가지려면 SDK가 필요하다. 이는 전략 보고서 이슈 N에서 확정된 결론이다.

---

### networkx

**역할**: PageRank 계산. `core/fitness.py`에서만 사용.

```python
import networkx as nx

G = nx.DiGraph()
G.add_nodes_from(paper_ids)
for comp in comparisons:
    G.add_edge(comp["loser"], comp["winner"])

pr = nx.pagerank(G, alpha=0.85, max_iter=100)
```

실제 사용 코드는 5줄이다. networkx 전체를 설치하는 것은 이 5줄을 위해서다. `numpy`, `scipy`는 networkx의 의존 라이브러리로 함께 설치된다.

수렴 실패 시 폴백:

```python
except nx.PowerIterationFailedConvergence:
    # win ratio로 폴백: wins / (wins + losses)
    pr[pid] = wins / max(total, 1)
```

---

### SQLite + WAL

**역할**: 지식 저장소 전체. 5개 테이블, 인덱스, 불변 트리거.

**설정**:

```python
# core/__init__.py
conn.execute("PRAGMA journal_mode=wal")   # 쓰기 중 읽기 허용
conn.execute("PRAGMA busy_timeout=5000")  # 쓰기 경합 5초 대기
conn.execute("PRAGMA foreign_keys=ON")    # 참조 무결성
```

**WAL 모드를 선택한 이유**:
- 단일 프로세스 에이전트 루프에서 유일하게 필요한 동시성 패턴 제공
- 쓰기 중에도 읽기 가능 → `calculate_fitness()` 중 `build_session_context()` 호출 가능
- 자동 복구: 비정상 종료 후 재시작 시 WAL 파일에서 자동 복원

**스키마 파일**: `core/schema.sql` — `CREATE TABLE IF NOT EXISTS` 패턴으로 재실행 안전.

---

### asyncio (Python 내장)

**역할**: 비동기 LLM 호출 조율. `autoresearch_v2.py`의 `research_loop()`에서 사용.

```python
# 진입점
asyncio.run(research_loop(args.db, args.topic, max_cycles=args.max_cycles))

# 사이클 간 대기 (non-blocking)
await asyncio.sleep(5)

# 오류 후 backoff
await asyncio.sleep(30)
```

동기/비동기 경계 규칙: Phase 5의 `calculate_fitness()`, `update_lifecycle_states()`, `update_map_elites()` 호출 사이에 `await`를 삽입하면 안 된다. 이 함수들은 내부적으로 `conn.execute()` + `conn.commit()`을 사용하며 동기다.

---

## 선택하지 않은 것

### FAISS / sqlite-vss (벡터 임베딩)

**제안 이유**: 수백 개의 논문이 쌓이면 의미적 유사성 검색이 필요할 것이라는 예측.

**선택하지 않은 이유**: L0 요약 + SQL LIKE 필터 + LLM 일괄 판단이 실제로 더 정확했다. 전략 보고서 이슈 B에서 현장 검증 결과로 확정. 벡터 임베딩은 추가 의존성(FAISS 설치, 임베딩 모델), 추가 API 비용(embedding 호출), 추가 복잡성(인덱스 관리)을 가져오지만 실제 검색 품질 향상이 없었다.

현재 검색 구현:

```python
# core/memory.py:search_papers()
# No vector embeddings — L0 + LLM filtering is sufficient per strategy report.
rows = conn.execute(
    "SELECT id, claim, l0_summary, fitness, status, perspective FROM papers "
    "WHERE topic_tag = ? AND status != 'archived' AND (claim LIKE ? OR l0_summary LIKE ?) "
    "ORDER BY fitness DESC LIMIT 10",
    (topic, pattern, pattern),
).fetchall()
```

---

### Neo4j / ArangoDB

**제안 이유**: 지식 관계 그래프를 그래프 DB에 저장하면 복잡한 관계 쿼리가 쉬울 것이라는 예측.

**선택하지 않은 이유**: 전략 보고서 이슈 A에서 확정. 그래프 DB의 역할은 "발견된 관계의 정리장"이지 "검색/발견 엔진"이 아니다. 검색과 발견은 SQL 필터 + LLM 판단이 담당한다. SQLite의 `edges` 테이블로 같은 역할을 한다. 외부 DB 서버를 설치하고 유지할 이유가 없다.

`edges` 테이블은 현재 스키마에 존재하지만 Phase 2 전까지 데이터가 채워지지 않는다.

---

### CrewAI / AutoGen

**제안 이유**: 멀티에이전트 프레임워크를 사용하면 에이전트 조율이 더 쉬울 것이라는 예측.

**선택하지 않은 이유**:
- 오버헤드가 높다. 프레임워크가 루프 제어를 가져가면 비용 최적화(모델별 역할 분배)가 어려워진다
- 루프 제어가 약하다. `while True` 루프의 각 단계에서 세밀한 제어(30% 반박 확률, 만장일치 체크, Phase 5 결정론적 갱신)가 필요한데, 프레임워크가 이를 추상화해버린다
- `autoresearch_v2.py`의 메인 루프는 70줄이다. 프레임워크가 해결할 문제가 없다

---

### LangGraph

**제안 이유**: 상태 머신 기반 에이전트 오케스트레이션으로 복잡한 플로우를 관리할 수 있을 것이라는 예측.

**선택하지 않은 이유**: Claude Agent SDK가 Claude 환경에 더 통합적이다. OMC 플러그인, 프로젝트/사용자 설정(CLAUDE.md), 스킬, 훅이 SDK를 통해 자동으로 로드된다. LangGraph는 이 통합을 제공하지 않는다.

---

### Docker (Phase 1)

**제안 이유**: 에이전트가 코드를 실행할 때 격리 환경이 필요하다.

**선택하지 않은 이유**: Phase 1은 코드 실행을 포함하지 않는다. WebSearch + WebFetch만 사용한다. Docker 격리는 Phase 3에서 추가 예정이다 (Q4 LLM 성능, Q5 행렬 알고리즘, Q6 에이전틱 메모리, Q7 로컬 챗봇 주제에서 코드 실행이 필요할 때).

---

## OMC 플러그인 통합 방식

`agents/_sdk.py`가 oh-my-claudecode 플러그인 경로를 동적으로 탐색하고 research_agent에 주입한다.

```python
# agents/_sdk.py

def _find_omc_plugin_path() -> str:
    # 1. OMC_PLUGIN_PATH 환경변수 확인
    env_path = os.environ.get("OMC_PLUGIN_PATH")
    if env_path and os.path.isdir(os.path.expanduser(env_path)):
        return os.path.expanduser(env_path)

    # 2. ~/.claude/plugins/cache/omc/oh-my-claudecode/ 에서 최신 버전 자동 탐색
    base = os.path.expanduser("~/.claude/plugins/cache/omc/oh-my-claudecode")
    if os.path.isdir(base):
        versions = sorted(glob.glob(os.path.join(base, "*")), reverse=True)
        if versions and os.path.isdir(versions[0]):
            return versions[0]

    # 3. 폴백: 빈 문자열 (플러그인 로딩 건너뜀)
    return ""

OMC_OPTS = dict(
    setting_sources=["user", "project"],
    plugins=[{"type": "local", "path": OMC_PLUGIN_PATH}] if OMC_PLUGIN_PATH else [],
)
```

**research_agent에만 OMC를 적용하는 이유**: OMC 플러그인은 WebSearch, WebFetch 같은 도구를 강화한다. compare_agent와 reflector_agent는 `allowed_tools=[]`로 도구를 전혀 사용하지 않는 순수 추론 에이전트다. OMC를 로드해도 이들에게는 아무 이점이 없다.

```python
# agents/compare_agent.py, reflector_agent.py
## OMC not loaded — but Stop hooks are used for quality enforcement
options=ClaudeAgentOptions(
    allowed_tools=[],
    permission_mode="bypassPermissions",
    model="claude-haiku-4-5-20251001",
    max_turns=3,  # Stop hook이 최대 2회 거부 가능
    hooks={
        "Stop": [HookMatcher(matcher="*", hooks=[enforce_comparison_quality])]
    },
)
```

---

## 비용 추정

전략 보고서와 README의 비용 표를 통합한다.

| 에이전트 | 모델 | 사이클당 호출 수 | 예상 비용 |
|----------|------|-----------------|-----------|
| research_agent | claude-sonnet-4-6 | 1회 (최대 15턴) | ~$0.030 |
| compare_agent — 분류 | claude-haiku-4-5 | 1회 (1턴) | ~$0.001 |
| compare_agent — 판정 | claude-haiku-4-5 | 2회 (1턴 × 2) | ~$0.003 |
| reflector_agent | claude-haiku-4-5 | 1회 (1턴) | ~$0.002 |
| **합계** | | | **~$0.036/사이클** |

**일별 비용 예시**:

| 운영 패턴 | 사이클 수 | 일별 비용 |
|-----------|-----------|-----------|
| 가벼운 탐색 | 50 사이클/일 | ~$1.80 |
| 일반 운영 | 100 사이클/일 | ~$3.60 |
| 24시간 overnight (사이클당 ~40초) | ~2,160 사이클 | ~$78 |
| cold start (LLM 시드 생성) | +10 사이클 (1회) | +$0.30 추가 |

**비용 변수**: 논문 길이와 컨텍스트 크기에 따라 달라진다. topic당 L1 컨텍스트가 누적될수록 research_agent 비용이 증가한다. seed_data.py로 cold start를 대체하면 초기 $0.30을 절약할 수 있다.

---

## 전체 의존성

```
# requirements.txt 대응
claude-agent-sdk>=0.1.49  # Claude Agent SDK
networkx>=3.0             # PageRank
numpy>=2.0                # networkx 의존
scipy>=1.13               # networkx 의존

# Python 내장 (설치 불필요)
sqlite3            # 지식 저장소
hashlib            # SHA-256 ID
asyncio            # 비동기 루프
pathlib            # 경로 처리
```
