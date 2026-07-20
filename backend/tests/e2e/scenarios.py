"""Trip Agent E2E 시나리오 테스트 (API 레벨).

실행 중인 백엔드(localhost:8000)에 실제 HTTP 요청을 보내 주요 기능을 자동 검증하고 리포트한다.
실 provider(TourAPI·Geoapify·LiteAPI·Duffel·OpenWeather·Wikipedia)와 LLM까지 태우는 통합 테스트라
mock이 아닌 실데이터 흐름을 확인한다. (단위 테스트가 아니라 서버가 떠 있어야 함)

실행:
    # 1) 백엔드 기동 (별도 터미널)
    cd backend && .venv/bin/uvicorn app.main:app --reload
    # 2) 시나리오 실행
    cd backend && .venv/bin/python tests/e2e/scenarios.py

포함: 인증/IDOR · 목적지 추출(정정·오타·미지원) · 국내/해외(큐레이션) 계획 · FAQ(RAG) ·
결제 영속화 · SSE 스트리밍 · 해외 임의 도시 자동해석 · 사진/지도/날씨 · 멀티 목적지 동선(A/B).
"""
import time

import httpx

BASE = "http://localhost:8000"
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f"  — {detail}" if detail else ""))


def chat(msg, token=None, conv=None):
    h = {"Authorization": f"Bearer {token}"} if token else {}
    r = httpx.post(f"{BASE}/chat", json={"message": msg, "conversation_id": conv}, headers=h, timeout=180)
    return r.json() if r.status_code == 200 else {"_status": r.status_code}


def turn_types(resp):
    return [t.get("type") for t in resp.get("turns", [])]


def card(resp, ctype):
    """응답 turns에서 특정 카드 타입의 payload(첫 개)를 반환."""
    for t in resp.get("turns", []):
        if t.get("type") == ctype:
            return t.get("payload") or {}
    return None


def dest_city(resp):
    p = card(resp, "destination_carousel")
    return p.get("city") if p else None


print("\n========== 1. 인증 ==========")
email = f"scn{int(time.time())}@trip.com"
r = httpx.post(f"{BASE}/auth/register", json={"email": email, "password": "pass1234", "name": "시나리오"}, timeout=20)
token = r.json().get("access_token")
check("A1 회원가입 → 토큰 발급", r.status_code == 200 and token)
check("A2 중복 가입 → 409", httpx.post(f"{BASE}/auth/register", json={"email": email, "password": "x123456", "name": "중복"}, timeout=20).status_code == 409)
check("A3 로그인 성공", httpx.post(f"{BASE}/auth/login", json={"email": email, "password": "pass1234"}, timeout=20).status_code == 200)
check("A4 잘못된 비번 → 401", httpx.post(f"{BASE}/auth/login", json={"email": email, "password": "wrong"}, timeout=20).status_code == 401)
me = httpx.get(f"{BASE}/auth/me", headers={"Authorization": f"Bearer {token}"}, timeout=20)
check("A5 /auth/me → 유저", me.status_code == 200 and me.json().get("email") == email)

# IDOR: B는 A의 대화에 접근 불가
email_b = f"scnb{int(time.time())}@trip.com"
token_b = httpx.post(f"{BASE}/auth/register", json={"email": email_b, "password": "pass1234", "name": "B"}, timeout=20).json().get("access_token")
conv_a = chat("안녕", token=token).get("conversation_id")
resp_b = chat("안녕", token=token_b, conv=conv_a)  # B가 A의 conv_id로 시도
b_conv = resp_b.get("conversation_id")
# IDOR 차단은 두 방식 모두 정상: (1) B에게 새 대화 발급(현 구현) 또는 (2) 접근 거부(401/403/404).
# 실패는 B가 A의 대화(conv_a)를 그대로 받는 경우.
idor_ok = (b_conv and b_conv != conv_a) or resp_b.get("_status") in (401, 403, 404)
check("A6 IDOR 차단 (타 유저 대화 접근 불가)", idor_ok and b_conv != conv_a,
      f"A={str(conv_a)[:8]} B받은={str(b_conv)[:8]} status={resp_b.get('_status')}")

