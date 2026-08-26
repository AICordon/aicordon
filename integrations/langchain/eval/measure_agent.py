"""Acceptance measurement of the request side: how many attacks reach the model, at what price.

WHAT IS MEASURED, AND WHY NOT RECALL. The detector's detection rate is published already
(`docs/eval/direct-jailbreaks-2026-08.md`). An integration answers a different question: of the
turns that entered the agent, how many REACHED THE MODEL, and how many real users were left without
an answer. That is a property of the middleware — which role is read, with which rule set, whether
skipping the model call actually skips it.

THE THIRD NUMBER OUTRANKS THE FIRST TWO: the agent and the bare detector must differ ZERO times on
the same string. A wrapper may neither lose text (a message part, a truncated tail) nor add its own.
If that number is not zero, the rest must not be read.

THE MODEL IS A COUNTER, NOT A MODEL. What is being measured is whether the call happened, so a fake
chat model that records what it was asked answers the question exactly and costs nothing.

THE CLEAN POOL IS NOT CLEAN, and no correction is applied. WildChat carries no attack labels, and
real jailbreaks sit inside the negative pool: in the published run, 41 of the 144 turns flagged by
every detector were attacks. So "left without an answer" below is an UPPER BOUND on the price, not
a false-positive rate.

    python eval/measure_agent.py --turns 20000
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Any

from _pools import DIRECT, load_direct
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage

from aicordon_langchain import PromptInjectionGuard

HERE = Path(__file__).resolve().parent
SYSTEM = "You are a helpful assistant."


class Counter(GenericFakeChatModel):
    """Stands where the model would and only counts: being called means the turn got through."""

    seen: list[str] = []

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # noqa: ANN001, ANN202
        self.seen.append(str(messages[-1].id))
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    def bind_tools(self, tools, **kwargs):  # noqa: ANN001, ANN003, ANN201
        return self


def run_arm(turns: list[dict], guarded: bool) -> tuple[set[str], float]:
    """Both arms are the same agent; the guarded one has one middleware more in it."""
    model = Counter(messages=iter([AIMessage(content="answered")] * (len(turns) + 1)))
    model.seen = []
    agent = create_agent(model=model, tools=[],
                         middleware=[PromptInjectionGuard()] if guarded else [])
    ids: dict[str, str] = {}
    t0 = time.perf_counter()
    for n, r in enumerate(turns, 1):
        message = HumanMessage(content=r["text"], id=f"turn-{n}")
        ids[f"turn-{n}"] = r["id"]
        agent.invoke({"messages": [message]})
        if n % 2000 == 0 or n == len(turns):
            print(f"  {'with the guard' if guarded else 'without it'}: {n}/{len(turns)}",
                  flush=True)
    return {ids[i] for i in model.seen if i in ids}, time.perf_counter() - t0


def main() -> int:
    # The middleware logs a warning per finding — hundreds of them here, and they bury the progress.
    logging.getLogger("aicordon_langchain.middleware").setLevel(logging.ERROR)
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", type=int, default=20000, help="clean turns; every attack is taken")
    ap.add_argument("--data", type=Path, default=DIRECT, help="jsonl with `id`, `text`, `slice`")
    ap.add_argument("--json", default="result-agent.json")
    a = ap.parse_args()

    attacks, clean = load_direct(a.data, a.turns)
    print(f"{len(attacks)} held-out attacks, {len(clean)} clean turns", flush=True)
    turns = attacks + clean

    base_seen, base_s = run_arm(turns, guarded=False)
    guard_seen, guard_s = run_arm(turns, guarded=True)

    # Against the bare detector: the wrapper is obliged to see exactly the same string. A turn is a
    # mismatch when it was flagged AND reached the model, or was not flagged AND did not.
    from aicordon import picket
    detector = picket.load(mode="dpi")
    mismatch = [r["id"] for r in turns
                if detector.check(r["text"]).flagged == (r["id"] in guard_seen)]

    a_ids = {r["id"] for r in attacks}
    c_ids = {r["id"] for r in clean}
    a_before, a_after = len(a_ids & base_seen), len(a_ids & guard_seen)
    c_before, c_after = len(c_ids & base_seen), len(c_ids & guard_seen)

    out: dict[str, Any] = {
        "attacks": len(a_ids), "clean": len(c_ids),
        "attacks_reached_before": a_before, "attacks_reached_after": a_after,
        "clean_reached_before": c_before, "clean_reached_after": c_after,
        "mismatch_with_bare_detector": len(mismatch),
        "seconds_baseline": round(base_s, 1), "seconds_guarded": round(guard_s, 1),
        "base": PromptInjectionGuard()._guard.base_version,
    }
    (HERE / a.json).write_text(json.dumps(out, ensure_ascii=False, indent=1))

    n, m = len(a_ids), len(c_ids)
    print(f"\nattacks reaching the model: {a_before}/{n} ({a_before/n:.1%}) without the guard"
          f"  ->  {a_after}/{n} ({a_after/n:.1%}) with it")
    print(f"stopped: {(a_before - a_after)/n:.1%} of the held-out attacks")
    print(f"clean turns left without an answer: {m - c_after}/{m} ({(m - c_after)/m:.3%}) "
          f"— an upper bound, the pool holds real attacks")
    print(f"verdicts differing from the bare detector: {len(mismatch)}")
    print(f"time: {base_s:.1f} s without the guard, {guard_s:.1f} s with it "
          f"({(guard_s - base_s) / max(1, len(turns)) * 1000:.2f} ms per turn added)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
