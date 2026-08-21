"""Numbers on the DEMONSTRATION set: what the shop window shows when it is measured honestly.

These must not be passed off as the detector's quality — the set is a shop window, and its infected
half was picked from what fires. They answer a different question: "the thing the reader is about to
see in the example — does it work at all, and is it quiet?" The measured numbers come from Quadrat
and live in the integration README next door.

    python3 measure_demo.py
"""
from __future__ import annotations

import collections
import json
import re
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path

HERE = Path(__file__).resolve().parent

from aicordon.guard import InjectionGuard          # noqa: E402


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def survival(payload: str, text: str) -> float:
    p, t = norm(payload), norm(text)
    if not p:
        return 0.0
    if p in t:
        return 1.0
    m = SequenceMatcher(None, p, t, autojunk=False).find_longest_match(0, len(p), 0, len(t))
    return m.size / len(p) if m.size >= 25 else 0.0


def main() -> int:
    corpus = HERE / "corpus.jsonl"
    if not corpus.exists():
        # 2.7 MB of third-party carrier text: it is not in the repository. Rebuilding needs the
        # injection bank, which is not in it either — this window is reproducible by us, not by a
        # reader, and saying so is better than a traceback about a missing file.
        raise SystemExit(f"no {corpus.name} here: build it with make_demo_corpus.py, which needs "
                         f"the injection bank (not part of this repository)")
    rows = [json.loads(l) for l in corpus.open()]
    guard = InjectionGuard(mode="redact")
    guard.warm_up()

    by_host = collections.defaultdict(lambda: [0, 0, 0])     # carrier -> [gone, touched, total]
    fp, gone, touched, n_inj = 0, 0, 0, 0
    t0 = time.perf_counter()
    for r in rows:
        v = guard.inspect(r["text"])
        if r["label"] == "clean":
            fp += v.flagged
            continue
        n_inj += 1
        payload = r["text"][r["inj_span"][0]:r["inj_span"][1]]
        left = survival(payload, v.text)
        gone += left < 0.10
        touched += left < 0.99
        b = by_host[r["host_type"]]
        b[0] += left < 0.10
        b[1] += left < 0.99
        b[2] += 1
    seconds = time.perf_counter() - t0

    print(f"{len(rows)} documents ({n_inj} infected), {seconds:.1f} s "
          f"({seconds / len(rows) * 1000:.1f} ms per document)\n")
    print(f"payload gone entirely : {gone}/{n_inj} ({gone / n_inj:.0%})")
    print(f"payload touched       : {touched}/{n_inj} ({touched / n_inj:.0%})")
    print(f"false alarms on clean : {fp}/{len(rows) - n_inj}\n")
    print(f"{'carrier':10s} {'gone':>9s} {'touched':>9s} {'n':>5s}")
    for h, (g, t, n) in sorted(by_host.items(), key=lambda x: -x[1][0] / max(1, x[1][2])):
        print(f"{h:10s} {g / n:>8.0%} {t / n:>9.0%} {n:>5d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
