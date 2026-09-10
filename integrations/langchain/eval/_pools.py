"""The corpora these measurements stand on, and the two functions every arm needs.

Research corpora, not part of any release: one holds other people's chat turns, the other is the
public Quadrat-IPI set. Point at them with `AICORDON_DIRECT_CORPUS` and `AICORDON_QUADRAT_DIR`, or
pass `--data` to any script.
"""
from __future__ import annotations

import collections
import hashlib
import json
import os
import re
import zlib
from difflib import SequenceMatcher
from pathlib import Path

#: Typed attacks and real user turns: a jsonl with `id`, `text` and `slice`.
DIRECT = Path(os.environ.get("AICORDON_DIRECT_CORPUS", "direct.jsonl"))
#: Documents with a known planted span: the `data` directory of Quadrat-IPI v1.0.1.
QUADRAT = Path(os.environ.get("AICORDON_QUADRAT_DIR", "quadrat-ipi/data"))

ATTACK_SLICES = ("jb_wild", "jb_public")
CLEAN_SLICE = "wildchat_user"


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def held_out(rows: list[dict]) -> list[dict]:
    """The held-out half, minus anything with a near-duplicate in the training half.

    The same selection as the detector's direct-mode report, so the numbers here and there are
    about the same texts. The
    cleaning is not tidiness: public jailbreaks are variations on one DAN, and without it the figure
    runs about eight points high.
    """
    def half(key: str) -> bool:
        return int(hashlib.md5(key.encode()).hexdigest(), 16) % 2 == 0

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


def survival(payload: str, seen: str) -> float:
    """Share of the payload still there: 1.0 verbatim, 0.0 gone without a trace."""
    p = norm(payload)
    if not p:
        return 0.0
    if p in seen:
        return 1.0
    match = SequenceMatcher(None, p, seen, autojunk=False).find_longest_match(0, len(p), 0, len(seen))
    # A run shorter than this is language, not payload: any two English texts share "of the", and
    # counting that as a surviving fragment would make the cut look worse than it is.
    return match.size / len(p) if match.size >= 25 else 0.0


def load_direct(path: Path, turns: int) -> tuple[list[dict], list[dict]]:
    if not path.exists():
        raise SystemExit(f"no corpus at {path}: pass --data with a jsonl carrying the slices "
                         f"{ATTACK_SLICES} and {CLEAN_SLICE!r}")
    rows = [json.loads(line) for line in path.open()]
    attacks = held_out([r for r in rows if r["slice"] in ATTACK_SLICES])
    clean = [r for r in rows if r["slice"] == CLEAN_SLICE]
    clean = clean[::max(1, len(clean) // turns)][:turns]
    return attacks, clean


def load_quadrat(path: Path, docs: int,
                 action: str | None = None) -> tuple[list[dict], list[dict], dict[str, str]]:
    """Injected documents, clean ones, and the planted payload of each injected one.

    `action` slices the positives along the goal axis. A separate number for `disclose` is not
    cherry-picking but the answer to a different question — what the integration does WHERE the
    rules are strong — and a report has to carry it beside the figure for the whole corpus, because
    on its own a slice reads as the result over the whole set.
    """
    if not path.is_dir():
        raise SystemExit(f"no corpus at {path}: pass --data, or fetch Quadrat-IPI from "
                         f"https://huggingface.co/datasets/mihailgribov/quadrat-ipi")
    pos = [json.loads(line) for line in (path / "positives.jsonl").open()]
    neg = [json.loads(line) for line in (path / "negatives.jsonl").open()]
    if action:
        wanted = {x.strip() for x in action.split(",")}
        pos = [r for r in pos if r.get("action") in wanted]
        print(f"slice: action in {sorted(wanted)}, {len(pos)} available", flush=True)
    pos = pos[::max(1, len(pos) // docs)][:docs]
    neg = neg[::max(1, len(neg) // docs)][:docs]
    payload = {}
    for r in pos:
        lo, hi = json.loads(r["inj_span"]) if isinstance(r["inj_span"], str) else r["inj_span"]
        payload[r["id"]] = r["text"][lo:hi]
    return pos, neg, payload
