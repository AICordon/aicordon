"""The shipped base: one file holding the automaton and the rules that run on it.

Why it exists. For a CLI called on one file, load time IS the run time: parsing a document costs
~1.9 ms while assembling the engine from the 16 dictionaries costs ~82 ms, and 45 of those are
spent rebuilding a trie that comes out identical every time. Shipping the built trie removes that
work: 12 ms instead of 82, with verdicts identical to the byte on the measurement set
(six storage formats were compared by load time, size AND verdict equality before this one was
chosen).

What is stored: `goto`/`fail`/`out` of the Aho-Corasick automaton, the names of the 136 slots, the
whole rule spec (rules, threat names, measured numbers, caveats), and a stamp of what it was built
from. `marshal` holds only lists, dicts, tuples, strings, ints and bools, and the dump was loaded
on 3.10, 3.11, 3.12 and 3.14 with identical results — the portability its documentation does not
promise was measured rather than assumed. Gzip is a deliberate trade: 365 KB instead of 1.7 MB on
disk for 2.3 ms of decompression.

The dictionaries and the rule file are BUILD INPUTS: they live where the base is built and are not
part of a release. This module is therefore two things at once — the loader every run goes through,
and the builder that only ever runs where the sources are.

    python3 -m aicordon.picket.rule.compiled --build --rules <base.json> --slots <dir>
    python3 -m aicordon.picket.rule.compiled --verify --rules <base.json> --slots <dir>
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import marshal
import sys
from pathlib import Path

from .ac import Automaton
from .l2 import Engine, inflect

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
SLOTS = DATA / "slots"


def artifact_for(rule_path: Path) -> Path:
    """The prebuilt automaton belonging to a base — derived from its name, never searched for.

    `rule_v1_20260731_b1.json` -> `engine_v1_20260731_b1.bin`. Deriving instead of globbing is what
    keeps a dump from a different freeze out of a run: there is exactly one name it can have, and
    if that file is missing the loader falls back to the dictionaries.
    """
    return rule_path.with_name(rule_path.name.replace("rule_", "engine_", 1)).with_suffix(".bin")


def find_artifact(rule_path: Path) -> Path:
    """Where the base built from this rule file actually lies: beside it, or in the package.

    Sources and release live apart — the rule file stays where bases are built, the built base
    ships inside the package — so both are looked at. The name is the same in either place, which
    is what keeps this a lookup rather than a search.
    """
    name = artifact_for(rule_path).name
    beside = rule_path.with_name(name)
    return beside if beside.is_file() else DATA / name

# Bumped when the layout of the dump changes. An older tool must refuse a newer dump rather than
# read it wrongly, so the check is equality, not "at least".
FORMAT = 1
MARSHAL_VERSION = 4


def source_files(directory: Path | None = None) -> list[Path]:
    """The dictionaries the frozen rule was measured on — the single definition of that list.

    `slots_override.v1.json` is a superseded revision and `slots_de_derived.json` a German
    experiment; neither took part in the frozen working point. The exclusion lives here alone: a
    second copy of this glob is exactly how the engine silently grew to 17 dictionaries once.

    An installed package holds no dictionaries: they are build inputs and stay where the base is
    built. The empty list is therefore a normal answer here, and the callers that need sources say
    so in their own words.
    """
    d = directory or SLOTS
    if not d.is_dir():
        return []
    return [f for f in sorted(d.glob("slots_*.json"))
            if ".v1." not in f.name and "_de_derived" not in f.name]


def literals(files: list[Path]) -> tuple[dict[str, list[str]], list[str]]:
    """Every literal that goes into the trie, sorted: (slot -> forms, forms written into patterns).

    This repeats `Engine.__init__` deliberately and must keep repeating it: the shipped trie has to
    contain what the measured engine contained, no more and no less. The template literals (`LIT:`)
    are part of that even though `scan` never matches templates — their hits mask tokens in
    `collect` and therefore change the distances inside edges. Leaving them out cost one disagreeing
    document out of 61 in the first run of the comparison.

    Sorting is what makes the build reproducible: iterating a set of strings gives a different
    order per process, which would change node numbering and thus the dump bytes on every rebuild.
    """
    slots: dict[str, list[str]] = {}
    templates: list[dict] = []
    for p in files:
        d = json.loads(p.read_text(encoding="utf-8"))
        for s in d["slots"]:
            slots.setdefault(s["slot"], [])
            slots[s["slot"]].extend(v for v in s["variants"] if v not in slots[s["slot"]])
        templates.extend(d["templates"])

    forms: dict[str, list[str]] = {}
    for slot, variants in slots.items():
        acc = set()
        for v in variants:
            acc.add(v.lower())
            if slot.endswith("_VERB"):
                acc |= inflect(v.lower())
        forms[slot] = sorted(acc)

    lits: set[str] = set()
    for t in templates:
        for seq in Engine._expand(Engine._parse(t["pattern"])):
            for slot, _gap in seq:
                if slot.startswith("LIT:"):
                    lits.add(slot[4:].lower())
    return forms, sorted(lits)


def assemble(forms: dict[str, list[str]], lits: list[str]) -> Engine:
    """An Engine with the trie built and no templates: `scan` goes through `hits()` only."""
    eng = Engine.__new__(Engine)
    eng.slots = {k: [] for k in forms}     # the names are what `scan` consults; variants are not
    eng.templates = []
    ac = Automaton()
    for slot in sorted(forms):
        for f in forms[slot]:
            ac.add(f, slot)
    for lit in lits:
        ac.add(lit, "LIT:" + lit)
    ac.build()
    eng.ac = ac
    return eng


def fingerprint(forms: dict[str, list[str]], lits: list[str]) -> str:
    """Hash of the literal set itself, independent of node numbering and of build order.

    Comparing dumps byte for byte would not work as a check — two correct builds may number nodes
    differently — so what gets compared is what the trie was built FROM.
    """
    h = hashlib.sha256()
    for slot in sorted(forms):
        for f in forms[slot]:
            h.update(f"{slot}\t{f}\n".encode("utf-8"))
    for lit in lits:
        h.update(f"LIT\t{lit}\n".encode("utf-8"))
    return h.hexdigest()


def shipped_spec(spec: dict) -> dict:
    """The base as it goes out: everything except how it was selected.

    `provenance` names the statistics files and the criterion the rules were picked by — a recipe
    for the base, useful in the research record and pointless to anyone running the tool. What
    stays is what the product actually stands behind: the rules, their names, the measured numbers
    and the split those numbers were measured on, because a number without its denominator is not
    a number.
    """
    return {k: v for k, v in spec.items() if k != "provenance"}


def dumps(eng: Engine, files: list[Path], spec: dict, fp: str) -> bytes:
    """The artifact carries the WHOLE base: the automaton and the rules that run on it.

    It used to carry only the trie, with the rules read from a JSON file beside it. That split does
    not survive shipping: the dictionaries and the rule file are build inputs, they are not part of
    a release, and `explain`/`coverage` would then have no threat names and no measured numbers to
    print. One file, one base, one thing to name in a report.
    """
    return marshal.dumps({
        "format": FORMAT,
        "rule_version": spec["version"],
        "spec": shipped_spec(spec),
        "dictionaries": [{"name": p.name,
                          "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in files],
        "engine": {"dictionaries": len(files), "slots": len(eng.slots)},
        "fingerprint": fp,
        "phrases": eng.ac.n_phrases,
        "nodes": len(eng.ac.goto),
        "slots": sorted(eng.slots),
        "goto": eng.ac.goto,
        "fail": eng.ac.fail,
        "out": eng.ac.out,
    }, MARSHAL_VERSION)


def restore(d: dict) -> Engine:
    ac = Automaton.__new__(Automaton)
    ac.goto, ac.fail, ac.out = d["goto"], d["fail"], d["out"]
    ac.n_phrases, ac._built = d["phrases"], True
    eng = Engine.__new__(Engine)
    eng.slots = {k: [] for k in d["slots"]}
    eng.templates = []
    eng.ac = ac
    return eng


def load(path: Path, spec: dict | None = None) -> tuple[Engine, dict] | None:
    """The base as shipped: (engine, spec), or None when this file cannot serve as one.

    None is an answer, not an error, because the caller decides what it means. For a release
    install it means the detector does not come up (exit code 3); in a development tree, where the
    dictionaries are at hand, it means "assemble from them instead".

    The per-run check is cheap on purpose: the layout of the dump and, when a separate spec was
    passed alongside, that the two describe the same base. Hashing the dictionaries would mean
    reading all 519 KB of them on every run — the very cost this artifact exists to avoid; the full
    check is what `--verify` is for, and it needs the sources.
    """
    try:
        d = marshal.loads(gzip.decompress(path.read_bytes()))
        if d.get("format") != FORMAT:
            return None
        inside = d.get("spec")
        if spec is None:
            spec = inside
        elif d.get("rule_version") != spec.get("version"):
            return None
        elif d.get("engine") != {"dictionaries": spec["engine"]["dictionaries"],
                                 "slots": spec["engine"]["slots"]}:
            return None
        if not isinstance(spec, dict) or "rules" not in spec:
            return None
        return restore(d), spec
    except Exception:
        return None


def write(path: Path | None = None, spec_path: Path | None = None,
          slots_dir: Path | None = None) -> dict:
    from .scan import pick_base                 # here, not at module level: `scan` imports us
    spec_path = spec_path or pick_base(kind="json")
    path = path or DATA / artifact_for(spec_path).name
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    files = source_files(slots_dir)
    if not files:
        raise SystemExit(f"no dictionaries in {slots_dir or SLOTS}: the base is built where its "
                         f"sources live, not from an installed package")
    forms, lits = literals(files)
    eng = assemble(forms, lits)
    if len(eng.slots) != spec["engine"]["slots"] or len(files) != spec["engine"]["dictionaries"]:
        raise SystemExit(f"the dictionaries no longer match the frozen rule: "
                         f"{len(files)} dictionaries / {len(eng.slots)} slots against "
                         f"{spec['engine']['dictionaries']} / {spec['engine']['slots']}")
    blob = dumps(eng, files, spec, fingerprint(forms, lits))
    path.write_bytes(gzip.compress(blob, 9))
    return {"path": str(path), "raw": len(blob), "gz": path.stat().st_size,
            "phrases": eng.ac.n_phrases, "nodes": len(eng.ac.goto), "slots": len(eng.slots)}


def verify(path: Path | None = None, spec_path: Path | None = None,
           slots_dir: Path | None = None) -> list[str]:
    """The full check: the artifact against the sources on disk. Returns the problems found.

    A check for whoever BUILDS a base, not for whoever runs it: it needs the dictionaries and the
    rule file, and a release install has neither.
    """
    from .scan import pick_base
    spec_path = spec_path or pick_base(kind="json")
    path = path or find_artifact(spec_path)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    problems: list[str] = []
    try:
        d = marshal.loads(gzip.decompress(path.read_bytes()))
    except Exception as e:
        return [f"the artifact is unreadable: {e}"]
    if d.get("format") != FORMAT:
        problems.append(f"format {d.get('format')}, expected {FORMAT}")
    if d.get("rule_version") != spec["version"]:
        problems.append(f"built for rule {d.get('rule_version')}, on disk {spec['version']}")
    if d.get("spec") != shipped_spec(spec):
        problems.append("the rules inside the artifact differ from the rule file")

    files = source_files(slots_dir)
    if not files:
        return problems + [f"no dictionaries in {slots_dir or SLOTS} — nothing to check against"]
    have = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    was = {r["name"]: r["sha256"] for r in d.get("dictionaries", [])}
    for name in sorted(set(have) | set(was)):
        if name not in was:
            problems.append(f"{name}: appeared after the build")
        elif name not in have:
            problems.append(f"{name}: was built in but is gone")
        elif have[name] != was[name]:
            problems.append(f"{name}: changed since the build")

    forms, lits = literals(files)
    fp = fingerprint(forms, lits)
    if d.get("fingerprint") != fp:
        problems.append("the literal set differs from the dictionaries — rebuild the artifact")
    eng = assemble(forms, lits)
    if d.get("phrases") != eng.ac.n_phrases or d.get("nodes") != len(eng.ac.goto):
        problems.append(f"trie size {d.get('phrases')}/{d.get('nodes')} against "
                        f"{eng.ac.n_phrases}/{len(eng.ac.goto)} rebuilt")
    if sorted(d.get("slots", [])) != sorted(eng.slots):
        problems.append("the slot set differs from the dictionaries")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="the shipped base: build it, or check it against "
                                             "its sources (a tool for building, not for running)")
    ap.add_argument("--build", action="store_true", help="rebuild the artifact from its sources")
    ap.add_argument("--verify", action="store_true", help="check the artifact against its sources")
    ap.add_argument("--path", type=Path, default=None, help="the artifact; derived from the rule "
                                                            "file when not given")
    ap.add_argument("--rules", type=Path, default=None, help="the rule file to build from")
    ap.add_argument("--slots", type=Path, default=None, help="the directory of dictionaries")
    a = ap.parse_args()
    if a.build:
        info = write(a.path, a.rules, a.slots)
        print(f"written {info['path']}: {info['gz']/1024:.0f} KB gzip "
              f"({info['raw']/1024:.0f} KB raw), {info['slots']} slots, "
              f"{info['phrases']} phrases, {info['nodes']} nodes", flush=True)
    if a.verify or not a.build:
        problems = verify(a.path, a.rules, a.slots)
        for p in problems:
            print(f"MISMATCH: {p}", file=sys.stderr, flush=True)
        if problems:
            return 1
        print("the artifact matches the dictionaries", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
