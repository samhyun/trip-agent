"""경량 서킷브레이커 — 외부 의존성이 연속 실패하면 일정 시간 호출을 건너뛴다.

라이브러리 없이 이름별 상태(연속 실패 수 + open 만료 시각)만 관리한다.
- closed    : 정상 호출
- open      : 연속 실패가 임계 이상 → cooldown 동안 호출 차단(빠른 실패, 지연 누적 방지)
- half-open : cooldown 경과 후 시험 호출 1개만 통과(성공→closed / 실패→다시 open)

provider가 다운됐을 때 매 요청마다 그 provider를 또 때리며 타임아웃을 쌓는 걸 막는 게 목적이다.

**half-open 단일 시험 보장 범위**: `allow()`는 락으로 감싸 check-and-set이 원자적이라, cooldown이
지난 뒤 첫 요청 하나만 통과(그 즉시 open_until을 앞으로 밀어 나머지는 차단)한다. 이 보장은
'provider 타임아웃 < cooldown'을 전제로 한다 — 시험 호출이 cooldown 안에 반드시 성공/실패로
끝나므로 두 시험이 겹치거나 결과가 역전될 일이 없다(이 프로젝트는 httpx TIMEOUT ≪ 60s). 시험이
멈춰 cooldown이 다시 지나면 open_until이 backstop이 되어 새 시험을 허용한다(영구 정지 방지).

**허용하는 한계**: open 직후, 그보다 먼저 시작한 느린 호출의 stale 성공이 도착하면 회로가 조기에
닫힐 수 있다. 완전 다운(모든 호출 실패)에는 영향이 없고 flaky provider에서 차단이 살짝 덜
공격적이 되는 정도라 데모 스코프에선 허용한다. 다중 워커·초장기 호출·엄격한 차단이 필요하면
세대 토큰 기반 half-open으로 'open 이후 시작된 성공만 닫도록' 구분해야 한다.

provider.fetch는 스레드풀에서 동시 실행될 수 있어 상태 접근을 락으로 보호한다.
"""

import threading
import time
from dataclasses import dataclass

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class _State:
    fails: int = 0
    open_until: float = 0.0


class CircuitBreaker:
    """이름(provider 등)별 서킷브레이커. 상태는 프로세스 메모리에 유지되고 락으로 보호된다."""

    def __init__(self, threshold: int = 3, cooldown: float = 60.0, clock=time.monotonic):
        if threshold < 1:
            raise ValueError("threshold는 1 이상이어야 합니다")
        if cooldown <= 0:
            raise ValueError("cooldown은 0보다 커야 합니다")
        self.threshold = threshold  # 이 횟수만큼 연속 실패하면 open
        self.cooldown = cooldown  # open 유지 시간(초)
        self._clock = clock  # 테스트용 주입 가능(단조 시계)
        self._lock = threading.Lock()
        self._states: dict[str, _State] = {}

    def allow(self, name: str) -> bool:
        """이 호출을 허용할지 원자적으로 판단. closed면 True, open이면 False.

        cooldown이 지난 half-open에서는 락 안에서 open_until을 앞으로 밀며 첫 요청만 통과시키고
        나머지는 막는다(stampede 방지). backstop이라 시험이 멈춰도 cooldown 뒤 새 시험이 허용된다.
        """
        with self._lock:
            st = self._states.get(name)
            if st is None or not st.open_until:
                return True  # closed
            now = self._clock()
            if now < st.open_until:
                return False  # open(또는 진행 중인 시험의 backstop 시간 내) → 차단
            st.open_until = now + self.cooldown  # half-open 시험 1개 통과 + backstop 갱신
            return True

    def record_success(self, name: str) -> None:
        """성공(또는 응답이 온 alive 상태) → closed로 리셋."""
        with self._lock:
            st = self._states.get(name)
            if st and (st.fails or st.open_until):
                logger.info("circuit[%s] 복구 → closed", name)
            self._states[name] = _State()

    def record_failure(self, name: str) -> None:
        """실패(예외) → 연속 실패 누적, 임계 도달 시 open."""
        with self._lock:
            st = self._states.setdefault(name, _State())
            st.fails += 1
            if st.fails >= self.threshold:
                st.open_until = self._clock() + self.cooldown
                logger.warning(
                    "circuit[%s] open (연속 %d회 실패) → %.0fs 차단", name, st.fails, self.cooldown
                )
