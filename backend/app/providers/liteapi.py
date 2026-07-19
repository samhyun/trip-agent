"""LiteAPI provider — 해외 호텔.

해외 도시의 호텔 목록(`/data/hotels`)과 요금(`/hotels/rates`)을 조회해, mock(`hotels.json`)과
동일한 hotel 스키마로 정규화한다. `LITEAPI_API_KEY`(.env)가 없거나 실패하면 None → mock 폴백.

인증: `X-API-Key` 헤더. 요금은 숙박 총액(USD)이라 박수로 나눠 1박가로 환산 후 KRW 변환.
"""

from datetime import date, timedelta

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.providers.intl import INTL_CITIES, supports_intl, to_krw

logger = get_logger(__name__)

BASE_URL = "https://api.liteapi.travel/v3.0"
TIMEOUT = 25.0
NIGHTS = 3  # 요금 조회 기준 박수 (총액 → 1박가 환산용)

_CACHE: dict[tuple[str, int], list[dict]] = {}


def _stay_dates() -> tuple[str, str]:
    """요금 조회용 미래 체크인/체크아웃(오늘+30일, NIGHTS박). 날짜 하드코딩 방지."""
    checkin = date.today() + timedelta(days=30)
    return checkin.isoformat(), (checkin + timedelta(days=NIGHTS)).isoformat()


def _headers() -> dict:
    return {"X-API-Key": get_settings().liteapi_api_key, "Accept": "application/json"}


def _list_hotels(country: str, city_en: str, limit: int) -> list[dict]:
    """도시의 호텔 목록(정적 정보). 실패 시 []."""
    try:
        r = httpx.get(
            f"{BASE_URL}/data/hotels",
            headers=_headers(),
            params={"countryCode": country, "cityName": city_en, "limit": limit},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return r.json().get("data", [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("LiteAPI hotels 실패(%s): %s", city_en, exc)
        return []


def _rate_map(hotel_ids: list[str]) -> dict[str, int]:
    """hotelId → 1박 요금(KRW). 요금 조회 실패 시 빈 dict(→ 데모값 폴백)."""
    if not hotel_ids:
        return {}
    checkin, checkout = _stay_dates()
    try:
        r = httpx.post(
            f"{BASE_URL}/hotels/rates",
            headers={**_headers(), "Content-Type": "application/json"},
            json={
                "hotelIds": hotel_ids,
                "checkin": checkin,
                "checkout": checkout,
                "currency": "USD",
                "guestNationality": "KR",
                "occupancies": [{"adults": 2}],
            },
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        out: dict[str, int] = {}
        for h in r.json().get("data", []):
            total = _min_total_usd(h)
            if total:
                out[h.get("hotelId")] = to_krw(total / NIGHTS)  # 총액 → 1박가
        return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("LiteAPI rates 실패: %s", exc)
        return {}


def _to_float(v) -> float | None:
    """숫자/숫자문자열 → float. 아니면 None (API가 금액을 문자열로 줄 수 있어 방어)."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _min_total_usd(hotel_rate: dict) -> float | None:
    """호텔 요금 응답에서 최저 숙박 총액(USD)."""
    totals: list[float] = []
    for rt in hotel_rate.get("roomTypes", []):
        for rate in rt.get("rates", []):
            for t in (rate.get("retailRate") or {}).get("total", []):
                amt = _to_float(t.get("amount"))
                if amt is not None:
                    totals.append(amt)
    return min(totals) if totals else None


def _demo_price(hid: str) -> int:
    """요금 미조회 시 결정적 데모 1박가(90,000~200,000)."""
    h = sum(ord(c) for c in str(hid))
    return 90000 + (h % 111) * 1000


def _rating5(rating10) -> float | None:
    """LiteAPI 10점 평점 → 5점 스케일."""
    try:
        return round(float(rating10) / 2, 1)
    except (TypeError, ValueError):
        return None


def search_stays(city: str, limit: int = 6) -> list[dict] | None:
    """해외 도시의 호텔을 hotel 스키마로 반환."""
    meta = INTL_CITIES.get(city)
    if not meta or not get_settings().has_liteapi:
        return None
    if (city, limit) in _CACHE:
        return _CACHE[(city, limit)]

    hotels = _list_hotels(meta["country"], meta.get("stay_city", meta["en"]), limit)
    if not hotels:
        return None
    rates = _rate_map([h["id"] for h in hotels if h.get("id")])

    result = []
    for i, h in enumerate(hotels[:limit]):
        hid = h.get("id") or f"{city}-hotel-{i}"
        stars = h.get("stars")
        result.append(
            {
                "id": hid,
                "name": h.get("name", "").strip(),
                "area": h.get("city") or meta["en"],
                "price_per_night": rates.get(hid) or _demo_price(hid),
                "rating": _rating5(h.get("rating")) or 4.3,
                "tags": [f"{stars}성"] if stars else [meta["en"]],
                "gradient": i % 6,
                "lat": h.get("latitude"),
                "lng": h.get("longitude"),
            }
        )
    logger.info("LiteAPI stays[%s] %d개", city, len(result))
    _CACHE[(city, limit)] = result
    return result


class LiteApiStays:
    """해외 호텔 provider (base.Provider 규약)."""

    name = "liteapi.stays"

    def supports(self, city: str) -> bool:
        return supports_intl(city) and get_settings().has_liteapi

    def fetch(self, city: str, limit: int = 6) -> list[dict] | None:
        return search_stays(city, limit)
