"""CircuitBreaker 유닛 테스트 (주입 시계로 결정론적 검증)."""

import pytest

from app.core.circuit_breaker import CircuitBreaker


class FakeClock:
    """테스트용 단조 시계 — advance로 시간을 수동으로 진행시킨다."""

    def __init__(self):
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


class TestCircuitBreaker:
    def test_allows_by_default(self):
        cb = CircuitBreaker(threshold=3, cooldown=60.0, clock=FakeClock())
        assert cb.allow("duffel") is True

    def test_opens_after_threshold_failures(self):
        cb = CircuitBreaker(threshold=3, cooldown=60.0, clock=FakeClock())
        cb.record_failure("duffel")
        cb.record_failure("duffel")
        assert cb.allow("duffel") is True  # 아직 임계 미만
        cb.record_failure("duffel")
        assert cb.allow("duffel") is False  # 3회째 → open

    def test_success_resets_failures(self):
        cb = CircuitBreaker(threshold=3, cooldown=60.0, clock=FakeClock())
        cb.record_failure("tour_api")
        cb.record_failure("tour_api")
        cb.record_success("tour_api")  # 리셋
        cb.record_failure("tour_api")
        cb.record_failure("tour_api")
        assert cb.allow("tour_api") is True  # 리셋 후 2회뿐

    def test_half_open_after_cooldown(self):
        clock = FakeClock()
        cb = CircuitBreaker(threshold=2, cooldown=60.0, clock=clock)
        cb.record_failure("geoapify")
        cb.record_failure("geoapify")
        assert cb.allow("geoapify") is False
        clock.advance(59.0)
        assert cb.allow("geoapify") is False  # 아직 cooldown 중
        clock.advance(2.0)  # 61s 경과
        assert cb.allow("geoapify") is True  # half-open → 시험 호출 1개 허용

    def test_half_open_single_trial_no_stampede(self):
        clock = FakeClock()
        cb = CircuitBreaker(threshold=2, cooldown=60.0, clock=clock)
        cb.record_failure("liteapi")
        cb.record_failure("liteapi")  # open
        clock.advance(61.0)
        assert cb.allow("liteapi") is True  # 첫 시험 호출만 통과
        assert cb.allow("liteapi") is False  # 동시 후속 요청은 막힘(stampede 방지)

    def test_trial_success_closes_circuit(self):
        clock = FakeClock()
        cb = CircuitBreaker(threshold=2, cooldown=30.0, clock=clock)
        cb.record_failure("duffel")
        cb.record_failure("duffel")
        clock.advance(31.0)
        assert cb.allow("duffel") is True  # half-open 시험
        cb.record_success("duffel")  # 시험 성공 → closed
        assert cb.allow("duffel") is True
        assert cb.allow("duffel") is True  # 완전 복구(더는 막지 않음)

    def test_trial_failure_reopens(self):
        clock = FakeClock()
        cb = CircuitBreaker(threshold=2, cooldown=30.0, clock=clock)
        cb.record_failure("liteapi")
        cb.record_failure("liteapi")  # open
        clock.advance(31.0)
        assert cb.allow("liteapi") is True  # half-open 시험
        cb.record_failure("liteapi")  # 시험 실패 → 다시 open
        assert cb.allow("liteapi") is False

    def test_breakers_are_independent_per_name(self):
        cb = CircuitBreaker(threshold=2, cooldown=60.0, clock=FakeClock())
        cb.record_failure("duffel")
        cb.record_failure("duffel")
        assert cb.allow("duffel") is False
        assert cb.allow("tour_api") is True  # 다른 provider는 영향 없음

    def test_stuck_trial_backstop(self):
        # 시험 호출이 응답 없이 멈춰도 backstop(cooldown) 뒤 새 시험을 허용(영구 정지 방지).
        clock = FakeClock()
        cb = CircuitBreaker(threshold=2, cooldown=30.0, clock=clock)
        cb.record_failure("x")
        cb.record_failure("x")  # open, open_until=30
        clock.advance(31.0)
        assert cb.allow("x") is True  # 시험 허용(in_flight), open_until=61
        assert cb.allow("x") is False  # 시험 진행 중 → 막힘 (record 없음)
        clock.advance(31.0)  # t=62 > 61 (시험이 멈춘 채 cooldown 재경과)
        assert cb.allow("x") is True  # backstop으로 새 시험 허용

    def test_invalid_constructor_args(self):
        with pytest.raises(ValueError):
            CircuitBreaker(threshold=0)
        with pytest.raises(ValueError):
            CircuitBreaker(cooldown=0)
        with pytest.raises(ValueError):
            CircuitBreaker(cooldown=-1)
