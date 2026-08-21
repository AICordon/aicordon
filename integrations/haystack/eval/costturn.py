"""What checking ONE turn costs - the number a README reader scales to their own traffic.

Why not the difference between the two arms in `measure_dialog.py`: the pool there is mixed, 537
forum jailbreaks of several thousand characters against twenty thousand live turns. A mean over that
mixture describes the measurement, not traffic, and will not reproduce elsewhere. Here the pool is
live WildChat turns only, with the length the cost depends on shown alongside.

FOUR LEVELS, TO SEE WHERE EACH SHARE GOES:

    detector    bare `picket.check` - the check itself; this is Picket
    policy      + the role map and the verdict for the exchange (`DialogueGuard`) - our core
    component   + `run()`: reading message parts, copies, metadata - our wrapper
    pipeline    + `Pipeline.run()` - Haystack's dispatcher, somebody else's code

Messages are built BEFORE the timer starts: in a real pipeline a prompt builder assembles them, and
timing that would claim somebody else's expense as ours. `pipeline` is a line of its own for the
same reason - it is the host's per-step cost, paid by every component.

PROCEDURE, as in `experiments/40_prefilter/`: R repeats of the whole pool, the MEDIAN of the repeats
per turn (removes scheduler noise), then the distribution over turns. The uncertainty on the
headline number is the standard deviation of the per-repeat means. Cost drifts with machine load:
compare only figures from one procedure in one run.

    python eval/costturn.py --turns 3000 --repeat 5
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

import logging as _logging

from haystack import Pipeline
from haystack.dataclasses import ChatMessage
from haystack_integrations.components.validators.aicordon import PromptInjectionGuard

# Research corpus, not part of any release: it holds other people's turns. The path is the one on
# the machine this was measured on; pass `--data` to point somewhere else.
DIRECT = Path("/home/mike/Projects/ai-safity/experiments/45_picket_direct/data/direct.jsonl")
HERE = Path(__file__).resolve().parent
CLEAN_SLICE = "wildchat_user"
SYSTEM = "You are a helpful assistant."
BUCKETS = [(0, 200), (200, 500), (500, 1500), (1500, 4000), (4000, 10 ** 9)]


def pool(path: Path, n: int) -> list[str]:
    rows = [json.loads(l) for l in path.open() if f'"{CLEAN_SLICE}"' in l]
    rows = [r for r in rows if r["slice"] == CLEAN_SLICE and (r["text"] or "").strip()]
    return [r["text"] for r in rows[::max(1, len(rows) // n)][:n]]


def warm_up_cost(repeat: int) -> list[float]:
    """The one-off cost: raising the base. Paid once per process, not once per turn."""
    out = []
    for _ in range(repeat):
        guard = PromptInjectionGuard()
        t0 = time.perf_counter()
        guard.warm_up()
        out.append((time.perf_counter() - t0) * 1000)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", type=int, default=3000)
    ap.add_argument("--repeat", type=int, default=5)
    ap.add_argument("--data", type=Path, default=DIRECT, help="jsonl with `text` and `slice`")
    ap.add_argument("--json", default="result-costturn.json")
    a = ap.parse_args()

    # The component logs a warning per finding — here they only get in the way of the progress line.
    _logging.getLogger("haystack_integrations.components.validators.aicordon"
                       ".prompt_injection_guard").setLevel(_logging.ERROR)
    if not a.data.exists():
        raise SystemExit(f"no corpus at {a.data}: pass --data with a jsonl carrying the slice "
                         f"{CLEAN_SLICE!r}")
    turns = pool(a.data, a.turns)
    lengths = sorted(len(t) for t in turns)
    print(f"{len(turns)} turns, characters: median {lengths[len(lengths) // 2]}, "
          f"p90 {lengths[int(len(lengths) * 0.9)]}, max {lengths[-1]}", flush=True)

    from aicordon import picket
    det = picket.load(mode="dpi")
    component = PromptInjectionGuard()
    component.warm_up()
    guard = component._guard

    pipe = Pipeline()
    pipe.add_component("guard", PromptInjectionGuard())
    pipe.get_component("guard").warm_up()

    def bare(text: str) -> None:
        det.check(text)

    def policy(text: str) -> None:
        guard.decide([("system", SYSTEM), ("user", text)])

    # Messages built up front: assembling them is the prompt builder's expense, not the check's.
    built = {t: [ChatMessage.from_system(SYSTEM), ChatMessage.from_user(t)] for t in set(turns)}

    def wrapper(text: str) -> None:
        component.run(built[text])

    def wired(text: str) -> None:
        pipe.run({"guard": {"messages": built[text]}})

    levels = {"detector": bare, "policy": policy, "component": wrapper, "pipeline": wired}
    # Per turn, per level: the list of times across the repeats.
    samples = {name: [[] for _ in turns] for name in levels}
    for r in range(1, a.repeat + 1):
        for name, fn in levels.items():
            for i, text in enumerate(turns):
                t0 = time.perf_counter()
                fn(text)
                samples[name][i].append((time.perf_counter() - t0) * 1000)
        print(f"  repeat {r}/{a.repeat}", flush=True)

    out: dict = {"turns": len(turns), "repeats": a.repeat,
                 "chars_median": lengths[len(lengths) // 2],
                 "chars_p90": lengths[int(len(lengths) * 0.9)],
                 "base": guard.base_version, "levels": {}}
    for name in levels:
        per_turn = sorted(statistics.median(v) for v in samples[name])
        # The uncertainty on the headline number is the spread of the per-REPEAT means, not of the
        # turns: the turns differ in length, and their spread is the spread of traffic rather than
        # the uncertainty of the measurement.
        per_repeat_mean = [statistics.fmean(samples[name][i][r] for i in range(len(turns)))
                           for r in range(a.repeat)]
        out["levels"][name] = {
            "mean": statistics.fmean(per_turn),
            "sd_of_repeat_means": statistics.stdev(per_repeat_mean) if a.repeat > 1 else 0.0,
            "median": per_turn[len(per_turn) // 2],
            "p90": per_turn[int(len(per_turn) * 0.9)],
            "p99": per_turn[int(len(per_turn) * 0.99)],
            "max": per_turn[-1],
        }

    # The breakdown by length is taken at the top level — that is what the user pays.
    med = {i: statistics.median(v) for i, v in enumerate(samples["pipeline"])}
    out["by_length"] = []
    for lo, hi in BUCKETS:
        idx = [i for i, t in enumerate(turns) if lo <= len(t) < hi]
        if idx:
            out["by_length"].append({"from": lo, "to": None if hi > 10 ** 8 else hi,
                                     "turns": len(idx),
                                     "median_ms": statistics.median(med[i] for i in idx)})

    warm = warm_up_cost(a.repeat)
    out["warm_up_ms_median"] = statistics.median(warm)
    (HERE / a.json).write_text(json.dumps(out, ensure_ascii=False, indent=1))

    print()
    print(f"{'level':11s} {'mean':>16s} {'median':>9s} {'p90':>7s} {'p99':>7s} {'max':>8s}")
    for name, v in out["levels"].items():
        print(f"{name:11s} {v['mean']:8.2f} ± {v['sd_of_repeat_means']:.2f} ms "
              f"{v['median']:8.2f} {v['p90']:7.2f} {v['p99']:7.2f} {v['max']:8.1f}")
    lv = out["levels"]
    top = lv["pipeline"]["mean"]
    print(f"\nof {top:.2f} ms: detector {lv['detector']['mean']:.2f}, "
          f"policy {lv['policy']['mean'] - lv['detector']['mean']:+.2f}, "
          f"wrapper {lv['component']['mean'] - lv['policy']['mean']:+.2f}, "
          f"Haystack pipeline {top - lv['component']['mean']:+.2f}")
    print("\nby turn length (median, the whole path):")
    for b in out["by_length"]:
        rng = f"{b['from']}-{b['to']}" if b["to"] else f"{b['from']}+"
        print(f"  {rng:>12s} characters  {b['turns']:5d} turns  {b['median_ms']:6.2f} ms")
    print(f"\nloading the base, once: {out['warm_up_ms_median']:.0f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
