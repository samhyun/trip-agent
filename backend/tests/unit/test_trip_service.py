"""trip_service.py 예약 파싱(정규식)·금액 변환 유닛 테스트."""

from decimal import Decimal

from app.services import trip_service


class TestParseSelectedBookings:
    def test_flight_and_hotels_recorded(self):
        text = (
            "대한항공 07:30 항공편으로 예약할게요\n"
            "제주신라 숙소로 예약할게요\n"
            "서귀포롯데 숙소로 예약할게요"
        )
        items = trip_service._parse_selected_bookings(text)
        assert items[0]["type"] == "flight"
        assert "대한항공 07:30" in items[0]["title"]
        hotels = [i["title"] for i in items if i["type"] == "hotel"]
        assert any("제주신라" in h for h in hotels)
        assert any("서귀포롯데" in h for h in hotels)

    def test_latest_flight_used(self):
        text = (
            "아시아나 06:00 항공편으로 예약할게요\n"
            "대한항공 08:00 항공편으로 예약할게요\n"
            "신라스테이 숙소로 예약할게요"
        )
        items = trip_service._parse_selected_bookings(text)
        flight = next(i for i in items if i["type"] == "flight")
        assert "대한항공 08:00" in flight["title"]  # 마지막 항공 선택

    def test_hotels_dedup(self):
        text = (
            "대한항공 07:30 항공편으로 예약할게요\n"
            "제주신라 숙소로 예약할게요\n"
            "제주신라 숙소로 예약할게요"
        )
        items = trip_service._parse_selected_bookings(text)
        assert [i["type"] for i in items].count("hotel") == 1

    def test_only_hotels_after_last_flight(self):
        text = (
            "옛날호텔 숙소로 예약할게요\n"
            "대한항공 07:30 항공편으로 예약할게요\n"
            "새호텔 숙소로 예약할게요"
        )
        items = trip_service._parse_selected_bookings(text)
        hotels = [i["title"] for i in items if i["type"] == "hotel"]
        assert hotels == ["새호텔"]  # 마지막 항공 이후 블록만 최종 선택

    def test_empty_when_nothing_matches(self):
        assert trip_service._parse_selected_bookings("그냥 잡담입니다") == []


class TestToDecimal:
    def test_valid_number(self):
        assert trip_service._to_decimal("1350000") == Decimal("1350000")
        assert trip_service._to_decimal(9000) == Decimal("9000")

    def test_invalid_returns_zero(self):
        assert trip_service._to_decimal("abc") == Decimal(0)
        assert trip_service._to_decimal(None) == Decimal(0)


class TestConfirmationTurn:
    def test_finds_confirmation(self):
        turns = [{"type": "text"}, {"type": "confirmation", "payload": {"code": "TA-1"}}]
        found = trip_service._confirmation_turn(turns)
        assert found is not None
        assert found["payload"]["code"] == "TA-1"

    def test_none_when_absent(self):
        assert trip_service._confirmation_turn([{"type": "text"}]) is None
