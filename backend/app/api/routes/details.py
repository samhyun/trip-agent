"""상세 조회 라우트 — 카드에서 ID로 호텔 상세를 조회한다."""

import math

import httpx
from fastapi import APIRouter, HTTPException, Query, Response

from app.core.logging import get_logger, redact
from app.providers import geoapify
from app.services import travel_service as ts

logger = get_logger(__name__)
router = APIRouter(prefix="/details", tags=["details"])

_MAP_MAX_POINTS = 20  # 마커 상한(URL 길이·남용 방지)
_MAP_CACHE: dict[str, tuple[bytes, str]] = {}  # 정규화 좌표키 → (이미지, content-type)
_MAP_CACHE_MAX = 200  # 서버 캐시 상한(동일 좌표 재호출·쿼터 절약, 초과 시 비움)


@router.get("/hotel")
def hotel_detail(id: str = Query(..., description="호텔 ID"), city: str = Query(..., description="도시")):
    """호텔 상세 (사진·편의시설·주소·체크인아웃·설명). 국내=TourAPI, 해외=LiteAPI."""
    detail = ts.get_hotel_detail(city, id)
    if not detail:
        raise HTTPException(status_code=404, detail="상세 정보를 찾지 못했어요.")
    logger.info("hotel_detail [city=%s id=%s] 사진 %d장", city, id, len(detail.get("images", [])))
    return detail


@router.get("/map")
def static_map(pts: str = Query(..., description="'lat,lng;lat,lng ...' 명소 좌표")):
    """명소 마커 정적 지도 이미지 프록시. Geoapify 키를 프론트에 노출하지 않도록 백엔드 경유."""
    points: list[tuple[float, float]] = []
    for pair in pts.split(";")[:_MAP_MAX_POINTS]:
        try:
            lat_s, lng_s = pair.split(",")
            lat, lng = float(lat_s), float(lng_s)
        except ValueError:
            continue  # 잘못된 좌표 쌍은 건너뜀
        if not (math.isfinite(lat) and math.isfinite(lng)):
            continue  # nan/inf 방어
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            continue  # 위·경도 범위 밖 방어
        points.append((lat, lng))
    if not points:
        raise HTTPException(status_code=404, detail="지도를 생성하지 못했어요.")

    cache_key = ";".join(f"{la:.5f},{lo:.5f}" for la, lo in points)  # 정규화 좌표키
    hit = _MAP_CACHE.get(cache_key)
    if hit:  # 동일 좌표 재요청 → 서버 캐시 반환(Geoapify 재호출·쿼터 절약)
        content, ctype = hit
    else:
        url = geoapify.static_map_url(points)
        if not url:
            raise HTTPException(status_code=404, detail="지도를 생성하지 못했어요.")
        try:
            r = httpx.get(url, timeout=15.0)
            r.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            logger.warning("static map fetch 실패: %s", redact(exc))
            raise HTTPException(status_code=502, detail="지도를 불러오지 못했어요.")
        content = r.content
        ctype = r.headers.get("content-type", "image/jpeg")
        if len(_MAP_CACHE) >= _MAP_CACHE_MAX:
            _MAP_CACHE.clear()
        _MAP_CACHE[cache_key] = (content, ctype)
    return Response(
        content=content,
        media_type=ctype,
        headers={"Cache-Control": "public, max-age=86400"},  # 좌표 동일하면 하루 캐시
    )
