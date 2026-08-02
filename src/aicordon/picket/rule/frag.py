"""Fragment parsing primitives: tokens, entity terms, surroundings, edges.

Split out of `termstat.py` so that collecting the statistics and checking the rule run through ONE
piece of code. A copy here would be the worst kind of mistake: the rule would be measured with
something other than what built it, and the divergence would surface as "the rule does not
reproduce" rather than as a difference between two implementations.

LANGUAGE MARK: `LANG(en)` — depends on English, `LANG(any)` — portable.
"""
from __future__ import annotations

import bisect
import collections
import re

from . import ent

WORD = re.compile(r"[^\W\d_]+|\d+", re.UNICODE)   # LANG(any): by Unicode properties, not by alphabet
MAXD = 8                 # LANG(en): window in tokens; in synthetic languages the same semantic
                         # distance takes fewer tokens, so the value would need recomputing
PARA = re.compile(r"\n[ \t]*\n")                  # LANG(any): a paragraph is a property of markup


def crosses(breaks, a: int, b: int) -> bool:
    """Is there a paragraph break inside [a, b)?

    `breaks` is sorted, so the question is answered by two binary searches instead of a scan. That
    is not micro-optimisation: the check sits inside the per-hit, per-token loop, and scanning the
    whole list made the pass quadratic in document length. Measured on a 128 KB page: 38 million
    comparisons, about 3.3 of the 4.4 seconds it took. Long HTML pages are exactly what this is
    pointed at, so the cost showed up where it hurts.
    """
    return bisect.bisect_left(breaks, a) != bisect.bisect_left(breaks, b)


def bucket(d: int) -> str:
    """Distance in tokens -> a positional class. Near positions are told apart, far ones merged.

    LANG(en): the bucket edges were chosen for English word order; the mechanism itself is portable.
    """
    return "1" if d == 1 else "2" if d == 2 else "3" if d == 3 else "4-5" if d <= 5 else "6-8"


EntHit = collections.namedtuple("EntHit", "lo hi slot")


def tokens_of(low: str):
    """Document tokens with entities folded in: (start, end, token) plus the entities themselves.

    LANG(any): the entities of `ent.py` (address, URL, IBAN, path, command) have no language — they
    are the most portable part of the dictionary.
    """
    out: list[tuple[int, int, str]] = []
    spans: list[tuple[int, int]] = []
    ents = []
    for e in ent.find(low):
        if any(not (e.hi <= a or e.lo >= b) for a, b in spans):
            continue                       # entities of different kinds may overlap; the token is one
        spans.append((e.lo, e.hi))
        out.append((e.lo, e.hi, f"<{e.kind}>"))
        ents.append(e)
    for m in WORD.finditer(low):
        lo, hi = m.span()
        if any(not (hi <= a or lo >= b) for a, b in spans):
            continue
        out.append((lo, hi, m.group(0)))
    out.sort(key=lambda t: t[0])
    return out, ents


def ent_hits(ents, hits, slots) -> list:
    """Entities as FULL terms wherever their kind is named as a slot of the dictionary.

    Without this the masking is inconsistent: `EXTERNAL_ADDR` is listed in `slots_exfil.json` as 53
    literals (`@gmail.com`, `@yahoo.com`, …), so an address at gmail becomes a hit and gets masked
    as a neighbour, while an address on an unknown domain stays an ordinary token in the
    surroundings. The same address is a term or context depending on whether its domain made it
    into a handwritten list. The rule covers the open class whole; the list stays its special case.
    """
    out = [EntHit(e.lo, e.hi, e.kind) for e in ents if e.kind in slots]
    return out


