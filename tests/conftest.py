"""Pytest configuration.

This project uses a `src/` package layout without an installed wheel.
For local test runs, we add the repository root to `sys.path` so imports like
`from src...` work under `pytest`.
"""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
