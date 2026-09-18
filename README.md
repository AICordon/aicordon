# AI Cordon

[![PyPI](https://img.shields.io/pypi/v/aicordon.svg)](https://pypi.org/project/aicordon/)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/AICordon/aicordon/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Dependencies](https://img.shields.io/badge/dependencies-0-brightgreen.svg)](https://github.com/AICordon/aicordon/blob/main/pyproject.toml)

**Find prompt injections in the text your model reads: mail, pages, tool results, retrieved chunks.**

Two detectors, one interface. Code written against one works with the other unchanged.

| | **Picket** — fast | **Intent** — accurate |
|---|---|---|
| what it is | a signature rule, runs in your process | the full AI Cordon detector, over an API |
| speed | **100–200 documents a second** on one CPU core | a network round trip per document |
| false alarms | **~1 in 1 000** clean documents | **~1 in 10 000** clean documents (FPR 1e-4) |
| catches | the obvious: textbook phrasing an attacker did not bother to hide | instructions written as ordinary prose, in any wording, hidden in markup |
| needs | nothing: no model, no network, no key | an API key |
| your text | **never leaves the process**: Picket has no network code | **is sent to the AI Cordon API** to be judged |
| details | [docs/picket.md](https://github.com/AICordon/aicordon/blob/main/docs/picket.md) | [docs/intent.md](https://github.com/AICordon/aicordon/blob/main/docs/intent.md) |

Use Picket where a heavier check cannot go at all: a whole corpus, an ingest path, a mail gateway.
Use Intent where a miss is expensive. They also stack: Picket first, Intent on the rest.

## Quick start

```console
$ pip install aicordon
$ aicordon picket scan letter.txt          # local, works right away
$ aicordon login                           # once: stores the Intent API key
$ aicordon intent scan letter.txt
```

```python
from aicordon import picket, intent

fast = picket.load()
full = intent.load()          # key: api_key=..., AICORDON_API_KEY, or `aicordon login`

for det in (fast, full):
    rep = det.check(text)
    if rep.flagged:
        for f in rep.findings:
            print(det.title, f.threat, text[f.span[0]:f.span[1]])
```

A report says what was found and where. It never says a text is safe: no finding is not a verdict.

## Both on the same five texts

`python examples/compare.py` runs both over [examples/texts](https://github.com/AICordon/aicordon/tree/main/examples/texts):

```text
text                         Picket (local rule)              Intent (API)
01-obvious-email.txt         alarm  IPI/Secret.Reveal.C       alarm  score 0.98
02-support-ticket.txt        —                                alarm  score 0.97
03-release-notes.html        —                                alarm  score 0.99
04-warning-question.txt      —                                —      score 0.52
05-quarterly-report.txt      —                                —      score 0.03
```

The textbook injection is caught by both. The polite note to "the assistant that summarises this
ticket" and the instruction in an HTML comment carry none of the words a rule looks for — only Intent
sees them. A question that merely contains "ignore" and "previous instructions" alarms neither.

## Licensing

**Apache License 2.0** (`LICENSE`), the code and the shipped Picket base alike. Contributions are
accepted under the DCO: sign your commits off with `git commit -s`.

Get an Intent key at [ai-cordon.com](https://ai-cordon.com).
