"""Atomic file writer for safe note modifications.

Uses a write-to-temp-then-rename strategy (FR3.5) to ensure that
note files are never left in a partially-written state.
"""

import logging
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def atomic_write(path: Path, content: str) -> None:
    """Write content to a file atomically using temp-file-then-rename.

    Creates a temporary file in the same directory as the target,
    writes the content, then atomically renames it to the target path.
    This ensures the file is never left in a partially-written state.

    Args:
        path: Absolute path to the target file.
        content: Content to write.

    Raises:
        OSError: If the write or rename fails.
    """
    parent = path.parent

    # Write to a temp file in the same directory (same filesystem
    # guarantees atomic rename on POSIX systems).
    fd = None
    tmp_path = None
    try:
        fd, tmp_path_str = tempfile.mkstemp(
            dir=str(parent), prefix=".tmp_", suffix=".md",
        )
        tmp_path = Path(tmp_path_str)

        with open(fd, "w", encoding="utf-8") as f:
            f.write(content)
        fd = None  # Closed by context manager

        # Atomic rename (same filesystem)
        tmp_path.rename(path)
        logger.debug("Atomic write: %s", path)

    except Exception:
        # Clean up temp file on failure
        if fd is not None:
            import os
            os.close(fd)
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink()
        raise