def collapse_runs(hits) -> list:
    """Хиты одного слота на ОДНОЙ И ТОЙ ЖЕ словесной позиции — один термин, а не сотня.

    Найдено замером скорости на реальных документах. Словарь границ содержит `---`, `----`,
    `-----`; обычная разделительная линия в подписи письма даёт по хиту почти на каждый символ:
    2 084 хита на письме в 3 КБ при обычных семидесяти на тысячу символов. Дальше они попарно
    перебираются в `pairs`, и документ считается две секунды вместо трёх миллисекунд.

    Ключ схлопывания — (слот, начало, конец) В СЛОВАХ, а не перекрытие в символах. Это не
    придирка к формулировке, а условие безвредности: все расстояния правила считаются в словах,
    поэтому два хита одного слота, занимающих одни и те же словесные позиции, для правила
    неразличимы — остаётся самый длинный. Схлопывание по перекрытию СИМВОЛОВ, наоборот,
    отбрасывает хиты, стоящие на разных словах, и роняет recall (замерено: 19.8% → 12.2% на почте).

    Разные слоты не трогаются: там перекрытие содержательно.
    """
    best: dict[tuple, object] = {}
    for h in hits:
        key = (h.slot, h.w_start, h.w_end)
        prev = best.get(key)
        if prev is None or (h.hi - h.lo) > (prev.hi - prev.lo):
            best[key] = h
    out = list(best.values())
    out.sort(key=lambda h: (h.lo, h.hi))
    return out


def merge_hits(raw, ents, slots) -> list:
    """Dictionary hits plus entities, where an entity is ATOMIC.

    On the merged engine (16 dictionaries) it turned out that `EXTERNAL_ADDR` is listed in one of
    them as the literals `@` and `.example`, so the address `steal@evil.example` broke into three
    scraps (`@`, `@evil`, `.example`), and inside it `NEW_PERSONA_MOD` = `evil` was found as well.
    For relation statistics that is direct damage: instead of one term "address" there are four
    junk ones, and the neighbour window fills up with pieces of that same address.

    The rule: an entity is indivisible; every dictionary hit lying entirely inside it is dropped.
    LANG(any).
    """
    spans = [(e.lo, e.hi) for e in ents]
    kept = [h for h in raw if not any(lo <= h.lo and h.hi <= hi for lo, hi in spans)]
    return collapse_runs(kept) + ent_hits(ents, kept, slots)


def collect(low: str, toks, hits, lo_limit: int, hi_limit: int, src):
    """The surroundings of every hit within [lo_limit, hi_limit) of the original text.

    Returns the counters of ONE document: `merge()` then pours them into the shared ones and marks
    that the key was present in this document. The separation exists precisely for the per-document
    counter — otherwise "a key a hundred times in one letter" is indistinguishable from "a key in a
    hundred letters".

    The bounds are given in coordinates of the ORIGINAL text (that is where inj_start/inj_end live),
    while hit and token positions are in normalised ones, so the comparison goes through the offset
    map `src`.
    """
    local = {"ctx": collections.defaultdict(collections.Counter),
             "pairs": collections.defaultdict(collections.Counter),
             "hits": collections.Counter()}
    if not hits:
        return local
    masked = [(h.lo, h.hi) for h in hits]
    # LANG(any): everything in this function is about positions and masking, never about language.
    # Only the tokens that land in the counter carry a language of their own.
    # A paragraph bounds the window: the next paragraph is already another element of the page, not
    # the surroundings of a term (the same argument that forbids a fragment to cross a line break,
    # measured).
    breaks = [m.start() for m in PARA.finditer(low)]
    starts = [t[0] for t in toks]
    # The mask "this token belongs to some term" is computed ONCE per document. It used to walk
    # every hit span for every token of the window, and on the merged engine (hundreds of hits in a
    # long letter) the pass grew cubically: anchors x window x hits.
    tokmask = bytearray(len(toks))
    for h in hits:
        for i in range(bisect.bisect_left(starts, h.lo),
                       min(len(toks), bisect.bisect_left(starts, h.hi) + 1)):
            if toks[i][0] < h.hi and toks[i][1] > h.lo:
                tokmask[i] = 1

    def keep(h) -> bool:
        if lo_limit < 0:
            return True
        o = src[h.lo] if h.lo < len(src) else -1
        return lo_limit <= o < hi_limit

    for h in hits:
        if not keep(h):
            continue
        c = local["ctx"][h.slot]
        i0 = bisect.bisect_left(starts, h.lo)
        i1 = bisect.bisect_left(starts, h.hi)
        for side, rng in (("L", range(i0 - 1, max(-1, i0 - 1 - MAXD), -1)),
                          ("R", range(i1, min(len(toks), i1 + MAXD)))):
            d = 0
            for i in rng:
                if tokmask[i]:
                    continue               # another dictionary term: not surroundings but pattern
                tlo, thi, tok = toks[i]
                a, b = (thi, h.lo) if side == "L" else (h.hi, tlo)
                if crosses(breaks, a, b):
                    break                  # the window does not leave the paragraph
                d += 1
                if d > MAXD:
                    break
                c[f"{tok}|{side}|{bucket(d)}"] += 1
        local["hits"][h.slot] += 1
    pairs(low, toks, hits, local["pairs"], keep, breaks, starts, tokmask,
          local.setdefault("pair_spans", {}))
    return local


