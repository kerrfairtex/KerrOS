"""
memory/manage.py
================
Portable API to export / import / inspect KerrOS agent memory (ADR-106).
"""

from __future__ import annotations

import json
import shutil
import time
import zipfile
from pathlib import Path
from typing import Any

from memory import unified_store as us


def status() -> dict[str, Any]:
    enabled = us.is_enabled()
    stores = []
    for s in us.list_stores():
        name = s["name"]
        stores.append(
            {
                **s,
                "files": us.list_files(name),
                "file_count": len(us.list_files(name)),
            }
        )
    return {
        "ok": True,
        "enabled": enabled,
        "root": str(us.ROOT),
        "stores": stores,
        "ts": time.time(),
    }


def export_store(store: str, dest: str | Path) -> dict[str, Any]:
    store = us._validate_store(store)
    dest = Path(dest)
    src = us._store_dir(store)
    if not src.is_dir():
        return {"ok": False, "error": f"store missing: {store}"}
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.suffix == ".zip":
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in src.rglob("*"):
                if p.is_file():
                    zf.write(p, arcname=str(Path(store) / p.relative_to(src)))
            # include version index summaries
            vroot = us.VERSIONS / store
            if vroot.is_dir():
                for p in vroot.rglob("index.json"):
                    zf.write(p, arcname=str(Path("versions") / store / p.relative_to(vroot)))
        return {"ok": True, "store": store, "path": str(dest), "format": "zip"}
    # directory export
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    meta = {
        "store": store,
        "exported_at": time.time(),
        "files": us.list_files(store),
        "history": {rel: us.history(store, rel) for rel in us.list_files(store)},
    }
    (dest / "_export_meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "store": store, "path": str(dest), "format": "dir"}


def import_store(store: str, src: str | Path, *, overwrite: bool = False) -> dict[str, Any]:
    store = us._validate_store(store)
    src = Path(src)
    us.register_store(store, description=f"imported from {src}")
    written = []
    if src.suffix == ".zip" and src.is_file():
        with zipfile.ZipFile(src, "r") as zf:
            for name in zf.namelist():
                if name.endswith("/") or "_export_meta" in name:
                    continue
                # expect store/... or bare relative
                parts = Path(name).parts
                if parts and parts[0] == store:
                    rel = str(Path(*parts[1:]))
                elif parts and parts[0] == "versions":
                    continue
                else:
                    rel = name
                try:
                    rel = us._validate_rel(rel)
                except ValueError:
                    continue
                content = zf.read(name).decode("utf-8", errors="replace")
                existing = us.read(store, rel)
                if existing.get("exists") and not overwrite:
                    continue
                us.write(store, rel, content, agent="import", reason=f"import {src.name}")
                written.append(rel)
        return {"ok": True, "store": store, "written": written}
    if not src.is_dir():
        return {"ok": False, "error": "src must be a directory or .zip"}
    for p in sorted(src.rglob("*")):
        if not p.is_file() or p.name.startswith("_export"):
            continue
        rel = str(p.relative_to(src)).replace("\\", "/")
        try:
            rel = us._validate_rel(rel)
        except ValueError:
            continue
        content = p.read_text(encoding="utf-8")
        existing = us.read(store, rel)
        if existing.get("exists") and not overwrite:
            continue
        us.write(store, rel, content, agent="import", reason=f"import {src}")
        written.append(rel)
    return {"ok": True, "store": store, "written": written}


def tool_manage(raw: str) -> str:
    """CLI/tool entry: status | list | export <store> <path> | import <store> <path> [overwrite]"""
    text = (raw or "status").strip()
    parts = text.split()
    cmd = (parts[0] if parts else "status").lower()
    if cmd in ("status", "list"):
        return json.dumps(status(), indent=2)
    if cmd == "export" and len(parts) >= 3:
        return json.dumps(export_store(parts[1], parts[2]), indent=2)
    if cmd == "import" and len(parts) >= 3:
        overwrite = len(parts) > 3 and parts[3].lower() in ("overwrite", "--overwrite", "1")
        return json.dumps(import_store(parts[1], parts[2], overwrite=overwrite), indent=2)
    if cmd == "files" and len(parts) >= 2:
        return json.dumps({"ok": True, "store": parts[1], "files": us.list_files(parts[1])}, indent=2)
    if cmd == "history" and len(parts) >= 3:
        return json.dumps({"ok": True, "history": us.history(parts[1], parts[2])}, indent=2)
    return json.dumps(
        {
            "ok": False,
            "error": "usage: status|list|files <store>|history <store> <path>|"
            "export <store> <path>|import <store> <path> [overwrite]",
        },
        indent=2,
    )
