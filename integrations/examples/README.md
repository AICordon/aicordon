# Examples for the integration documentation

Small sets behind the snippets in READMEs, catalogue cards and wrapper tests. There are two places
to sit, by the role the text plays in the prompt — material and request — and each gets a set of its
own.

**Not taken from Quadrat**, for two reasons: Quadrat is a measuring stick, and scattering its rows
across shop windows contaminates somebody else's measurement; and picking the examples "where it
fired" out of a measuring set quietly turns into fitting. These texts are ours, carry no personal
data, and every name and address in them is invented.

## Material (`ipi`) — documents at ingest

The carriers are the ones that really end up in a RAG index: a wiki page, a support ticket, meeting
notes, a knowledge-base article, a web page. The injection goals are RAG-natural as well: replace
the answer, divert the task, get data out.

`manifest.jsonl` holds the ground truth: where the payload sits (`inj_span`), what it is after
(`action`), and whether the current base fires on it (`caught`, filled in by a run, not by hand).

    python3 build.py            # build, verify, write docs/ and manifest.jsonl
    python3 measure_demo.py     # honest numbers for the material window

## The request (`dpi`) — turns ahead of the generator

The carrier is the exchange that goes into the model. The attack here is not spliced into a
document, it *is* the turn: an attempt to take the rules off the model (cancelling instructions, an
amoral persona, a role-play frame, "no warnings"). The jailbreaks are written by us — the live
corpus of forum jailbreaks holds real turns written by other people and does not travel in a
release. The clean exchanges are deliberately hard: they sit right next to the attacks in wording
("ignore", "cancel", "refuse", "jailbreak", "role-play") while taking no rule off the model.

The decision is made for the whole exchange, so the carrier in this set is a list of turns rather
than a single string. `dialog_manifest.jsonl` holds the ground truth: which turn attacks
(`attack_turn`), whether the wrapper kept it out of the model (`caught`), and what fired (`threats`,
filled in by a run).

    python3 build_dialogs.py         # build, verify, write dialogues.jsonl and dialog_manifest.jsonl
    python3 measure_demo_dialog.py   # numbers for the request window, plus the "zero disagreements" invariant

The numbers from `measure_demo*.py` belong to the shop window and must not be passed off as the
detector's quality. The measured ones are taken on held-out attacks and live traffic, and they live
in the integration README next door.
