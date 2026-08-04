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

## 3 steps to wire it in

**1. Install + set the key**
```bash
pip install pyyaml
echo 'OPENROUTER_API_KEY=sk-or-...' >> ~/offline_ai/.env
```

**2. Drop the four new files into your repo** at the paths shown above.

**3. Point `AdaptiveEngine._online_generate` at the router**

In `core/adaptive_engine.py`, replace the `kernel.access.get_llm_port()` call
with `core.router.Router`:

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

That's it — `/online`, `/apistatus`, and everything else in `chat.py` keeps
working; `/apistatus` will now also want to print `router.status()` if you
want OpenRouter's per-model health in that view (optional, one extra print
line where `/apistatus` currently reads `engine._multi.health`).

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
