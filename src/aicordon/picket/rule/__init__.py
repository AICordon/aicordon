"""The rule engine: normalisation, automaton, relation extraction, scanner and threat names.

The single home of this code. The exp40 research tools import it from here instead of keeping a
copy of their own: parsing that had drifted into two copies would mean the measurements no longer
describe the product (the rule is written down in `frag.py`).
"""
