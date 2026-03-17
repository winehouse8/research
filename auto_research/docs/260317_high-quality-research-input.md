# 고품질 연구 입력 전략: 논문 PDF 접근 + X 정보 탐색봇

**작성일**: 2026-03-17
**목적**: 자율 연구 에이전트의 입력 품질을 높이기 위한 두 가지 전략 조사
**범위**: (1) 논문 PDF 자동 다운로드·읽기, (2) X(트위터) AI 정보 탐색봇

---

## 요약 (두괄식)

**결론 먼저**:

| 전략 | 실현 가능성 | 권장 방법 | 비용 |
|---|---|---|---|
| **논문 PDF 접근** | ✅ 즉시 가능 | `arxiv-latex-mcp` + `pymupdf4llm-mcp` | 무료 |
| **X 정보 탐색봇** | ⚠️ 조건부 가능 | `TwitterAPI.io` + MCP 서버 | $5~200/월 |

**핵심 권장**:
- 논문: `paper-search-mcp`(다중소스) + `arxiv-latex-mcp`(수식 정확) + `pymupdf4llm-mcp`(PDF→Markdown) 3종 조합이 2026년 최선
- X봇: 완전 자동 팔로우는 정책 위반으로 불가. 대신 **특정 계정 타임라인 읽기 + Claude 분석** 파이프라인이 현실적

---

## 1부. 논문 PDF 자동 다운로드 + LLM 읽기

### 1.1 현황 — MCP 생태계가 성숙함

2025~2026년 기준, arXiv 논문 접근 MCP 서버가 10개 이상 활성화됐다. 크게 세 레이어로 구분된다:

```
Layer 1: 검색·발견 (Search & Discovery)
  → arXiv API, Semantic Scholar API, PubMed 등

Layer 2: 다운로드·파싱 (Download & Parse)
  → PDF 다운로드 + Markdown 변환

Layer 3: 에이전트 읽기 (LLM Consumption)
  → L0/L1/L2 계층화 로딩 (기존 설계와 연결)
```

### 1.2 핵심 MCP 서버 목록

#### Layer 1: 검색 (arXiv/다중소스)

