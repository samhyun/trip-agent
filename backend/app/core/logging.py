"""로깅 설정.

`setup_logging()`을 앱 시작 시 한 번 호출해 포맷과 레벨을 지정한다.
"""

import logging
import re

from app.core.config import get_settings

# URL 쿼리에 담긴 API 키를 로그에서 마스킹(apiKey/appid/serviceKey/token/secret 등).
# httpx 예외 문자열에 요청 URL이 그대로 들어가 키가 로그로 유출되는 것을 방지한다.
# 이름이 key/appid/token/secret/password로 끝나는 파라미터의 값을 가린다(serviceKey 등 포함).
_SECRET_RE = re.compile(r"(?i)(\b[\w-]*(?:key|appid|token|secret|password))=[^&\s'\"]+")


def redact(value: object) -> str:
    """문자열(예외 등)에서 API 키 쿼리 값을 '***'로 마스킹한다."""
    return _SECRET_RE.sub(r"\1=***", str(value))


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
