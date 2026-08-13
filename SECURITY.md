# Security policy

## Reporting a vulnerability

Write to **security@ai-cordon.com**, or open a private advisory through GitHub
(*Security → Report a vulnerability*). Please do not open a public issue for
something exploitable.

Tell us what you can: what you did, what happened, and what you expected. A
document that reproduces it is worth more than a description of it — attach it
even if it looks unremarkable, and say if it must not be redistributed.

Reports are read. There is no service commitment attached to this address: no
response time, no bounty, no guarantee that a given report leads to a change. If
a fix does follow, the reporter is credited by whatever name they choose, or not
at all if they prefer, and the timing of any public write-up is settled with
them first.

## What counts as a vulnerability here

This is a signature detector. It is honest about missing most injections, so a
**missed injection is not a vulnerability** — it is the working point, published
as a number in the README and printed by `aicordon picket coverage`. Send those
as ordinary issues; they are useful and they are how the base improves.

What is worth reporting here:

* **anything the tool does to the host it runs on** — a document that makes it
  crash, hang, or consume memory or time out of proportion to its size. The cost
  grows with the length of the text, and the current model is in the README and
  measurable on your own documents with `aicordon picket bench`; a document that
  breaks it by orders of magnitude is a denial-of-service bug;
* **a report that lies about position** — a span pointing outside the payload, or
  offsets that do not match the text handed in. Code cuts documents by those
  offsets;
* **anything that makes the tool do work it should not**: reading files it was
  not given, writing outside `--collect`/`--report`, or reaching the network. It
  has no network code, and a path that acquires one is a defect of the first
  order;
* **a way to make a finding disappear that does not require rewriting the
  payload** — for instance a control sequence that suppresses the check while
  leaving the instruction readable to a model.

## Scope

This repository: the `aicordon` distribution, the `aicordon.picket` detector and
the rule base shipped inside it.

Not in scope here: the AI Cordon API and the detector behind it. Those are a
separate product; send reports about them to the same address with `Intent` in
the subject line.

## Versions

Fixes land in the next release; there is no long-term branch and no backporting.
The base carries its own date-based version, so a report can name exactly which
one it was seen on (`aicordon picket version`).
