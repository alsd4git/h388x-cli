"""Safe writers for files that may contain modem credentials or keys."""

from __future__ import annotations

import os
from pathlib import Path


def write_private_bytes(path: Path, data: bytes) -> None:
    """Create *path* once with mode ``0600`` and write *data* to it.

    Existing files are deliberately refused: modem backups and decrypted
    configuration often contain credentials, and silently replacing either is
    unsafe.  Callers should choose a new output name instead.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as file:
            fd = -1
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        # ``os.open`` does not tighten permissions on platforms with a
        # restrictive or permissive umask, so assert the intended mode.
        os.chmod(path, 0o600)
    finally:
        if fd != -1:
            os.close(fd)
