"""AI Cordon Picket for LangChain: check what the model is given, in each place it arrives.

| what you are guarding | this package | reads with |
|---|---|---|
| documents at ingest | `PromptInjectionFilter` | Picket's `ipi` rules |
| what a tool handed back | `ToolOutputFilter` | `ipi` |
| the turn an agent is about to answer | `PromptInjectionGuard` | `dpi` |
| the request in a chain that is not an agent | `PromptInjectionValidator` | `dpi` |

The two rule sets are disjoint and neither is a stricter version of the other; the choice follows
from the role the text plays in the prompt, never from who fetched it. Everything decided here comes
from `aicordon.guard` inside the detector distribution — what lives in this package is the
translation into LangChain's types and contracts.
"""
from aicordon.guard import InjectionFound

from .chain import PromptInjectionValidator
from .documents import PromptInjectionFilter
from .middleware import PromptInjectionGuard, ToolOutputFilter

__all__ = ["PromptInjectionFilter", "PromptInjectionGuard", "ToolOutputFilter",
           "PromptInjectionValidator", "InjectionFound"]
