# 메인 루프 라이프사이클 — `autoresearch_v2.py`

## 진입점

```python
asyncio.run(research_loop(args.db, args.topic, max_cycles=args.max_cycles, research_question=args.prompt))
```

`research_loop()`는 단일 asyncio 이벤트 루프에서 전체 생명주기를 관리합니다. DB 연결(`conn`)은 세션 전체 수명 동안 유지합니다.

### research_question 파라미터

CLI의 `--prompt` 인자로 전달되는 상세 연구 질문입니다. 모든 에이전트에 전달되어 연구의 방향성을 결정합니다.

```python
async def research_loop(db_path: str, topic: str, max_cycles: int = None, research_question: str = ""):
```

| CLI 인자 | 파라미터 | 용도 |
|----------|----------|------|
| `--topic` | `topic` | 주제 태그 (MAP-Elites 셀 주소) |
| `--prompt` | `research_question` | 상세 연구 질문 (에이전트의 North Star) |
| `--max-cycles` | `max_cycles` | 최대 사이클 수 |
| `--db` | `db_path` | SQLite DB 경로 |

---

## Trial ID 시스템

각 사이클은 고유한 **Trial ID**로 식별됩니다: `YYYYMMDDHHMMSS_HASH` (예: `20260318020359_a3f8b2`).

```python
def generate_trial_id() -> str:
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%d%H%M%S")
    hash_suffix = hashlib.sha256(
        f"{timestamp}{uuid.uuid4().hex}".encode()
    ).hexdigest()[:6]
    return f"{timestamp}_{hash_suffix}"
```

| 구성 요소 | 역할 |
|-----------|------|
| `YYYYMMDDHHMMSS` 타임스탬프 접두사 | 시간순 정렬 보장 |
| `_` 구분자 | 가독성 |
| 6자 SHA-256 해시 접미사 | 같은 초 내 유일성 보장 |

### Per-Trial 로그 파일

각 사이클은 자체 로그 파일(`logs/{trial_id}.log`)을 생성합니다. 세션 로그(`logs/research.log`)와 별도로 운영됩니다.

```python
def setup_logger(log_dir: str, trial_id: str) -> logging.FileHandler:
    # ROOT autoresearch 로거에 핸들러 부착
    # → 모든 하위 로거(research, compare, reflector, memory)가 자동으로 캡처됨
    fh = logging.FileHandler(os.path.join(log_dir, f"{trial_id}.log"), encoding="utf-8")
    logging.getLogger("autoresearch").addHandler(fh)
    return fh
```

사이클 종료(정상/오류 모두) 시 trial handler를 제거하여 세션 핸들러만 유지합니다.

### 로깅 계층

| 핸들러 | 파일 | 레벨 | 수명 |
|--------|------|------|------|
| Session FileHandler | `logs/research.log` | DEBUG | 전체 세션 |
| Trial FileHandler | `logs/{trial_id}.log` | DEBUG | 단일 사이클 |
| StreamHandler | stdout | INFO | 전체 세션 |

---

## 시그널 처리

```python
shutdown_requested = False

def handle_signal(signum, frame):
    nonlocal shutdown_requested
    logger.info(f"Shutdown signal received (signal {signum}). Finishing current cycle...")
    shutdown_requested = True

signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)
```

`SIGINT`(Ctrl+C) 또는 `SIGTERM` 수신 시 현재 사이클을 완료한 후 루프를 종료합니다. 사이클 중간에 강제 종료하지 않으므로 DB 상태가 일관성을 유지합니다.

---

## 루프 조건

```python
while not shutdown_requested and (max_cycles is None or cycle_num < max_cycles):
```

| 조건 | 동작 |
|------|------|
| `shutdown_requested = True` | 현재 사이클 완료 후 종료 |
| `max_cycles` 지정 | 해당 횟수 완료 후 종료 |
| `max_cycles = None` (기본) | 무한 루프 |

CLI에서 `--max-cycles N`으로 지정합니다. 테스트나 파일럿 실행 시 안전 밸브로 사용합니다.

---

## 5단계 사이클

### Phase 1: 세션 컨텍스트 구성

```python
context = build_session_context(conn, topic, session_id)
```

`build_session_context()`는 다음을 수행합니다.

- L0 요약 전체 스캔 → 관련도 높은 항목만 L1으로 승격
- 이전 세션 annotations를 컨텍스트 앞에 주입 (Context Hub 패턴)

반환값은 research_agent의 user prompt에 삽입됩니다.

---

### Phase 2: 논문 생성

```python
champion = get_champion(conn, topic)
is_rebuttal = random.random() < 0.3 and bool(champion)

new_paper = await run_research(
    conn, topic, session_id, context,
    champion_claim=champion.get("claim") if is_rebuttal and champion else None,
    is_rebuttal=is_rebuttal,
    research_question=research_question,
)
```

- 70%: 일반 논문 생성
- 30%: 챔피언 claim에 대한 반박 논문 생성 (챔피언이 존재할 때만)

