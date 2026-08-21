"""Run the ten demonstration DOCUMENTS through the detector and show every one of them.

Ten is the whole point. A window you can read in a minute says what a corpus of five hundred cannot:
which document fired, which rule fired on it, and how much of it the redaction took away. Nothing is
averaged here, because an average over ten examples is a number pretending to be a measurement.

The measured numbers are somewhere else and are meant to stay there: Quadrat-IPI, 16 800 injections
across three carriers, https://huggingface.co/datasets/mihailgribov/quadrat-ipi. This set is picked
so that every example behaves — that is what a shop window is, and reading recall off it would be
reading the selection.

    python3 show_material.py
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

from aicordon.guard import InjectionGuard          # noqa: E402


def main() -> int:
    manifest = HERE / "manifest.jsonl"
    if not manifest.exists():
        raise SystemExit("no manifest.jsonl here: build the set with `python3 build.py` first")
    rows = [json.loads(l) for l in manifest.open()]
    guard = InjectionGuard(mode="redact")
    guard.warm_up()

    print(f"{'document':22s} {'label':9s} {'verdict':9s} {'cut':>6s}  what fired")
    print("-" * 78)
    wrong = 0
    for r in rows:
        text = (HERE / r["file"]).read_text(encoding="utf-8")
        v = guard.inspect(text)
        expected = r["label"] == "injected"
        wrong += v.flagged != expected
        cut = len(text) - len(v.text)
        print(f"{r['id']:22s} {r['label']:9s} {'FIRED' if v.flagged else 'quiet':9s} "
              f"{(str(cut) + 'c') if cut else '-':>6s}  {', '.join(v.threats) or ''}")

    print("-" * 78)
    inj = sum(1 for r in rows if r["label"] == "injected")
    print(f"{inj} infected, all of them caught; {len(rows) - inj} clean, none of them flagged"
          if not wrong else f"{wrong} example(s) disagree with the detector - the set is broken, "
                            f"rebuild it with build.py")
    return 1 if wrong else 0


if __name__ == "__main__":
    raise SystemExit(main())
