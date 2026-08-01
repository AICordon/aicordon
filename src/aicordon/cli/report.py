"""The machine-readable side of the shell: one JSON shape, two ways of delivering it.

`--json` streams a line per document; `--collect DIR` writes the same objects for the documents that
fired into `report.json`, next to copies of them. The shape is built HERE for both, because two
serialisers of one thing drift: the day a field is added to one, a consumer of the other silently
loses it. The only difference between the two is what the delivery adds — `--collect` knows where it
put the copy, so its objects carry `copy`.

Putting the documents that fired aside, together with a machine-readable report.

Why this is not a quarantine. A scanner has nowhere to isolate a document TO, and cutting the
payload out of somebody else's text is not its business either — so nothing here moves, deletes or
edits anything. Originals are left exactly where they were; what lands in the directory is a COPY
plus `report.json`, and the point of the pair is triage: one place to look through by hand, one file
to feed to the next step.

The directory says nothing about the documents that are not in it. At 32.4% recall "not collected"
means "nothing fired", the same thing the exit code means, and never "checked and found harmless"
(SPEC §2). The word quarantine is avoided for that reason and not out of squeamishness: a quarantine
implies the rest of the ward is healthy.

Two rules the implementation follows literally:

* **nothing is written outside the target directory.** Source paths are turned into relative ones
  and `..` is dropped, so a document from `/etc` cannot land in `/etc` again through a crafted name;
* **nothing existing is overwritten.** A name that is taken gets a numeric suffix — two files called
  `index.html` from different directories are a normal case, and silently keeping one of them would
  lose the other.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..core.model import Report

REPORT_NAME = "report.json"
SCHEMA = 1

_UNSAFE = re.compile(r"[^\w.\-/]+", re.UNICODE)


def target_name(doc_id: str, origin: str) -> str:
    """A path inside the collection directory, derived from where the document came from.

    The layout of the source tree is kept — `docs/mail/letter.txt` stays `docs/mail/letter.txt` —
    because a flat pile of `letter.txt`, `letter_1.txt`, `letter_2.txt` answers none of the
    questions the collection exists for.
    """
    raw = origin or doc_id or "document"
    p = Path(raw)
    parts = [x for x in p.parts if x not in ("/", "..", ".")]
    parts = [_UNSAFE.sub("_", x.replace(":", "_")) for x in parts]
    name = "/".join(parts) or "document"
    if name.startswith("-"):                      # never produce something argparse would eat
        name = "_" + name[1:]
    return name


def document_json(rep: Report, text: str = "", **extra) -> dict:
    """One document as JSON: the report plus the text of every span.

    `Report.to_json` gives what the ENGINE said — offsets and names. The text is added here, by the
    shell, for the same reason the shell prints it: a consumer that gets offsets alone has to open
    the file again, and in `--collect` that file may be a copy under a different name. `extra` is
    what the delivery knows and the engine does not, `source` and `copy`.
    """
    out = rep.to_json()
    for f, raw in zip(out["findings"], rep.findings):
        f["text"] = text[raw.span[0]:raw.span[1]] if (raw.span and text) else ""
    out.update(extra)
    return out


class Collector:
    """Accumulates the report and, when there is a directory, copies the documents that fired.

    One class for two flags on purpose. `--report FILE` and `--collect DIR` differ in exactly one
    thing — whether copies are made — and everything else (which documents get in, what the object
    looks like, what the header says) has to stay identical, or the same run would describe itself
    two ways.

    The report is held in memory for the FLAGGED documents only — the same set that is being written
    to disk anyway — so a scan of a large tree is still bounded by what it found, not by what it
    read.
    """

    def __init__(self, directory: Path | None, product: str, engine: str, engine_version: str,
                 report_path: Path | None = None) -> None:
        self.dir = Path(directory) if directory else None
        self.reused = False
        if self.dir is not None:
            self.dir.mkdir(parents=True, exist_ok=True)
            # A directory that already holds a collection is not an error — re-running a check is
            # the normal case — but the report describes THIS run only, and files from the previous
            # one stay behind under `_1` names. Left unsaid, that reads as one collection, not two.
            self.reused = any(self.dir.iterdir())
        self.report_path = Path(report_path) if report_path else (
            self.dir / REPORT_NAME if self.dir else None)
        self.head = {"schema": SCHEMA, "product": product,
                     "engine": engine, "engine_version": engine_version}
        self.documents: list[dict] = []
        self.errors: list[str] = []

    def _free_path(self, name: str) -> Path:
        path = self.dir / name
        # Belt and braces over `target_name`: whatever the name looked like, it must resolve inside
        # the directory. A path that does not is a bug here, not a case to handle gracefully.
        if not str(path.resolve()).startswith(str(self.dir.resolve())):
            raise ValueError(f"path escapes the collection directory: {name}")
        if not path.exists():
            return path
        stem, suffix = path.stem, path.suffix
        for i in range(1, 10_000):
            candidate = path.with_name(f"{stem}_{i}{suffix}")
            if not candidate.exists():
                return candidate
        raise ValueError(f"cannot find a free name for {name}")

    def add(self, rep: Report, text: str, origin: str = "") -> None:
        if not rep.flagged:
            return
        if self.dir is None:                      # a report without copies: nothing to write yet
            self.documents.append(document_json(rep, text, source=origin or rep.doc_id))
            return
        name = target_name(rep.doc_id, origin)
        try:
            path = self._free_path(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            # Written from the text the engine actually saw, not copied byte for byte from disk:
            # for `--jsonl`, `--text` and stdin there is no file to copy, and one behaviour for all
            # inputs beats a special case that only works for files.
            path.write_text(text, encoding="utf-8")
        except OSError as e:
            self.errors.append(f"{rep.doc_id}: {e}")
            return

        self.documents.append(document_json(rep, text, source=origin or rep.doc_id,
                                            copy=str(path.relative_to(self.dir))))

    def payload(self) -> dict:
        report = dict(self.head)
        report["documents"] = self.documents
        report["collected"] = len(self.documents)
        if self.errors:
            report["errors"] = self.errors
        return report

    def write(self) -> Path | None:
        if self.report_path is None:
            return None
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        self.report_path.write_text(json.dumps(self.payload(), ensure_ascii=False, indent=1),
                                    encoding="utf-8")
        return self.report_path
