"""
adapters/storage/local_fs_adapter.py
====================================
StoragePort adapter implementing local filesystem operations.
"""

from __future__ import annotations

import os
from pathlib import Path
from ports.storage_port import StoragePort


class LocalFSAdapter(StoragePort):
    """Local filesystem storage adapter."""

    def __init__(self, base_dir: str | Path | None = None) -> None:
        if base_dir is None:
            self.base_dir = Path(os.getcwd()) / "data" / "storage"
        else:
            self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _safe_path(self, path: str) -> Path:
        """Resolve absolute path and ensure it's within the sandbox base_dir to avoid path traversal."""
        resolved = Path(path)
        if not resolved.is_absolute():
            resolved = self.base_dir / resolved
        else:
            # If absolute, verify if we can make it relative to base_dir,
            # or allow it but check constraints. For security, we force it to be under base_dir.
            try:
                resolved = self.base_dir / resolved.relative_to(resolved.anchor)
            except ValueError:
                pass
        
        try:
            # Ensure it resolves underneath base_dir
            real_base = self.base_dir.resolve()
            real_target = resolved.resolve()
            # If target doesn't exist yet, we can check its parent
            if not real_target.exists():
                real_parent = real_target.parent.resolve()
                real_parent.relative_to(real_base)
            else:
                real_target.relative_to(real_base)
        except ValueError:
            raise ValueError(f"Path {path} is outside of safe storage directory {self.base_dir}")
        
        return resolved

    def read(self, path: str) -> bytes:
        target = self._safe_path(path)
        if not target.is_file():
            raise FileNotFoundError(f"File not found: {path}")
        return target.read_bytes()

    def write(self, path: str, content: bytes) -> None:
        target = self._safe_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    def delete(self, path: str) -> None:
        target = self._safe_path(path)
        if target.is_file():
            target.unlink()

    def exists(self, path: str) -> bool:
        try:
            target = self._safe_path(path)
            return target.exists()
        except ValueError:
            return False
