from __future__ import annotations

import sys
from pathlib import Path

# Ensure smart_contracts package is importable when tests run from any working directory.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
