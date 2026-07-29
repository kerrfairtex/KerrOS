# KerrOS RAG × OmniRoute promptfoo

Attacks **KerrOS** RAG injection (`[Relevant knowledge]:` wrappers), not OmniRoute’s
upstream suite. See [`docs/OMNIROUTE_SECURITY_AUDIT.md`](../../docs/OMNIROUTE_SECURITY_AUDIT.md).

## Prerequisites

- OmniRoute on loopback (`scripts/omniroute_droplet.sh up`)
- Node.js + `npx` (promptfoo)
- Optional: `OMNIROUTE_API_KEY` if the gateway requires auth

## Run

```bash
export OMNIROUTE_ENDPOINT=http://127.0.0.1:20128/v1
../../scripts/run_omniroute_rag_promptfoo.sh
```

Fixtures: `fixtures/rag_injected_prompts.json`  
Config: `promptfooconfig.yaml`
