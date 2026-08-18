"""Policy for AI Cordon Picket, shared by every framework wrapper.

Two sides, because a string plays one of two roles in a prompt and Picket carries a rule set for
each: `InjectionGuard` reads MATERIAL the model is to work on, `TurnGuard` and `DialogueGuard` read
the REQUEST it is answering. Which one applies is decided by the role of the text, not by who
fetched it — see `guard.py`.

It lives inside the `aicordon` distribution itself (`aicordon.guard`) rather than in a package of
its own: it has no dependencies beyond the detector, and a second published package for two hundred
lines of policy would be a maintenance cost with nothing on the other side. The framework wrappers
under `integrations/` depend on `aicordon` alone and import this module.
"""
from .dialogue import DEFAULT_ROLES, DialogueGuard, ExchangeVerdict, TurnGuard
from .guard import MODES, NON_EDITING_MODES, InjectionFound, InjectionGuard, Verdict

__all__ = ["InjectionGuard", "TurnGuard", "DialogueGuard", "InjectionFound", "Verdict",
           "ExchangeVerdict", "MODES", "NON_EDITING_MODES", "DEFAULT_ROLES"]
