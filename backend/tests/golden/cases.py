"""골든셋 — 비결정적 에이전트 회귀 케이스 10개.

각 케이스:
- id: 식별자
- messages: 사용자 발화(여러 개면 멀티턴 — 순서대로 실행, 직전 응답을 히스토리에 넣음)
- expect: 구조·계약 단언(결정적). 지원 키: has_card / any_card / no_card / contains / not_contains / final_agent
- rubric: LLM judge가 볼 판정 기준(비었으면 judge 생략)
- requires: 이 케이스에 필요한 외부 키(정보용 표기). intl = Geoapify/Duffel/LiteAPI

카드 타입: destination_carousel · destination_reco · itinerary · route_plan ·
           flight_results · hotel_results · confirmation · text
"""

GOLDENS = [
    {
        "id": "ask-back-vague",
        "messages": ["제주도 갈까 하는데"],
        "expect": {
            "no_card": ["itinerary", "flight_results", "hotel_results", "destination_carousel"],
        },
        "rubric": (
            "사용자가 목적지만 말하고 기간·인원은 말하지 않았다. "
            "봇이 명소나 일정을 바로 제시하지 않고, 기간이나 인원을 되물어야 한다."
        ),
        "requires": [],
    },
    {
        "id": "plan-basic",
        "messages": ["제주 2박 3일 둘이 여행 계획 짜줘. 가볼 만한 명소도 추천해줘"],
        "expect": {
            "any_card": ["destination_carousel", "itinerary"],
        },
        "rubric": "제주의 실제 명소나 일자별 일정을 제시하는지. 정보가 부족하다며 되묻기만 하면 안 된다.",
        "requires": [],
    },
    {
        "id": "itinerary-complete",
        "messages": ["제주 2박 3일 둘이 일정 짜줘"],
        "expect": {
            "any_card": ["itinerary"],
        },
        "rubric": (
            "명소 목록만 나열하고 '골라 주세요'라고 되묻는 게 아니라, "
            "Day별로 장소가 배치된 완성된 일정표를 제시해야 한다."
        ),
        "requires": [],
    },
    {
        "id": "faq-refund",
        "messages": ["예약 취소하면 환불 수수료는 어떻게 돼?"],
        "expect": {
            "contains": ["환불"],
        },
        "rubric": (
            "등록된 FAQ를 근거로 환불 규정(예: 3일 전 100%, 2~1일 전 50% 등)을 답하고, "
            "답변에 참고한 FAQ 출처가 표기돼야 한다. 규정을 임의로 지어내면 안 된다."
        ),
        "requires": [],
    },
    {
        "id": "faq-unrelated-gate",
        "messages": ["오늘 서울 날씨 어때?"],
        "expect": {},
        "rubric": (
            "날씨는 서비스 정책 FAQ가 아니다. 있지도 않은 FAQ를 근거로 규정을 지어내면 안 되고, "
            "모르면 모른다고 하거나 일반 대화로 자연스럽게 응대해야 한다."
        ),
        "requires": [],
    },
    {
        "id": "correction-city",
        "messages": [
            "제주 2박 3일 둘이 명소 추천해줘",
            "아 제주 말고 부산으로 바꿔줘",
        ],
        "expect": {
            "contains": ["부산"],
        },
        "rubric": "정정 요청을 반영해 부산 기준으로 응답하는지. 제주 결과를 그대로 고집하면 안 된다.",
        "requires": [],
    },
    {
        "id": "flight-date-first",
        # 날짜(출발일)가 없으면 항공을 바로 나열하지 않고 날짜부터 되묻는 게 설계 의도(맞음).
        "messages": ["세부 왕복 항공권 보여줘"],
        "expect": {},
        "rubric": (
            "출발일(또는 기간)이 없는 상태다. 항공편을 바로 나열하지 않고 "
            "출발일이나 기간을 먼저 되묻는 게 정답이다."
        ),
        "requires": [],
    },
    {
        "id": "multicity-route",
        "messages": ["세부랑 보홀 둘 다 가고 싶어. 3박 4일 둘이, 동선 짜줘"],
        "expect": {
            "any_card": ["route_plan"],
        },
        "rubric": (
            "두 도시의 방문 순서를 A안·B안 두 가지로 비교해 제시하는지. "
            "A안과 B안의 방문 순서가 실제로 서로 반대여야 한다."
        ),
        "requires": [],
    },
    {
        "id": "unsupported-domestic",
        # 미지원 도시여도 노드는 카드(응답)를 낸다 — 카드 타입 유무가 아니라 '거절 안내 내용'으로 검증한다.
        # (itinerary 노드는 계획에 있으면 내용이 거절이어도 type="itinerary" 카드로 응답을 냄)
        "messages": ["대전 2박 3일 여행 계획 짜줘"],
        "expect": {
            "contains": ["지원하지 않"],
        },
        "rubric": (
            "대전은 현재 지원 목적지가 아니다(제주·부산·세부·보홀만 지원). "
            "지원하지 않는다고 안내해야 하고, 대전의 실제 명소·일정을 지어내면 안 된다."
        ),
        "requires": [],
    },
    {
        "id": "intl-city-resolve",
        "messages": ["발리 3박 4일 둘이 명소 추천해줘"],
        "expect": {
            "any_card": ["destination_carousel", "itinerary"],
            "not_contains": ["지원하지 않"],
        },
        "rubric": "발리를 미지원이라 거절하지 않고, 발리의 실제 여행 정보(명소 등)를 제공하는지.",
        "requires": ["intl"],
    },
]
