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
from app.core.logging import get_logger
from app.providers.intl import INTL_CITIES, ORIGIN_AIRPORT, supports_intl, to_krw

logger = get_logger(__name__)

OFFER_URL = "https://api.duffel.com/air/offer_requests"
TIMEOUT = 40.0
NUM_DATES = 4  # 조회할 출발일 수 (날짜별 카드용)
DEPART_OFFSET = 30  # 오늘로부터 며칠 뒤부터
PER_DATE = 3  # 날짜별 표시할 항공편 수

_CACHE: dict[str, dict] = {}


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {get_settings().duffel_api_key}",
        "Duffel-Version": "v2",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _dates(n: int) -> list[str]:
    """오늘+OFFSET 부터 n일치 ISO 날짜."""
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


def _offers(dest: str, dep_date: str) -> list[dict]:
    """단일 출발일의 offer 목록. 실패 시 []."""
    try:
        r = httpx.post(
            OFFER_URL,
            headers=_headers(),
            params={"return_offers": "true"},
            json={"data": {
                "slices": [{"origin": ORIGIN_AIRPORT, "destination": dest, "departure_date": dep_date}],
                "passengers": [{"type": "adult"}],
                "cabin_class": "economy",
            }},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return r.json()["data"].get("offers", [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Duffel offers 실패(%s %s): %s", dest, dep_date, exc)
        return []


def search_flights(city: str, limit: int | None = None) -> dict | None:
    """해외 도시행 날짜별 항공편을 flights 스키마로 반환."""
    meta = INTL_CITIES.get(city)
    if not meta or not get_settings().has_duffel:
        return None
    if city in _CACHE:
        return _CACHE[city]

    dest = meta["airport"]
    duration = ""
    date_prices = []
    for dep in _dates(NUM_DATES):
        offers = _offers(dest, dep)
        if not offers:
            continue
        cheapest = sorted(offers, key=lambda o: float(o["total_amount"]))[:PER_DATE]
        flights = []
        for o in cheapest:
            segs = o["slices"][0]["segments"]
            flights.append({
                "airline": o["owner"]["name"],
                "dep": segs[0]["departing_at"][11:16],
                "arr": segs[-1]["arriving_at"][11:16],
                "price": to_krw(o["total_amount"]),
            })
        if not duration:
            duration = _fmt_duration(cheapest[0]["slices"][0].get("duration"))
        date_prices.append({"date": dep, "lowest": min(f["price"] for f in flights), "flights": flights})

    if not date_prices:
        return None
    result = {
        "route_key": f"{ORIGIN_AIRPORT}-{dest}",
        "route": f"인천 → {city}",
        "duration": duration or "약 5시간",
        "date_prices": date_prices,
    }
    logger.info("Duffel flights[%s] %d일치", city, len(date_prices))
    _CACHE[city] = result
    return result


class DuffelFlights:
    """해외 항공 provider (base.Provider 규약). fetch는 flights dict 반환."""

    name = "duffel.flights"

    def supports(self, city: str) -> bool:
        return supports_intl(city) and get_settings().has_duffel

    def fetch(self, city: str, limit: int | None = None) -> dict | None:
        return search_flights(city)
