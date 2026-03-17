# AutoResearch 밤새 돌리기 - 완전 가이드

> 작성일: 2026-03-16
> 조사 기반: karpathy/autoresearch 커뮤니티, Ralph Wiggum 기법, oh-my-claudecode, ralphton 사례

---

## TL;DR

**핵심 문제**: Claude가 컨텍스트 한계에 도달하거나 스스로 멈춤
**해결책**: Ralph 루프 + tmux 세션 + 외부 재시작 래퍼 조합

---

## 1. 왜 Claude가 중간에 꺼지는가?

### 1.1 컨텍스트 창 초과
autoresearch는 각 실험마다 다음을 컨텍스트에 누적한다:
- `train.py` 전체 (630줄)
- `run.log` 읽기
- `results.tsv` 읽기/쓰기
- 도구 호출 히스토리

약 20~30회 실험 후 컨텍스트가 포화된다. Claude Code가 자동 압축(compaction)을 수행하지만, 이 과정에서 `program.md`의 "LOOP FOREVER" 지침이 소실될 수 있다.

### 1.2 Claude의 자발적 정지
안전 가이드라인 또는 불확실한 상황에서 Claude가 "계속할까요?" 라고 묻거나 멈춘다.

### 1.3 세션 종료
SSH 연결 끊김, 노트북 슬립, 터미널 닫힘 등으로 Claude Code 프로세스가 종료된다.

---

## 2. Ralph Wiggum 기법 (핵심 해결책)

**Ralph Wiggum**은 Geoffrey Huntley가 창안하고 Anthropic이 공식 플러그인화한 자율 루프 기법이다.

### 2.1 기본 원리

```bash
# 가장 단순한 형태
while :; do
    cat PROMPT.md | claude
done
```

Claude가 꺼지면 **즉시 재시작**한다. 이름은 심슨의 Ralph Wiggum 캐릭터에서 따왔다 — 실패해도 계속 시도하는 집착적 반복을 상징.

### 2.2 autoresearch에 적용

```bash
#!/bin/bash
# ralph_autoresearch.sh

PROMPT="program.md를 읽고 autoresearch 실험 루프를 계속 진행해.
results.tsv를 확인해서 마지막으로 완료된 실험 이후부터 이어서 진행해.
NEVER STOP."

MAX_ITERATIONS=200
ITER=0

while [ $ITER -lt $MAX_ITERATIONS ]; do
    echo "[Ralph] 이터레이션 $ITER 시작: $(date)"

    claude --continue "$PROMPT" 2>&1 | tee -a ralph_session.log

    EXIT_CODE=$?
    ITER=$((ITER + 1))

    echo "[Ralph] Claude 종료 (코드: $EXIT_CODE). 5초 후 재시작..."
    sleep 5
done

echo "[Ralph] $MAX_ITERATIONS 이터레이션 완료."
```

### 2.3 증명된 결과 (커뮤니티 사례)
- $50,000 규모 프로젝트를 $297 API 비용으로 완료 (99.4% 절감)
- 하룻밤에 Y Combinator 해커톤 레포 6개 생성
- 30시간+ 무중단 자율 개발

---

## 3. oh-my-claudecode Ralph 모드

**oh-my-claudecode(OMC)**의 `/ralph` 스킬은 이를 더 정교하게 구현한다:

### 3.1 동작 방식
1. **PRD(Product Requirements Document)** 기반 목표 설정 — 완료 조건을 명시적으로 정의
2. **ultrawork 병렬 실행** — 독립적 작업을 동시 처리
3. **architect 검증** — 각 이터레이션을 독립 에이전트가 검증
4. **state 영속성** — `.omc/state/`에 진행 상태 저장, 재시작 시 이어받기

### 3.2 autoresearch에 맞춘 OMC Ralph 프롬프트

```
/ralph

program.md를 읽고 autoresearch 실험을 진행해.
각 실험은 train.py 수정 → 실행 → 결과 확인 → keep/discard 사이클.
목표: results.tsv에 50개 이상의 실험 기록, 최저 val_bpb 달성.
NEVER STOP.
```

### 3.3 컨텍스트 한계 해결
OMC Ralph는 `/compact`를 자동으로 호출하고, 압축 후에도 핵심 지침(루프 지속)이 유지되도록 state 파일에 저장한다.

---

## 4. Ralphton (Ralph + Marathon)

**Ralphton**은 hackathon의 변형으로, Ralph 루프를 이용해 밤새 자율적으로 AI 실험을 진행하는 이벤트다.

### 4.1 개념
- 해커톤: 인간이 밤새 코딩
- **Ralphton**: Claude(AI)가 밤새 코딩/실험, 인간은 자는 동안 결과를 수확

autoresearch의 설계 철학("하룻밤에 100개 실험")과 정확히 일치한다.

### 4.2 실제 운영 방식

```
저녁 11시: Ralph 루프 + tmux 세션 시작
밤새:       Claude가 자율적으로 train.py 수정 → 실험 → 기록
아침 7시:   results.tsv 확인, 최선의 커밋 분석
```

---

## 5. 실전 설정: 완전한 overnight 세팅

### Step 1: tmux 세션 시작 (필수)

```bash
# 세션 생성
tmux new-session -d -s autoresearch

# 세션 안으로 들어가기
tmux attach -t autoresearch

# 실험 후 detach: Ctrl+B, D
# 나중에 재접속: tmux attach -t autoresearch
```

### Step 2: autoresearch 디렉토리에서 git 브랜치 생성

