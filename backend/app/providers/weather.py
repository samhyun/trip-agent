"""OpenWeather 현재 날씨.

목적지 좌표(또는 도시명)로 현재 기온·날씨를 조회해 목적지 카드에 곁들인다.
`OPENWEATHER_API_KEY`(.env)가 없거나 실패하면 None → 프론트가 날씨 칩을 숨긴다.
좌표 기준 캐시로 재조회를 막는다.
"""

import time

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger, redact

logger = get_logger(__name__)

WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
TIMEOUT = 8.0

# OpenWeather 아이콘 코드 앞 2자리 → 이모지
_ICON = {
    "01": "☀️", "02": "🌤️", "03": "⛅", "04": "☁️",
    "09": "🌧️", "10": "🌦️", "11": "⛈️", "13": "❄️", "50": "🌫️",
}

_CACHE: dict[str, tuple[float, dict | None]] = {}  # key → (만료시각, 값)
_CACHE_MAX = 500  # 좌표 누적으로 메모리 무한 증가 방지(초과 시 비움)
_TTL = 1800  # '현재 날씨' 캐시 유효 30분(오래된 값 반환 방지)


def _cache_get(key: str) -> tuple[bool, dict | None]:
    """(적중 여부, 값). 만료됐으면 미적중."""
    hit = _CACHE.get(key)
    if hit and time.time() < hit[0]:
        return True, hit[1]
    return False, None


def _cache_put(key: str, value: dict | None) -> None:
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.clear()
    _CACHE[key] = (time.time() + _TTL, value)


def current(lat: float | None = None, lon: float | None = None, city_en: str | None = None) -> dict | None:
    """현재 날씨 {temp, desc, emoji}. 좌표 우선, 없으면 도시명. 실패 시 None."""
    s = get_settings()
    if not s.has_openweather:
        return None
    params = {"units": "metric", "lang": "kr", "appid": s.openweather_api_key}
    if lat is not None and lon is not None:
        key = f"{round(lat, 2)},{round(lon, 2)}"
        params["lat"], params["lon"] = lat, lon
    elif city_en:
        key = city_en
        params["q"] = city_en
    else:
        return None
    cached, value = _cache_get(key)
    if cached:
        return value

    try:
        r = httpx.get(WEATHER_URL, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        d = r.json()
    except Exception as exc:  # noqa: BLE001 - 실패는 프론트에서 숨김
        logger.warning("weather 실패(%s): %s", key, redact(exc))
        _cache_put(key, None)
        return None

    temp = (d.get("main") or {}).get("temp")
    if not isinstance(temp, (int, float)):  # temp 누락/비정상(null 등) → 날씨 칩 생략
        _cache_put(key, None)
        return None
    w = (d.get("weather") or [{}])[0]
    icon = (w.get("icon") or "")[:2]
    result = {
        "temp": round(temp),
        "desc": w.get("description", ""),
        "emoji": _ICON.get(icon, "🌡️"),
    }
    _cache_put(key, result)
    return result
