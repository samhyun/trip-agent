# Trip Agent 🧳

여행지 정보를 조회해 사용자의 일정에 맞춰 플랜을 짜주고, 예약과 (더미) 결제까지
이어주는 대화형 여행 에이전트. LangGraph supervisor 멀티에이전트 구조.

> 이어드림스쿨 8주차 개인 프로젝트 · 설계 문서: [`docs/design.md`](docs/design.md)

## 주요 기능

- 💬 대화로 여행 요청 파악 (목적지·기간·인원·예산)
- 🗺️ 여행지·명소·숙박·액티비티 정보 조회
- 📅 일정에 맞춘 일자별 플랜 생성
- ✈️ 항공·숙소·액티비티 검색 및 예약
- 💳 더미 결제 + 예약 확정서 발급

## 기술 스택

| 구분 | 스택 |
|---|---|
| 백엔드 | Python 3.12, FastAPI, LangGraph, langchain-openai |
| 프론트엔드 | Vite + React |
| LLM | OpenAI (gpt-4o-mini 기본, env 교체 가능) |
| 데이터 | 국내 TourAPI · 해외 Amadeus · JSON mock 폴백 |

## 빠른 시작

### 1. 환경변수 설정
```bash
cp .env.example .env
# .env 를 열어 OPENAI_API_KEY 입력 (그 외 API 키는 없어도 mock 으로 동작)
```

### 2. 백엔드
```bash
cd backend
uv sync                 # 의존성 설치
uv run uvicorn app.main:app --reload --port 8000
```

### 3. 프론트엔드
```bash
cd frontend
npm install
npm run dev             # http://localhost:5173
```

### Makefile 단축 명령
```bash
make install    # 백엔드+프론트 의존성 설치
make backend    # 백엔드 개발 서버
make frontend   # 프론트엔드 개발 서버
make test       # 백엔드 테스트
```

## 프로젝트 구조

```
backend/app/
├── main.py          # FastAPI 진입점
├── api/             # 라우트, 스키마
├── core/            # 설정, 로깅
├── agents/          # 그래프, 상태, LLM, 노드, 프롬프트
├── tools/           # LangChain 툴
├── services/        # 도메인 로직 + provider 선택
├── providers/       # TourAPI, Amadeus, Weather 클라이언트
└── data/            # mock JSON
frontend/src/        # React 챗 UI
```

자세한 아키텍처는 [`docs/design.md`](docs/design.md) 참고.
