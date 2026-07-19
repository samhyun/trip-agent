# Auth UI 디자인 브리프 (Claude Design 전달용)

> Trip Agent에 **로그인·회원가입**을 추가하고 관련 화면을 개선하기 위한 Claude Design 브리프.
> 기존 프로젝트 "Trip Agent"(제주 여행 챗봇 UI)의 디자인 시스템을 그대로 이어간다.

## 1. 배경

Trip Agent는 채팅으로 여행지·항공·숙소를 조회하고 예약하는 **chat-first** 웹앱(React+Vite).
백엔드에 **회원 인증(JWT)**을 붙였고, 로그인 유저의 대화·여행·예약이 계정에 연결된다.
이제 프론트에 로그인/회원가입 UI와 로그인 상태 반영이 필요하다.

## 2. 신규 화면

### 로그인 (Login)
- 필드: 이메일, 비밀번호
- 버튼: "로그인" / 하단 링크 "계정이 없으신가요? 회원가입"
- 에러: "이메일 또는 비밀번호가 올바르지 않습니다." (필드 하단 인라인)

### 회원가입 (Signup)
- 필드: 이름, 이메일, 비밀번호(6자 이상), 비밀번호 확인
- 버튼: "회원가입" / 하단 링크 "이미 계정이 있으신가요? 로그인"
- 인라인 검증: 이메일 형식, 비밀번호 6자 이상, 비밀번호 확인 일치
- 에러: "이미 가입된 이메일입니다." (이메일 필드 하단)

### 형태 (권장)
- **중앙 모달 카드 + 딤 배경** (chat-first라 화면 전환보다 모달이 자연스러움).
- 게스트도 **닫고 그냥 사용 가능**(비로그인 허용). 단 예약 저장·기록은 로그인 유도.
- 로그인/회원가입은 **탭 전환** 또는 링크 토글로 한 모달 안에서 오간다.

## 3. 개선 필요 화면

1. **헤더(Header)** — 현재 우측에 테마 토글만 있음.
   - 비로그인: "로그인" 버튼(우측 상단)
   - 로그인: 유저 이름/이니셜 아바타 + 드롭다운(로그아웃)
2. **"내 여행" 우측 패널(TripSummaryPanel)** — 게스트/로그인 상태 구분.
   - 게스트: "로그인하면 예약과 여행이 저장돼요" CTA
   - 로그인: 유저 인사 + (선택) "내 예약 내역" 진입
3. **(선택) 내 예약 내역** — 로그인 유저의 지난 여행·예약 리스트(드로어/뷰). 예약이 계정에 연결되므로 확장 가능.

## 4. 디자인 시스템 (그대로 유지)

- 브랜드: ✈️ **Trip Agent**, 한국어 UI
- 색(oklch 토큰, 라이트/다크 `data-theme`):
  - `--primary` teal(라이트 `oklch(0.48 0.075 210)`), `--accent` orange, `--success` green
  - `--surface`/`--panel`/`--bg`, `--text`/`--muted`/`--faint`, `--border`
  - 버튼 primary는 `--primary` 배경 + `--primary-ink` 텍스트
- 요소: 둥근 카드(라운드 큼), 소프트 섀도(`--shadow`), 칩 버튼, 부드러운 fade-up 모션
- 다크모드 필수 대응(`data-theme="dark"`), 반응형(모바일: 전체폭 모달)

## 5. 백엔드 API 계약 (연동 기준)

베이스: `VITE_API_BASE_URL`(기본 `http://localhost:8000`). 토큰은 `Authorization: Bearer <token>`.

| 메서드 | 경로 | 요청 body | 응답 | 에러 |
|---|---|---|---|---|
| POST | `/auth/register` | `{email, password, name}` | `{access_token, token_type:"bearer", user:{id,email,name}}` | 409 이메일 중복 |
| POST | `/auth/login` | `{email, password}` | 위와 동일 | 401 자격 오류 |
| GET | `/auth/me` | — (Bearer) | `{id, email, name}` | 401 미인증 |
| POST | `/chat` | `{message, conversation_id}` (+선택 Bearer) | 기존과 동일 | — |

