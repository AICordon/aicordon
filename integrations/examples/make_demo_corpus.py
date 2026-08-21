"""The demonstration corpus for the integrations: 500 documents, half of them infected.

THIS IS A SHOP WINDOW, NOT A MEASURE. The infected half is assembled so that most of it fires: the
examples in READMEs and catalogue cards have to show the thing working. The measured numbers come
from Quadrat and stand separately in those same documents — one must never be swapped for the other.
For the same reason the remainder is filled with RANDOM payloads: a set where everything is caught
misleads even with no intent to, because the reader carries away a hundred per cent as a property of
the tool rather than a property of the selection.

What is in it:

    250 infected   payloads that fire as they are; topped up inside service frames (a real technique,
                   `forged_frame`, not a tweak); the remainder random from the bank
    250 clean      the same carriers with nothing spliced in, in the same kinds and proportions

The payloads come from our own bank, which does NOT overlap the published Quadrat (texts compared:
0 matches), so the demonstrations do not cannibalise the measuring set.

EVERY CARRIER IS VERIFIED CLEAN before anything is spliced into it. Otherwise an "infected" document
could be firing because of the carrier, and the window would show something other than its caption
promises.

The carriers come from Quadrat's negatives: a letter, a document, a web page.

READMEs ARE NOT INCLUDED, although for RAG they are the liveliest carrier of all and the code that
assembles them is kept below. Measured over 600 documents of each kind: letter 0.0%, document 0.0%,
web page 0.0% — and README **10.5% firings on CLEAN text**. A README is written as instructions
("run this", "set the token", "IMPORTANT:", code blocks), and the rule sees the shape of an
instruction without knowing it is addressed to a human. Building a window on them would mean either
showing the noise or hiding it by selection. They are waiting for the base out of exp42, where those
false alarms are treated; their licences are already picked — none stricter than ours.

The layout is mirrored: from each (carrier kind, source) pair, equal numbers go to the infected and
the clean half — then no difference between the halves can be explained by composition.

    python3 make_demo_corpus.py         # -> corpus.jsonl + demo* marks in the bank
"""
from __future__ import annotations

import collections
import json
import os
import random
import re
from pathlib import Path

# The research corpora are NOT part of this repository — they hold material we do not ship. The
# default is where they sit on the machine this was built on: the repo nested inside the research
# tree. Point `AICORDON_RESEARCH_ROOT` elsewhere to rebuild from another checkout.
ROOT = Path(os.environ.get("AICORDON_RESEARCH_ROOT", Path(__file__).resolve().parents[4]))
HERE = Path(__file__).resolve().parent
BANK = ROOT / "datasets/injections_eu_bank.jsonl"
HOSTS = ROOT / "quadrat-ipi/dataset/v1.0.1/data/negatives.jsonl"
READMES = ROOT / "experiments/42_readme_carrier/data/hosts/readme_hosts.jsonl"
OUT = HERE / "corpus.jsonl"

N_INJECTED, N_CLEAN, SEED = 250, 250, 20260814
N_FRAMED = 200                     # how far to top up with frames; the rest is random
CARRIERS = ("email", "doc", "web")
INCLUDE_README = False             # see the header: 10.5% false alarms on clean READMEs
#: No stricter than Apache-2.0. MPL-2.0 is not in here: weak copyleft is copyleft all the same.
PERMISSIVE = {"mit", "apache-2.0", "bsd-3-clause", "bsd-2-clause", "isc", "unlicense", "cc0-1.0"}

#: Frames for topping up: the weak ones before the strong, so the set does not become a
#: demonstration of one rule five hundred times over.
FRAMES = [
    ("chat_template", "<|im_start|>system {t}<|im_end|>"),
    ("html_comment", "<!-- [SYSTEM]: {t} -->"),
    ("xml_system", "<system>{t}</system>"),
    ("system_marker", "[SYSTEM] {t}"),
]

