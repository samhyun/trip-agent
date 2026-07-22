"""골든셋 회귀 러너 (비결정적 서비스).

에이전트를 실제로 실행(elice LLM 필요)해서 각 케이스가
  (1) 구조·계약 단언(결정적) + (2) LLM judge 판정(비결정적)
을 통과하는지 본다. 비결정성 때문에 케이스를 --repeat 회 반복해 통과율로 판정하고,
임계 통과율 미달이 하나라도 있으면 종료코드 1(회귀)로 나가 CI 게이트로 쓸 수 있다.

실행:
  cd backend
  uv run python tests/golden/run.py                 # 1회씩
  uv run python tests/golden/run.py --repeat 3       # 각 3회, 통과율 판정
  uv run python tests/golden/run.py --filter faq     # id에 faq 포함만
  uv run python tests/golden/run.py --no-judge       # 구조 단언만(무료·빠름)

주의: LLM(elice) 실호출이라 돌릴 때마다 비용·시간이 든다. judge는 케이스당 LLM 1회 추가.
"""

import argparse
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(os.path.dirname(_HERE))  # tests/golden → backend
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _HERE)

from dotenv import load_dotenv  # noqa: E402

# 루트 .env → os.environ (골든 실행에도 LangSmith 트레이싱이 걸리도록)
load_dotenv(os.path.join(os.path.dirname(_BACKEND), ".env"))

from cases import GOLDENS  # noqa: E402

from app.agents.graph import run_agent  # noqa: E402
from app.agents.llm import get_llm  # noqa: E402
from app.core.config import get_settings  # noqa: E402

# ---------- 구조·계약 단언 (결정적) ----------

def check_expect(expect: dict, result: dict) -> list[str]:
    """구조 단언을 검사하고 실패 사유 목록을 돌려준다(빈 리스트 = 통과)."""
    fails = []
    turns = result["turns"]
    types = [t["type"] for t in turns]
    text = " ".join(t.get("content", "") for t in turns)

    for kind in expect.get("has_card", []):
        if kind not in types:
            fails.append(f"카드 없음: {kind}")
    if "any_card" in expect and not any(k in types for k in expect["any_card"]):
        fails.append(f"카드 중 하나도 없음: {expect['any_card']} (실제: {types})")
    for kind in expect.get("no_card", []):
        if kind in types:
            fails.append(f"있으면 안 되는 카드: {kind}")
    for kw in expect.get("contains", []):
        if kw not in text:
            fails.append(f"미포함 문구: {kw}")
    for kw in expect.get("not_contains", []):
        if kw in text:
            fails.append(f"있으면 안 되는 문구: {kw}")
    if "final_agent" in expect:
        actual = turns[-1]["agent"] if turns else None
        if actual != expect["final_agent"]:
            fails.append(f"final agent {actual} != {expect['final_agent']}")
    return fails


# ---------- LLM judge (비결정적 의미 판정) ----------

_JUDGE_SYS = (
    "너는 여행 챗봇의 응답을 평가하는 엄격한 심사자다. "
    "아래 [기준]을 응답이 충족하면 PASS, 아니면 FAIL로만 판정한다. "
    "반드시 첫 줄에 PASS 또는 FAIL 한 단어만 쓰고, 다음 줄에 한 줄 사유를 쓴다."
)


def _card_digest(turn: dict) -> str:
    """카드 payload의 핵심을 judge가 볼 수 있게 한 줄로 요약(텍스트만 보면 카드 내용을 못 봄)."""
    p = turn.get("payload") or {}
    typ = turn["type"]
    if typ == "route_plan":
        rs = p.get("routes", {})
        opts = []
        for k in ("A", "B"):
            o = rs.get(k) or {}
            first = (o.get("first") or {}).get("arriveLabel", "")
            second = (o.get("second") or {}).get("arriveLabel", "")
            opts.append(f"{k}[{o.get('label', '?')}]: {first} → {second}")
        return "route_plan → " + " / ".join(opts)
    if typ == "flight_results":
        return f"flight_results → 항공 {len(p.get('flights', []))}편"
    if typ == "hotel_results":
        names = ", ".join(h.get("name", "") for h in p.get("hotels", [])[:4])
        return f"hotel_results → 숙소 {len(p.get('hotels', []))}곳 ({names})"
    if typ == "destination_carousel":
        names = ", ".join(i.get("name", "") for i in p.get("items", [])[:5])
        return f"destination_carousel → 명소 {len(p.get('items', []))}개 ({names})"
    return ""


