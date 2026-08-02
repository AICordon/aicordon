# Security policy

## Reporting a vulnerability

Write to **security@ai-cordon.com**, or open a private advisory through GitHub
(*Security → Report a vulnerability*). Please do not open a public issue for
something exploitable.

Tell us what you can: what you did, what happened, and what you expected. A
document that reproduces it is worth more than a description of it — attach it
even if it looks unremarkable, and say if it must not be redistributed.

You will get an acknowledgement within **3 working days** and an assessment
within **10**. If a fix is warranted we will agree the disclosure date with you
and credit you by the name you choose, or not at all if you prefer.

## What counts as a vulnerability here

This is a signature detector. It is honest about missing most injections, so a
**missed injection is not a vulnerability** — it is the working point, published
as a number in the README and printed by `aicordon picket coverage`. Send those
as ordinary issues; they are useful and they are how the base improves.

What we do want to hear about:

* **anything the tool does to the host it runs on** — a document that makes it
  crash, hang, or consume memory or time out of proportion to its size. The cost
  model is published (about 2 ms and 0.23 MB per KB of text); a document that
  breaks it by orders of magnitude is a denial-of-service bug and we treat it as
  one;
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

Not in scope here: the AI Cordon API and the detector behind it — those are a
separate product with their own contact, and reports about them go to the same
address with `Intent` in the subject.

## Supported versions

The published version is supported. There is no long-term branch: fixes go into
the next release, and the base carries its own date-based version so a report can
name exactly which one it was seen on (`aicordon picket version`).
