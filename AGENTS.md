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
Test packages live under `tests/unit_*` (not `tests/tools`, `tests/kernel`, etc.)
so they do not shadow real packages during discovery.

```
./scripts/run_tests.sh
# or:
python3 -m unittest discover -s tests -p 'test_*.py' -t .
```

Install core deps first if needed: `pip install -r requirements.txt`.
CI runs the same command via `.github/workflows/tests.yml`.

### Brand / naming sanitation
Re-implement capabilities natively in KerrOS. Do **not** name competing
third-party agent portals (or their org/product/repo strings) in KerrOS code,
docs, env vars, filenames, comments, or git submodules. Keep the angel + sword
brand. Never commit local dumps (`files.txt`, `folders.txt`), `*.bak*`, runtime
`*.db`, or third-party checkouts.

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

### Common issue: empty/timeout in chat.py
If `cli/chat.py` returns nothing or hangs for ~30s before generating:

**Root cause:** `core/engine.py` `chat()` previously iterated the entire
`fallback_chain` (10+ cloud providers) sequentially. With no API keys
configured in `.env`, every provider timed out on an HTTP request before the
engine finally fell back to local llama.cpp — often exceeding the REPL's read
timeout.

**Fix (already applied):** `LLMEngine` now calls `_has_cloud_key(name)` to check
whether any provider in `fallback_chain` has a real key *before* attempting the
loop. If all keys are missing/empty, it short-circuits directly to
`_call_local()`. Result: instant local generation even with no `.env` keys.

**To re-apply if needed:** ensure the `_has_cloud_key()` method exists in
`LLMEngine` and that `chat()` checks `cloud_available` before entering the
fallback loop (see `core/engine.py`).
