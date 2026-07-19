"""
tools/scope_gate.py
====================
Fail-closed authorization gate for active/offensive tools.

Any tool that touches a real network target (scanning, exploitation-adjacent,
recon) must pass through is_authorized() before it runs. If the target isn't
in the explicit allowlist, execution is blocked — no LLM judgment call, no
"seems fine" — a hard code-level check that cannot be talked around by prompt
engineering or agent reasoning.

This is intentionally conservative. Add targets via /scope add <target>
in chat, which requires the human to explicitly confirm.
"""
import os, json, ipaddress, re, time

BASE = os.path.expanduser("~/offline_ai")
SCOPE_PATH = f"{BASE}/config/scope.json"

# Tools that touch real targets and require scope authorization.
# Passive/local tools (calc, sysinfo, file ops, knowledge lookups) are exempt.
OFFENSIVE_TOOLS = {
    "nmap", "nikto", "osint", "recon", "geoip", "geoint",
    "dnsenum", "reversedns", "email_osint", "sigint",
    "headers", "cert", "whois", "dig", "ping", "traceroute",
}

# Tools that mutate remote infra/repos/payments — never network-recon,
# so they don't fit the target-allowlist model above. Blocked by default;
# require a short explicit arm window instead.
DEPLOY_TOOLS = {
    "github_create_repo", "github_push", "supabase_migrate",
    "vercel_deploy", "netlify_deploy", "railway_deploy",
    "cloudflare_deploy", "stripe_trigger",
}


def _arm_status():
    scope = _load_scope()
    until = scope.get("deploy_armed_until", 0)
    return until, time.time() < until


def arm_deploy(minutes=5):
    """Opens a time-limited window during which DEPLOY_TOOLS will run.
    Call this only from an explicit human-issued command, never
    automatically from agent reasoning."""
    scope = _load_scope()
    scope["deploy_armed_until"] = time.time() + (minutes * 60)
    _save_scope(scope)
    return minutes


def disarm_deploy():
    scope = _load_scope()
    scope["deploy_armed_until"] = 0
    _save_scope(scope)



def _load_scope():
    if not os.path.exists(SCOPE_PATH):
        return {"authorized_targets": [], "authorized_cidrs": [], "require_explicit_authorization": True}
    try:
        with open(SCOPE_PATH) as f:
            return json.load(f)
    except Exception:
        return {"authorized_targets": [], "authorized_cidrs": [], "require_explicit_authorization": True}


def _save_scope(scope):
    os.makedirs(os.path.dirname(SCOPE_PATH), exist_ok=True)
    with open(SCOPE_PATH, "w") as f:
        json.dump(scope, f, indent=2)


def _extract_target(args):
    """args may be a string target or a tuple - normalize to a bare string."""
    if isinstance(args, (list, tuple)):
        return str(args[0]) if args else ""
    return str(args or "")


def is_authorized(target):
    """Returns True if target is explicitly allowlisted (exact match, domain, or CIDR)."""
    if not target:
        return False

    scope = _load_scope()
    target = target.strip().lower()
    # Strip protocol/path if a URL was passed
    target = re.sub(r'^https?://', '', target).split('/')[0]

    authorized = [t.lower() for t in scope.get("authorized_targets", [])]
    if target in authorized:
        return True

    # CIDR check for IPs
    try:
        ip = ipaddress.ip_address(target)
        for cidr in scope.get("authorized_cidrs", []):
            if ip in ipaddress.ip_network(cidr, strict=False):
                return True
    except ValueError:
        pass  # not an IP, skip CIDR check

    return False


def requires_gate(tool):
    return tool in OFFENSIVE_TOOLS


def check(tool, args):
    """
    Main gate entry point. Returns (allowed: bool, reason: str).
    Call this BEFORE run_tool() for any offensive OR deploy tool.
    """
    if tool in DEPLOY_TOOLS:
        until, armed = _arm_status()
        if armed:
            remaining = int(until - time.time())
            return True, f"deploy armed, {remaining}s remaining"
        return False, (
            f"BLOCKED: '{tool}' requires an armed deploy window. "
            f"Use /scope arm-deploy <minutes> to authorize, then retry."
        )

    if not requires_gate(tool):
        return True, "passive tool, no gate required"

    target = _extract_target(args)
    if is_authorized(target):
        return True, "authorized"

    return False, (
        f"BLOCKED: '{target}' is not in the authorized scope. "
        f"Use /scope add {target} to explicitly authorize it first."
    )


def add_target(target):
    scope = _load_scope()
    target = target.strip().lower()
    if target not in scope.get("authorized_targets", []):
        scope.setdefault("authorized_targets", []).append(target)
        _save_scope(scope)
        return True
    return False


def remove_target(target):
    scope = _load_scope()
    target = target.strip().lower()
    if target in scope.get("authorized_targets", []):
        scope["authorized_targets"].remove(target)
        _save_scope(scope)
        return True
    return False


def list_scope():
    scope = _load_scope()
    return scope.get("authorized_targets", []), scope.get("authorized_cidrs", [])
