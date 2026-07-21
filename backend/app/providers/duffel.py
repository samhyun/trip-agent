"""Duffel provider — 해외 항공.

인천(ICN) → 해외 도시 공항의 날짜별 항공편을 조회해, mock(`flights.json`)과 동일한
flights 스키마({route_key, route, duration, date_prices})로 정규화한다. 날짜별 최저가 카드용으로
여러 출발일을 조회한다. `DUFFEL_API_KEY`(.env)가 없거나 실패하면 None → mock 폴백.

인증: `Authorization: Bearer` + `Duffel-Version` 헤더. 요금은 USD → KRW 변환.
"""

import re
from datetime import date, timedelta

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger, redact
from app.providers.intl import INTL_CITIES, ORIGIN_AIRPORT, supports_intl, to_krw

logger = get_logger(__name__)

OFFER_URL = "https://api.duffel.com/air/offer_requests"
TIMEOUT = 40.0
NUM_DATES = 4  # 조회할 출발일 수 (날짜별 카드용)
DEPART_OFFSET = 30  # 오늘로부터 며칠 뒤부터
PER_DATE = 5  # 날짜별 표시할 항공편 수 ('더보기'용으로 넉넉히)

_CACHE: dict[tuple[str, str], dict] = {}  # (도시, 시작일) → 결과


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {get_settings().duffel_api_key}",
        "Duffel-Version": "v2",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _dates(n: int, start: str | None = None) -> list[str]:
    """출발일 n일치 ISO 날짜. start(YYYY-MM-DD)가 유효한 미래면 그 날부터, 아니면 오늘+OFFSET부터."""
    base = None
    if start:
        try:
            base = date.fromisoformat(start)
        except ValueError:
            base = None
    if base is None or base < date.today():  # 과거·미지정 날짜 방어 (Duffel은 과거 출발일 거부)
        base = date.today() + timedelta(days=DEPART_OFFSET)
    return [(base + timedelta(days=i)).isoformat() for i in range(n)]


def _fmt_duration(iso: str | None) -> str:
    """ISO8601 기간('PT5H30M') → '약 5시간 30분'."""
    if not iso:
        return ""
    m = re.search(r"PT(?:(\d+)H)?(?:(\d+)M)?", iso)
    if not m:
        return ""
    h, mi = m.group(1), m.group(2)
    parts = []
    if h:
        parts.append(f"{h}시간")
    if mi:
        parts.append(f"{mi}분")
    return "약 " + " ".join(parts) if parts else ""


def _offers(dest: str, dep_date: str, return_date: str | None) -> list[dict]:
    """왕복(ICN→dest→ICN) offer 목록. return_date 없으면 편도. 실패 시 []."""
    slices = [{"origin": ORIGIN_AIRPORT, "destination": dest, "departure_date": dep_date}]
    if return_date:
        slices.append({"origin": dest, "destination": ORIGIN_AIRPORT, "departure_date": return_date})
    try:
        r = httpx.post(
            OFFER_URL,
            headers=_headers(),
            params={"return_offers": "true"},
            json={"data": {"slices": slices, "passengers": [{"type": "adult"}], "cabin_class": "economy"}},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return r.json()["data"].get("offers", [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Duffel offers 실패(%s %s~%s): %s", dest, dep_date, return_date, redact(exc))
        return []


def roundtrip(city: str, dep_date: str | None, return_date: str | None) -> dict | None:
    """해외 도시행 왕복 항공편(가는 편+오는 편이 한 옵션). 지정 날짜로 실제 조회. 실패 시 None."""
    meta = INTL_CITIES.get(city)
    if not meta or not meta.get("airport") or not get_settings().has_duffel:
        return None  # 공항코드 미해석(자동 해석 실패) 시 항공 조회 생략
    dep = _dates(1, dep_date)[0]  # 과거·미지정 방어 포함
    ret = _dates(1, return_date)[0] if return_date else None
    cache_key = (city, dep, ret or "")
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    dest = meta["airport"]
    offers = _offers(dest, dep, ret)
    if not offers:
        return None
    cheapest = sorted(offers, key=lambda o: float(o["total_amount"]))[:PER_DATE]
    flights = []
    for o in cheapest:
        slices = o["slices"]
        out = slices[0]["segments"]
        opt = {
            "air": o["owner"]["name"],
            "outDep": out[0]["departing_at"][11:16],
            "outArr": out[-1]["arriving_at"][11:16],
            "price": to_krw(o["total_amount"]),  # 왕복 총액
        }
        if len(slices) > 1:  # 오는 편
            inb = slices[1]["segments"]
            opt["inDep"] = inb[0]["departing_at"][11:16]
            opt["inArr"] = inb[-1]["arriving_at"][11:16]
        flights.append(opt)

    result = {"route": f"인천 ↔ {city}", "depDate": dep, "returnDate": ret, "flights": flights}
    logger.info("Duffel 왕복[%s] %d옵션 (%s~%s)", city, len(flights), dep, ret)
    _CACHE[cache_key] = result
    return result
