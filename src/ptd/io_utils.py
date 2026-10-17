"""IO and diagnostic utilities for PTD Pipeline."""

import hashlib
import logging
import os
from pathlib import Path
from typing import Any, Dict, Generator, Optional
import psutil

logger = logging.getLogger("ptd")


def setup_logging(level: int = logging.INFO) -> None:
    """Configure structured logging for stdout."""
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def compute_sha256(file_path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Compute sha256 checksum of a file in chunks."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def get_process_memory_mb() -> float:
    """Return current process resident memory in MB."""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024 * 1024)


def get_ijson_backend_info() -> Dict[str, Any]:
    """Diagnose and return the active ijson backend and available alternatives."""
    import ijson

    backends = ["yajl2_c", "yajl2_cffi", "yajl2", "yajl", "python"]
    availability = {}
    for b in backends:
        try:
            ijson.get_backend(b)
            availability[b] = True
        except Exception:
            availability[b] = False

    return {
        "active_backend": getattr(ijson, "backend", "unknown"),
        "availability": availability,
    }
