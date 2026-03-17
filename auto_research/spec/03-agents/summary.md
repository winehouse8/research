# 03. 에이전트 모듈

이 폴더는 3개 LLM 에이전트와 SDK 통합 설정을 명세합니다.

## 파일 목록

| 파일 | 설명 |
|------|------|
| `sdk-integration.md` | Claude Agent SDK + OMC 플러그인 통합 + Quality-Enforcement Stop Hooks (Mini-Ralph 패턴) |
| `research-agent.md` | 논문 생성 에이전트 (sonnet, WebSearch/WebFetch, Stop hook 품질 강제) |
| `compare-agent.md` | Pairwise 비교 에이전트 (haiku, position bias 제거, Stop hook 품질 강제) |
| `reflector-agent.md` | Annotation 추출 에이전트 (haiku, 결정론적 작업 분리, Stop hook 품질 강제) |
