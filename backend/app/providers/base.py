"""Provider 추상화 레이어.

여행 데이터 도메인(attractions·stays·flights·hotels)마다 여러 provider를 같은
인터페이스(`Provider`)로 다룬다. `travel_service`는 구체 provider(tour_api 등)를 직접
알지 않고 `registry` 파사드만 호출하므로, provider 교체·추가 시 이 레이어와 registry만 손대면 된다.

각 provider 규약:
- name            : 로깅·식별용 이름
- supports(city)  : 이 provider가 해당 도시를 커버하는지 (예: 국내/해외 구분)
- fetch(city, limit) : mock과 동일 스키마의 결과(명소·숙박=list, 항공=날짜별 dict), 또는
                       None(미커버·실패·빈결과)
"""

from typing import Protocol, runtime_checkable

from app.core.circuit_breaker import CircuitBreaker
from app.core.logging import get_logger, redact

logger = get_logger(__name__)

# provider별 서킷브레이커(이름 기준). 연속 3회 실패하면 60초 동안 그 provider를 건너뛴다.
_breaker = CircuitBreaker(threshold=3, cooldown=60.0)

# 도메인 결과 타입: 명소/숙박은 list[dict], 항공은 flights dict.
Result = list[dict] | dict


@runtime_checkable
class Provider(Protocol):
    """도메인 provider 공통 인터페이스."""

    name: str

    def supports(self, city: str) -> bool:
        ...

    def fetch(self, city: str, limit: int) -> Result | None:
        ...


def first_available(providers: list[Provider], city: str, limit: int, **kwargs) -> Result | None:
    """등록 순서(=우선순위)대로 supports→fetch를 시도해 첫 유효 결과를 반환.

    supports가 False면 건너뛰고, fetch가 예외/None/빈결과면 다음 provider로.
    모두 실패하면 None(호출부가 mock으로 폴백). kwargs는 provider별 추가 인자(예: 항공 start_date).
    """
    for provider in providers:
        if not provider.supports(city):
            continue
        if not _breaker.allow(provider.name):  # open/half-open 차단 → 건너뜀(빠른 실패)
            logger.info("provider %s 차단됨(circuit) → 다음으로", provider.name)
            continue
        try:
            result = provider.fetch(city, limit, **kwargs)
        except Exception as exc:  # noqa: BLE001 - provider 실패는 다음 provider/mock로 흡수
            logger.warning("provider %s fetch 실패(%s): %s", provider.name, city, redact(exc))
            _breaker.record_failure(provider.name)  # 예외(장애)만 실패로 집계
            continue
        # 응답이 왔으면(빈 결과 포함) provider는 살아있음 → 실패 카운트 리셋
        _breaker.record_success(provider.name)
        if result:
            n = len(result) if isinstance(result, list) else len(result.get("date_prices", []))
            logger.info("provider %s → %s (%d)", provider.name, city, n)
            return result
        # 빈 결과는 '미커버'라 다음 provider로 (provider 자체는 alive로 처리됨)
    return None
