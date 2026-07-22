"""workers.py 결정론·순수 함수 유닛 테스트 (외부 API·LLM 의존 없음)."""

import pytest

from app.agents.nodes import workers


class TestPosInt:
    """구조화 출력값을 1~hi 범위 정수로 검증."""

    def test_valid_in_range(self):
        assert workers._pos_int(5, fallback=2, hi=30) == 5

    def test_below_range_uses_fallback(self):
        assert workers._pos_int(0, fallback=2, hi=30) == 2
        assert workers._pos_int(-3, fallback=2, hi=30) == 2

    def test_above_range_uses_fallback(self):
        assert workers._pos_int(99, fallback=2, hi=30) == 2

    def test_non_numeric_uses_fallback(self):
        assert workers._pos_int("abc", fallback=3, hi=30) == 3
        assert workers._pos_int(None, fallback=3, hi=30) == 3

    def test_numeric_string_coerced(self):
        assert workers._pos_int("4", fallback=2, hi=30) == 4

    def test_boundary_values(self):
        assert workers._pos_int(1, fallback=9, hi=30) == 1
        assert workers._pos_int(30, fallback=9, hi=30) == 30


class TestMockRoute:
    """총 박수를 두 도시에 배분(합 = 총 박수)하는 결정론 동선."""

    def test_zero_nights_defaults_two_each(self):
        r = workers._mock_route("제주", "부산", 0)
        assert set(r["routes"]) == {"A", "B"}
        assert r["routes"]["A"]["first"]["arriveLabel"] == "제주 도착 · 2박"
        assert r["routes"]["A"]["second"]["arriveLabel"] == "부산 도착 · 2박"

    def test_three_nights_split_one_two(self):
        r = workers._mock_route("제주", "부산", 3)
        a = r["routes"]["A"]
        assert a["first"]["arriveLabel"] == "제주 도착 · 1박"
        assert a["second"]["arriveLabel"] == "부산 도착 · 2박"
        # B안은 도시 순서만 반대, 박수 배분은 동일(n1, n2)
        b = r["routes"]["B"]
        assert b["first"]["arriveLabel"] == "부산 도착 · 1박"
        assert b["second"]["arriveLabel"] == "제주 도착 · 2박"

    def test_one_night_makes_daytrip(self):
        # n1 = max(1, 1//2) = 1, n2 = 0 → 두번째 도시는 당일
        r = workers._mock_route("세부", "보홀", 1)
        assert r["routes"]["A"]["first"]["arriveLabel"] == "세부 도착 · 1박"
        assert r["routes"]["A"]["second"]["arriveLabel"] == "보홀 당일"

    @pytest.mark.parametrize("nights", [2, 3, 4, 5, 6, 7])
    def test_split_always_sums_to_total(self, nights):
        # arriveLabel에서 실제 배분 박수를 뽑아 합이 총 박수와 같은지 확인
        r = workers._mock_route("A시", "B시", nights)
        a = r["routes"]["A"]
        n1 = int(a["first"]["arriveLabel"].split("·")[1].strip().replace("박", ""))
        second = a["second"]["arriveLabel"]
        n2 = 0 if "당일" in second else int(second.split("·")[1].strip().replace("박", ""))
        assert n1 + n2 == nights
        assert n1 >= 1


class TestDateHelpers:
    """ISO 날짜 산술 (오프바이원·월/연 넘김 검증)."""

    def test_date_md_basic(self):
        assert workers._date_md("2026-08-15") == "8.15"

    def test_date_md_with_offset(self):
        assert workers._date_md("2026-08-15", 2) == "8.17"

    def test_date_md_month_rollover(self):
        assert workers._date_md("2026-08-30", 3) == "9.2"

    def test_iso_add_days(self):
        assert workers._iso_add_days("2026-08-15", 2) == "2026-08-17"

    def test_iso_add_days_month_rollover(self):
        assert workers._iso_add_days("2026-08-30", 3) == "2026-09-02"

    def test_iso_add_days_year_rollover(self):
        assert workers._iso_add_days("2026-12-31", 1) == "2027-01-01"


