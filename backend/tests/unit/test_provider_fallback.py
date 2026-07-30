"""폴백 루프가 장애와 미커버를 구분하는지 검증한다.

provider가 HTTP 실패를 내부에서 None으로 흡수하면 first_available이 장애를 '그 도시
데이터 없음'으로 읽어 서킷이 열리지 않는다. 그래서 장애는 ProviderUnavailable로 올린다.
"""

import httpx
import pytest

from app.core.circuit_breaker import CircuitBreaker
from app.providers import base, duffel
from app.providers.base import ProviderUnavailable, call_with_breaker, first_available
from app.services import travel_service as ts


class FailingProvider:
    """호출할 때마다 장애를 내는 provider."""

    def __init__(self, name: str = "flaky"):
        self.name = name
        self.calls = 0

    def supports(self, city: str) -> bool:
        return True

    def fetch(self, city: str, limit: int, **kwargs):
        self.calls += 1
        raise ProviderUnavailable(self.name)


class EmptyProvider:
    """응답은 정상인데 그 도시 데이터가 없는 provider(미커버)."""

    def __init__(self, name: str = "empty"):
        self.name = name
        self.calls = 0

    def supports(self, city: str) -> bool:
        return True

    def fetch(self, city: str, limit: int, **kwargs):
        self.calls += 1
        return None


class OkProvider:
    """정상 결과를 주는 provider."""

    name = "ok"

    def supports(self, city: str) -> bool:
        return True

    def fetch(self, city: str, limit: int, **kwargs):
        return [{"name": "성산일출봉"}]


class BuggyProvider:
    """provider 구현 자체가 터지는 경우(장애가 아니라 코드 오류)."""

    def __init__(self, name: str = "buggy"):
        self.name = name
        self.calls = 0

    def supports(self, city: str) -> bool:
        return True

    def fetch(self, city: str, limit: int, **kwargs):
        self.calls += 1
        raise KeyError("offers")


@pytest.fixture(autouse=True)
def fresh_breaker(monkeypatch):
    """서킷 상태는 모듈 전역이라 테스트마다 새로 깐다."""
    monkeypatch.setattr(base, "_breaker", CircuitBreaker(threshold=3, cooldown=60.0))


class TestProviderFallback:
    def test_failure_opens_circuit_and_skips_next_call(self):
        p = FailingProvider()
        for _ in range(4):
            assert first_available([p], "제주", 8) is None
        assert p.calls == 3  # 3회 실패로 열린 뒤 4번째는 호출조차 안 한다

    def test_empty_result_does_not_open_circuit(self):
        p = EmptyProvider()
        for _ in range(5):
            assert first_available([p], "제주", 8) is None
        assert p.calls == 5  # 미커버는 장애가 아니므로 계속 시도한다

    def test_falls_back_to_next_provider_on_failure(self):
        failing, ok = FailingProvider(), OkProvider()
        assert first_available([failing, ok], "제주", 8) == [{"name": "성산일출봉"}]
        assert failing.calls == 1

    def test_blocked_provider_yields_to_next(self):
        failing, ok = FailingProvider(), OkProvider()
        for _ in range(3):
            first_available([failing], "제주", 8)  # 여기서 열린다
        assert first_available([failing, ok], "제주", 8) == [{"name": "성산일출봉"}]
        assert failing.calls == 3  # 차단된 뒤로는 부르지 않는다

    def test_implementation_error_does_not_open_circuit(self):
        """구현 오류를 장애로 세면 코드 버그가 60초 차단 뒤에 숨는다."""
        p = BuggyProvider()
        for _ in range(5):
            assert first_available([p], "제주", 8) is None
        assert p.calls == 5


class TestCallWithBreaker:
    """폴백 목록이 없는 단일 provider(항공)도 같은 규칙을 쓴다."""

    def test_opens_after_three_failures(self):
        calls = []

        def fetch():
            calls.append(1)
            raise ProviderUnavailable("duffel.offers")

        for _ in range(4):
            assert call_with_breaker("duffel.flights", fetch) is None
        assert len(calls) == 3

    def test_empty_result_keeps_circuit_closed(self):
        calls = []

        def fetch():
            calls.append(1)
            return None  # 그 구간에 항공편이 없음

        for _ in range(5):
            assert call_with_breaker("duffel.flights", fetch) is None
        assert len(calls) == 5