`run_research()`는 내부에서 `save_paper()`를 호출하므로 반환 시 이미 DB에 저장되어 있습니다.

---

### Phase 3: Pairwise 비교

```python
rival = select_rival(conn, topic)

if rival and rival.get("id") != new_paper.get("id"):
    comparison = await run_comparison(conn, new_paper, rival, research_question=research_question)
else:
    comparison = None
```

`select_rival()`은 70% 확률로 챔피언, 30% 확률로 랜덤 논문을 선택합니다. 자기 자신과의 비교는 명시적으로 방지합니다.

`run_comparison()`은 내부에서 `comparisons` 테이블에 직접 기록합니다. 반환값은 `(winner_id, loser_id, reasoning)` 3-tuple 또는 `None`입니다.

---

### Phase 4: Annotation 추출

```python
annotations = await run_reflection(
    conn, session_id, topic, comparison, new_paper, context,
    research_question=research_question,
)
for ann in annotations:
    save_annotation(
        conn,
        new_paper.get("id", ""),
        session_id,
        ann["content"],
        ann.get("tags", ["general"]),
    )
```

reflector_agent가 반환한 annotation 리스트를 순회하며 `annotations` 테이블에 저장합니다. `comparison`은 Phase 3의 3-tuple `(winner_id, loser_id, reasoning)` 또는 `None`이며, reasoning이 reflector에게 전달되어 더 정확한 annotation 추출이 가능합니다.

---

### Phase 5: 결정론적 상태 갱신

```python
calculate_fitness(conn, topic)
update_lifecycle_states(conn, topic)
update_map_elites(conn, topic)
```

세 함수 모두 LLM을 호출하지 않습니다. `comparisons` 테이블 데이터를 읽어 순수 Python으로 상태를 갱신합니다.

**주의사항**: 이 세 호출 사이에 `await`를 놓으면 안 됩니다. asyncio에서 `await` 사이에 다른 코루틴이 끼어들 수 있고, `conn.execute()`와 `conn.commit()` 사이에 다른 DB 조작이 발생하면 상태 불일치가 생깁니다.

```python
# 올바른 순서 (await 없음)
calculate_fitness(conn, topic)       # conn.execute + conn.commit
update_lifecycle_states(conn, topic) # conn.execute + conn.commit
update_map_elites(conn, topic)       # conn.execute + conn.commit
```

---

## 에러 처리

```python
except Exception as e:
    elapsed = time.time() - cycle_start
    logger.error(f"Cycle {cycle_num} error after {elapsed:.1f}s: {e}", exc_info=True)
    if not shutdown_requested:
        await asyncio.sleep(30)
```

사이클 실패 시 30초 대기 후 다음 사이클을 시도합니다. 루프를 종료하지 않습니다.

---

## 로깅 설정

### 세션 레벨 로깅

```python
# Session FileHandler: DEBUG 레벨, logs/research.log
# StreamHandler: INFO 레벨, stdout
```

| 핸들러 | 레벨 | 대상 | 포맷 |
|--------|------|------|------|
| Session FileHandler | DEBUG | `logs/research.log` | `%(asctime)s [%(levelname)s] %(name)s: %(message)s` |
| StreamHandler | INFO | stdout | `%H:%M:%S [%(levelname)s] %(message)s` |
| Trial FileHandler | DEBUG | `logs/{trial_id}.log` | `%(asctime)s [%(levelname)s] %(name)s: %(message)s` |

장시간 실행 중에는 세션 파일 로그로 전체 기록을 확인하고, 특정 사이클 디버깅 시 trial 로그를 확인합니다.

### Per-Phase 로깅

각 Phase 시작 시 헤더를 출력합니다:

```
=== PHASE 1: Build Session Context ===
=== PHASE 2: Generate New Paper ===
=== PHASE 3: Pairwise Comparison ===
=== PHASE 4: Reflection & Annotation Extraction ===
=== PHASE 5: Deterministic State Updates ===
```

Phase 2에서는 논문의 claim, perspective, assumptions, evidence sources를 로깅합니다.
Phase 3에서는 rival 정보, 비교 결과, judge reasoning을 로깅합니다.
Phase 4에서는 각 annotation의 tags, content, suggested_search를 로깅합니다.
Phase 5에서는 갱신 후 새 논문의 fitness와 status를 로깅합니다.

---

## 사이클 통계 출력

각 사이클 완료 후 `log_cycle_stats()`가 trial_id를 포함하여 INFO로 출력합니다.

```python
def log_cycle_stats(conn, cycle_num, topic, elapsed, logger, trial_id):
```

```
=== Cycle {n} Complete [Trial: {trial_id}] ===
  Papers: {total} total ({active} active, {archived} archived)
  Comparisons: {comparisons} | Annotations: {annotations}
  Champion fitness: {fitness:.3f} — {claim[:60]}
  Elapsed: {elapsed:.1f}s
```
