"""Provider 추상화 레이어.

여행 데이터 도메인(attractions·stays·flights·hotels)마다 여러 provider를 같은
인터페이스(`Provider`)로 다룬다. `travel_service`는 구체 provider(tour_api 등)를 직접
알지 않고 `registry` 파사드만 호출하므로, provider 교체·추가 시 이 레이어와 registry만 손대면 된다.

각 provider 규약:
- name            : 로깅·식별용 이름
- supports(city)  : 이 provider가 해당 도시를 커버하는지 (예: 국내/해외 구분)
- fetch(city, limit) : mock과 동일 스키마의 결과(명소·숙박=list, 항공=날짜별 dict), 또는
                       None/빈결과(미커버 — 응답은 정상인데 그 도시 데이터가 없음)
                       장애(타임아웃·5xx·인증 실패·비정상 응답)는 ProviderUnavailable로 올린다.

장애와 미커버를 같은 값으로 돌려주면 서킷이 장애를 미커버로 읽어 열리지 않는다.
사진·상세·요금 같은 부가 조회는 실패해도 카드를 만들 수 있으므로 이 규약 밖이다.
그쪽은 빈 값으로 진행하고 호출부가 폴백(예: 데모 가격)을 쓴다.
"""

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from app.core.circuit_breaker import CircuitBreaker
from app.core.logging import get_logger, redact

logger = get_logger(__name__)

# provider별 서킷브레이커(이름 기준). 연속 3회 실패하면 60초 동안 그 provider를 건너뛴다.
_breaker = CircuitBreaker(threshold=3, cooldown=60.0)


class ProviderUnavailable(Exception):
    """provider가 응답하지 못했다(타임아웃·5xx·인증 실패 등).

    '그 도시 데이터가 없음'(미커버)과 구분하기 위한 타입. provider 내부에서 HTTP 실패를
    None으로 흡수해 버리면 first_available이 장애를 미커버로 읽어 서킷이 열리지 않는다.
    """

# 도메인 결과 타입: 명소/숙박은 list[dict], 항공은 flights dict.
Result = list[dict] | dict

def call_with_breaker[T](name: str, fetch: Callable[[], T], context: str = "") -> T | None:
    """provider 호출 하나에 서킷브레이커를 적용한다.

    차단 중이면 부르지 않고 None. 장애(ProviderUnavailable)만 실패로 집계한다.
    예상하지 못한 오류(provider 구현 버그 등)는 로그로 드러내되 서킷에는 세지 않는다.
    구현 오류가 실패 횟수에 섞이면 장애로 위장돼 60초 차단으로 조용히 넘어가기 때문이다.
    어느 쪽이든 None을 돌려주므로 호출부는 다음 provider나 mock으로 이어간다.
    context는 로그에 덧붙일 조회 대상(예: 도시명).
    """
    if not _breaker.allow(name):  # open/half-open 차단 → 건너뜀(빠른 실패)
        logger.info("provider %s 차단됨(circuit) → 다음으로", name)
        return None
    where = f"({context})" if context else ""
    try:
        result = fetch()
    except ProviderUnavailable as exc:
        logger.warning("provider %s fetch 실패%s: %s", name, where, redact(exc))
        _breaker.record_failure(name)
        return None
    except Exception:  # noqa: BLE001 - 구현 오류는 서킷과 무관하게 드러낸다
        logger.exception("provider %s 예상하지 못한 오류%s", name, where)
        return None
    # 응답이 왔으면(빈 결과 포함) provider는 살아있음 → 실패 카운트 리셋
    _breaker.record_success(name)
    return result


@runtime_checkable
class Provider(Protocol):
    """도메인 provider 공통 인터페이스."""

    name: str

    def supports(self, city: str) -> bool:
        ...

    def fetch(self, city: str, limit: int) -> Result | None:
        ...

    # cached(city, limit): 이미 받아둔 결과가 있으면 반환(HTTP 없음). 선택 구현.


def cached_result(provider: Provider, city: str, limit: int) -> Result | None:
    """provider가 앞선 조회로 이미 갖고 있는 결과. 없거나 미구현이면 None.

    캐시 히트는 HTTP 응답이 아니라서 provider가 지금 살아있다는 증거가 못 된다.
    그런데 call_with_breaker를 지나면 record_success가 불려 쌓인 실패 횟수가 지워진다.
    도시가 서킷 키를 공유하는 항공에서는 캐시된 도시를 부르는 것만으로 다른 도시의
    장애 기록이 사라지므로, 캐시는 서킷 앞에서 따로 확인한다.
    """
    getter = getattr(provider, "cached", None)
    return getter(city, limit) if callable(getter) else None


def first_available(providers: list[Provider], city: str, limit: int, **kwargs) -> Result | None:
    """등록 순서(=우선순위)대로 supports→fetch를 시도해 첫 유효 결과를 반환.

    supports가 False면 건너뛰고, 장애·차단·빈결과면 다음 provider로.
    모두 실패하면 None(호출부가 mock으로 폴백). kwargs는 provider별 추가 인자(예: 항공 start_date).
    서킷 규칙은 call_with_breaker 한 곳에 있다.
    """
    for provider in providers:
        if not provider.supports(city):
            continue
        hit = cached_result(provider, city, limit)
        if hit:  # 이미 받아둔 결과 → 서킷 판단 없이 그대로
            return hit
        result = call_with_breaker(
            provider.name, lambda p=provider: p.fetch(city, limit, **kwargs), context=city
        )
        if result:
            n = len(result) if isinstance(result, list) else len(result.get("date_prices", []))
            logger.info("provider %s → %s (%d)", provider.name, city, n)
            return result
        # 빈 결과는 '미커버'라 다음 provider로 (provider 자체는 alive로 처리됨)
    return None
