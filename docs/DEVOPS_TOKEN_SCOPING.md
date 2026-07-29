# KerrOS DevOps token scoping (P4 / README §6–§7)

> One dedicated, least-privilege token **per vendor**. Never reuse one shared
> key across GitHub / Supabase / Vercel / Netlify / Railway / Cloudflare / Stripe.
>
> Runtime: `tools/devops_tokens.py` (shape + presence; Stripe live keys refused).
> Arm/disarm of deploy tools remains `tools/scope_gate.py`.

## Checklist

| Service | Env (preferred) | Minimal scope | Forbidden / avoid |
|---------|-----------------|---------------|-------------------|
| GitHub | `GITHUB_TOKEN` | Fine-grained: Contents + Metadata (write) on **one** repo; or classic `repo` only | `admin:org`, `delete_repo`, org-owner PATs |
| Supabase | `SUPABASE_ACCESS_TOKEN` | Project-scoped Management / CLI token | Agent `.env` with `SUPABASE_SERVICE_ROLE_KEY` / `SUPABASE_SECRET_KEY` for routine migrate |
| Vercel | `VERCEL_TOKEN` | Deploy on one team/project (`VERCEL_ORG_ID`, `VERCEL_PROJECT_ID`) | Account-wide tokens spanning unrelated teams |
| Netlify | `NETLIFY_AUTH_TOKEN` (alias: `NETLIFTY_API_KEY`) | Site/team-scoped personal access token | Tokens with unrelated site access |
| Railway | `RAILWAY_API_KEY` | Project-scoped | Account admin keys when a project token exists |
| Cloudflare | `CLOUDFLARE_API_TOKEN` | Workers Scripts Edit (+ DNS Edit if needed) on one account/zone | Global API Key; unbound All-Zones tokens |
| Stripe | `STRIPE_API_KEY` or `STRIPE_SECRET_KEY` | **Test** secret `sk_test_` or restricted `rk_test_` | `sk_live_` / `rk_live_` (hard-refused by KerrOS) |

## Operator steps

1. Create **separate** tokens in each vendor console with the scopes above.
2. Put them in `.env` (see `.env.example` comments) — never commit secrets.
3. Audit locally:

```bash
python3 scripts/check_devops_tokens.py
```

4. Arm deploy only when needed: `/scope arm-deploy <minutes>` (fail-closed otherwise).

## Code hooks

- Capability manifests: `config/capabilities/devops_tools.yaml` (`token_env` metadata)
- Presence map: `api_config.yaml` → `deploy:` (used by `api_status.py`)
- Preflight: `kernel/router.py` deploy handlers call `preflight()` before CLI spawn
- Tests: `tests/unit_tools/test_devops_tokens.py`
