# Trip Agent 문서

여행지 조회 → 일정 플랜 → 예약 → (더미)결제까지 이어주는 대화형 여행 에이전트.
LangGraph supervisor 멀티에이전트 구조.

> 이어드림스쿨 8주차 개인 프로젝트 (2026-07-16 ~ 2026-07-22)
> 모든 프로젝트 문서는 이 `docs/`에서 로컬 관리한다.

## 문서 목록

| 문서 | 내용 |
|---|---|
| [design.md](design.md) | 시스템 설계 — 아키텍처(그래프·노드), 데이터 계층, 디렉토리 구조, API, 개발 접근, 위험 |
| [data-sources.md](data-sources.md) | 데이터 API 조사·비교·선정 — TourAPI / OpenTripMap / Duffel / LiteAPI, 무료 조건, provider 라우팅+폴백 |
| [ui-design.md](ui-design.md) | Chat-first UI 디자인 러프안 — 화면 구성, 메시지 타입별 리치 카드, 대화 흐름, 컴포넌트 목록 |

## 핵심 결정 요약

| 항목 | 결정 |
|---|---|
| 아키텍처 | LangGraph supervisor 멀티에이전트 (coordinator·planner·supervisor + 워커 4종) |
| LLM | OpenAI (gpt-4o-mini 기본, env 교체 가능) |
| UI | Vite + React 챗 UI + FastAPI |
| 데이터 (하이브리드) | 명소=OpenTripMap · 국내=TourAPI · 해외항공=Duffel · 해외호텔=LiteAPI · 전구간 mock 폴백 |
| 예약·결제 | 더미(mock) 처리 + 확정서 발급 |

## 개발 상태

- [x] 데이터 소스 조사·선정
- [x] 아키텍처·디렉토리 설계
- [ ] 프로젝트 골격 스캐폴딩 ← *진행 중*
- [ ] 그래프·노드 구현 (mock)
- [ ] 프론트엔드 챗 UI
- [ ] 실 provider 연동
- [ ] 더미 결제·데모 정리
