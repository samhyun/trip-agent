"""상세 조회 라우트 — 카드에서 ID로 호텔 상세를 조회한다."""

from fastapi import APIRouter, HTTPException, Query

from app.core.logging import get_logger
from app.services import travel_service as ts

logger = get_logger(__name__)
router = APIRouter(prefix="/details", tags=["details"])


@router.get("/hotel")
def hotel_detail(id: str = Query(..., description="호텔 ID"), city: str = Query(..., description="도시")):
    """호텔 상세 (사진·편의시설·주소·체크인아웃·설명). 국내=TourAPI, 해외=LiteAPI."""
    detail = ts.get_hotel_detail(city, id)
    if not detail:
        raise HTTPException(status_code=404, detail="상세 정보를 찾지 못했어요.")
    logger.info("hotel_detail [city=%s id=%s] 사진 %d장", city, id, len(detail.get("images", [])))
    return detail