print("\n========== 2. 대화 / 목적지 추출 ==========")
r_low = chat("여행 가고 싶어")
check("D1 정보부족 → 되묻기(카드 없음)", "destination_carousel" not in turn_types(r_low) and r_low.get("agent") in ("chat_reply", "coordinator"))
r_fix = chat("제주 갈까 하다가 제주 말고 부산으로 2박3일 2명 인기 명소 보여줘")
check("D2 목적지 정정 (제주 말고 부산)", dest_city(r_fix) == "부산", f"추출 도시={dest_city(r_fix)}")
r_typo = chat("부사난 2박3일 2명 명소 보여줘")
check("D3 오타 '부사난' → 부산", dest_city(r_typo) == "부산", f"추출 도시={dest_city(r_typo)}")
# 국내 비지원 도시(대전)는 해외 provider로 오라우팅하지 않고 미지원 안내 (KR 차단)
r_unsup = chat("대전 2박3일 2명 여행 계획 짜줘")
ans_unsup = (r_unsup.get("answer") or "") + " ".join(t.get("content") or "" for t in r_unsup.get("turns", []))
check("D4 국내 비지원(대전) → 미지원 안내", ("대전" in ans_unsup or "지원" in ans_unsup) and "destination_carousel" not in turn_types(r_unsup), f"응답: {ans_unsup[:40]}")

print("\n========== 3. 계획 (국내/해외 큐레이션) ==========")
r_jeju = chat("제주 2박3일 2명 명소랑 숙소 보여줘")
tt = turn_types(r_jeju)
pj = card(r_jeju, "destination_carousel") or {}
check("P1 제주 명소 카드", "destination_carousel" in tt, f"turns={tt}")
check("P1 제주 명소 실사진 URL", any(i.get("image") for i in pj.get("items", [])))
check("P1 제주 지도(mapPath)", bool(pj.get("mapPath")))
check("P1 제주 날씨(weather)", bool(pj.get("weather")), f"날씨={pj.get('weather')}")
check("P1 제주 숙소 카드", "hotel_results" in tt)
r_cebu = chat("세부 3박4일 2명 항공이랑 숙소 예약해줘")
tt2 = turn_types(r_cebu)
check("P2 세부 항공 카드 (Duffel)", "flight_results" in tt2, f"turns={tt2}")
check("P2 세부 숙소 카드 (LiteAPI)", "hotel_results" in tt2)

print("\n========== 4. FAQ (RAG) ==========")
r_f1 = chat("예약 취소하면 환불돼? 얼마나 걸려?")
check("F1 FAQ 답변 + 출처표시", r_f1.get("agent") == "faq" and "참고 FAQ" in r_f1.get("answer", ""))
r_f2 = chat("로그인이 안 돼요 비밀번호 잊어버렸어요")
check("F2 신규 FAQ (로그인/계정)", r_f2.get("agent") == "faq" and ("비밀번호" in r_f2.get("answer", "") or "가입" in r_f2.get("answer", "")))
r_f3 = chat("개인정보랑 결제정보 안전한가요?")
check("F3 신규 FAQ (개인정보)", r_f3.get("agent") == "faq")

print("\n========== 5. 결제 → 영속화 (로그인 유저) ==========")
chat("제주 2박3일 2명 여행 계획 짜줘. 명소랑 항공·숙소 예약까지", token=token, conv=conv_a)
chat("대한항공 07:30 항공편으로 예약할게요", token=token, conv=conv_a)
chat("제주신라호텔 숙소로 예약할게요", token=token, conv=conv_a)
r_pay = chat("결제까지 진행할게요", token=token, conv=conv_a)
check("E1 결제 확정 카드", "confirmation" in turn_types(r_pay))
trips = httpx.get(f"{BASE}/me/trips", headers={"Authorization": f"Bearer {token}"}, timeout=20).json()
if isinstance(trips, list) and trips:  # 비-list 오류응답(dict 등)에서 크래시 방지
    e2_detail = f"여행 {len(trips)}건, 예약항목 {len(trips[0].get('bookings', []))}개"
