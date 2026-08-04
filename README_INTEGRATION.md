# Zero-cost router patch — integration steps

## What this adds
```
config/openrouter_tiers.yaml          task-tiered free model registry
adapters/llm/openrouter_adapter.py    rate-limited, dead-model-aware OpenRouter client
core/context_builder.py               free embed+rerank context assembly
core/router.py                        single entry point: OpenRouter free → your keyed APIs → local → paid (opt-in)
```

## What this does NOT touch
`core/engine.py` and `core/multi_api.py` are untouched and still work standalone.
`router.py` imports and wraps them rather than replacing them, so nothing
that currently works can break from this patch.

## Providers (OpenRouter aggregator vs direct APIs)

See `config/openrouter_providers.yaml` for the full map. Short version:

| Your provider | How KerrOS uses it |
|---|---|
| OpenRouter | Free-first aggregator (`openrouter_tiers.yaml`) |
| Groq (`llama-3.1-8b-instant`) | Direct `GROQ_API_KEY` (MultiAPI) |
| Nvidia NIM | Direct `NVIDIA_API_KEY` + OpenRouter `nvidia/*` |
| Gemini | Direct `GEMINI_API_KEY` + OpenRouter `google/*` |
| Mistral / Cohere / DeepSeek / OpenAI / HF | Direct keys; some also via OpenRouter |
| Cerebras / SambaNova | Direct keys (Sol tier) |
| Poolside | Usually OpenRouter `poolside/*:free` |
| Snowflake | Direct PAT (`SNOWFLAKE_PAT_*`) — not OpenRouter |
| Firecrawl | Crawl API — not an LLM |
| LangChain / Cursor | Framework / IDE — not provider endpoints |

**1. Install + set keys**
```bash
pip install pyyaml
echo 'OPENROUTER_API_KEY=sk-or-...' >> ~/offline_ai/.env
# optional direct fallbacks:
# GROQ_API_KEY=...  NVIDIA_API_KEY=...  GEMINI_API_KEY=...  MISTRAL_API_KEY=...
```

**2. Files already in-tree** at the paths above (no manual copy needed on current KerrOS).

**3. AdaptiveEngine → Router (wired)**

`core/adaptive_engine.py` online mode uses `core.router.Router`:

```python
def _online_generate(self, user_message, system, history, stream):
    from core.router import Router
    if not getattr(self, "_router", None):
        self._router = Router(system=system)

    result = self._router.generate(user_message, system=system, history=history)
    provider = self._router.last_provider
    if provider:
        print(f"  \033[90m[{provider}]\033[0m", end=" ", flush=True)
    return result
```

Priority (zero-cost-first):
1. OpenRouter free tiers (`config/openrouter_tiers.yaml`)
2. MultiAPI keyed providers (Groq, DeepSeek, …)
3. Local llama.cpp
4. Paid OpenRouter — only if `allow_paid=True`

Check in the REPL:
```
/online
/apistatus
/llm
```

## Honesty check on the model list you gave me

I mapped your OpenRouter dashboard list into `config/openrouter_tiers.yaml`
by task (coding / reasoning / chat / research / embed / rerank / vision).
Every entry is marked `verified: false` because I can't browse your live
OpenRouter dashboard from here to confirm exact slug spelling — three names
in particular (**Fusion**, **Body Builder**, **Pareto Code Router**) aren't
in OpenRouter's public docs at all, so they may be account-specific betas
or names that render differently in the API than in the UI.

Before you rely on this in a real workflow:
```bash
curl https://openrouter.ai/api/v1/models | grep -i "your-model-name"
```
Wrong slugs fail loud (400/404), not silent — the adapter's dead-model
tracking will just mark them dead on first use and move to the next
candidate in that tier, so a bad slug degrades the tier, it doesn't break
the run.

## Cost guarantee
Nothing in this patch calls a paid model unless `allow_paid=True` is passed
explicitly to `Router.generate()`. The default path (steps 1-3 in
`router.py`) never spends money — worst case it exhausts all free tiers and
falls through to your local llama.cpp model, which was already your
documented last resort.
