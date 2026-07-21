"""에이전트별 시스템 프롬프트 (마크다운 자산 + 로더).

프롬프트는 이 디렉토리의 `*.md` 파일로 관리한다(에이전트마다 파일 분리, langmanus 방식).
노드/에이전트는 `render("<파일명>")` 으로 프롬프트를 가져다 쓴다. 로더가 `<<CURRENT_TIME>>`,
`<<PERSONA>>` 같은 런타임 변수를 치환한다. 프롬프트 튜닝은 해당 .md 파일만 고치면 된다.

파일:
- _persona.md          : 공통 페르소나(`<<PERSONA>>` 로 주입)
- coordinator_router.md: 라우팅(의도 분류·슬롯 추출)
- coordinator_chat.md  : 대화 답변
- planner.md           : 실행 워커 선택
- destination.md       : 여행지 에이전트(툴 get_attractions — 관심사 필터)
- booking.md           : 예약 에이전트(툴 search_flights/search_hotels)
- booking_caption.md   : 항공·숙소 결과 캡션
- itinerary.md         : 일정 ReAct 에이전트(툴 lookup_attractions/lookup_activities)
- itinerary_direct.md  : 일정 폴백(툴 없이 직접 생성)
- route.md             : 동선 ReAct 에이전트(툴 lookup_attractions + 구조화 A/B)
- payment.md           : 결제 에이전트(툴 issue_confirmation — 예약내용·총액 추출)
- recommend.md / faq.md / places.md
"""

from app.agents.prompts.template import render

__all__ = ["render"]
