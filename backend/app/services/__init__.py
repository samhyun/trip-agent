"""여행 도메인 서비스 (데이터 조회 + provider 선택).

툴은 데이터 출처를 모른 채 이 서비스를 호출한다. 지금은 mock JSON을 읽고,
이후 단계에서 실 provider(TourAPI·OpenTripMap·Duffel·LiteAPI)를 붙여
"실 API 성공 → 반환 / 실패·키없음 → mock 폴백"으로 확장한다.
"""

from app.services import travel_service

__all__ = ["travel_service"]
