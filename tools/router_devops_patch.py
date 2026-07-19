# ============================================================
# PATCH FOR router.py — three separate insertions, NOT one cat.
# ============================================================

# ------------------------------------------------------------
# INSERT 1 — inside detect_tool(), right before the final
#            `return (None, None)` line at the end of the
#            function. Anchor: this is the very last line of
#            detect_tool() in your pasted file.
# ------------------------------------------------------------

    # ── DevOps / Deploy pipeline ─────────────────────────
    if "create repo" in lower or "create github repo" in lower:
        m = re.search(r'create\s+(?:github\s+)?repo(?:sitory)?\s+(?:named\s+|called\s+)?["\']?([^\s"\']+)', lower)
        return ("github_create_repo", m.group(1)) if m else (None, None)
    if "push to github" in lower or "push to main" in lower or re.match(r'^git push', lower):
        m = re.search(r'push to (\w+)', lower)
        return ("github_push", m.group(1) if m else "main")
    if "run migrations" in lower or "push migrations" in lower or "supabase push" in lower or "supabase migrate" in lower:
        return ("supabase_migrate", "")
    if "deploy to vercel" in lower or "vercel deploy" in lower:
        return ("vercel_deploy", text)
    if "deploy to netlify" in lower or "netlify deploy" in lower:
        return ("netlify_deploy", text)
    if "deploy to railway" in lower or "railway deploy" in lower or "railway up" in lower:
        return ("railway_deploy", text)
    if "deploy worker" in lower or "cloudflare deploy" in lower or "wrangler deploy" in lower:
        return ("cloudflare_deploy", "")
    if lower.startswith("stripe trigger "):
        return ("stripe_trigger", text[len("stripe trigger "):].strip())


# ------------------------------------------------------------
# INSERT 2 — inside run_tool(), inside the `dispatch = {...}`
#            dict. Anchor: add these lines right after this
#            existing line in your file:
#                "self_run":_self_run,"self_explain":_self_explain,
# ------------------------------------------------------------

        "github_create_repo":_github_create_repo,
        "github_push":_github_push,
        "supabase_migrate":_supabase_migrate,
        "vercel_deploy":_vercel_deploy,
        "netlify_deploy":_netlify_deploy,
        "railway_deploy":_railway_deploy,
        "cloudflare_deploy":_cloudflare_deploy,
        "stripe_trigger":_stripe_trigger,


# ------------------------------------------------------------
# INSERT 3 — this block is safe to `cat >> router.py` since it's
#            new standalone functions, same style as your
#            _osint/_whois functions. Append after the last
#            function currently in the file.
# ------------------------------------------------------------

# ── DevOps / Deploy pipeline ─────────────────────────────
def _github_create_repo(args):
    reponame = args.strip()
    if not reponame: return "[Usage: create repo <name>]"
    if not shutil.which("gh"): return "[gh CLI not installed: pkg install gh]"
    return _run(f"gh repo create {reponame} --private --source=. --push", 30)

def _github_push(args):
    branch = args.strip() or "main"
    return _run(f"git push origin {branch}", 30)

def _supabase_migrate(args):
    if not shutil.which("supabase"): return "[supabase CLI not installed]"
    return _run("supabase db push", 30)

def _vercel_deploy(args):
    if not shutil.which("vercel"): return "[vercel CLI not installed]"
    flag = "--prod" if "prod" in args.lower() else ""
    return _run(f"vercel deploy {flag} --yes", 90)

def _netlify_deploy(args):
    if not shutil.which("netlify"): return "[netlify CLI not installed]"
    flag = "--prod" if "prod" in args.lower() else ""
    return _run(f"netlify deploy {flag}", 90)

def _railway_deploy(args):
    if not shutil.which("railway"): return "[railway CLI not installed]"
    return _run("railway up", 90)

def _cloudflare_deploy(args):
    if not shutil.which("wrangler"): return "[wrangler CLI not installed]"
    return _run("wrangler deploy", 60)

def _stripe_trigger(args):
    event = args.strip()
    if not event: return "[Usage: stripe trigger <event_name>]"
    if not shutil.which("stripe"): return "[stripe CLI not installed]"
    return _run(f"stripe trigger {event}", 20)
