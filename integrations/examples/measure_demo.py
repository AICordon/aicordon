"""Числа НА ДЕМОНСТРАЦИОННОМ наборе: что показывает витрина, если её честно померить.

Эти числа нельзя выдавать за качество детектора — набор витринный, заражённая половина подобрана
из срабатывающих. Они отвечают на другой вопрос: «то, что читатель сейчас увидит в примере, — оно
вообще работает и не шумит?» Мерные числа берутся с квадрата и живут в README интеграции рядом.

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
    rows = [json.loads(l) for l in (HERE / "corpus.jsonl").open()]
    guard = InjectionGuard(mode="redact")
    guard.warm_up()

    by_host = collections.defaultdict(lambda: [0, 0, 0])     # носитель -> [снесено, тронуто, всего]
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

    print(f"документов {len(rows)} ({n_inj} заражённых), {seconds:.1f} с "
          f"({seconds / len(rows) * 1000:.1f} мс на документ)\n")
    print(f"нагрузка снесена целиком : {gone}/{n_inj} ({gone / n_inj:.0%})")
    print(f"нагрузка тронута         : {touched}/{n_inj} ({touched / n_inj:.0%})")
    print(f"ложные на чистых         : {fp}/{len(rows) - n_inj}\n")
    print(f"{'носитель':10s} {'снесено':>9s} {'тронуто':>9s} {'n':>5s}")
    for h, (g, t, n) in sorted(by_host.items(), key=lambda x: -x[1][0] / max(1, x[1][2])):
        print(f"{h:10s} {g / n:>8.0%} {t / n:>9.0%} {n:>5d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
