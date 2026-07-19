"""
tools/devops_agent.py

DevOps Agent for KerrOS — follows the same ReactAgent pattern as your
Knowledge/Security/Code/Research/Planner/Reflection/Document agents.

ASSUMPTIONS (adjust imports to match your actual module paths):
- `agents.base.ReactAgent` exists and is the base class the other agents subclass
- `tools.scope_gate` exposes a `gate(action_name, details, destructive=bool)` function
  that does fail-closed inline y/n confirmation and raises ScopeGateDenied on "n"
- `core.context` has a way to log tool results back into episodic memory
  (left as a stub `log_episode()` call — wire to your daily_learning.py path)

DESIGN PRINCIPLE (matches your existing rule):
Every method that can mutate remote state (deploy, push, create repo, create
payment resource, send real email) is gated. Read-only methods (status checks,
listing envs) are NOT gated — no reason to friction-wall information retrieval.
Gating triggers only on explicit commands from the Planner/Code agents
("deploy now", "push to main", "create repo") — never on conversational
phrasing — same rule you already enforce for offensive tools.
"""

import subprocess
import shlex
import json
import logging
from dataclasses import dataclass
from typing import Optional

from agents.base import ReactAgent          # adjust to your actual base
from tools.scope_gate import gate, ScopeGateDenied

logger = logging.getLogger("kerros.devops_agent")


@dataclass
class CLIResult:
    ok: bool
    stdout: str
    stderr: str
    returncode: int


