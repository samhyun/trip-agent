"""로깅 설정.

`setup_logging()`을 앱 시작 시 한 번 호출해 포맷과 레벨을 지정한다.
"""

import logging

from app.core.config import get_settings


def setup_logging() -> None:
    """루트 로거에 포맷/레벨을 적용한다."""
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def get_logger(name: str) -> logging.Logger:
    """모듈용 로거를 반환한다."""
    return logging.getLogger(name)