class TestDuffelOffers:
    """항공도 장애와 '항공편 없음'을 가른다."""

    def test_http_error_raises_provider_unavailable(self, monkeypatch):
        def boom(*args, **kwargs):
            raise httpx.ConnectTimeout("timed out")

        monkeypatch.setattr(duffel.httpx, "post", boom)
        with pytest.raises(ProviderUnavailable):
            duffel._offers("CEB", "2026-08-01", None)

    def test_no_flights_returns_empty_list(self, monkeypatch):
        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"data": {"offers": []}}

        monkeypatch.setattr(duffel.httpx, "post", lambda *a, **kw: _Resp())
        assert duffel._offers("CEB", "2026-08-01", None) == []


class TestFlightCircuit:
    """항공은 provider가 하나라 폴백 목록이 없지만 서킷은 같이 적용된다.

    Duffel이 조회할 수 있는 도시만 호출로 이어져야 한다. 공항코드가 없는 값(자연어 문장,
    국내 도시)을 그대로 넘기면 HTTP 없이 None이 돌아오고, 서킷이 그걸 '정상 응답'으로 읽어
    실패 횟수를 지운다. 그러면 실제 장애가 쌓여도 영영 열리지 않는다.
    """

    @pytest.fixture(autouse=True)
    def _isolated(self, monkeypatch):
        monkeypatch.setattr(base, "_breaker", CircuitBreaker(threshold=3, cooldown=60.0))
        monkeypatch.setattr(ts, "mock_only", lambda: False)

    @staticmethod
    def _failing(seen: list):
        def roundtrip(city, dep, ret):
            seen.append(city)
            raise ProviderUnavailable("duffel.offers")

        return roundtrip

    def test_natural_language_passes_only_the_known_city(self, monkeypatch):
        seen: list[str] = []
        monkeypatch.setattr(ts.duffel, "roundtrip", self._failing(seen))
        for _ in range(4):
            ts.search_flights("세부 항공권 보여줘")  # mock으로 폴백되므로 예외는 안 난다
        assert seen == ["세부"] * 3  # 원문은 넘기지 않고, 네 번째는 차단돼 호출도 없다

    def test_domestic_search_does_not_reset_failures(self, monkeypatch):
        seen: list[str] = []
        monkeypatch.setattr(ts.duffel, "roundtrip", self._failing(seen))
        for _ in range(3):
            ts.search_flights("세부")
            ts.search_flights("제주")  # 국내는 Duffel 조회 대상이 아니다
        ts.search_flights("세부")
        assert seen == ["세부"] * 3  # 국내 검색이 사이에 끼어도 세 번이면 열린다


class TestDuffelSchemaErrors:
    """200 응답이지만 필드가 빠진 경우도 장애로 다뤄야 서킷이 집계한다."""

    def test_malformed_offer_raises_provider_unavailable(self, monkeypatch):
        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"data": {"offers": [{}]}}  # total_amount 등이 없다

        monkeypatch.setattr(duffel.httpx, "post", lambda *a, **kw: _Resp())
        monkeypatch.setattr(duffel, "_CACHE", {})
        with pytest.raises(ProviderUnavailable):
            duffel.roundtrip("세부", "2026-09-01", "2026-09-04")


class TestCacheDoesNotResetCircuit:
    """캐시 히트는 HTTP 응답이 아니므로 provider 생존 증거로 쓰지 않는다."""

    class _CachingProvider:
        """첫 호출만 성공하고 그 결과를 캐시에 담아두는 provider."""

        name = "cached.attractions"

        def __init__(self):
            self.fetch_calls = 0
            self._store: dict[tuple[str, int], list[dict]] = {}

        def supports(self, city: str) -> bool:
            return True

        def cached(self, city: str, limit: int):
            return self._store.get((city, limit))

        def fetch(self, city: str, limit: int, **kwargs):
            self.fetch_calls += 1
            if city == "제주":
                self._store[(city, limit)] = [{"name": "성산일출봉"}]
                return self._store[(city, limit)]
            raise ProviderUnavailable(self.name)

    def test_cached_city_does_not_clear_failures(self):
        p = self._CachingProvider()
        assert first_available([p], "제주", 8)  # 캐시 적재
        for _ in range(3):
            assert first_available([p], "부산", 8) is None  # 장애 3회
            first_available([p], "제주", 8)  # 캐시 히트가 사이에 끼어든다
        assert p.fetch_calls == 4  # 제주 1회 + 부산 3회, 이후 부산은 차단
        assert first_available([p], "부산", 8) is None
        assert p.fetch_calls == 4  # 차단됐으므로 호출이 늘지 않는다
