"""명소 대표 사진 (Wikipedia REST summary).

명소명(영문)으로 Wikipedia 대표 썸네일 URL을 가져온다. API 키가 필요 없고 https 이미지라
프론트 카드에 바로 쓸 수 있다. Geoapify 명소엔 사진이 없어, 이 모듈로 보강한다.
실패/없음은 None → 카드가 그라디언트 폴백을 쓴다. 프로세스 내 캐시로 재조회를 막는다.
"""

from urllib.parse import quote

import httpx

from app.core.logging import get_logger, redact

logger = get_logger(__name__)

SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/"
TIMEOUT = 4.0  # 명소마다 직렬 조회 → 최악 지연 억제
# Wikipedia REST는 User-Agent 없으면 403 → 식별 UA 필수
_HEADERS = {"accept": "application/json", "User-Agent": "trip-agent/1.0 (study demo)"}

_CACHE: dict[str, str | None] = {}
_CACHE_MAX = 1000  # 임의 명소 누적으로 메모리 무한 증가 방지(초과 시 비움)


def photo_for(name: str) -> str | None:
    """명소명(영문) → 대표 썸네일 https URL. 없거나 실패 시 None."""
    if not name:
        return None
    if name in _CACHE:
        return _CACHE[name]
    url: str | None = None
    try:
        r = httpx.get(
            SUMMARY_URL + quote(name.strip().replace(" ", "_"), safe=""),  # ?,#,/ 등 인코딩
            headers=_HEADERS,
            timeout=TIMEOUT,
            follow_redirects=True,
        )
        if r.status_code == 200:
            d = r.json()
            thumb = (d.get("thumbnail") or {}).get("source")
            if isinstance(thumb, str) and thumb.startswith("https://"):
                url = thumb
    except Exception as exc:  # noqa: BLE001 - 실패는 폴백(그라디언트)
        logger.warning("photo_for 실패(%s): %s", name, redact(exc))
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.clear()
    _CACHE[name] = url
    return url