```bash
cd /path/to/autoresearch
git checkout -b autoresearch/$(date +%b%d | tr '[:upper:]' '[:lower:]')
# 예: autoresearch/mar16
```

### Step 3: ralph 래퍼 스크립트 실행

```bash
# 방법 A: 단순 while 루프
while true; do
    claude --continue "program.md 보고 실험 이어서 진행해. 절대 멈추지 마."
    sleep 3
done

# 방법 B: OMC Ralph 모드 (권장)
# Claude Code에서:
# /ralph
# program.md 읽고 autoresearch 실험 루프 시작. 50회 이상 실험 목표.
```

### Step 4: 모니터링 (선택)

```bash
# 다른 tmux 창에서 실시간 결과 모니터링
watch -n 30 "cat results.tsv | column -t"

# 로그 확인
tail -f ralph_session.log
```

### Step 5: 아침에 확인

```bash
# 최고 성능 실험 확인
sort -t$'\t' -k2 -n results.tsv | head -5

# 실험 횟수 확인
wc -l results.tsv
```

---

## 6. 컨텍스트 한계 해결 전략 비교

| 전략 | 난이도 | 효과 | 설명 |
|------|--------|------|------|
| **while 루프 래퍼** | 쉬움 | 중간 | Claude 재시작은 되지만 컨텍스트 누적 없음 |
| **`--continue` 플래그** | 쉬움 | 높음 | 마지막 세션 이어받기 |
| **OMC Ralph 모드** | 중간 | 매우 높음 | PRD + state 영속성 + 자동 압축 |
| **`/compact` 주기적 호출** | 중간 | 높음 | 컨텍스트 압축 후 루프 지속 |
| **results.tsv를 체크포인트로** | 낮음 | 높음 | 재시작 시 마지막 기록부터 이어받기 가능 |

---

## 7. autoresearch 설계가 컨텍스트 문제를 완화하는 이유

karpathy의 설계가 영리한 이유:

1. **단일 파일 수정** (`train.py` 630줄): 컨텍스트에 항상 전체 파일을 올려도 무거운 크기가 아님
2. **git을 메모리로 사용**: `git log`, `git diff`만으로 전체 실험 히스토리 파악 가능 — 컨텍스트에 실험 내역을 쌓을 필요 없음
3. **results.tsv 체크포인트**: Claude가 재시작해도 이전 실험 결과를 이 파일 하나로 파악 가능
4. **고정 시간 예산(5분)**: 각 실험이 예측 가능하게 종료되므로 루프 구조가 단순함

---

## 8. 커뮤니티 포크 및 확장

| 프로젝트 | 특징 |
|----------|------|
| **autokernel** | PyTorch 모델 최적화에 적용, ~40 실험/시간 |
| **autoresearch-mlx** | Apple Silicon(M1/M2/M3) 지원 |
| **autoresearch-agents** | 에이전트가 다른 에이전트를 개선하는 메타 루프 |
| **autoresearch-win-rtx** | Windows + RTX 지원 |

autoresearch 패턴은 이제 **"primitive"**가 되었다 — GPU 최적화, 테스트 커버리지, 번들 크기, 접근성 등 **측정 가능한 모든 것**에 적용 가능.

---

## 9. 주의사항 및 한계

### Goodhart의 법칙
에이전트는 **메트릭을 최적화**하지, 실제 품질을 개선하지 않을 수 있다. `val_bpb`가 낮아져도 실제로 더 좋은 모델인지는 별도로 검증 필요.

### 하드웨어 의존성
실험 결과는 특정 GPU에 종속된다. H100에서 최적화된 설정이 다른 GPU에서 좋지 않을 수 있다.

### 아이디어 고갈
에이전트가 결국 새 아이디어를 소진하면 랜덤 변경을 시작할 수 있다. `program.md`에 탐색 방향을 주기적으로 업데이트하는 것이 좋다.

### API 비용
하룻밤 100회 실험 시 API 비용이 상당할 수 있다. 시작 전에 예상 비용을 계산할 것.

---

## 10. 권장 워크플로

```
1. 저녁에 준비:
   - tmux new -s autoresearch
   - git checkout -b autoresearch/$(date +%b%d)
   - uv run prepare.py (첫 실행 시)

2. 시작:
   - Claude Code 실행
   - /ralph 또는 while 루프 래퍼 사용
   - "program.md 읽고 실험 시작, 멈추지 마" 프롬프트

3. 아침에:
   - tmux attach -t autoresearch
   - results.tsv 분석
   - 최선의 커밋 확인 및 검토
```

---

## 참고 자료

- [karpathy/autoresearch](https://github.com/karpathy/autoresearch) — 원본 레포
- [Autoresearch Became a Primitive](https://paddo.dev/blog/autoresearch-ecosystem/) — 커뮤니티 확장 현황
- [Ralph Wiggum - Awesome Claude](https://awesomeclaude.ai/ralph-wiggum) — Ralph 기법 설명
- [oh-my-claudecode](https://github.com/yeachan-heo/oh-my-claudecode) — OMC Ralph 스킬
- [frankbria/ralph-claude-code](https://github.com/frankbria/ralph-claude-code) — Ralph 루프 구현체
- [Autoresearch in Google Colab](https://www.marktechpost.com/2026/03/12/how-to-build-an-autonomous-machine-learning-research-loop-in-google-colab-using-andrej-karpathys-autoresearch-framework-for-hyperparameter-discovery-and-experiment-tracking/) — Colab 적용 가이드
- [The New Stack: Karpathy autonomous experiment loop](https://thenewstack.io/karpathy-autonomous-experiment-loop/) — 개요 분석
