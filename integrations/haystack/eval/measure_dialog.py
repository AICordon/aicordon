"""Acceptance measurement of the request side: how many attacks reach the model, at what price.

WHAT IS MEASURED, AND WHY NOT RECALL. The detector's detection rate is published already
(`docs/eval/direct-jailbreaks-2026-08.md`). An integration answers a different question: of the
turns that entered the pipeline, how many REACHED THE GENERATOR, and how many real users were left
without an answer. That is a property of the wrapper - which role is read, with which rule set,
whether the exchange goes as a whole.

THE THIRD NUMBER OUTRANKS THE FIRST TWO: the pipeline and the bare detector must differ ZERO times
on the same string. A wrapper may neither lose text (part of a message, a truncated tail) nor add
its own. If that number is not zero, the rest must not be read.

THE POOLS. Attacks: the held-out half of `jb_wild` + `jb_public`, selected as in exp45/tune - half
by md5 of `id`, then near-duplicates dropped by five-word shingles, Jaccard > 0.3. Public jailbreaks
are variations on one DAN, and without that cleaning the figure runs about 8 points high. Clean
turns: `wildchat_user` from the same held-out half.

THE CLEAN POOL IS NOT CLEAN, and no correction is applied. WildChat carries no attack labels, and
real jailbreaks sit inside the negative pool: in the published run, 41 of the 144 turns flagged by
every detector were attacks. So "left without an answer" below is an UPPER BOUND on the price, not a
false-positive rate.

    python eval/measure_dialog.py --turns 20000
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import time
import zlib
from pathlib import Path
from typing import Any

import logging as _logging

from haystack import Pipeline, component
from haystack.dataclasses import ChatMessage
from haystack_integrations.components.validators.aicordon import PromptInjectionGuard

# Research corpus, not part of any release: it holds other people's turns. The path is the one on
# the machine this was measured on; pass `--data` to point somewhere else.
DIRECT = Path("/home/mike/Projects/ai-safity/experiments/45_picket_direct/data/direct.jsonl")
HERE = Path(__file__).resolve().parent
ATTACK_SLICES = ("jb_wild", "jb_public")
CLEAN_SLICE = "wildchat_user"
SYSTEM = "You are a helpful assistant."


@component
class Reached:
    """Stands where the generator would and only counts: arriving here means the model was called."""

    def __init__(self) -> None:
        self.seen: list[str] = []

    @component.output_types(replies=list[ChatMessage])
    def run(self, messages: list[ChatMessage]) -> dict[str, Any]:
        self.seen.append(messages[-1].meta.get("turn_id", ""))
        return {"replies": []}


def held_out(rows: list[dict]) -> list[dict]:
    """The held-out half, minus anything with a near-duplicate in the training half.

    The same selection as exp45/tune, so the numbers here and there are about the same texts."""
    half = lambda k: int(hashlib.md5(k.encode()).hexdigest(), 16) % 2 == 0   # noqa: E731

    def shingles(text: str, k: int = 5) -> set[int]:
        words = re.findall(r"[a-z']+", text.lower())
        return {zlib.crc32(" ".join(words[i:i + k]).encode())
                for i in range(max(0, len(words) - k + 1))}

    train = [(r, shingles(r["text"])) for r in rows if half(r["id"])]
    index: dict[int, list[int]] = collections.defaultdict(list)
    for i, (_, s) in enumerate(train):
        for x in list(s)[:400]:
            index[x].append(i)
    out = []
    for r in rows:
        if half(r["id"]):
            continue
        s = shingles(r["text"])
        hits: collections.Counter = collections.Counter()
        for x in list(s)[:400]:
            for i in index.get(x, ()):
                hits[i] += 1
        near = max((n / max(1, len(s | train[i][1])) for i, n in hits.most_common(5)), default=0.0)
        if near <= 0.3:
            out.append(r)
    return out


def build(guarded: bool) -> tuple[Pipeline, Reached]:
    """Both arms are one pipeline; the guarded one has a single component more in it."""
    reached = Reached()
    pipe = Pipeline()
    pipe.add_component("llm", reached)
    if guarded:
        pipe.add_component("guard", PromptInjectionGuard())      # mode="drop" is the default
        pipe.connect("guard.messages", "llm.messages")
    return pipe, reached


def run_arm(turns: list[dict], guarded: bool) -> tuple[set[str], float]:
    pipe, reached = build(guarded)
    entry = "guard" if guarded else "llm"
    t0 = time.perf_counter()
    for n, r in enumerate(turns, 1):
        messages = [ChatMessage.from_system(SYSTEM),
                    ChatMessage.from_user(r["text"], meta={"turn_id": r["id"]})]
        pipe.run({entry: {"messages": messages}})
        if n % 2000 == 0 or n == len(turns):
            print(f"  {'with the guard' if guarded else 'without it'}: {n}/{len(turns)}", flush=True)
    return set(reached.seen), time.perf_counter() - t0


def main() -> int:
    # The component logs a warning per finding — there are hundreds here, and they bury the progress.
    _logging.getLogger("haystack_integrations.components.validators.aicordon"
                       ".prompt_injection_guard").setLevel(_logging.ERROR)
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", type=int, default=20000, help="clean turns; every attack is taken")
    ap.add_argument("--data", type=Path, default=DIRECT, help="jsonl with `id`, `text`, `slice`")
    ap.add_argument("--json", default="result-dialog.json")
    a = ap.parse_args()

    if not a.data.exists():
        raise SystemExit(f"no corpus at {a.data}: pass --data with a jsonl carrying the slices "
                         f"{ATTACK_SLICES} and {CLEAN_SLICE!r}")
    rows = [json.loads(l) for l in a.data.open()]
    attacks = held_out([r for r in rows if r["slice"] in ATTACK_SLICES])
    clean = [r for r in rows if r["slice"] == CLEAN_SLICE]
    clean = clean[::max(1, len(clean) // a.turns)][:a.turns]
    print(f"{len(attacks)} held-out attacks, {len(clean)} clean turns", flush=True)

    turns = attacks + clean
    base_seen, base_s = run_arm(turns, guarded=False)
    guard_seen, guard_s = run_arm(turns, guarded=True)

    # Against the bare detector: the wrapper is obliged to see exactly the same string. A turn is a
    # mismatch when it was flagged AND reached the model, or was not flagged AND did not.
    from aicordon import picket
    det = picket.load(mode="dpi")
    mismatch = [r["id"] for r in turns
                if det.check(r["text"]).flagged == (r["id"] in guard_seen)]

    a_ids = {r["id"] for r in attacks}
    c_ids = {r["id"] for r in clean}
    a_before, a_after = len(a_ids & base_seen), len(a_ids & guard_seen)
    c_before, c_after = len(c_ids & base_seen), len(c_ids & guard_seen)

    out = {
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