else:
    e2_detail = f"응답={trips}"
check("E2 내 예약 저장됨 (/me/trips)", isinstance(trips, list) and len(trips) >= 1, e2_detail)

print("\n========== 6. 스트리밍 (SSE) ==========")
# 되묻기/추천 같은 텍스트 응답은 토큰 단위로 스트리밍된다(chat_reply). ('명소 보여줘'류는 카드라 스트림 없음)
deltas = 0
done = False
with httpx.stream("POST", f"{BASE}/chat/stream", json={"message": "동남아 여행지 짧게 추천해줘"}, timeout=90) as s:
    for line in s.iter_lines():
        if '"text_delta"' in line:
            deltas += 1
        if '"type": "done"' in line:
            done = True
check("S1 토큰 스트리밍 (text_delta 다수)", deltas >= 5, f"델타 {deltas}개")
check("S2 스트림 정상 종료 (done)", done)

print("\n========== 7. 해외 임의 도시 자동해석 (+사진/지도/날씨) ==========")
# 큐레이션 안 된 도시(랑카위)를 대화로 정하면 영문명→좌표·공항 자동해석 후 실데이터 조회
r_lang = chat("랑카위 3박4일 2명 명소랑 항공·숙소 예약해줘")
ttl = turn_types(r_lang)
pl = card(r_lang, "destination_carousel") or {}
check("R1 자동해석 랑카위 명소 카드", "destination_carousel" in ttl, f"turns={ttl}")
check("R2 자동해석 랑카위 실사진(Wikipedia)", any(i.get("image") for i in pl.get("items", [])))
check("R3 자동해석 랑카위 지도(mapPath)", bool(pl.get("mapPath")))
check("R4 자동해석 랑카위 날씨(weather)", bool(pl.get("weather")), f"날씨={pl.get('weather')}")
check("R5 자동해석 랑카위 항공(Duffel 자동공항)", "flight_results" in ttl)
check("R6 자동해석 랑카위 숙소(LiteAPI)", "hotel_results" in ttl)
r_dn = chat("다낭 2박3일 명소 보여줘")
check("R7 자동해석 다낭 명소 카드", "destination_carousel" in turn_types(r_dn), f"도시={dest_city(r_dn)}")

print("\n========== 8. 멀티 목적지 동선 (A/B) ==========")
r_multi = chat("세부랑 보홀 둘 다 4박5일 일정 짜줘")
ttm = turn_types(r_multi)
rp = card(r_multi, "route_plan") or {}
routes = rp.get("routes") or {}
check("M1 멀티도시 route_plan 카드", "route_plan" in ttm, f"turns={ttm}")
check("M2 A/B 동선 두 안 존재", bool(routes.get("A", {}).get("label")) and bool(routes.get("B", {}).get("label")),
      f"A={routes.get('A', {}).get('label')} / B={routes.get('B', {}).get('label')}")
check("M3 이동수단(transferLabel) 존재", bool(routes.get("A", {}).get("transferLabel")),
      f"transfer={routes.get('A', {}).get('transferLabel')}")
check("M4 비교 스트립(compareStrip)", bool((rp.get("compareStrip") or {}).get("lastDayAirport")))
r_single = chat("부산만 2박3일 일정 짜줘")
check("M5 단일 도시는 route 스킵", "route_plan" not in turn_types(r_single))

print("\n" + "=" * 40)
passed = sum(1 for _, ok, _ in results if ok)
print(f"결과: {passed}/{len(results)} 통과")
for name, ok, detail in results:
    if not ok:
        print(f"  ❌ 실패: {name} {detail}")
