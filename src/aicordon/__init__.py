"""AI Cordon — the shared core of the company's products: finding model, detector contract, CLI.

There is no detector here. Detectors live in subpackages of their own (`aicordon.picket`, `aicordon.intent`) and present
one and the same `core.engine` contract; the core does not know them and must not — which is
exactly why the command layer of the products is shared rather than "similar".
"""