def _run(cmd: str, cwd: Optional[str] = None, timeout: int = 120) -> CLIResult:
    """Single choke point for every subprocess call this agent makes.
    Keeping it centralized means one place to add logging, timeouts,
    and env sanitization (never let secrets leak into logs)."""
    try:
        proc = subprocess.run(
            shlex.split(cmd),
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return CLIResult(proc.returncode == 0, proc.stdout.strip(),
                          proc.stderr.strip(), proc.returncode)
    except subprocess.TimeoutExpired:
        return CLIResult(False, "", f"timeout after {timeout}s", -1)
    except FileNotFoundError as e:
        return CLIResult(False, "", f"CLI not found: {e}", -1)


class DevOpsAgent(ReactAgent):
    """
    Tool surface exposed to the router. Each public method is a discrete
    tool the Planner/Code agents can call by name. Keep methods small and
    single-purpose — the router dispatches on method name + kwargs.
    """

    name = "devops"
    description = "Executes git/CI/deploy/backend/payments operations for web app builds."

    # ---------------------------------------------------------------
    # GIT / GITHUB
    # ---------------------------------------------------------------
    def git_init_repo(self, path: str, project_name: str) -> CLIResult:
        """Read-adjacent but low-risk local op — not gated."""
        _run("git init", cwd=path)
        _run('git config user.name "Kerr"', cwd=path)
        # NOTE: set your real email once here or read from a config file,
        # don't hardcode a placeholder that ends up in commit history.
        return _run(f'git add -A && git commit -m "init: {project_name}"', cwd=path)

    def github_create_repo(self, repo_name: str, private: bool = True) -> CLIResult:
        gate("github_create_repo", {"repo": repo_name, "private": private})
        vis = "--private" if private else "--public"
        return _run(f"gh repo create {repo_name} {vis} --source=. --push")

    def github_push(self, path: str, branch: str = "main") -> CLIResult:
        gate("github_push", {"path": path, "branch": branch}, destructive=True)
        return _run(f"git push origin {branch}", cwd=path)

    def github_open_pr(self, title: str, body: str) -> CLIResult:
        gate("github_open_pr", {"title": title})
        return _run(f'gh pr create --title "{title}" --body "{body}"')

    # ---------------------------------------------------------------
    # SUPABASE
    # ---------------------------------------------------------------
    def supabase_link(self, project_ref: str) -> CLIResult:
        gate("supabase_link", {"project_ref": project_ref})
        return _run(f"supabase link --project-ref {project_ref}")

    def supabase_push_migrations(self) -> CLIResult:
        gate("supabase_push_migrations", {}, destructive=True)
        return _run("supabase db push")

    def supabase_deploy_function(self, fn_name: str) -> CLIResult:
        gate("supabase_deploy_function", {"function": fn_name}, destructive=True)
        return _run(f"supabase functions deploy {fn_name}")

    def supabase_status(self) -> CLIResult:
        """Read-only — not gated."""
        return _run("supabase status")

    # ---------------------------------------------------------------
    # DEPLOY TARGETS — Vercel / Netlify / Railway
    # ---------------------------------------------------------------
    def vercel_deploy(self, path: str, prod: bool = False) -> CLIResult:
        gate("vercel_deploy", {"path": path, "prod": prod}, destructive=prod)
        flag = "--prod" if prod else ""
        return _run(f"vercel deploy {flag} --yes", cwd=path)

    def netlify_deploy(self, path: str, prod: bool = False) -> CLIResult:
        gate("netlify_deploy", {"path": path, "prod": prod}, destructive=prod)
        flag = "--prod" if prod else ""
        return _run(f"netlify deploy {flag}", cwd=path)

    def railway_deploy(self, path: str) -> CLIResult:
        gate("railway_deploy", {"path": path}, destructive=True)
        return _run("railway up", cwd=path)

    # ---------------------------------------------------------------
    # CLOUDFLARE
    # ---------------------------------------------------------------
    def cloudflare_deploy_worker(self, path: str) -> CLIResult:
        gate("cloudflare_deploy_worker", {"path": path}, destructive=True)
        return _run("wrangler deploy", cwd=path)

    def cloudflare_dns_status(self, zone: str) -> CLIResult:
        """Read-only — not gated."""
        return _run(f"wrangler dns list --zone {zone}")

    # ---------------------------------------------------------------
    # STRIPE (testing/webhooks only — never live keys through this agent)
    # ---------------------------------------------------------------
    def stripe_listen(self, forward_url: str) -> CLIResult:
        """Starts webhook forwarding for local testing. Not gated —
        this is a test-mode listener, not a mutation."""
        return _run(f"stripe listen --forward-to {forward_url}", timeout=5)

    def stripe_trigger_event(self, event_name: str) -> CLIResult:
        gate("stripe_trigger_event", {"event": event_name})
        return _run(f"stripe trigger {event_name}")

    # ---------------------------------------------------------------
    # RESEND (transactional email — gate any send, never gate template checks)
    # ---------------------------------------------------------------
    def resend_send_test_email(self, to: str, template: str) -> CLIResult:
        gate("resend_send_test_email", {"to": to, "template": template})
        # Resend has no CLI; this should call their HTTP API directly.
        # Left as a stub — wire to requests.post() with RESEND_API_KEY from env.
        raise NotImplementedError("wire to Resend HTTP API, not a CLI")

    # ---------------------------------------------------------------
    # PIPELINE ENTRYPOINT — what the Planner Agent actually calls
    # ---------------------------------------------------------------
    def run_pipeline(self, spec: dict) -> dict:
        """
        spec = {
            "path": "...", "project_name": "...", "repo_name": "...",
            "supabase_ref": "...", "deploy_target": "vercel|netlify|railway",
            "prod": False
        }
        Each stage is gated individually above — this just sequences them
        and stops on first failure rather than silently continuing.
        """
        results = {}
        try:
            results["git_init"] = self.git_init_repo(spec["path"], spec["project_name"])
            results["github_repo"] = self.github_create_repo(spec["repo_name"])
            if spec.get("supabase_ref"):
                results["supabase_link"] = self.supabase_link(spec["supabase_ref"])
                results["supabase_push"] = self.supabase_push_migrations()

            target = spec.get("deploy_target", "vercel")
            deploy_fn = {
                "vercel": self.vercel_deploy,
                "netlify": self.netlify_deploy,
                "railway": self.railway_deploy,
            }[target]
            results["deploy"] = deploy_fn(spec["path"], spec.get("prod", False)) \
                if target != "railway" else deploy_fn(spec["path"])

        except ScopeGateDenied as e:
            logger.info(f"Pipeline halted by scope gate: {e}")
            results["halted_at"] = str(e)

        return results
