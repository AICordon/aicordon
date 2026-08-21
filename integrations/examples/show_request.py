"""Run the ten demonstration EXCHANGES through the detector and show every one of them.

The pair to `show_material.py`: that one reads material (`ipi`), this one the request (`dpi`). The
carrier here is not a document but the message list on its way into the model, so what is shown per
row is whether the exchange would have been sent at all.

Nothing is cut on this side and nothing is averaged. What IS checked, on every user turn, is the
invariant that licenses the rest: the wrapper's finding must equal the bare detector's on the same
string. If that column is not zero, the wrapper is losing or adding text and the demonstration says
nothing about the detector.

The measured numbers live elsewhere: held-out forum jailbreaks against live WildChat turns, in the
integration README. This set is picked so that every example behaves.

    python3 show_request.py
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

from aicordon.guard import DialogueGuard, TurnGuard          # noqa: E402


def main() -> int:
    src = HERE / "dialogues.jsonl"
    if not src.exists():
        raise SystemExit("no dialogues.jsonl here: build the set with `python3 build_dialogs.py`")
    rows = [json.loads(l) for l in src.open()]
    guard = DialogueGuard(mode="drop")
    guard.warm_up()
    bare = TurnGuard(mode="annotate")          # the same dpi rules, with no wrapper around them
    bare.warm_up()

    print(f"{'exchange':22s} {'label':7s} {'turns':>5s}  {'goes to the model':18s} what fired")
    print("-" * 88)
    wrong = mismatch = 0
    for r in rows:
        turns = [(role, text) for role, text in r["turns"]]
        v = guard.decide(turns)
        expected_block = r["label"] == "attack"
        wrong += (v.flagged and not v.keep) != expected_block
        for i, (role, text) in enumerate(turns):
            if role == "user" and text:
                found = v.per_message.get(i)
                mismatch += bare.inspect(text).flagged != bool(found and found.flagged)
        print(f"{r['id']:22s} {r['label']:7s} {len(turns):>5d}  "
              f"{'no, blocked' if not v.keep else 'yes':18s} {', '.join(v.threats) or ''}")

    print("-" * 88)
    att = sum(1 for r in rows if r["label"] == "attack")
    print(f"{att} attacks, none of them reached the model; {len(rows) - att} clean, all of them did"
          if not wrong else f"{wrong} exchange(s) disagree with the detector - the set is broken, "
                            f"rebuild it with build_dialogs.py")
    print(f"turns where the wrapper and the bare detector disagree: {mismatch}   <- must be 0")
    return 1 if (wrong or mismatch) else 0


if __name__ == "__main__":
    raise SystemExit(main())