- 성공 시: `access_token`을 localStorage 저장 → 이후 `/chat`·`/auth/me`에 Bearer로 전송.
- `/chat`에 토큰을 실으면 그 대화가 로그인 유저에 연결된다(게스트는 익명).
- 앱 로드 시 저장된 토큰으로 `/auth/me` 호출해 로그인 상태 복원.

## 6. 동작/상태

- 폼 제출 중 로딩(버튼 스피너/비활성), 성공 시 모달 닫고 헤더 갱신.
- 에러는 인라인 메시지, 필드 포커스 유지.
- 로그아웃: 토큰 삭제 → 게스트 상태로.

## 7. 파일 목록

> **원칙**: 기존 Claude Design "Trip Agent" 프로젝트에서 **이어서** 작업하면 디자인 시스템을
> 이미 보유하므로 **아래 참고 파일 재전달은 불필요**하다. Claude Design엔 §8 프롬프트(+연동까지
> 시키면 §5 계약표)만 있으면 된다.

### (A) Claude Design 전달물
- **§8 프롬프트** — 필수
- **§5 API 계약표** — 화면에서 로그인/가입 연동까지 시킬 때만
- (새 프로젝트/새 대화로 시작하는 경우에 한해) `frontend/src/index.css` — 토큰 참고용 1개면 충분

### (B) 통합 시 손댈 코드 (Claude Design 전달물 아님 — 산출물을 React 앱에 붙일 때 작업 계획)
신규 생성
- `frontend/src/components/auth/AuthModal.jsx` — 로그인/회원가입 모달(탭 토글)
- `frontend/src/components/auth/LoginForm.jsx`, `SignupForm.jsx`
- `frontend/src/context/AuthContext.jsx` (또는 `hooks/useAuth.js`) — 토큰·유저 상태
- `frontend/src/lib/auth.js` — register/login/me API 클라이언트

수정 대상
- `frontend/src/components/Header.jsx` — 우측 유저 영역
- `frontend/src/App.jsx` — Auth 상태 주입·모달 마운트
- `frontend/src/lib/api.js` — `/chat`에 Bearer 헤더
- `frontend/src/components/TripSummaryPanel.jsx` — 게스트 CTA

## 8. 붙여넣기용 프롬프트 (Claude Design)

```
Trip Agent(✈️ chat-first 여행 플래닝 웹앱, React+Vite)에 로그인/회원가입 UI를 추가하고 관련 화면을 개선해줘.
기존 "Trip Agent" 디자인 시스템(index.css의 oklch 토큰 — teal --primary, orange --accent, 라이트/다크 data-theme,
둥근 카드, 소프트 섀도, 칩 버튼)을 그대로 이어가고 한국어 UI로.

[신규] 로그인/회원가입을 하나의 중앙 모달(딤 배경)로. 상단 탭 또는 링크로 로그인↔회원가입 전환.
- 로그인: 이메일, 비밀번호 / "로그인" / "회원가입" 링크 / 에러 인라인("이메일 또는 비밀번호가 올바르지 않습니다.")
- 회원가입: 이름, 이메일, 비밀번호(6자+), 비밀번호 확인 / 인라인 검증 / 에러("이미 가입된 이메일입니다.")
- 게스트도 모달을 닫고 사용 가능. 로딩/성공/에러 상태 포함.

[개선]
- 헤더 우측: 비로그인 시 "로그인" 버튼, 로그인 시 이름+이니셜 아바타+로그아웃 드롭다운(테마 토글은 유지).
- 우측 "내 여행" 패널: 게스트에 "로그인하면 예약과 여행이 저장돼요" CTA, 로그인 시 유저 인사.
- (선택) 로그인 유저용 "내 예약 내역" 리스트 뷰.

다크모드와 모바일(전체폭 모달) 반응형 필수. 접근성(라벨/포커스) 고려.
```
