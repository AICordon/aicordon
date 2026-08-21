"""Numbers on the DEMONSTRATION set of dialogues: the request window, measured honestly.

The pair to `measure_demo.py`: that one measures material (`ipi`), this one the request (`dpi`). And
as there, these numbers MUST NOT be passed off as the detector's quality: the set is a shop window,
its attacks were picked from what fires and its clean exchanges from what stays quiet. The measured
numbers for the request side are taken on held-out forum jailbreaks and live traffic, and they live
in the integration README next door.

What is counted here:

    attacks blocked          - exchanges the wrapper kept out of the model
    clean reached the model  - exchanges that went through untouched
    disagreements with the   - the wrapper's verdict against a bare TurnGuard on the same turn; MUST
    detector                   be zero. A wrapper has no licence either to lose text or to add its
                               own; if that number is not zero, the rest must not be read.

    python3 measure_demo_dialog.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

from aicordon.guard import DialogueGuard, TurnGuard          # noqa: E402


def main() -> int:
    rows = [json.loads(l) for l in (HERE / "dialogues.jsonl").open()]
    guard = DialogueGuard(mode="drop")
    guard.warm_up()
    bare = TurnGuard(mode="annotate")     # the same dpi rules, with no wrapper around them
    bare.warm_up()

    attacks = [r for r in rows if r["label"] == "attack"]
    cleans = [r for r in rows if r["label"] == "clean"]

    blocked = 0
    clean_through = 0
    mismatch = 0
    t0 = time.perf_counter()
    for r in rows:
        turns = [(role, text) for role, text in r["turns"]]
        verdict = guard.decide(turns)
        if r["label"] == "attack":
            blocked += verdict.flagged and not verdict.keep
        else:
            clean_through += verdict.keep and not verdict.flagged

        # The invariant: on every user turn, the wrapper's finding must equal the bare detector's.
        for role, text in turns:
            if role != "user" or not text:
                continue
            if bare.inspect(text).flagged != _turn_flagged(verdict, turns, text):
                mismatch += 1
    seconds = time.perf_counter() - t0

    n_turns = sum(len(r["turns"]) for r in rows)
    print(f"{len(rows)} dialogues ({len(attacks)} attacks, {len(cleans)} clean), "
          f"{n_turns} turns, {seconds * 1000:.0f} ms "
          f"({seconds / len(rows) * 1000:.1f} ms per exchange), base {guard.base_version}\n")
    print(f"attacks blocked          : {blocked}/{len(attacks)} ({blocked / len(attacks):.0%})")
    print(f"clean reached the model  : {clean_through}/{len(cleans)} ({clean_through / len(cleans):.0%})")
    print(f"disagreements with det.  : {mismatch}   <- must be 0")
    return 1 if mismatch else 0


def _turn_flagged(verdict, turns: list[tuple[str, str]], text: str) -> bool:
    """Whether the wrapper flagged the message carrying `text`, read off its per-message verdicts."""
    for i, (_role, t) in enumerate(turns):
        if t == text:
            found = verdict.per_message.get(i)
            return bool(found and found.flagged)
    return False


if __name__ == "__main__":
    raise SystemExit(main())