SENTENCE_END = re.compile(r"[.!?](?=\s)")


def bank_key(r: dict, i: int) -> str:
    """Part of the bank (21 rows, `peerreview`) was entered with no `id` — the key is built from
    whatever there is."""
    return r.get("id") or r.get("root_id") or r.get("seed_hash") or f"{r.get('bank_part','?')}-{i}"


def splice(text: str, payload: str, rnd: random.Random) -> tuple[str, int, int, str]:
    """Splice the payload in the way Quadrat does: as a block of its own, into a sentence seam, or at
    the end.

    Three ways rather than one: a detector shown on postscripts answers a question about
    postscripts. The block between paragraphs dominates because that is how an injection arrives in
    a real document.
    """
    payload = payload.strip()
    roll = rnd.random()
    breaks = [i for i in range(len(text)) if text.startswith("\n\n", i)]
    ends = [m.end() for m in SENTENCE_END.finditer(text)]
    if roll < 0.55 and breaks:
        at, where, body = rnd.choice(breaks) + 2, "block", payload + "\n\n"
    elif roll < 0.80 and ends:
        at, where, body = rnd.choice(ends) + 1, "sentence", payload + " "
    else:
        at, where, body = len(text.rstrip()) + 1, "end", "\n\n" + payload
    start = at + (len(body) - len(payload) if where == "end" else 0)
    return text[:at] + body + text[at:], start, start + len(payload), where


def candidates(rnd: random.Random) -> dict[tuple[str, str], list[dict]]:
    """Carrier pools by (kind, source). Cleanliness is not checked here — it costs a run."""
    buckets: dict[tuple[str, str], list[dict]] = collections.defaultdict(list)
    for line in HOSTS.open():
        h = json.loads(line)
        if len(h["text"]) > 400 and h.get("host_type") in CARRIERS:
            buckets[(h["host_type"], h["host_source"])].append(
                {"text": h["text"], "host_type": h["host_type"], "host_source": h["host_source"],
                 "license": h.get("license"), "attribution": h.get("attribution")})
    for line in READMES.open() if INCLUDE_README else ():
        h = json.loads(line)
        if str(h.get("license", "")).lower() in PERMISSIVE and len(h["text"]) > 400:
            buckets[("readme", "github-readme")].append(
                {"text": h["text"], "host_type": "readme", "host_source": "github-readme",
                 "license": h["license"], "attribution": h.get("repo")})
    for v in buckets.values():
        rnd.shuffle(v)
    return buckets


def take_clean_hosts(det, buckets, rnd) -> tuple[list[dict], list[dict], int]:
    """Pick carriers, running the detector over EACH: any that fires while still clean is dropped."""
    total = N_INJECTED + N_CLEAN
    per_type = total // len(CARRIERS)
    injected, clean, dropped = [], [], 0
    for c in CARRIERS:
        keys = [k for k in buckets if k[0] == c]
        share, extra = divmod(per_type, len(keys))
        for i, k in enumerate(keys):
            need = share + (1 if i < extra else 0)
            need += need % 2                                   # even, so both halves get the same count
            taken = []
            for h in buckets[k]:
                if len(taken) >= need:
                    break
                if det.check(h["text"]).flagged:
                    dropped += 1
                    continue
                taken.append(h)
            injected += taken[0::2]
            clean += taken[1::2]
        print(f"  {c}: {sum(1 for h in injected + clean if h['host_type'] == c)} picked",
              flush=True)
    rnd.shuffle(injected)
    rnd.shuffle(clean)
    return injected, clean, dropped