class TestHotelCard:
    """숙박 구간 카드: cardKey·체크인 날짜·배너 생성."""

    HOTELS = [
        {"name": "제주신라", "price": 200000, "rating": 4.5, "area": "제주시"},
        {"name": "제주오션", "price": 150000, "rating": 4.2, "area": "제주시"},
    ]

    def test_card_key_and_stay_labels(self, monkeypatch):
        monkeypatch.setattr(workers.ts, "search_hotels", lambda c, area=None: list(self.HOTELS))
        result = workers._hotel_card(
            "제주", sort="price", region="제주시",
            stay_nights=2, checkin_iso="2026-08-15", segment=1,
        )
        assert result is not None
        card_type, payload, summary, note = result
        assert card_type == "hotel_results"
        # cardKey = {city}:{region|all}:{segment}
        assert payload["cardKey"] == "제주:제주시:1"
        assert payload["stayNights"] == 2
        assert payload["stayCheckin"] == "2026-08-15"
        # 체크인–체크아웃 라벨 (8.15 ~ 8.17)
        assert payload["stayLabel"].startswith("8.15")
        assert payload["stayLabel"].endswith("8.17")
        assert "제주 제주시 2박" in payload["banner"]
        assert note == ""

    def test_card_key_all_when_no_region(self, monkeypatch):
        monkeypatch.setattr(workers.ts, "search_hotels", lambda c, area=None: list(self.HOTELS))
        _, payload, _, _ = workers._hotel_card("제주", sort="rating", stay_nights=0, segment=0)
        assert payload["cardKey"] == "제주:all:0"
        # 박수가 0이면 stay 라벨을 붙이지 않음
        assert "stayLabel" not in payload

    def test_no_hotels_returns_none(self, monkeypatch):
        monkeypatch.setattr(workers.ts, "search_hotels", lambda city, area=None: [])
        assert workers._hotel_card("제주", sort="price") is None

    def test_region_empty_falls_back_to_city(self, monkeypatch):
        def fake_search(city, area=None):
            return [] if area else list(self.HOTELS)  # 지역 지정 시 0건, 도시 전체는 결과

        monkeypatch.setattr(workers.ts, "search_hotels", fake_search)
        result = workers._hotel_card(
            "제주", sort="rating", region="없는동네", stay_nights=1, checkin_iso="2026-08-15"
        )
        assert result is not None
        _, payload, _, note = result
        assert "없는동네" in note  # 폴백 안내가 노트로 나감
        assert payload["cardKey"].startswith("제주:all")  # region 비워져 all


class TestCardRegion:
    """숙소 카드의 숙소가 모두 같은 지역이면 그 지역명."""

    def test_non_hotel_returns_empty(self):
        assert workers._card_region("flight_results", {}) == ""

    def test_single_region(self):
        payload = {"hotels": [{"region": "제주시"}, {"region": "제주시"}]}
        assert workers._card_region("hotel_results", payload) == "제주시"

    def test_mixed_region_returns_empty(self):
        payload = {"hotels": [{"region": "제주시"}, {"region": "서귀포"}]}
        assert workers._card_region("hotel_results", payload) == ""

    def test_none_region_returns_empty(self):
        payload = {"hotels": [{"region": None}]}
        assert workers._card_region("hotel_results", payload) == ""


class TestDetCaption:
    """카드별 결정론 캡션 (노트 우선)."""

    def test_note_takes_priority(self):
        cap = workers._det_caption("hotel_results", "제주", "지역 숙소 없음 안내")
        assert "지역 숙소 없음 안내" in cap

    def test_flight_caption(self):
        assert "왕복 항공편" in workers._det_caption("flight_results", "부산", "")

    def test_hotel_with_region(self):
        cap = workers._det_caption("hotel_results", "제주", "", region="제주시")
        assert cap.startswith("제주시 숙소")

    def test_hotel_without_region(self):
        assert workers._det_caption("hotel_results", "제주", "").startswith("제주 숙소")
