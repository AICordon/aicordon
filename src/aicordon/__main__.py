"""Python3 -m aicordon — the same thing as the `aicordon` executable."""
from __future__ import annotations

import sys

from .cli.umbrella import main

if __name__ == "__main__":
    sys.exit(main())
