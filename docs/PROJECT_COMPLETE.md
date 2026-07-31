# KerrOS Soft Foundation — Complete

**Status:** Complete (Soft foundation)  
**Date:** 2026-07-31  
**Branch intent:** land remaining agent/channel Soft work on `main`

## Verdict

KerrOS Soft foundation for the offline/online terminal assistant is **complete**.
Phases A–E offline combo, mesh/LGU foundation, and the agent-capability Soft
port (ADR-061…104) are in-tree. Remaining items are **operator-owned live
verification** or **contract-gated production** upgrades — not missing Soft
product surface.

## Completed arcs

| Arc | ADRs / docs | Soft outcome |
|-----|-------------|--------------|
| Kernel / ports / workflows / mesh | ADR-001…047 | Foundation + Soft on-ramps |
| Local LLM ops | ADR-016, 048–054 | Offline A–E Soft; live containers operator-owned |
| Offline RAG Phase B | ADR-051 | FTS primary + nomic/FAISS Soft |
| Coding index / LoRA / LiteLLM Soft | ADR-052…054 | Soft/Fake shipped |
| Agent capability port | ADR-061…104 | Subagents, sessions, REPL/TUI, channels, bridges |

## Explicitly out of Soft scope (not blockers)

- Live llama.cpp + LiteLLM container verification on a host with GGUF
- Production TLS / public LiteLLM / multi-node HA
- Discord Gateway presence, live Ed25519 without optional PyNaCl
- OS keyring / HSM custody / accreditation seals
- Remote sandbox fleet vendors (HTTP Soft contract only)

## Operator quick start

```bash
ln -sfn "$PWD" "$HOME/offline_ai"
export KERROS_OFFLINE_PROFILE=offline_qwen05   # optional offline combo
python3 -m pytest tests/
python3 cli/chat.py                            # claw slash-cmds work without LLM
python3 -m cli.tui                             # Soft full-screen shell
```

Termux: pull latest; the nested-`import os` crash after first offline reply is fixed.

## Brand

Angel + sword chrome retained. Tagline: **SECURE BY DESIGN. BUILT FOR CONTROL.**
External agent-product names are not KerrOS dependencies.
