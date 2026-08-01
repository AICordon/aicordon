"""exp40 — threat names and severities: derived from the SLOTS of a rule and written into the base.

Why a module of its own. Until now the threat name was assembled by a heuristic inside the CLI
engine, which broke SPEC §5: the name must be derivable from the rule artifact, otherwise `explain`
and `scan` drift apart at the first change of base, and a name printed yesterday cannot be matched
against the rule of today.

What lives here:

    TECHNIQUES   the table "slots -> family.technique", ordered by specificity
    signature()  the canonical fingerprint of a rule — names travel between base versions by it
    assign()     naming that keeps previous names by fingerprint
    annotate()   writing `threat`/`severity` into the base (the working point is not touched)

Name stability across base versions (SPEC §5) rests on the fingerprint, not on ordering: a rule that
survives reselection is recognised by its set of edges and keeps its variant letter; a rule that
drops out takes its letter with it, and the letter is not reused.

    python3 -m aicordon.picket.rule.threats --selftest
    python3 -m aicordon.picket.rule.threats --annotate <base>.json
    python3 -m aicordon.picket.rule.threats --catalog <base>.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
SLOTS = DATA / "slots"

HIGH, MEDIUM, LOW = "high", "medium", "low"

# The technique is determined by slots, and the order here is DESCENDING SPECIFICITY, not
# importance. A rule almost always carries several slots at once (SEND_VERB next to NEW_SECRET_MOD,
# say); the name comes from the first technique that matches, so what stands at the top is what says
# more about the rule: "send it outside" is more specific than "a new block started".
#
# Severity is a property of the TECHNIQUE, not of how strongly the rule fired (SPEC §6): the rule has
# no continuous score, there is nothing to grade with, and a scale must not be drawn out of nothing.
TECHNIQUES: list[tuple[str, str, str, tuple[str, ...], str]] = [
    # family      technique      severity  defining slots                      description
    ("Exfil", "Send", HIGH, ("SEND_VERB", "EXTERNAL_ADDR", "URL_REF"),
     "A demand to send content outside: by mail, by request, through a link. More dangerous than "
     "the rest, because the success of the attack is visible to the attacker, not to the user."),
    ("Secret", "Reveal", HIGH, ("REVEAL_VERB", "TARGET_SECRET", "NEW_SECRET_HEAD",
                                "NEW_SECRET_MOD"),
     "A demand to reveal the system instruction, a key, or other hidden content of the session."),
    ("Privilege", "Escalate", HIGH, ("NEW_PRIV_MOD",),
     "Claiming elevated rights: \"developer mode\", \"no restrictions\", \"full access\"."),
    ("System", "Marker", HIGH, ("SYSTEM_MARKER", "FRAME_MARKER"),
     "Forged control markup inside the document body: the text pretends to be a system message or "
     "a dialogue boundary so the model reads it as its owner's instruction rather than as data."),
    ("Override", "Cancel", MEDIUM, ("CANCEL_VERB", "SCOPE", "PRIOR_REF"),
     "Cancelling instructions received earlier: \"ignore everything above\", \"forget the previous "
     "instructions\"."),
    ("Persona", "Switch", MEDIUM, ("NEW_PERSONA_HEAD", "PERSONA"),
     "Substituting the identity of the actor: the document assigns the model another role or "
     "character."),
    ("Container", "Payload", MEDIUM, ("CONTAINER_REF", "NEW_PAYLOAD_FIELD", "NEW_CONTAINER_MOD",
                                      "NEW_STRIP_VERB", "NEW_SERIALIZE_VERB"),
     "Addressing the data envelope: a demand to extract, unwrap or hand over the content of a "
     "field, an attachment, a serialised structure."),
    ("Instruct", "Follow", MEDIUM, ("FOLLOW_VERB", "NEW_BLOCK_VERB"),
     "A direct demand to obey the instructions coming from the document."),
    ("Role", "Assign", MEDIUM, ("NEW_ROLE_WORD",),
     "Assigning the addressee: the document speaks to the model as the actor instead of "
     "describing it."),
    ("Chain", "Position", LOW, ("NEW_CHAIN_POS",),
     "Reordering instructions: \"from now on\", \"next\", \"first of all\"."),
    ("Block", "New", LOW, ("NEW_BLOCK_HEAD", "DATA_OBJECT"),
     "The start of a new directive block inside data, with no more specific marker."),
]

FALLBACK = ("Generic", "Relation", MEDIUM,
            "A relation between terms that fits no known technique. The name is temporary: a rule "
            "like this is a reason to extend the technique table.")

DESCRIPTIONS = {f"{fam}.{tech}": desc for fam, tech, _sev, _slots, desc in TECHNIQUES}
# Position in the table = how specific the technique is. Merging findings needs it: when several
# rules fire over one sentence, the block is named by the technique that says the most about the
# text. Only this module knows that ordering, so it is published rather than guessed downstream.
RANK = {f"IPI/{fam}.{tech}": i for i, (fam, tech, _s, _k, _d) in enumerate(TECHNIQUES)}


def rank(threat: str) -> int:
    """Specificity of a threat NAME (`IPI/Exfil.Send.A`); unknown names sort last."""
    return RANK.get(threat.rpartition(".")[0], len(TECHNIQUES))
DESCRIPTIONS[f"{FALLBACK[0]}.{FALLBACK[1]}"] = FALLBACK[3]

ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def slots_of(rule: dict) -> list[str]:
    """Every slot of a rule: the anchors and the fillers of both its edges."""
    out = []
    for e in rule["edges"]:
        out += [e["anchor"], e["filler"]]
    return out


def technique(rule: dict) -> tuple[str, str, str]:
    """(family, technique, severity) from the slots of a rule."""
    present = set(slots_of(rule))
    for fam, tech, sev, keys, _desc in TECHNIQUES:
        if present & set(keys):
            return fam, tech, sev
    return FALLBACK[0], FALLBACK[1], FALLBACK[2]


def signature(rule: dict) -> str:
    """The fingerprint of a rule: its set of edges, independent of the order they are written in.

    Names travel to a new version of the base by it. The order of edges in a conjunction carries no
    meaning (a rule is an AND), so the edges are sorted; distance and connective are part of the
    fingerprint, because a rule with a different distance is a DIFFERENT rule and must not inherit
    the name.
    """
    parts = sorted(f"{e['anchor']}|{e['filler']}|{e['side']}|{e['distance']}|{e['connective'] or ''}"
                   for e in rule["edges"])
    return "&".join(parts)


def assign(rules: list[dict], previous: list[dict] | None = None) -> list[dict]:
    """Fills in `threat`, `severity`, `signature`. Returns the same dicts (edited in place).

    `previous` — the rules of the previous base version, already named. A matching fingerprint
    carries the name over; the letters of rules that dropped out are not reused, otherwise a name
    from yesterday's report would mean a different rule tomorrow.
    """
    inherited: dict[str, str] = {}
    used: dict[str, set[str]] = {}
    for old in previous or []:
        name = old.get("threat")
        if not name:
            continue
        inherited[signature(old)] = name
        stem, _, letter = name.rpartition(".")
        used.setdefault(stem, set()).add(letter)

    for r in rules:
        sig = signature(r)
        fam, tech, sev = technique(r)
        stem = f"IPI/{fam}.{tech}"
        name = inherited.get(sig)
        if name is None:
            taken = used.setdefault(stem, set())
            letter = next((c for c in ALPHABET if c not in taken), None)
            if letter is None:                       # 26 rules of one technique — fall back to numbers
                letter = f"Z{len(taken)}"
            taken.add(letter)
            name = f"{stem}.{letter}"
        r["threat"] = name
        r["severity"] = sev
        r["signature"] = sig
    return rules


def catalog(spec: dict) -> dict[str, dict]:
    """Threat name -> severity, description, what it fires on. The basis of the `explain` command."""
    out: dict[str, dict] = {}
    for r in spec["rules"]:
        name = r.get("threat")
        if not name:
            continue
        stem = name.split("/", 1)[1].rpartition(".")[0]
        entry = out.setdefault(name, {
            "threat": name,
            "severity": r.get("severity", MEDIUM),
            "family": stem.split(".")[0],
            "technique": stem,
            "description": DESCRIPTIONS.get(stem, ""),
            "rules": [],
        })
        # What a name stands for, not how it is matched. The catalogue used to spell out the terms
        # of every rule, their order and their distance — a description of the technique on the
        # face of it and a recipe for walking around it in practice. The base itself is not
        # published for the same reason; printing it back out through `explain` would undo that.
        entry["rules"].append({"kind": r["kind"]})
    return dict(sorted(out.items()))


def annotate(path: Path) -> dict:
    """Writes the names into the base. Selection, edges and measured numbers are not touched."""
    spec = json.loads(path.read_text(encoding="utf-8"))
    before = json.dumps(spec["rules"], ensure_ascii=False, sort_keys=True)
    assign(spec["rules"], previous=spec["rules"])
    spec["threat_naming"] = {
        "scheme": "IPI/Family.Technique.Variant",
        "source": "threats.py — the table of techniques keyed by the slots of a rule",
        "stability": "a name travels to a new version of the base by the `signature` field",
    }
    path.write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    after = json.dumps([{k: v for k, v in r.items()
                         if k not in ("threat", "severity", "signature")} for r in spec["rules"]],
                       ensure_ascii=False, sort_keys=True)
    assert after == before, "annotation changed the rules themselves — that is not allowed"
    return spec


def _selftest() -> int:
    r_send = {"kind": "conjunction", "edges": [
        {"anchor": "NEW_BLOCK_HEAD", "filler": "SEND_VERB", "side": "R", "distance": "4-5",
         "connective": None},
        {"anchor": "SYSTEM_MARKER", "filler": "PRIOR_HEAD", "side": "R", "distance": "1",
         "connective": None}]}
    fam, tech, sev = technique(r_send)
    assert (fam, tech, sev) == ("Exfil", "Send", HIGH), (fam, tech, sev)

    r_block = {"kind": "single", "edges": [
        {"anchor": "NEW_BLOCK_HEAD", "filler": "DATA_OBJECT", "side": "R", "distance": "1",
         "connective": None}]}
    assert technique(r_block)[:2] == ("Block", "New")

    # The fingerprint does not depend on edge order: a rule is a conjunction, not a sequence.
    flipped = {"kind": "conjunction", "edges": list(reversed(r_send["edges"]))}
    assert signature(r_send) == signature(flipped)

    # Different rules of the same technique get different letters.
    r2 = {"kind": "single", "edges": [
        {"anchor": "SEND_VERB", "filler": "PRIOR_HEAD", "side": "R", "distance": "3",
         "connective": None}]}
    names = [r["threat"] for r in assign([dict(r_send), dict(r2)])]
    assert names == ["IPI/Exfil.Send.A", "IPI/Exfil.Send.B"], names

    # A name travels by fingerprint, and the letter of a departed rule is not reused.
    prev = assign([dict(r_send), dict(r2)])
    again = assign([dict(r2)], previous=prev)
    assert again[0]["threat"] == "IPI/Exfil.Send.B", again[0]["threat"]
    fresh = assign([dict(r_block), dict(r2)], previous=prev)
    assert fresh[1]["threat"] == "IPI/Exfil.Send.B"
    assert fresh[0]["threat"] == "IPI/Block.New.A"

    # Every technique has a description — otherwise `explain` prints an empty line.
    for fam, tech, _sev, _slots, desc in TECHNIQUES:
        assert desc.strip(), f"{fam}.{tech} has no description"

    print("threats.py: self-test passed", flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="threat names and severities for the rule artifact")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--annotate", type=Path, metavar="BASE")
    ap.add_argument("--catalog", type=Path, metavar="BASE")
    a = ap.parse_args()

    if a.selftest:
        return _selftest()
    if a.annotate:
        spec = annotate(a.annotate)
        cat = catalog(spec)
        print(f"rules {len(spec['rules'])}, threat names {len(cat)}", flush=True)
        for name, e in cat.items():
            print(f"  {name:<28} {e['severity']:<7} rules {len(e['rules'])}", flush=True)
        return 0
    if a.catalog:
        spec = json.loads(a.catalog.read_text(encoding="utf-8"))
        print(json.dumps(catalog(spec), ensure_ascii=False, indent=1), flush=True)
        return 0
    ap.error("pass --selftest, --annotate or --catalog")
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        sys.exit(0)