def prune(sink):
    """Drop keys seen once: without this the counter grows like the vocabulary of the corpus.

    The bias is known and accepted — a token occurring less than once per cleaning window falls out
    of the statistics. For finding GROUPS that is no loss: a group repeats by definition.
    """
    for slot, c in sink.items():
        if slot.startswith("__"):
            continue
        for k in [k for k, v in c.items() if v < 2]:
            del c[k]
    for group in ("__pairs__", "__ctxdocs__", "__pairdocs__"):
        for c in sink[group].values():
            for k in [k for k, v in c.items() if v < 2]:
                del c[k]


def pairs(low: str, toks, hits, sink, keep, breaks, starts, tokmask, spans=None):
    """Edges "anchor -> filler": an attention head in its cheap form.

    The context counter MASKS neighbouring terms — right for the question "what surrounds this
    construction" and wrong for relations: what matters is the link "directive->target",
    and masking the target erases exactly what it sees. So pairs are counted separately, in the same
    pass.

    An edge key is `filler|order|distance|connective`, where the connective is the path between
    anchor and filler: the unmasked tokens between them, up to three, otherwise `~`. Connective plus
    order in an SVO language stand in for a syntactic parse: `send —to→ <EXTERNAL_ADDR>` and
    `send —from→ <EXTERNAL_ADDR>` are different relations over the same pair of classes.
    """
    # The enumeration is limited to NEIGHBOURS BY POSITION rather than all pairs. The result is the
    # same (distant pairs were cut by the window anyway), but on the merged engine of 16
    # dictionaries a long letter yields hundreds of hits, and the quadratic loop turned the pass
    # into hours.
    order = sorted(range(len(hits)), key=lambda i: hits[i].lo)
    tok_of = {i: bisect.bisect_left(starts, hits[i].lo) for i in order}
    pos_in_order = {i: j for j, i in enumerate(order)}
    for hi_ in order:
        h = hits[hi_]
        if not keep(h):
            continue
        c = sink[h.slot]
        j0 = pos_in_order[hi_]
        near = []
        for step in (-1, 1):
            j = j0 + step
            while 0 <= j < len(order) and abs(tok_of[order[j]] - tok_of[hi_]) <= MAXD + 1:
                near.append(hits[order[j]])
                j += step
        for g in near:
            if g is h or not (g.hi <= h.lo or g.lo >= h.hi):
                continue
            side = "R" if g.lo >= h.hi else "L"
            a, b = (h.hi, g.lo) if side == "R" else (g.hi, h.lo)
            if crosses(breaks, a, b):
                continue                   # the next paragraph is another element, not a relation
            i0, i1 = bisect.bisect_left(starts, a), bisect.bisect_left(starts, b)
            span = toks[i0:i1]
            if len(span) > MAXD:
                continue
            # The path is function words only. Another term between anchor and filler is not part
            # of the connective: it is the anchor of an edge of its own. Without that rule
            # "send … to <address>" gets the connective "the_conversation_history_to" and merges
            # with any other act of sending.
            free = [toks[i][2] for i in range(i0, i1) if not tokmask[i]]
            conn = "_".join(free) if len(free) <= 3 else "~"
            key = f"{g.slot}|{side}|{bucket(len(span) + 1)}|{conn}"
            c[key] += 1
            if spans is not None:
                # The span of the EDGE itself, not of every hit in the document. The context
                # features (`ctx.py`) are computed around it: computed on the span of all hits they
                # degenerate — `boundary` came out 99.8% on positives and 100.0% on clean text,
                # because such a span almost always touches the start or the end of the document.
                lo_, hi_ = min(h.lo, g.lo), max(h.hi, g.hi)
                prev = spans.get((h.slot, key))
                if prev is None or hi_ - lo_ < prev[1] - prev[0]:
                    spans[(h.slot, key)] = (lo_, hi_)


