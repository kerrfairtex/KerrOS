# AGENTS.md

## Cursor Cloud specific instructions

KerrOS ("offline_ai") is a Python 3 terminal AI-assistant app. There is no build
step and no Node runtime is needed for development (the root `package.json` /
`.mcp.json` are only for optional MCP tooling).

### Base-path assumption (important)
Many modules hardcode the project root as `~/offline_ai`
(e.g. `core/config.py`, `rag/store.py`, `memory/manager.py` read
`~/offline_ai/config.json`, `~/offline_ai/data/...`). The startup update script
creates a symlink `~/offline_ai -> <repo>` so these resolve to the checkout. If
the app fails at import with `unable to open database file` or a missing
`config.json`, recreate it:

```
ln -sfn "$PWD" "$HOME/offline_ai"
```

### Tests
Run with pytest from the repo root (pytest lives in `~/.local/bin`, which is not
on `PATH`, so invoke via the module form):

```
python3 -m pytest tests/
```

Do NOT use `python3 -m unittest discover` — `tests/tools/__init__.py` collides
with the top-level `tools/` package and shadows it. pytest's rootdir-based import
resolves the top-level `tools` package correctly.

### Lint
No linter is configured in the repo. For a quick syntax/import sanity check use
`python3 -m py_compile <files>`.

### Running the app
```
python3 cli/chat.py
```
On startup it asks "Online mode? [y/n]" only when it detects internet.

- Online mode needs a cloud LLM key (e.g. `GROQ_API_KEY`, see `.env.example`).
- Offline mode needs a local llama.cpp binary + a GGUF model (`models/*.gguf`,
  gitignored and absent here); without one the LLM chat cannot generate.

The "claw" filesystem/exec slash-commands (`/read`, `/write`, `/edit`, `/list`,
`/exec`, `/remove`, `/tool`, `/workspace`) are handled in the REPL BEFORE any LLM
call, so they run fully without a model or API key — this is the reliable way to
exercise the app end-to-end in the cloud VM. The claw workspace defaults to the
repo root; override it with `KERROS_WORKSPACE=/some/dir`. `exec` only allows
commands listed in `config.json` `safe_commands` and blocks path traversal
outside the workspace.
