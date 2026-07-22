"""travel_service.py 파싱·집계·빌드 함수 유닛 테스트."""

import re

from app.services import travel_service as ts


class TestParsePeople:
    def test_digit_with_unit(self):
        assert ts.parse_people("3명이서 갈래") == 3
        assert ts.parse_people("5인 예약") == 5

    def test_honja(self):
        assert ts.parse_people("혼자 여행 갈래") == 1

    def test_duri(self):
        assert ts.parse_people("둘이 가려고") == 2
        assert ts.parse_people("두 명 예약") == 2

    def test_default_when_absent(self):
        assert ts.parse_people("제주도 갈까") == 2
        assert ts.parse_people("제주도 갈까", default=1) == 1


class TestParseNights:
    def test_single(self):
        assert ts.parse_nights("2박 3일 갈래") == 2

    def test_first_match_only(self):
        # 백엔드는 첫 '박'만 취한다 (프론트 parseNights의 합산과 의도적으로 다름)
        assert ts.parse_nights("제주시 1박, 서귀포 1박") == 1

    def test_default_when_absent(self):
        assert ts.parse_nights("당일치기 갈래") == 3
        assert ts.parse_nights("당일치기", default=1) == 1


class TestFindCities:
    def test_finds_known_cities(self):
        cities = ts.find_cities("제주랑 부산 갈래")
        assert "제주" in cities
        assert "부산" in cities

    def test_empty_for_unknown(self):
        assert ts.find_cities("두바이 갈래") == []


class TestBuildHotelPayload:
    HOTELS = [
        {"name": "A호텔", "price_per_night": 100000, "rating": 4.0, "area": "제주시"},
        {"name": "B호텔", "price_per_night": 80000, "rating": 4.8, "area": "서귀포"},
    ]

    def test_sort_price_ascending(self):
        p = ts.build_hotel_payload("제주", list(self.HOTELS), sort="price")
        assert [h["name"] for h in p["hotels"]] == ["B호텔", "A호텔"]  # 80k < 100k
        assert "가격 낮은순" in p["banner"]

    def test_sort_rating_default(self):
        p = ts.build_hotel_payload("제주", list(self.HOTELS))
        assert [h["name"] for h in p["hotels"]] == ["B호텔", "A호텔"]  # 4.8 > 4.0
        assert "평점 높은순" in p["banner"]

    def test_regions_listed_when_multiple(self):
        p = ts.build_hotel_payload("제주", list(self.HOTELS), sort="price")
        assert p["regions"][0] == "전체"
        assert set(p["regions"][1:]) == {"제주시", "서귀포"}

    def test_no_regions_key_when_single_area(self):
        one_area = [{"name": "C호텔", "price_per_night": 90000, "rating": 4.1, "area": "제주시"}]
        p = ts.build_hotel_payload("제주", one_area, sort="price")
        assert "regions" not in p


class TestEstimateTotal:
    def test_cheapest_flight_and_hotel(self, monkeypatch):
        flights = {"flights": [{"price": 100000}, {"price": 120000}]}
        hotels = {"제주": [{"price_per_night": 50000}, {"price_per_night": 70000}]}
        monkeypatch.setattr(ts, "search_flights", lambda city, nights=3: flights)
        monkeypatch.setattr(ts, "load", lambda kind: hotels if kind == "hotels" else {})
        # 최저 항공 100000×2인 + 최저 숙소 50000×3박 = 200000 + 150000
        assert ts.estimate_total(["제주"], travelers=2, nights=3) == 350000


class TestMakeConfirmation:
    def test_format(self):
        code = ts.make_confirmation()
        assert re.match(r"^TA-\d{8}-\d{4}$", code)

    def test_custom_prefix(self):
        assert ts.make_confirmation("XY").startswith("XY-")
