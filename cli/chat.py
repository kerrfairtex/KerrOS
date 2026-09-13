import sys, os
from pathlib import Path

# Add the repository root before importing project modules. This is required
# for direct execution (`python3 cli/chat.py`) as well as `python3 -m cli.chat`.
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

import time, threading, random

# Handle dual invocation: python cli/chat.py and python -m cli.chat
try:
    from core.adaptive_engine import AdaptiveEngine, check_internet
    from core.context import build, build_chat
    from kernel.compat import generate_complete
    from memory.manager import (add_message, clear_session, init_session,
        get_history, get_recent, extract_and_learn, get_profile, update_profile,
        format_resume_picker, resume_session)
    from kernel.access import (
        detect_tool,
        run_tool,
        detect_domain,
        memory_query,
        memory_list_sources,
        memory_upsert,
        memory_ingest_file,
    )
    from tools.goal_state import ToolResult, GoalState, split_goal_steps
    from tools.code_saver import save_code_blocks, run_and_verify, extract_code_blocks
    from tools.claw_cli import detect_claw_tool, run_claw_tool, claw_tool_help_lines, claw_tools_summary
    from kernel import boot as kernel_boot, get_kernel, resolve
    from cli.chat_service import build_service
    from cli.ui import (
        Spinner,
        SwordSpinner,
        ai_header,
        ask_online_prompt,
        boot_sequence,
        divider,
        draw_agent_response,
        draw_header_panel,
        info_mode,
        info_ok,
        info_warn,
        mode_badge,
        print_welcome_banner,
        prompt_input,
        session_end,
        typewrite,
        BL,
        BOL,
        CY,
        GO,
        GR,
        GY,
        PU,
        RE,
        R,
        YL,
    )
except ImportError:
    # Fallback for direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from core.adaptive_engine import AdaptiveEngine, check_internet
    from core.context import build, build_chat
    from kernel.compat import generate_complete
    from memory.manager import (add_message, clear_session, init_session,
        get_history, get_recent, extract_and_learn, get_profile, update_profile,
        format_resume_picker, resume_session)
    from kernel.access import (
        detect_tool,
        run_tool,
        detect_domain,
        memory_query,
        memory_list_sources,
        memory_upsert,
        memory_ingest_file,
    )
    from tools.goal_state import ToolResult, GoalState, split_goal_steps
    from tools.code_saver import save_code_blocks, run_and_verify, extract_code_blocks
    from tools.claw_cli import detect_claw_tool, run_claw_tool, claw_tool_help_lines, claw_tools_summary
    from kernel import boot as kernel_boot, get_kernel, resolve
    from cli.chat_service import build_service
    from cli.ui import (
        Spinner,
        SwordSpinner,
        ai_header,
        ask_online_prompt,
        boot_sequence,
        divider,
        draw_agent_response,
        draw_header_panel,
        info_mode,
        info_ok,
        info_warn,
        mode_badge,
        print_welcome_banner,
        prompt_input,
        session_end,
        typewrite,
        BL,
        BOL,
        CY,
        GO,
        GR,
        GY,
        PU,
        RE,
        R,
        YL,
    )

# ── Markdown stripper ────────────────────────────────────
def strip_md(text):
    import re
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*[\*\-]\s+', '  • ', text, flags=re.MULTILINE)
    text = re.sub(r'`{1,3}([^`]+)`{1,3}', r'\1', text)
    return text.strip()

# ── Internet prompt ───────────────────────────────────────
def ask_mode(engine, spinner):
    has_net = check_internet()
    print()
    if has_net:
        choice = ask_online_prompt()
        if choice == "y":
            spinner.label = "Connecting"
            spinner.start()
            ok, msg = engine.switch_online()
            spinner.stop()
            if ok:
                info_ok("Online mode active")
                return "online"
            else:
                logging.debug(f"Online failed: {msg}")
                info_mode("Falling back to offline mode")
                engine.init_offline()
                return "offline"
        else:
            info_mode("Offline mode selected")
            engine.init_offline()
            return "offline"
    else:
        info_mode("No internet — offline mode active")
        engine.init_offline()
        return "offline"

def is_interactive():
    if os.environ.get("CI"):
        return False
    return sys.stdin.isatty() and sys.stdout.isatty()


def read_stdin_non_interactive() -> str | None:
    """Read one line from stdin when available; return None if empty/closed."""
    try:
        line = sys.stdin.readline()
        if not line:
            return None
        return line.strip()
    except (KeyboardInterrupt, EOFError):
        return None


