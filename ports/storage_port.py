"""
ports/storage_port.py
=====================
StoragePort — stable interface for filesystem and general storage operations.
"""

from typing import Protocol


class StoragePort(Protocol):
    def read(self, path: str) -> bytes:
        """Read file content as bytes."""
        ...

    def write(self, path: str, content: bytes) -> None:
        """Write bytes to a file path."""
        ...

    def delete(self, path: str) -> None:
        """Delete a file if it exists."""
        ...

    def exists(self, path: str) -> bool:
        """Check if a file or directory exists."""
        ...
