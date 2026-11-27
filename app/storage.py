from __future__ import annotations

import os
from pathlib import Path


def data_path(filename: str) -> str:
    """Return a writable path for local and serverless runtimes.

    Vercel's deployed filesystem is read-only except for /tmp. Local runs
    continue to use the repository's data/ directory.
    """
    if os.getenv("VERCEL") == "1":
        root = Path("/tmp/golden-mind-ai")
    else:
        root = Path(os.getenv("GMAI_DATA_DIR", "data"))
    root.mkdir(parents=True, exist_ok=True)
    return str(root / filename)
