"""mock 데이터(JSON) 로더.

`app/data/*.json` 을 읽어 캐시한다. 실 provider 실패 시 폴백 데이터로 쓰인다.
"""

import json
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@lru_cache
def load(name: str):
    """`data/<name>.json` 을 파싱해 반환 (캐시)."""
    path = DATA_DIR / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))