def judge(rubric: str, user_msgs: list[str], result: dict) -> tuple[bool, str]:
    """rubric 기준으로 응답을 PASS/FAIL 판정. (통과여부, 사유)."""
    turns = result["turns"]
    bot_text = "\n".join(t.get("content", "") for t in turns) or "(빈 응답)"
    digests = [d for d in (_card_digest(t) for t in turns) if d]
    cards_block = "\n".join(digests) if digests else "(카드 없음)"
    prompt = (
        f"[사용자 발화]\n{chr(10).join(user_msgs)}\n\n"
        f"[봇 응답 텍스트]\n{bot_text}\n\n"
        f"[봇이 보낸 카드 내용]\n{cards_block}\n\n"
        f"[기준]\n{rubric}"
    )
    resp = get_llm("coordinator").invoke(
        [{"role": "system", "content": _JUDGE_SYS}, {"role": "user", "content": prompt}]
    )
    out = (resp.content or "").strip()
    passed = out.upper().lstrip().startswith("PASS")
    reason = out.split("\n", 1)[1].strip() if "\n" in out else out
    return passed, reason


# ---------- 케이스 1회 실행 ----------

def run_once(case: dict, use_judge: bool) -> tuple[bool, list[str]]:
    """멀티턴을 순서대로 실행하고 마지막 응답에 단언·judge를 적용. (통과, 사유목록)."""
    history: list[dict] = []
    result: dict = {"turns": [], "answer": "", "agent": None}
    for i, um in enumerate(case["messages"]):
        history.append({"role": "user", "content": um})
        result = run_agent(history, conversation_id=f"golden-{case['id']}-{i}", authenticated=True)
        for t in result["turns"]:  # 직전 응답을 다음 턴 히스토리에 반영
            if t.get("content"):
                history.append({"role": "assistant", "content": t["content"]})

    fails = check_expect(case.get("expect", {}), result)
    if use_judge and case.get("rubric"):
        ok, reason = judge(case["rubric"], case["messages"], result)
        if not ok:
            fails.append(f"judge FAIL: {reason}")
    return (not fails), fails


# ---------- 메인 ----------

def _unmet_requires(case: dict) -> list[str]:
    """이 케이스가 요구하는 외부 키 중 없는 것. 있으면 '환경 누락'이라 스킵(제품 회귀 아님)."""
    s = get_settings()
    unmet = []
    if "intl" in case.get("requires", []) and not (
        s.geoapify_api_key and s.duffel_api_key and s.liteapi_api_key
    ):
        unmet.append("intl(Geoapify/Duffel/LiteAPI)")
    return unmet


def main() -> int:
    ap = argparse.ArgumentParser(description="골든셋 회귀 러너")
    ap.add_argument("--repeat", type=int, default=1, help="케이스당 반복 횟수(통과율 판정)")
    ap.add_argument("--threshold", type=float, default=1.0, help="케이스 통과로 볼 최소 통과율(0~1)")
    ap.add_argument("--filter", default="", help="id에 이 문자열이 포함된 케이스만")
    ap.add_argument("--no-judge", action="store_true", help="LLM judge 생략(구조 단언만)")
    args = ap.parse_args()

    if args.repeat < 1:
        print("--repeat 는 1 이상이어야 합니다.")
        return 2
    if not (0.0 < args.threshold <= 1.0):
        print("--threshold 는 0 초과 1 이하여야 합니다.")
        return 2
    if not get_settings().llm_enabled:
        print("⚠️  LLM 미설정 — 에이전트가 mock으로만 동작해 골든셋이 의미가 없습니다. .env에 LLM 키를 넣고 실행하세요.")
        return 2

    cases = [c for c in GOLDENS if args.filter in c["id"]]
    if not cases:
        print(f"선택된 케이스가 없습니다 (filter={args.filter!r}). id를 확인하세요.")
        return 2
    use_judge = not args.no_judge
    print(f"골든셋 {len(cases)}개 · 반복 {args.repeat} · 임계 통과율 {args.threshold} · judge {'ON' if use_judge else 'OFF'}\n")

    regressed, skipped = [], []
    for c in cases:
        unmet = _unmet_requires(c)
        if unmet:  # 필요한 키가 없으면 환경 누락 → 실패가 아니라 스킵
            skipped.append(c["id"])
            print(f"⏭️  {c['id']:<22} 스킵 (키 없음: {', '.join(unmet)})")
            continue
        passes, last_fails = 0, []
        t0 = time.time()
        for _ in range(args.repeat):
            ok, fails = run_once(c, use_judge)
            passes += 1 if ok else 0
            if not ok:
                last_fails = fails
        rate = passes / args.repeat
        ok_case = rate >= args.threshold
        mark = "✅" if ok_case else "❌"
        print(f"{mark} {c['id']:<22} 통과율 {passes}/{args.repeat}  {time.time() - t0:4.1f}s")
        if not ok_case:
            regressed.append(c["id"])
            for f in last_fails:
                print(f"     └ {f}")

    print()
    if skipped:
        print(f"스킵 {len(skipped)}개(환경 키 없음): {', '.join(skipped)}")
    if regressed:
        print(f"회귀 감지: {len(regressed)}개 — {', '.join(regressed)}")
        return 1
    print(f"전체 통과 ({len(cases) - len(skipped)}개 실행)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