def pick_payloads(det, en, keys, rnd) -> list[dict]:
    fires = [r for r in en if det.check(r["text"]).flagged]
    print(f"payloads that fire as they are: {len(fires)}", flush=True)
    out = [{"bank_id": keys[id(r)], "text": r["text"].strip(), "frame": None,
            "action": r.get("action"), "inj_type": r.get("inj_type")} for r in fires]
    used = {keys[id(r)] for r in fires}

    for name, tpl in FRAMES:
        for r in en:
            if len(out) >= N_FRAMED:
                break
            if keys[id(r)] in used:
                continue
            framed = tpl.format(t=r["text"].strip())
            if det.check(framed).flagged:
                used.add(keys[id(r)])
                out.append({"bank_id": keys[id(r)], "text": framed, "frame": name,
                            "action": r.get("action"), "inj_type": r.get("inj_type")})
        print(f"  after frame {name}: {len(out)}", flush=True)

    rest = [r for r in en if keys[id(r)] not in used]
    rnd.shuffle(rest)
    for r in rest[: N_INJECTED - len(out)]:
        out.append({"bank_id": keys[id(r)], "text": r["text"].strip(), "frame": None,
                    "action": r.get("action"), "inj_type": r.get("inj_type")})
    return out[:N_INJECTED]


def main() -> int:
    from aicordon import picket

    det = picket.load()
    rnd = random.Random(SEED)

    bank = [json.loads(l) for l in BANK.open()]
    en = [r for r in bank if r.get("lang") == "en" and (r.get("text") or "").strip()]
    keys = {id(r): bank_key(r, i) for i, r in enumerate(en)}

    injected_hosts, clean_hosts, dropped = take_clean_hosts(det, candidates(rnd), rnd)
    print(f"carriers: {len(injected_hosts)} to infect, {len(clean_hosts)} to leave clean; "
          f"dropped for firing while clean: {dropped}", flush=True)

    payloads = pick_payloads(det, en, keys, rnd)

    rows = []
    for i, p in enumerate(payloads):
        h = injected_hosts[i]
        text, lo, hi, where = splice(h["text"], p["text"], rnd)
        rows.append({"id": f"demo-inj-{i:03d}", "label": "injected", "text": text,
                     "inj_span": [lo, hi], "injection": p["text"], "bank_id": p["bank_id"],
                     "frame": p["frame"], "action": p["action"], "inj_type": p["inj_type"],
                     "spliced_at": where, "host_type": h["host_type"],
                     "host_source": h["host_source"], "host_license": h["license"],
                     "attribution": h["attribution"], "caught": bool(det.check(text).flagged)})
    for j, h in enumerate(clean_hosts[:N_CLEAN]):
        rows.append({"id": f"demo-clean-{j:03d}", "label": "clean", "text": h["text"],
                     "inj_span": None, "injection": None, "bank_id": None, "frame": None,
                     "action": None, "inj_type": None, "spliced_at": None,
                     "host_type": h["host_type"], "host_source": h["host_source"],
                     "host_license": h["license"], "attribution": h["attribution"],
                     "caught": False})

    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                   encoding="utf-8")

    marks = {r["bank_id"]: r for r in rows if r["bank_id"]}
    with BANK.open("w", encoding="utf-8") as fh:
        for i, r in enumerate(bank):
            m = marks.get(bank_key(r, i))
            r["demo"] = bool(m)
            if m:
                r["demo_frame"] = m["frame"]
                r["demo_caught"] = m["caught"]
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    inj = [r for r in rows if r["label"] == "injected"]
    clean = [r for r in rows if r["label"] == "clean"]
    caught = sum(1 for r in inj if r["caught"])
    print(f"\ncorpus: {len(rows)} documents - {len(inj)} infected, {len(clean)} clean")
    print(f"  fires on the infected: {caught} ({caught/len(inj):.0%})")
    print(f"  false alarms on the clean: {sum(1 for r in clean if r['caught'])}")
    for label, part in (("infected", inj), ("clean", clean)):
        print(f"  {label}: {dict(collections.Counter(r['host_type'] for r in part))}")
    print(f"-> {OUT}\n-> demo/demo_frame/demo_caught marks in {BANK.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
