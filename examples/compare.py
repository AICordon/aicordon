"""Run Picket and Intent on the example texts and print both results.

    python examples/compare.py                 # examples/texts/*
    python examples/compare.py my-letter.txt   # your files

Intent needs an API key (`aicordon login` or AICORDON_API_KEY). Without it the Intent column shows
"no key" and Picket still runs.
"""
from __future__ import annotations

import sys
from pathlib import Path

from aicordon import intent, picket

HERE = Path(__file__).resolve().parent


def main(paths: list[str]) -> int:
    files = [Path(p) for p in paths] or sorted((HERE / "texts").iterdir())
    fast = picket.load()
    full = intent.load() if intent.has_key() else None

    print(f"{'text':28} {'Picket (local rule)':32} Intent (API)")
    print("-" * 92)
    for path in files:
        text = path.read_text(encoding="utf-8")
        p = fast.check(text, doc_id=path.name)
        left = f"alarm  {p.threats[0]}" if p.flagged else "—"
        if full is None:
            right = "no key: aicordon login"
        else:
            a = full.assess(text, doc_id=path.name)
            if not a.judged:
                right = f"not judged ({a.reason})"
            else:
                top = max(a.spans, key=lambda s: s.p) if a.spans else None
                where = f"  «{text[top.start:top.end].strip()[:40]}…»" if a.flagged and top else ""
                right = f"{'alarm' if a.flagged else '—':5}  score {a.score:.2f}{where}"
        print(f"{path.name:28} {left:32} {right}")
    if full is not None:
        print(f"\nIntent {full.version}, operating point: the service default (FPR 1e-4).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
