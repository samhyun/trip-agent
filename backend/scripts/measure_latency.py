"""플로우 지연 실측 스크립트 (발표 수치 근거).

사용: .venv/bin/python scripts/measure_latency.py
- 멀티도시 전체 계획(명소+동선+일정) 총 소요와 단계별 시간을 출력한다.
- elice LLM 지연 편차(호출당 ±5~10s)가 있어 1회 실측은 참고치이며, 2~3회 평균 권장.
- 2026-07-21 실측: 병렬화·선주입 전 126.3s → 후 54~63s / itinerary 단독 15s→7.6s /
  명소 API 도시당 20~32s→3~8s(첫 호출, 캐시 후 0s) / route 25.6s→19.8s(평문 파싱).
"""

import time

from app.agents.graph import stream_agent


def main() -> None:
    t0 = time.time()
    events = list(
        stream_agent(
            [{"role": "user", "content": "제주랑 부산 3박4일 여행 명소랑 동선이랑 일정 짜줘"}],
            "measure-latency",
        )
    )
    total = time.time() - t0
    cards = [e.get("card_type") for e in events if e.get("type") in ("card", "text_end")]
    print(f"멀티도시 전체 계획: {total:.1f}s / 카드: {cards}")


if __name__ == "__main__":
    main()
