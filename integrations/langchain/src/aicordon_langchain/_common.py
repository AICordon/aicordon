"""The two things every surface here needs: what a message says, and what to call its role.

Kept apart from `middleware.py` so that the document and chain surfaces need `langchain-core` only —
`AgentMiddleware` lives in `langchain`, and importing it to read a role name would make an agent
dependency out of an ingest script.
"""
from __future__ import annotations

from typing import Any

#: LangChain's message type to the role name the policy speaks. Both vocabularies are ordinary and
#: neither is wrong, but they disagree on two of four words: a `HumanMessage` says `human` where the
#: policy says `user`, an `AIMessage` says `ai` where it says `assistant`. A role map keyed on the
#: host's word would match nothing in the default policy and read no message at all, while reporting
#: for each one that it had been read and found clean.
ROLE_OF = {"human": "user", "ai": "assistant", "system": "system", "tool": "tool"}


def message_text(message: Any) -> str:
    """The text of a message, every text block of it.

    `.text` joins the text blocks and ignores images and files, which is what we want: Picket is a
    rule over text. What must NOT be used is `str(message.content)` — on a message whose content is
    a list of blocks that returns the Python repr of the list, so the check runs over punctuation
    and dictionary keys that nobody sent.
    """
    return str(message.text)
