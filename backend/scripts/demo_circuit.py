"""서킷브레이커가 열리고 다음 호출을 건너뛰는 흐름을 실제 provider로 확인한다.

잘못된 키를 환경변수로 덮어 실행한다(.env는 건드리지 않는다).

    TOUR_API_KEY=invalid uv run python scripts/demo_circuit.py
"""

import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
for noisy in ("httpx", "httpcore"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
# provider 내부의 401 경고(요청 URL 포함)는 줄이고 폴백 루프 쪽 로그만 남긴다.
logging.getLogger("app.providers.tour_api").setLevel(logging.ERROR)

from app.providers import registry  # noqa: E402

for i in range(1, 5):
    print(f"\n[{i}번째 요청] 제주 명소 검색")
    registry.attractions("제주", 8)