# ── Main ──────────────────────────────────────────────────
def main():
    from models.engine.loader import ModelLoader
    ModelLoader().validate()
    
    if not is_interactive():
        sys.argv.append("--no-prompt")
    
    # If stdin is not interactive and has no piped input, exit cleanly
    if not is_interactive() and sys.stdin.isatty() is False and sys.stdin.buffer.peek() == b"":
        return
    
    boot_sequence()
    kernel = kernel_boot()
    kcfg = kernel.config
    init_session()  # reset in-memory session
    engine = AdaptiveEngine()
    try:
        from agents.subagents import bind_engine

        bind_engine(engine)
    except Exception:
        pass
    try:
        from gateway.channels.bridge import bind_channel_engine

        bind_channel_engine(engine)
    except Exception:
        pass
    
    # Check for --offline flag
    if "--offline" in sys.argv:
        mode = "offline"
        engine.init_offline()
        spinner = Spinner()
    else:
        spinner = Spinner()
        mode = ask_mode(engine, spinner)

    session_id = ""
    try:
        from memory.session_store import get_current_session_id

        session_id = get_current_session_id()
    except Exception:
        pass

    model_hint = ""
    try:
        model_hint = str(getattr(engine, "c", {}) or {}).get("model_path") or engine.current_mode
    except Exception:
        model_hint = mode

    print_welcome_banner(
        mode=mode,
        workspace=str(kcfg.workspace),
        session_id=session_id,
        phase=str(kernel.phase.value),
        model_hint=str(model_hint)[-48:],
    )

    chat_service = build_service(
        engine=engine,
        kernel=kernel,
        kcfg=kcfg,
        mode=mode,
        session_id=session_id,
        model_hint=model_hint,
    )

    while True:
        try:
            user = prompt_input()
        except (KeyboardInterrupt, EOFError):
            session_end()
            break

        if not user: continue

        # Fast-path dispatch for extracted testable commands.
        handled, svc_out = chat_service.dispatch(user)
        if handled:
            if svc_out:
                if svc_out == "":
                    session_end()
                    break
                print(f"  {svc_out}")
            continue

        if user=="/exit":
            session_end()
            break

        elif user.startswith("/scope add "):
            from tools.scope_gate import add_target
            t = user.replace("/scope add ", "").strip()
            confirm = input(f"  {YL}Authorize '{t}' for active scanning/recon tools? [y/n]{R} ").strip().lower()
            if confirm == "y":
                added = add_target(t)
                print(f"  {GR}[ ✓ ] '{t}' added to authorized scope{R}" if added else f"  {GY}Already authorized.{R}")
            else:
                print(f"  {GY}Cancelled.{R}")

        elif user.startswith("/scope remove "):
            from tools.scope_gate import remove_target
            t = user.replace("/scope remove ", "").strip()
            removed = remove_target(t)
            print(f"  {GR}[ ✓ ] Removed{R}" if removed else f"  {GY}Not in scope.{R}")

        elif user.startswith("/scope arm-deploy"):
            from tools.scope_gate import arm_deploy, load_policy
            parts = user.split()
            minutes = int(load_policy()["defaults"].get("deploy_arm_minutes", 5))
            if len(parts) >= 3:
                try:
                    minutes = int(parts[2])
                except ValueError:
                    print(f"  {GY}Usage: /scope arm-deploy <minutes>{R}")
                    minutes = None
            if minutes:
                confirm = input(f"  {YL}Arm deploy tools (github/vercel/netlify/railway/cloudflare/stripe/supabase) for {minutes} minute(s)? [y/n]{R} ").strip().lower()
                if confirm == "y":
                    arm_deploy(minutes)
                    print(f"  {GR}[ ✓ ] Deploy armed for {minutes} minute(s){R}")
                else:
                    print(f"  {GY}Cancelled.{R}")

        elif user.startswith("/scope policy"):
            handled, out = chat_service.dispatch(user)
            if handled and out:
                divider()
                print(f"  {out}")
                divider()
                continue

        elif user == "/scope":
            handled, out = chat_service.dispatch(user)
            if handled and out:
                divider()
                print(f"  {out}")
                divider()
                continue

        elif user == "/apistatus":
            handled, out = chat_service.dispatch(user)
            if handled and out:
                divider()
                print(f"  {out}")
                divider()
                continue

        elif user == "/integrations" or user.startswith("/integrations "):
            handled, out = chat_service.dispatch(user)
            if handled and out:
                divider()
                print(f"  {out}")
                divider()
                continue

        elif user == "/mode":
            handled, out = chat_service.dispatch(user)
            if handled and out:
                print(f"  {out}")
                continue

        elif user == "/online":
            handled, out = chat_service.dispatch(user)
            if handled and out:
                print(f"  {out}")
                continue

        elif user == "/offline":
            handled, out = chat_service.dispatch(user)
            if handled and out:
                info_mode(out)
                continue

        elif user.startswith("/setkey "):
            handled, out = chat_service.dispatch(user)
            if handled:
                print(f"  {out}")
                continue

        elif user == "/help":
            handled, out = chat_service.dispatch(user)
            if handled and out:
                divider()
                print(f"  {out}")
                divider()
                continue

        elif user == "/clear":
            handled, out = chat_service.dispatch(user)
            if handled and out:
                print(f"  {out}")
                continue

        elif user == "/resume" or user.startswith("/resume "):
            handled, out = chat_service.dispatch(user)
            if handled and out:
                print(f"  {out}")
                continue

        elif user == "/memory" or user.startswith("/memory "):
            handled, out = chat_service.dispatch(user)
            if handled and out:
                divider()
                print(f"  {out}")
                divider()
                continue

        elif user == "/history":
            handled, out = chat_service.dispatch(user)
            if handled and out:
                divider()
                print(f"  {out}")
                divider()
                continue

        elif user == "/tools":
            handled, out = chat_service.dispatch(user)
            if handled and out:
                divider()
                print(f"  {out}")
                divider()
                continue

        elif user == "/kernel":
            handled, out = chat_service.dispatch(user)
            if handled and out:
                divider()
                print(f"  {out}")
                divider()
                continue

        elif user == "/health":
            handled, out = chat_service.dispatch(user)
            if handled and out:
                divider()
                print(f"  {out}")
                divider()
                continue

        elif user == "/services":
            handled, out = chat_service.dispatch(user)
            if handled and out:
                divider()
                print(f"  {out}")
                divider()
                continue

        elif user.startswith("/events"):
            divider()
            try:
                parts = user.split()
                count = int(parts[1]) if len(parts) > 1 else 10
                bus = resolve("event_bus")
                events = bus.recent(count)
                if not events:
                    print(f"  {GY}No events yet.{R}")
                for ev in events:
                    payload = ev.get("payload", {}) or {}
                    if ev.get("topic") == "omniroute.usage":
                        summary = (
                            f"cost={payload.get('cost_usd', '?')} "
                            f"in={payload.get('tokens_in', '?')} "
                            f"out={payload.get('tokens_out', '?')} "
                            f"model={payload.get('model', payload.get('requested_model', '?'))} "
                            f"provider={payload.get('upstream_provider', '?')}"
                        )
                        print(
                            f"  {GO}{ev['topic']}{R} "
                            f"{GY}{ev.get('source', '')}{R} "
                            f"{summary}"
                        )
                    else:
                        print(
                            f"  {GO}{ev['topic']}{R} "
                            f"{GY}{ev.get('source', '')}{R} "
                            f"{str(payload)[:80]}"
                        )
                stats = bus.stats()
                print(f"  {BL}Total:{R} {stats['events']} events, {stats['listeners']} listeners")
            except Exception as e:
                print(f"  {RE}Events unavailable: {e}{R}")
            divider()

        elif user.startswith("/schedule"):
            divider()
            try:
                parts = user.split()
                sched = resolve("scheduler")
                if len(parts) >= 2 and parts[1] == "cron":
                    # /schedule cron <name> <m> <h> <dom> <mon> <dow>
                    if len(parts) < 8:
                        print(
                            f"  {GY}Usage: /schedule cron <name> <m h dom mon dow>{R}\n"
                            f"  {GY}Example: /schedule cron heartbeat */5 * * * *{R}"
                        )
                    else:
                        name = parts[2]
                        expr = " ".join(parts[3:8])
                        job_id = sched.schedule_cron(name, expr)
                        print(
                            f"  {GR}[ ✓ ]{R} cron job {GO}{name}{R} "
                            f"id={job_id[:8]}…  expr={expr}"
                        )
                elif len(parts) >= 3 and parts[1] == "cancel":
                    ok = sched.cancel(parts[2])
                    if ok:
                        print(f"  {GR}[ ✓ ]{R} cancelled {parts[2]}")
                    else:
                        print(f"  {RE}No job matched id prefix {parts[2]}{R}")
                else:
                    jobs = sched.list_jobs()
                    if not jobs:
                        print(f"  {GY}No scheduled jobs.{R}")
                    for job in jobs:
                        when = "-"
                        if job.get("cron"):
                            when = f"cron={job['cron']}"
                        elif job.get("interval_s"):
                            when = f"interval={job['interval_s']}"
                        print(
                            f"  {GO}{job['name']}{R} id={job['id'][:8]} "
                            f"runs={job['run_count']} {when}"
                        )
                    print(
                        f"  {GY}/schedule cron <name> <expr> · "
                        f"/schedule cancel <id>{R}"
                    )
            except Exception as e:
                print(f"  {RE}Scheduler unavailable: {e}{R}")
            divider()

        elif user.startswith("/workflows"):
            divider()
            try:
                parts = user.split()
                wf = resolve("workflow_engine")
                if len(parts) >= 3 and parts[1] == "resume":
                    run = wf.resume(parts[2])
                    print(
                        f"  {GO}resumed{R} {run.id[:8]}…  "
                        f"{run.workflow}  state={run.state.value}"
                    )
                elif len(parts) >= 2 and parts[1] == "runs":
                    limit = int(parts[2]) if len(parts) > 2 else 10
                    runs = wf.list_runs(limit=limit)
                    if not runs:
                        print(f"  {GY}No persisted workflow runs.{R}")
                    for row in runs:
                        rid = str(row.get("id", ""))[:8]
                        print(
                            f"  {GO}{row.get('workflow')}{R}  "
                            f"id={rid}…  state={row.get('state')}  "
                            f"err={row.get('error') or '-'}"
                        )
                elif len(parts) >= 2 and parts[1] == "run":
                    if len(parts) < 3:
                        print(f"  {RE}Usage: /workflows run <name>{R}")
                    else:
                        run = wf.run(parts[2])
                        print(
                            f"  {GO}ran{R} {run.workflow}  "
                            f"id={run.id[:8]}…  state={run.state.value}"
                        )
                        if run.results:
                            print(f"  {GY}results:{R} {run.results}")
                elif len(parts) >= 2 and parts[1] == "reload":
                    from pathlib import Path as _Path
                    from kernel.boot import get_kernel

                    k = get_kernel()
                    yaml_dir = _Path("config/workflows")
                    if k and k.config:
                        yaml_dir = _Path(
                            str(
                                k.config.get(
                                    "workflow_yaml_dir",
                                    k.config.base / "config" / "workflows",
                                )
                            )
                        )
                        if not yaml_dir.is_absolute():
                            yaml_dir = k.config.base / yaml_dir
                    names = wf.load_yaml_dir(yaml_dir)
                    print(
                        f"  {GO}reloaded{R} {len(names)} workflow(s) from {yaml_dir}"
                    )
                    for name in names:
                        print(f"  {GO}{name}{R}")
                else:
                    names = wf.list_workflows()
                    if not names:
                        print(f"  {GY}No workflows registered.{R}")
                    for name in names:
                        print(f"  {GO}{name}{R}")
                    print(
                        f"  {GY}/workflows run <name> · /workflows runs [n] · "
                        f"/workflows resume <id> · /workflows reload{R}"
                    )
            except Exception as e:
                print(f"  {RE}Workflows unavailable: {e}{R}")
            divider()

        elif user.startswith("/llm"):
            divider()
            try:
                parts = user.split()
                port = resolve("llm_port")
                if len(parts) >= 2 and parts[1] == "reset":
                    target = parts[2] if len(parts) > 2 else None
                    if hasattr(port, "reset_resilience"):
                        reset = port.reset_resilience(target)
                        print(
                            f"  {GR}[ ✓ ]{R} resilience reset: "
                            f"{', '.join(reset) if reset else (target or 'all')}"
                        )
                    else:
                        print(f"  {GY}Resilience reset not supported on this LLM port.{R}")
                else:
                    status = port.status() if hasattr(port, "status") else {}
                    print(f"  {BL}Provider:{R} {status.get('default_provider', 'cloud')}")
                    print(f"  {BL}Local first:{R} {status.get('local_first', False)}")
                    print(f"  {BL}Last API:{R} {status.get('last_api') or '-'}")
                    for key in ("ollama", "vllm", "litellm", "omniroute", "cloud"):
                        info = status.get(key, {})
                        if isinstance(info, dict):
                            avail = info.get("available", info.get("enabled", info.get("groq", "?")))
                            print(f"  {GO}{key}{R}: available={avail}")
                    resilience = status.get("resilience") or {}
                    if resilience:
                        print(
                            f"  {BL}Resilience:{R} enabled={resilience.get('enabled')} "
                            f"threshold={resilience.get('config', {}).get('failure_threshold')} "
                            f"cooldown={resilience.get('config', {}).get('cooldown_s')}s"
                        )
                        for pname, pinfo in (resilience.get("providers") or {}).items():
                            print(
                                f"    {GO}{pname}{R}: {pinfo.get('state')} "
                                f"fails={pinfo.get('consecutive_failures')} "
                                f"opens={pinfo.get('open_count')} "
                                f"cd={pinfo.get('cooldown_remaining_s')}s "
                                f"lock={pinfo.get('lockout_remaining_s')}s"
                            )
                    print(f"  {GY}/llm reset [provider]{R}")
            except Exception as e:
                print(f"  {RE}LLM status unavailable: {e}{R}")
            divider()

        elif user.startswith("/capabilities"):
            divider()
            try:
                parts = user.split()
                sub = parts[1] if len(parts) > 1 else None
                if sub in ("export", "docs", "render"):
                    import subprocess
                    import sys as _sys
                    from pathlib import Path
                    script = Path(__file__).resolve().parent.parent / "scripts" / "render_capabilities.py"
                    result = subprocess.run(
                        [_sys.executable, str(script)],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    out = (result.stdout or result.stderr or "").strip()
                    if result.returncode == 0:
                        print(f"  {GR}[ ✓ ]{R} {out or 'docs/CAPABILITIES.md regenerated'}")
                    else:
                        print(f"  {RE}Export failed:{R} {out}")
                else:
                    kind = sub
                    registry = resolve("capability_registry")
                    caps = registry.list(kind=kind)
                    if not caps:
                        print(f"  {GY}No capabilities registered{(' for kind=' + kind) if kind else ''}.{R}")
                    else:
                        print(f"  {BL}Count:{R} {len(caps)}" + (f"  kind={kind}" if kind else ""))
                        for cap in caps:
                            print(
                                f"  {GO}{cap.name}{R}  [{cap.kind}]  "
                                f"{cap.setup_state}  perms={','.join(cap.permissions) or '-'}"
                            )
                        print(f"  {GY}Tip: /capabilities export → docs/CAPABILITIES.md{R}")
            except Exception as e:
                print(f"  {RE}Capabilities unavailable: {e}{R}")
            divider()

        elif user == "/decisions" or user.startswith("/decisions "):
            divider()
            parts = user.split(None, 2)
            sub = parts[1].strip().lower() if len(parts) > 1 else ""
            try:
                log = resolve("decision_log")
                from adapters.audit.rbac import (
                    AuditRbacError,
                    audit_rbac_from_config,
                    current_audit_token,
                    require_audit_action,
                )

                if sub == "whoami":
                    rbac = audit_rbac_from_config(resolve("config").values)
                    if not rbac.enabled:
                        print(f"  {GY}audit RBAC disabled (open access){R}")
                    else:
                        role = rbac.role_for_token(current_audit_token())
                        print(
                            f"  {BL}role:{R} {role or 'none'}  "
                            f"(set KERROS_AUDIT_TOKEN)"
                        )
                elif sub == "privacy":
                    from adapters.audit.privacy import privacy_status

                    st = privacy_status(resolve("config").values)
                    print(
                        f"  {BL}privacy:{R} enabled={st['enabled']}  "
                        f"mode={st['mode']}  fields={','.join(st['fields'])}  "
                        f"apply_on={','.join(st['apply_on'])}"
                    )
                elif sub == "residency":
                    from adapters.audit.residency import residency_status

                    require_audit_action("residency")
                    st = residency_status(resolve("config").values)
                    print(
                        f"  {BL}residency:{R} enabled={st['enabled']}  "
                        f"region={st['region'] or '(unset)'}"
                    )
                elif sub == "erasure":
                    from adapters.audit.erasure_ledger import evaluate_erasure_request

                    # /decisions erasure <subject_ref> [id,id,...]
                    rest = parts[2].strip() if len(parts) > 2 else ""
                    if not rest:
                        print(
                            f"  {RE}Usage:{R} /decisions erasure <subject_ref> [id,id,...]"
                        )
                    else:
                        bits = rest.split(None, 1)
                        subject = bits[0]
                        ids: list[int] = []
                        if len(bits) > 1:
                            ids = [
                                int(x)
                                for x in bits[1].replace(" ", "").split(",")
                                if x.strip().isdigit()
                            ]
                        cfg = resolve("config")
                        out = evaluate_erasure_request(
                            subject_ref=subject,
                            decision_ids=ids,
                            actor="cli",
                            cfg=cfg.values,
                            base=cfg.base,
                        )
                        if out.get("ok"):
                            req = out.get("request") or {}
                            print(
                                f"  {GR}[ ✓ ]{R} erasure #{req.get('id')}  "
                                f"status={req.get('status')}  "
                                f"policy={out.get('policy')}"
                            )
                            if out.get("overlap_ids"):
                                print(
                                    f"  {GY}sealed overlap (not rewritten): "
                                    f"{out['overlap_ids']}{R}"
                                )
                        else:
                            print(f"  {RE}Erasure failed:{R} {out.get('error') or out}")
                elif sub == "erasure-review":
                    from adapters.audit.erasure_ledger import review_sealed_erasure

                    rest = parts[2].strip() if len(parts) > 2 else ""
                    bits = rest.split(None, 1)
                    if len(bits) < 2 or not bits[0].isdigit():
                        print(
                            f"  {RE}Usage:{R} /decisions erasure-review <id> "
                            f"<legal_hold_retain|acknowledged_immutable|schedule_post_retention>"
                        )
                    else:
                        cfg = resolve("config")
                        out = review_sealed_erasure(
                            int(bits[0]),
                            outcome=bits[1].strip(),
                            actor="cli",
                            cfg=cfg.values,
                            base=cfg.base,
                        )
                        if out.get("ok"):
                            rev = out.get("review") or {}
                            print(
                                f"  {GR}[ ✓ ]{R} review #{rev.get('id')}  "
                                f"outcome={out.get('outcome')}  "
                                f"worm_untouched={out.get('worm_untouched')}"
                            )
                        else:
                            print(f"  {RE}Review failed:{R} {out.get('error') or out}")
                elif sub == "transfer":
                    from adapters.audit.transfer_ledger import record_transfer_intent

                    rest = parts[2].strip() if len(parts) > 2 else ""
                    bits = rest.split(None, 2)
                    if len(bits) < 2:
                        print(
                            f"  {RE}Usage:{R} /decisions transfer <to_region> "
                            f"<scc|adequacy|consent|derogation|internal> [purpose]"
                        )
                    else:
                        cfg = resolve("config")
                        out = record_transfer_intent(
                            to_region=bits[0],
                            mechanism=bits[1],
                            purpose=bits[2] if len(bits) > 2 else "",
                            actor="cli",
                            cfg=cfg.values,
                            base=cfg.base,
                        )
                        if out.get("ok"):
                            tr = out.get("transfer") or {}
                            print(
                                f"  {GR}[ ✓ ]{R} transfer #{tr.get('id')}  "
                                f"{tr.get('from_region')}→{tr.get('to_region')}  "
                                f"via {tr.get('mechanism')}  "
                                f"cross_border={out.get('cross_border')}"
                            )
                        else:
                            print(f"  {RE}Transfer failed:{R} {out.get('error') or out}")
                elif sub == "transfer-exec":
                    from adapters.audit.transfer_pipeline import execute_transfer

                    rest = parts[2].strip() if len(parts) > 2 else ""
                    if not rest or not rest.split()[0].isdigit():
                        print(f"  {RE}Usage:{R} /decisions transfer-exec <id>")
                    else:
                        cfg = resolve("config")
                        out = execute_transfer(
                            int(rest.split()[0]),
                            cfg=cfg.values,
                            base=cfg.base,
                        )
                        if out.get("ok"):
                            print(
                                f"  {GR}[ ✓ ]{R} executed transfer #{out.get('request_id')}  "
                                f"artifacts={len(out.get('artifacts') or [])}  "
                                f"dest={out.get('dest_dir')}"
                            )
                        else:
                            print(f"  {RE}Execute failed:{R} {out.get('error') or out}")
                elif sub == "verify":
                    require_audit_action("verify")
                    result = log.verify_chain()
                    if result.get("ok"):
                        print(
                            f"  {GR}[ ✓ ]{R} chain ok  checked={result.get('checked')}  "
                            f"tip={(result.get('tip') or '')[:16]}…"
                        )
                    else:
                        print(
                            f"  {RE}[ ✗ ]{R} chain broken at #{result.get('broken_at')}: "
                            f"{result.get('error')}"
                        )
                elif sub == "export":
                    from pathlib import Path as _Path
                    from adapters.audit.decision_log_export import export_decision_log_jsonl

                    if len(parts) > 2 and parts[2].strip():
                        dest = parts[2].strip()
                    else:
                        base = resolve("config").base
                        dest = str(_Path(base) / "data" / "audit_export" / "decision_log.jsonl")
                    out = export_decision_log_jsonl(dest, log=log)
                    if out.get("ok"):
                        print(
                            f"  {GR}[ ✓ ]{R} exported {out.get('exported')} → {out.get('path')}"
                            + (" (hmac)" if out.get("hmac") else "")
                        )
                    else:
                        print(f"  {RE}Export failed:{R} {out.get('error') or out}")
                elif sub == "seal":
                    from adapters.audit.worm_store import WormStore, WormStoreError

                    if len(parts) < 3 or not parts[2].strip().split()[0].isdigit():
                        print(f"  {RE}Usage:{R} /decisions seal <through_id>")
                    else:
                        cfg = resolve("config")
                        worm_rel = (
                            (cfg.values.get("audit_retention") or {}).get("worm_dir")
                            or "data/audit_worm"
                        )
                        worm_dir = cfg.base / worm_rel
                        try:
                            out = WormStore(worm_dir).seal_from_log(
                                log, through_id=int(parts[2].strip().split()[0])
                            )
                            print(
                                f"  {GR}[ ✓ ]{R} sealed segment "
                                f"{out.get('segment'):06d} "
                                f"ids {out.get('first_id')}–{out.get('last_id')} → "
                                f"{out.get('path')}"
                            )
                        except (WormStoreError, AuditRbacError) as exc:
                            print(f"  {RE}Seal failed:{R} {exc}")
                elif sub == "retain":
                    from adapters.audit.retention import apply_retention

                    cfg = resolve("config")
                    policy = dict(cfg.values.get("audit_retention") or {})
                    policy["enabled"] = True
                    out = apply_retention(
                        log,
                        cfg={**cfg.values, "audit_retention": policy},
                        base=cfg.base,
                    )
                    if out.get("ok"):
                        print(
                            f"  {GR}[ ✓ ]{R} retention {out.get('action')} "
                            f"{out.get('reason') or out.get('through_id') or ''}"
                        )
                    else:
                        print(f"  {RE}Retention failed:{R} {out.get('error') or out}")
                else:
                    require_audit_action("read")
                    from adapters.audit.privacy import maybe_redact_record
                    from adapters.audit.residency import maybe_stamp_residency

                    rows = log.read_recent(15)
                    if not rows:
                        print(f"  {GY}No decision log entries yet.{R}")
                    cfg_values = resolve("config").values
                    for row in rows:
                        view = maybe_redact_record(
                            row, channel="cli_read", cfg=cfg_values
                        )
                        view = maybe_stamp_residency(
                            view, channel="cli_read", cfg=cfg_values
                        )
                        digest = (view.get("entry_hash") or "")[:12]
                        suffix = f"  {GY}{digest}…{R}" if digest else ""
                        summary = str(view.get("input_summary") or "")[:60]
                        region = view.get("residency_region")
                        region_s = f"  {GY}[{region}]{R}" if region else ""
                        print(
                            f"  {GO}#{view.get('id')}{R} "
                            f"{GY}{view.get('decision_type')}{R} "
                            f"{view.get('outcome')} — {summary}{suffix}{region_s}"
                        )
                    print(
                        f"  {GY}Tip: /decisions verify | export | seal | retain | "
                        f"whoami | privacy | residency | erasure | "
                        f"erasure-review | transfer | transfer-exec{R}"
                    )
            except AuditRbacError as e:
                print(f"  {RE}Denied:{R} {e}")
            except Exception as e:
                print(f"  {RE}Decision log unavailable: {e}{R}")
            divider()

        elif user == "/reflect":
            from agents.reflection import ReflectionAgent
            spinner.stop()
            ReflectionAgent(engine).run(stream=True)

        elif user == "/reflections":
            from agents.reflection import ReflectionAgent
            hist = ReflectionAgent(engine).history()
            divider()
            if hist:
                for r in hist:
                    print(f"  {GO}{r['timestamp']}{R} [{r['confidence']}]")
                    print(f"  {CY}Lesson:{R} {r['lesson']}")
            else:
                print(f"  {GY}No reflections saved yet.{R}")
            divider()

        elif user.startswith("/security "):
            from agents.security import SecurityAgent
            t = user.split(" ",1)[1].strip()
            spinner.stop()
            result = SecurityAgent(engine).run(t, stream=True)
            add_message("assistant", result)

        elif user.startswith("/code "):
            from agents.code import CodeAgent
            t = user.split(" ",1)[1].strip()
            spinner.stop()
            result = CodeAgent(engine).run(t, stream=True)
            add_message("assistant", result)

        elif user.startswith("/research "):
            from agents.research import ResearchAgent
            t = user.split(" ",1)[1].strip()
            spinner.stop()
            result = ResearchAgent(engine).run(t, stream=True)
            add_message("assistant", result)

        elif user.startswith("/plan "):
            from agents.planner import Planner
            t = user.split(" ",1)[1].strip()
            spinner.stop()
            result = Planner(engine).run(t, stream=True)
            add_message("assistant", result)

        elif user.startswith("/knowledge ") or user.startswith("/kb "):
            from agents.knowledge import KnowledgeAgent
            q = user.split(" ", 1)[1].strip() if " " in user else ""
            if not q:
                print(f"  {RE}Usage: /knowledge <question>{R}")
            else:
                agent = KnowledgeAgent(engine)
                spinner.stop()
                result = agent.run(q, stream=True)
                add_message("assistant", result)

        elif user.startswith("/react ") or user.startswith("agent:"):
            from agents.react import ReactAgent
            task = user.replace("/react ","").replace("agent:","").strip()
            if not task:
                print(f"  {RE}Usage: /react <task>{R}")
            else:
                agent = ReactAgent(engine)
                spinner.stop()
                result = agent.run(task, stream=True)
                divider()
                ai_header(mode)
                typewrite(result)
                divider()
                add_message("assistant", result)

        elif user.startswith("/delegate ") or user == "/delegate":
            from agents.subagents import bind_engine, delegate_tasks, parse_delegate_args

            raw = user[len("/delegate") :].strip()
            jobs = parse_delegate_args(raw)
            if not jobs:
                print(
                    f"  {RE}Usage: /delegate knowledge: <q> || research: <q2>{R}\n"
                    f"  {GY}Enable with KERROS_SUBAGENTS=1 (RAM-aware; max 2 workers).{R}"
                )
            else:
                bind_engine(engine)
                spinner.label = "Delegating"
                spinner.start()
                try:
                    from kernel.config import load_config

                    out = delegate_tasks(jobs, engine, cfg=load_config().values)
                except Exception as exc:
                    spinner.stop()
                    print(f"  {RE}[delegate] {exc}{R}")
                    out = None
                else:
                    spinner.stop()
                if out is not None:
                    text = out.get("summary") or out.get("error") or str(out)
                    divider()
                    ai_header(mode)
                    typewrite(text)
                    divider()
                    add_message("assistant", text[:800])

        elif user.startswith("/analyze"):
            handled, out = chat_service.dispatch(user)
            if handled:
                if out:
                    divider()
                    print(f"  {out}")
                    divider()
                continue

        elif user.startswith("/switch "):
            handled, out = chat_service.dispatch(user)
            if handled:
                print(f"  {out}")
                continue

        elif user.startswith("/learn "):
            handled, out = chat_service.dispatch(user)
            if handled:
                print(f"  {out}")
                continue

        elif user.startswith("/ingest "):
            handled, out = chat_service.dispatch(user)
            if handled:
                print(f"  {out}")
                continue

        elif user == "/sources":
            handled, out = chat_service.dispatch(user)
            if handled:
                print(f"  {out}")
                continue

        elif user == "/recall" or user.startswith("/recall "):
            handled, out = chat_service.dispatch(user)
            if handled:
                divider()
                print(f"  {out}")
                divider()
                continue

        elif user.startswith("/search "):
            handled, out = chat_service.dispatch(user)
            if handled:
                divider()
                print(f"  {out}")
                divider()
                continue

        else:
            result = chat_service.run_noninteractive_flow(user, None, active_goal, engine)
            active_goal = result["active_goal"]
            response = result["response"]
            if result.get("goal_complete"):
                print(f"  {GR}[goal] complete!{R}")
            elif result.get("goal_stuck"):
                _step_desc = active_goal.current_step()["desc"] if active_goal else ""
                print(f"  {RE}[goal] still stuck on: {_step_desc}{R}")
            if response:
                print(draw_agent_response(response, label=f"KerrOS [{mode}]"))
            if result.get("error"):
                print(f"  {RE}[error] {result['error']}{R}")

            # Only save clean short responses
            clean_resp = response.strip()
            if clean_resp and len(clean_resp) < 800:
                add_message("assistant", clean_resp)

if __name__=="__main__":
    main()
