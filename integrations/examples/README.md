# The demonstration sets

Two sets of **ten examples each**, one per role the text plays in the prompt. Ten, because the point
is that you can read the whole thing in a minute and run it through the detector in one command —
see which example fired, which rule fired on it, and what the wrapper did about it.

They are a shop window, not a measure. Every example is picked so that it behaves: the infected ones
fire, the clean ones stay quiet. Reading a detection rate off ten chosen examples would be reading
the selection, so no rate is printed. The measuring set is **Quadrat-IPI** — 16 800 injections
across three carriers, published at
[huggingface.co/datasets/mihailgribov/quadrat-ipi](https://huggingface.co/datasets/mihailgribov/quadrat-ipi) —
and the numbers taken on it live in the integration README next door.

**Not taken from Quadrat**, for two reasons: it is a measuring stick, and scattering its rows across
shop windows contaminates somebody else's measurement; and picking the examples "where it fired" out
of a measuring set quietly turns into fitting. These texts are ours, carry no personal data, and
every name and address in them is invented.

## Material (`ipi`) — ten documents at ingest

Five infected, five clean. The carriers are the ones that really end up in a RAG index: a wiki page,
a support ticket, meeting notes, a knowledge-base article, a web page. The five injections take one
goal each — replace the answer, divert the task, get data out, approve something, reveal the
instructions.

The clean five are not filler. Each is built to sit next to an attack in wording while asking
nothing of the model, and the last of them, `onboarding-analysts`, is the hardest: it is written as
instructions, in the shape a README has — "IMPORTANT:", a command to run, a token to set, and the
word "ignore" in a sentence addressed to a person.

`manifest.jsonl` holds the ground truth: where the payload sits (`inj_span`), what it is after
(`action`), and what fired (`caught`, `threats`, filled in by a run rather than by hand).

    python3 build.py            # build, verify, write docs/ and manifest.jsonl
    python3 show_material.py    # run all ten and show every one of them

## The request (`dpi`) — ten exchanges ahead of the generator

Five attacks, five clean. The carrier is the exchange that goes into the model, so each example is a
list of turns rather than one string — the decision is made for the whole exchange, and two of the
attacks arrive in the third turn to show it.

The attacks are written by us; the live corpus of forum jailbreaks holds real turns written by other
people and does not travel in a release. They take one shape each: cancel the rules outright, cancel
them in a single turn, lock in an amoral persona, hide the rules inside a character, strip the
disclaimers.

Each clean exchange is the benign twin of one of them: `policy-doc` cancels a company policy,
`roleplay-interview` asks for a role-play, `no-warnings-copy` asks for no disclaimers,
`translate-attack` quotes "ignore all previous instructions" verbatim, and `docker-ignore` carries
the same words in a sentence about build caches.

`dialog_manifest.jsonl` holds the ground truth: which turn attacks (`attack_turn`), whether the
wrapper kept it out of the model (`caught`), and what fired (`threats`).

    python3 build_dialogs.py    # build, verify, write dialogues.jsonl and dialog_manifest.jsonl
    python3 show_request.py     # run all ten, plus the "zero disagreements" invariant

That last invariant is the one that licenses everything else on this side: on every user turn the
wrapper's finding must equal the bare detector's. If it does not, the wrapper is losing or adding
text, and no number taken through it means anything.
