"""프롬프트 로더 — prompts/*.md 를 읽어 `<<VAR>>` 런타임 변수를 치환한다.

langmanus 방식: 프롬프트를 마크다운 자산으로 두고, 호출 시 로더가 변수를 주입한다.
- `<<CURRENT_TIME>>` : 오늘 날짜 (자동 주입)
- `<<PERSONA>>`      : 공통 페르소나(_persona.md) 내용 (자동 주입)
- 그 외 `<<VAR>>`    : render(name, VAR=...) 로 넘긴 값. 안 넘기면 원문 그대로 둔다.
"""

import functools
import os
import re
from datetime import datetime

_DIR = os.path.dirname(__file__)
_VAR_RE = re.compile(r"<<\s*([A-Za-z_][A-Za-z0-9_]*)\s*>>")


@functools.lru_cache(maxsize=64)
def _raw(name: str) -> str:
    """prompts/<name>.md 원문 (파일 읽기는 캐시)."""
    path = os.path.join(_DIR, f"{name}.md")
    with open(path, encoding="utf-8") as f:
        return f.read()


def render(name: str, **variables) -> str:
    """prompts/<name>.md 를 읽어 `<<VAR>>`를 치환한 시스템 프롬프트 문자열을 반환한다."""
    variables.setdefault("CURRENT_TIME", datetime.now().strftime("%Y-%m-%d (%a)"))
    variables.setdefault("PERSONA", _raw("_persona").strip())

    def _sub(m: re.Match) -> str:
        key = m.group(1)
        return str(variables[key]) if key in variables else m.group(0)  # 미제공은 원문 유지

    return _VAR_RE.sub(_sub, _raw(name)).strip()