| 이름 | 특징 | GitHub/링크 |
|---|---|---|
| **paper-search-mcp** | arXiv + PubMed + bioRxiv + Semantic Scholar + Sci-Hub 통합 | [openags/paper-search-mcp](https://github.com/openags/paper-search-mcp) |
| **arxiv-mcp-server** | arXiv 전용, 검색+메타데이터+콘텐츠 접근 | [blazickjp/arxiv-mcp-server](https://github.com/blazickjp/arxiv-mcp-server) |
| **arxiv-latex-mcp** | LaTeX 원본 소스 파싱 (수식 정확) | [takashiishida/arxiv-latex-mcp](https://github.com/takashiishida/arxiv-latex-mcp) |
| **mcp-simple-arxiv** | 검색 → Markdown 변환 | [andybrandt/mcp-simple-arxiv](https://github.com/andybrandt/mcp-simple-arxiv) |
| **semantic-scholar-mcp** | SS API 기반, 인용 관계 추적 | [akapet00/semantic-scholar-mcp](https://github.com/akapet00/semantic-scholar-mcp) |

**가장 포괄적**: `paper-search-mcp` — arXiv, PubMed, bioRxiv, medRxiv, Google Scholar, IACR, Semantic Scholar, Sci-Hub(옵션) 통합

#### Layer 2: PDF 파싱

| 이름 | 특징 | 설치 |
|---|---|---|
| **pymupdf4llm-mcp** | PDF→Markdown, 속도 최고, LLM 최적화 | `uvx pymupdf4llm-mcp@latest stdio` |
| **docling-mcp** | 복잡 레이아웃, 다중 열, 표 추출 | [docling-project/docling-mcp](https://github.com/docling-project/docling-mcp) |
| **markitdown-mcp** | PDF+Word+PPT→Markdown, 29+ 형식 | [trsdn/markitdown-mcp](https://github.com/trsdn/markitdown-mcp) |
| **mcp-pdf2md** | MinerU 기반, 구조 보존+LaTeX 공식 | [FutureUnreal/mcp-pdf2md](https://github.com/FutureUnreal/mcp-pdf2md) |

**성능 비교**:

| 라이브러리 | 속도 | 텍스트 품질 | 표 추출 | 복잡 레이아웃 |
|---|---|---|---|---|
| PyMuPDF4LLM | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ |
| Docling | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Marker | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| pdfplumber | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ |

### 1.3 arxiv-latex-mcp — 수식이 있는 논문의 정답

AI/Agent 논문에는 수학 공식이 많다. PDF에서 공식을 파싱하면 OCR 오류가 생긴다. **해결책**: LaTeX 원본 소스를 직접 다운로드.

```bash
# 설치 (uv 권장)
pip install arxiv-to-prompt  # 기반 라이브러리

# Claude Desktop 설정 (.mcp.json)
{
  "mcpServers": {
    "arxiv-latex-mcp": {
      "command": "python",
      "args": ["-m", "arxiv_latex_mcp"],
      "env": {}
    }
  }
}
```

**작동 방식**:
```
arXiv ID → LaTeX 원본 소스 다운로드 → 텍스트 정확 파싱 → Claude 전달
```

장점: PDF 없이 LaTeX 직접 파싱 → 수식, 표, 알고리즘 완벽 보존

### 1.4 Python CLI 직접 사용 (MCP 없이)

```python
# arxiv.py — 가장 간단한 방법
import arxiv

client = arxiv.Client()
search = arxiv.Search(
    query="agentic memory long-term",
    max_results=5,
    sort_by=arxiv.SortCriterion.SubmittedDate
)

for result in client.results(search):
    print(f"제목: {result.title}")
    print(f"PDF URL: {result.pdf_url}")
    result.download_pdf(dirpath="./papers")
```

```bash
# 설치
pip install arxiv arxiv-dl
```

**`arxiv-dl`**: arXiv 외에 CVPR, ICCV, ECCV, NeurIPS, ICLR 등 학회 논문도 다운로드

### 1.5 자율 연구 에이전트에 최적인 워크플로우

기존 `auto_research` 설계(L0/L1/L2)와 연결하면:

```
[Paper Discovery]
paper-search-mcp → 키워드 검색 → 논문 목록 (제목 + abstract)
                ↓
[L0 생성]
abstract → LLM 요약 → L0 (50토큰 필터용 요약)
                ↓
[L1 생성] (관련성 0.7 이상만)
arxiv-latex-mcp → LaTeX 원본 → L1 (2000토큰 추론용)
                ↓
[L2 생성] (실제 작업 시)
pymupdf4llm-mcp → PDF → Markdown → L2 (전문)
                ↓
[knowledge.db 저장]
papers 테이블: l0_summary, l1_summary, l2_content
```

**핵심 이점**: 외부 논문이 자동으로 `papers` 테이블에 시드됨 → 콜드 스타트 문제 해결

### 1.6 권장 MCP 설정 (Claude Code `.mcp.json`)

```json
{
  "mcpServers": {
    "paper-search": {
      "command": "python",
      "args": ["-m", "paper_search_mcp"],
      "env": {}
    },
    "arxiv-latex": {
      "command": "python",
      "args": ["-m", "arxiv_latex_mcp"],
      "env": {}
    },
    "pymupdf4llm": {
      "command": "uvx",
      "args": ["pymupdf4llm-mcp@latest", "stdio"],
      "env": {}
    }
  }
}
```

**설치**:
```bash
pip install paper-search-mcp arxiv pymupdf4llm-mcp
uvx install pymupdf4llm-mcp
```

---

## 2부. X(트위터) AI 정보 탐색봇

### 2.1 X API 현황 (2026년 3월 기준)

2026년 2월, X가 기존 월정액에서 **Pay-as-you-go** 모델로 전환 발표했다.

**티어 구조**:

| 티어 | 월 비용 | 읽기 | 쓰기 | 용도 |
|---|---|---|---|---|
| **Free** | $0 | ❌ 불가 | 1,500 트윗/월 | 포스팅 전용 |
| **Basic** | $200 | 15,000 트윗/월 | 50,000 트윗/월 | 최저가 읽기 옵션 |
| **Pro** | $5,000 | 상위 제한 | 상위 제한 | 엔터프라이즈 |
| **Enterprise** | $42,000+ | 무제한 | 무제한 | 대형 서비스 |
| **Pay-as-you-go** | 사용량 기반 | 변동 | 변동 | 2026년 신규 |

**핵심 문제**: **읽기는 최소 $200/월**(Basic). 무료로 타임라인을 읽는 공식 방법은 없다.

### 2.2 자동 팔로우의 현실

❌ **완전 자동 팔로우는 정책 위반으로 불가**

X 자동화 정책:
- 대량 팔로우/언팔로우 금지
- 스팸 감지 알고리즘 트리거 위험
- 급속한 연속 동작 시 계정 정지
- 지수 백오프(exponential backoff) 필수

**현실적 대안**:
- 수동으로 AI 거물 계정 리스트 생성 → 봇이 해당 계정만 모니터링
- X "리스트" 기능으로 계정 그룹화 (팔로우 없이 타임라인 모니터링 가능)
- 관심 계정 고정, 자동 읽기만 수행

### 2.3 Twitter MCP 서버 (Claude 통합)

8개 이상의 X MCP 서버가 활성화됨:

| MCP 서버 | 특징 | GitHub |
|---|---|---|
| **DataWhisker/x-mcp-server** | 타임라인 읽기 최적화, Claude Desktop | [DataWhisker/x-mcp-server](https://github.com/DataWhisker/x-mcp-server) |
| **0xGval/twitter-X-mcp-server** | 고급 검색 필터, 자연어 쿼리 | [0xGval/twitter-X-mcp-server](https://github.com/0xGval/twitter-X-mcp-server) |
| **arnaldo-delisio/x-mcp** | 트윗/스레드, 메트릭 조회 | [arnaldo-delisio/x-mcp](https://github.com/arnaldo-delisio/x-mcp) |
| **EnesCinr/twitter-mcp** | 트윗 포스팅 + 검색 | [EnesCinr/twitter-mcp](https://github.com/EnesCinr/twitter-mcp) |
| **lord-dubious/x-mcp** | Twikit 기반, DM 관리 | [lord-dubious/x-mcp](https://github.com/lord-dubious/x-mcp) |

**Claude Code `.mcp.json` 설정**:
```json
{
  "mcpServers": {
    "twitter": {
      "command": "node",
      "args": ["/path/to/x-mcp-server/dist/index.js"],
      "env": {
        "TWITTER_API_KEY": "your_api_key",
        "TWITTER_API_SECRET": "your_api_secret",
        "TWITTER_ACCESS_TOKEN": "your_access_token",
        "TWITTER_ACCESS_SECRET": "your_access_secret"
      }
    }
  }
}
```

### 2.4 비용 효율적 대안 — TwitterAPI.io

공식 API($200/월) 대신 써드파티 서비스 사용:

**TwitterAPI.io**:
- Pay-as-you-go: **$0.15 per 1,000 tweets**
- 월 10,000 트윗 기준: **$1.50**
- 신규 가입 시 무료 크레딧 제공
- 크리덴셜 불필요
- 1,000+ requests/second 지원

⚠️ **주의**: 써드파티 서비스 → X 정책 변경 시 중단 위험. 안정성 검증 필요.

**기타 대안**:
- **Netrows**: $49/월, 26개 X 엔드포인트
- **Apify**: 로그인 없이 스크래핑

### 2.5 팔로우할 AI 거물 계정 리스트

자율 연구 에이전트의 입력 소스로 적합한 계정:

**최우선 (AI 연구 핵심)**:

| 계정 | 인물 | 특징 |
|---|---|---|
| @karpathy | Andrej Karpathy | LLM, 에이전트, 자동화 AI 최전선 |
| @ylecun | Yann LeCun | Meta Chief AI Scientist, 딥러닝 기초 |
| @sama | Sam Altman | OpenAI CEO, AGI 방향 |
| @demishassabis | Demis Hassabis | DeepMind CEO, 강화학습 |
| @AndrewYNg | Andrew Ng | AI 교육, 실무 적용 |

**AI Agent/자동화 특화**:

| 계정 | 특징 |
|---|---|
| @HuggingFace | 모델, 데이터셋, 라이브러리 최신 소식 |
| @OpenAI | GPT, o1 모델 발표 |
| @DeepMind | 알파 시리즈, 연구 논문 |
| @AnthropicAI | Claude, 안전성 연구 |
| @LangChainAI | LangChain, LangGraph 업데이트 |

**빠른 뉴스 (소식 빠름)**:
- @TheNextIntel — AI 기술 트렌드
- @AIHighlight — 일일 AI 도구 & 프롬프트
- @theinformation — AI 산업 뉴스

### 2.6 실현 가능한 구현 방안 (3가지)

#### 방안 A: 공식 X API Basic + Tweepy + Claude (안정, $200/월)

```python
import tweepy
from anthropic import Anthropic

# X API 설정
client = tweepy.Client(
    bearer_token="...",
    consumer_key="...",
    consumer_secret="...",
    access_token="...",
    access_token_secret="..."
)

# 특정 계정들 타임라인 읽기
AI_ACCOUNTS = ["karpathy", "ylecun", "sama", "demishassabis"]

def fetch_recent_tweets(username, max_results=10):
    user = client.get_user(username=username)
    tweets = client.get_users_tweets(
        id=user.data.id,
        max_results=max_results,
        tweet_fields=["created_at", "text", "public_metrics"]
    )
    return tweets.data

# Claude로 분석
anthropic = Anthropic()

def analyze_tweets(tweets):
    content = "\n".join([f"- {t.text}" for t in tweets])
    response = anthropic.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1000,
        messages=[{
            "role": "user",
            "content": f"다음 AI 연구자들의 트윗에서 중요한 연구 동향을 요약해줘:\n{content}"
        }]
    )
    return response.content[0].text

# 크론 작업 (6시간마다)
if __name__ == "__main__":
    all_tweets = []
    for account in AI_ACCOUNTS:
        tweets = fetch_recent_tweets(account)
        if tweets:
            all_tweets.extend(tweets)

    summary = analyze_tweets(all_tweets)
    print(summary)
    # → auto_research의 papers 테이블에 저장 가능
```

#### 방안 B: TwitterAPI.io + Claude (저비용, ~$5~50/월)

```python
import requests
from anthropic import Anthropic

TWITTERAPI_KEY = "your_key"

def get_user_timeline(username, max_results=10):
    response = requests.get(
        f"https://api.twitterapi.io/twitter/user/last_tweets",
        params={"userName": username, "count": max_results},
        headers={"X-API-Key": TWITTERAPI_KEY}
    )
    return response.json()["tweets"]

# Claude 분석 동일
```

#### 방안 C: Claude MCP 서버 통합 (최고 편의성)

```bash
# .mcp.json 설정 후 Claude Code에서 자연어로:
# "karpathy의 최근 트윗에서 에이전트 관련 내용 요약해줘"
```

### 2.7 Nitter 스크래핑은 비추천

2025년 기준 Nitter 상태:
- **40% 실패율** (로드 테스트)
- 대부분 공개 인스턴스 차단됨
- 운영에 실제 계정 풀 + 프록시 필수
- **결론**: 개인 실험 수준만 가능, 프로덕션 부적합

---

## 3부. 자율 연구 에이전트 통합 설계

### 3.1 두 입력 채널을 기존 설계에 연결

기존 `auto_research` 에이전트에 두 채널을 추가하면:

```
[입력 채널 1: 논문 PDF]
paper-search-mcp → 검색
  ↓
arxiv-latex-mcp → LaTeX 원본 로드
  ↓
pymupdf4llm-mcp → PDF → Markdown
  ↓
L0/L1/L2 생성 → knowledge.db papers 테이블

[입력 채널 2: X 타임라인]
Tweepy/TwitterAPI.io → AI 거물 계정 타임라인
  ↓
Claude Haiku → 요약 + 키워드 추출
  ↓
arXiv 검색 → 관련 논문 발견 → 채널 1로 연결

[메인 루프]
research_agent: 두 채널의 입력을 받아 새 논문 생성
pair_compare_agent: pairwise 평가
reflector_agent: 메모리 갱신
```

**X → 논문 자동 발굴 파이프라인**:
```
karpathy가 "새 논문 X가 흥미롭다" 트윗
  ↓
트윗 텍스트에서 arXiv ID 또는 논문 제목 추출
  ↓
paper-search-mcp로 논문 자동 검색
  ↓
L0/L1 생성 → knowledge.db 시드
```

이 파이프라인은 **콜드 스타트 문제**(이슈 3)를 해결한다. AI 연구자들이 언급한 논문이 자동으로 시드 데이터가 된다.

### 3.2 비용 및 구현 우선순위

| 단계 | 방법 | 비용 | 구현 난이도 |
|---|---|---|---|
| **즉시** | arXiv 논문 MCP 3종 설정 | 무료 | ⭐ (쉬움) |
| **단기** | TwitterAPI.io + Tweepy 파이프라인 | $5~50/월 | ⭐⭐ |
| **중기** | X MCP 서버 → Claude 자연어 쿼리 | $200/월 | ⭐⭐⭐ |
| **장기** | X → arXiv 자동 발굴 파이프라인 | $5~200/월 | ⭐⭐⭐⭐ |

---

## 4부. 풀린 이슈 / 안 풀린 이슈

### 이 조사로 새로 풀린 이슈

**이슈 3 (콜드 스타트) → 부분 해결**:
- `paper-search-mcp`로 arXiv에서 관련 논문 자동 시드 수집 가능
- X 타임라인에서 AI 거물이 언급한 논문 자동 발굴 가능

**이슈 6 (인터넷 검색 품질) → 보완됨**:
- 논문 PDF 직접 파싱 > 웹 검색 요약 (품질 훨씬 높음)
- arXiv LaTeX 원본 > PDF 파싱 (수식 정확도)
- Semantic Scholar citation_count 활용

### 새로 발생한 이슈

**이슈 신규 A: X API 비용**
- 읽기 기능에 최소 $200/월(공식) 또는 $5~50/월(써드파티)
- 써드파티 안정성 불확실

**이슈 신규 B: 트위터 정보의 노이즈**
- AI 거물들의 트윗 = 논쟁, 개인 의견, 잡담 포함
- 연구 관련 신호를 추출하는 필터 필요
- 권장: Claude Haiku로 "연구 관련성" 분류 후 arXiv 검색 연결

---

## 결론

**논문 PDF 접근**은 즉시, 무료로 구현 가능하다. `paper-search-mcp` + `arxiv-latex-mcp` + `pymupdf4llm-mcp` 3종 조합이 2026년 현재 최선이다. 이 조합은 기존 `auto_research` 설계의 콜드 스타트 문제를 해결하고, L0/L1/L2 계층화 메모리에 직접 연결된다.

**X 정보 탐색봇**은 조건부로 가능하다. 자동 팔로우는 정책 위반이므로 불가하지만, **특정 계정 타임라인 읽기 → Claude 분석 → arXiv 연결** 파이프라인은 $5~200/월 비용으로 구현 가능하다. 트위터가 가장 빠른 AI 소식 채널이라는 점에서, X 타임라인 → 논문 자동 발굴 파이프라인은 자율 연구 에이전트의 핵심 입력 채널이 될 수 있다.

---

## 참고 자료

### 논문 PDF 관련
- [paper-search-mcp](https://github.com/openags/paper-search-mcp) — 다중소스 통합
- [arxiv-latex-mcp](https://github.com/takashiishida/arxiv-latex-mcp) — LaTeX 원본 파싱
- [pymupdf4llm-mcp](https://github.com/pymupdf/pymupdf4llm-mcp) — PDF→Markdown 최속
- [docling-mcp](https://github.com/docling-project/docling-mcp) — 복잡 레이아웃
- [blazickjp/arxiv-mcp-server](https://github.com/blazickjp/arxiv-mcp-server) — arXiv 전용
- [arxiv.py](https://github.com/lukasschwab/arxiv.py) — Python 라이브러리
- [arXiv MCP at MCP Servers](https://mcpservers.org/servers/openags/paper-search-mcp)

### X/Twitter 관련
- [X API Rate Limits](https://docs.x.com/x-api/fundamentals/rate-limits)
- [Tweepy 공식 문서](https://docs.tweepy.org/en/stable/)
- [TwitterAPI.io](https://twitterapi.io/)
- [DataWhisker/x-mcp-server](https://github.com/DataWhisker/x-mcp-server)
- [0xGval/twitter-X-mcp-server](https://github.com/0xGval/twitter-X-mcp-server)
- [ClaudeLog: Twitter MCP](https://claudelog.com/claude-code-mcps/twitter-mcp/)
