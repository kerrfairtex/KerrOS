import logging
logging.basicConfig(filename="kerros.log", level=logging.DEBUG)
import sys, os, time, threading, random
sys.path.insert(0, os.path.expanduser("~/offline_ai"))

from core.adaptive_engine import AdaptiveEngine, check_internet
from core.context import build, build_chat
from core.thinking import needs_thinking
from core.complete import generate_complete
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
from cli.ui import (
    ANGEL_LOGO,
    Spinner,
    ai_header,
    ask_online_prompt,
    boot_sequence,
    divider,
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

# ── Main ──────────────────────────────────────────────────
def main():
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

    while True:
        try:
            user = prompt_input()
        except (KeyboardInterrupt, EOFError):
            session_end()
            break

        if not user: continue

        if user=="/exit":
            session_end()
            break

        elif user.startswith("/scope add "):
            from tools.scope_gate import add_target
            t = user.replace("/scope add ","").strip()
            confirm = input(f"  {YL}Authorize '{t}' for active scanning/recon tools? [y/n]{R} ").strip().lower()
            if confirm == "y":
                added = add_target(t)
                print(f"  {GR}[ ✓ ] '{t}' added to authorized scope{R}" if added else f"  {GY}Already authorized.{R}")
            else:
                print(f"  {GY}Cancelled.{R}")

        elif user.startswith("/scope remove "):
            from tools.scope_gate import remove_target
            t = user.replace("/scope remove ","").strip()
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
            parts = user.split()
            if len(parts) >= 3 and parts[2] in ("export", "docs", "render"):
                divider()
                try:
                    import subprocess
                    import sys
                    from pathlib import Path
                    script = Path(__file__).resolve().parent.parent / "scripts" / "render_scope_policy.py"
                    result = subprocess.run(
                        [sys.executable, str(script)],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    out = (result.stdout or result.stderr or "").strip()
                    if result.returncode == 0:
                        print(f"  {GR}[ ✓ ]{R} {out or 'docs/SCOPE_POLICY.md regenerated'}")
                    else:
                        print(f"  {RE}Export failed:{R} {out}")
                except Exception as e:
                    print(f"  {RE}Export failed: {e}{R}")
                divider()
            else:
                from tools.scope_gate import policy_summary
                summary = policy_summary()
                divider()
                print(f"  {BL}Source:{R} {summary.get('source')}")
                print(f"  {BL}Offensive ({len(summary['offensive_tools'])}):{R} {', '.join(summary['offensive_tools'])}")
                print(f"  {BL}Deploy ({len(summary['deploy_tools'])}):{R} {', '.join(summary['deploy_tools'])}")
                print(f"  {BL}Defaults:{R} {summary.get('defaults')}")
                print(f"  {GY}Tip: /scope policy export → docs/SCOPE_POLICY.md{R}")
                divider()

        elif user=="/scope":
            from tools.scope_gate import list_scope, policy_summary
            targets, cidrs = list_scope()
            summary = policy_summary()
            divider()
            print(f"  {BL}Authorized targets:{R} {', '.join(targets) if targets else 'none'}")
            print(f"  {BL}Authorized CIDRs:{R} {', '.join(cidrs) if cidrs else 'none'}")
            print(f"  {BL}Policy:{R} {summary.get('source')}  (use /scope policy)")
            divider()

        elif user=="/apistatus":
            divider()
            if engine._multi:
                h = engine._multi.health
                if h:
                    for name, status in h.items():
                        print(f"  {BL}{name:<20}{R} {status}")
                else:
                    print(f"  {GY}No API calls made yet this session.{R}")
                if engine._multi.dead_apis:
                    print(f"  {RE}Dead (auth failed): {', '.join(engine._multi.dead_apis)}{R}")
            else:
                print(f"  {GY}Online mode not initialized yet — showing catalog instead.{R}")
            try:
                from adapters.integrations.registry import catalog_status, format_status_lines, resolve_for_task
                st = catalog_status()
                print(f"  {BL}catalog{R} ready={st.get('ready_count')} needs_setup={st.get('needs_setup_count')}")
                coding = resolve_for_task("coding")
                if coding.get("ok"):
                    print(f"  {GR}coding tier → {coding.get('provider')} ({coding.get('model') or ''}){R}")
                else:
                    print(f"  {GY}coding tier: no provider key configured yet{R}")
                print(f"  {GY}Tip: /integrations [section|coding] — full catalog{R}")
            except Exception as exc:
                print(f"  {GY}integrations catalog unavailable: {exc}{R}")
            divider()

        elif user == "/integrations" or user.startswith("/integrations "):
            divider()
            try:
                from adapters.integrations.registry import (
                    catalog_status,
                    format_status_lines,
                    list_tiers,
                    resolve_tier,
                )
                arg = user[len("/integrations"):].strip().lower()
                if arg in ("sol", "terra", "luna", "coding", "research"):
                    tiers = list_tiers()
                    spec = tiers.get(arg) or {}
                    print(f"  {BL}tier:{arg}{R} {spec.get('description', '')}")
                    print(f"  providers: {', '.join(spec.get('providers') or [])}")
                    print(f"  resolve: {resolve_tier(arg)}")
                else:
                    section = arg or None
                    ready_only = False
                    if arg == "ready":
                        section = None
                        ready_only = True
                    st = catalog_status(sections=[section] if section else None)
                    for line in format_status_lines(st, section=section, ready_only=ready_only):
                        print(f"  {line}")
            except Exception as exc:
                print(f"  {RE}integrations error: {exc}{R}")
            divider()

        elif user=="/mode":
            print(f"  {mode_badge(engine.current_mode)}")

        elif user=="/online":
            spinner.label="Connecting"
            spinner.start()
            ok,msg=engine.switch_online()
            spinner.stop()
            mode=engine.current_mode
            if ok: print(f"  {GR}[ ✓ ] Switched to online — LLaMA-3.3-70B{R}")
            else: print(f"  {RE}[ ✗ ] {msg}{R}")

        elif user=="/offline":
            engine.switch_offline()
            mode=engine.current_mode
            info_mode("Switched to offline mode")

        elif user.startswith("/setkey "):
            parts=user.split()
            if len(parts)==3 and parts[1]=="groq":
                import json
                p="/data/data/com.termux/files/home/offline_ai/config.json"
                with open(p) as f: c=json.load(f)
                c["groq_api_key"]=parts[2]
                with open(p,"w") as f: json.dump(c,f,indent=2)
                print(f"  {GR}[ ✓ ] Groq API key saved{R}")
            else:
                print(f"  {GY}Usage: /setkey groq YOUR_API_KEY{R}")

        elif user=="/help":
            divider()
            cmds=[
                ("/online",            "Switch to online mode (Groq)"),
                ("/offline",           "Switch to offline mode (local)"),
                ("/mode",              "Show current mode"),
                ("/scope",             "Show authorized scan/recon targets"),
                ("/scope add <t>",     "Authorize a target for active tools"),
                ("/scope remove <t>",  "Remove a target from scope"),
                ("/scope arm-deploy",  "Arm deploy tools for N minutes"),
                ("/scope policy",      "Show declarative scope_policy.yaml"),
                ("/scope policy export","Regenerate docs/SCOPE_POLICY.md"),
                ("/apistatus",         "Show online API health/dead status"),
                ("/integrations",      "Adaptive catalog / tiers (coding, sol, terra…)"),
                ("search past sessions <q>", "FTS recall across chat history"),
                ("skills curate",      "Archive duplicate/stale learned skills"),
                ("execute pipeline <py>", "Allowlisted multi-tool script (ADR-060)"),
                ("/setkey groq <key>", "Set Groq API key"),
                ("/switch small|large","Switch local model"),
                ("/react <task>",      "ReAct agent — multi-step reasoning"),
                ("/knowledge <q>",     "Knowledge Agent — RAG-grounded Q&A + live tools"),
                ("/delegate a:q || b:q2", "Parallel subagents (KERROS_SUBAGENTS=1; ADR-061)"),
                ("profile memory …",     "Durable MEMORY.md/USER.md notes (ADR-062)"),
                ("tool search <q>",      "Progressive tool disclosure (KERROS_TOOL_SEARCH=1)"),
                ("agent cron …",         "Persisted agent cron jobs (data/agent_cron)"),
                ("list sessions",        "List indexed chat sessions (ADR-063)"),
                ("browse session <id>",  "Browse turns in a past session"),
                ("/resume [id|latest]",  "Resume indexed session into REPL (ADR-068)"),
                ("bg spawn|poll|kill",   "Background process registry"),
                ("skills hub …",         "Install/scan/quarantine skills (ADR-064)"),
                ("gateway start|status", "Webhook channel gateway (KERROS_GATEWAY=1)"),
                ("gateway channel …",    "Telegram/Discord adapters (ADR-066)"),
                ("/recall [keyword]",  "Search past sessions"),
                ("/clear",             "Summarize + clear session"),
                ("/history",           "Show conversation history"),
                ("/memory",            "Show user profile"),
                ("/tools",             "List all tools"),
                ("/read <path>",       "Read a workspace file (claw)"),
                ("/write <p> :: <txt>", "Write a workspace file (claw)"),
                ("/exec <cmd>",        "Run shell command in workspace (claw)"),
                ("/list [path]",       "List workspace directory (claw)"),
                ("/workspace",         "Show claw workspace root"),
                ("/kernel",            "Show kernel boot status"),
                ("/health",            "Show runtime health report"),
                ("/services",          "Show managed service status"),
                ("/events [n]",        "Show recent event bus events"),
                ("/schedule",          "List jobs; cron <name> <expr>; cancel <id>"),
                ("/workflows",         "List/run/reload YAML workflows; runs; resume"),
                ("/reflect",           "Review episodes → lessons (Reflection Agent)"),
                ("/reflections",       "Show saved reflection lessons"),
                ("/llm",               "LLM providers + resilience; reset [name]"),
                ("/capabilities [kind]", "List capability registry entries"),
                ("/capabilities export", "Regenerate docs/CAPABILITIES.md from YAML"),
                ("/decisions",         "Show recent decision log entries"),
                ("/decisions verify",  "Verify decision_log hash chain (ADR-017)"),
                ("/decisions export [path]", "Export decision_log JSONL"),
                ("/decisions seal <id>", "Seal id prefix to WORM segment (ADR-019)"),
                ("/decisions retain",  "Apply retention policy once (ADR-019)"),
                ("/decisions whoami",  "Show audit RBAC role (ADR-021)"),
                ("/decisions privacy", "Show audit privacy egress status (ADR-024)"),
                ("/decisions residency", "Show residency stamp status (ADR-025)"),
                ("/decisions erasure <ref> [ids]", "Record erasure request (ADR-025)"),
                ("/decisions erasure-review <id> <outcome>", "Sealed-cold review (ADR-026)"),
                ("/decisions transfer <to> <mechanism>", "Record transfer intent (ADR-026)"),
                ("/decisions transfer-exec <id>", "Execute transfer copy pipeline (ADR-027)"),
                ("/sources",           "List RAG knowledge sources"),
                ("/analyze <topic>",   "Deep system analysis"),
                ("/search <query>",    "Search knowledge base"),
                ("/learn <text>",      "Teach KerrOS something"),
                ("/ingest <file>",     "Load file into knowledge base"),
                ("/exit",              "End session"),
            ]
            for cmd,desc in cmds:
                print(f"  {BL}{cmd:<28}{R} {GY}{desc}{R}")
            divider()

        elif user=="/clear":
            try:
                from memory.summarizer import summarize_session
                spinner.label="Summarizing session"
                spinner.start()
                result = summarize_session(engine)
                spinner.stop()
                if result:
                    ep_id, summary = result
                    print(f"  {GR}[ ✓ ] Session saved as Episode #{ep_id}{R}")
                    print(f"  {GY}{summary[:100]}...{R}")
            except Exception as e:
                spinner.stop()
                print(f"  {GY}[Summary skipped: {e}]{R}")
            clear_session()
            print(f"  {GR}[ ✓ ] Session cleared{R}")

        elif user == "/resume" or user.startswith("/resume "):
            arg = user[len("/resume") :].strip()
            if not arg:
                print(f"  {format_resume_picker()}{R}")
            else:
                out = resume_session(arg)
                if out.get("ok"):
                    title = (out.get("title") or "")[:60]
                    print(
                        f"  {GR}[ ✓ ] Resumed{R} {BL}{out.get('session_id')}{R}  "
                        f"{GY}loaded {out.get('loaded')} turn(s)"
                        f"{(' · ' + title) if title else ''}{R}"
                    )
                else:
                    print(f"  {RE}[resume] {out.get('error') or 'failed'}{R}")

        elif user=="/memory":
            divider()
            p=get_profile()
            if p:
                print(f"  {GO}Profile:{R}")
                for k,v in p.items(): print(f"  {BL}{k:<20}{R} {v}")
            try:
                from memory.semantic import get_all
                sem=get_all()
                if sem:
                    print(f"\n  {GO}Semantic Memory:{R}")
                    for cat,facts in sem.items():
                        print(f"  {GY}{cat}{R}")
                        for k,v in facts.items():
                            print(f"    {BL}{k:<16}{R} {v['value']}")
            except: pass
            try:
                from memory.episodic import get_all_episodes
                eps=get_all_episodes()
                if eps: print(f"\n  {GO}Episodes stored:{R} {len(eps)}")
            except: pass
            if not p: print(f"  {GY}No profile data yet{R}")
            divider()

        elif user=="/history":
            divider()
            for m in get_history(10):
                col=YL if m['role']=='user' else CY
                role="You    " if m['role']=='user' else "KerrOS "
                print(f"  {col}{role}{R} {GY}│{R} {m['content'][:65]}")
            divider()

        elif user=="/tools":
            divider()
            print(f"  {GO}Filesystem (claw){R}  {GY}{claw_tools_summary()}{R}")
            for cmd, desc in claw_tool_help_lines():
                print(f"    {BL}{cmd:<28}{R} {GY}{desc}{R}")
            print()
            cats={
                f"{GO}Network{R}":       "nmap · ping · traceroute · nikto · whois · dig",
                f"{GO}OSINT{R}":         "osint · recon · geoip · geoint · dnsenum · reversedns",
                f"{GO}Investigation{R}": "metadata · headers · cert · email_osint · fake_detect",
                f"{GO}Intel{R}":         "sigint · humint · verify_source · opsec · psyop",
                f"{GO}System{R}":        "sysinfo · netstat · speedtest · calc · file_read · bash",
                f"{GO}Hardware{R}":      "esptool · mikrotik · modem",
            }
            for cat,tools in cats.items():
                print(f"  {cat}  {GY}{tools}{R}")
            divider()

        elif (claw_match := detect_claw_tool(user))[0]:
            claw_name, claw_args = claw_match
            print(f"  {GR}◈ Claw: {claw_name}{R}")
            spinner.label = "Executing"
            spinner.start()
            tool_result = run_claw_tool(claw_name, claw_args)
            spinner.stop()
            divider()
            for line in tool_result.split("\n"):
                print(f"  {GY}{line}{R}")
            divider()
            add_message("user", user)
            add_message("assistant", tool_result[:800])

        elif user=="/kernel":
            divider()
            status = get_kernel().status()
            print(f"  {BL}Phase:{R}      {status['phase']}")
            print(f"  {BL}Workspace:{R}  {status['workspace']}")
            print(f"  {BL}Base:{R}       {status['base']}")
            print(f"  {BL}Services:{R}   {', '.join(status['services'])}")
            print(f"  {BL}Boot log:{R}   {' → '.join(status['boot_log'])}")
            divider()

        elif user=="/health":
            divider()
            try:
                health = resolve("health_monitor")
                mgr = resolve("service_manager")
                report = health.collect(mgr)
                print(f"  {BL}Healthy:{R}   {report['healthy']}")
                print(f"  {BL}Uptime:{R}    {report['uptime_s']}s")
                for name, comp in report["components"].items():
                    status = comp.get("status", "unknown")
                    if name == "omniroute":
                        enabled = "on" if comp.get("enabled") else "off"
                        avail = "up" if comp.get("available") else "down"
                        url = comp.get("base_url", "")
                        extra = f"  enabled={enabled}  {avail}  {url}"
                        err = comp.get("error")
                        if err:
                            extra += f"  ({err})"
                        print(f"  {GO}{name}{R}: {status}{extra}")
                    else:
                        print(f"  {GO}{name}{R}: {status}")
            except Exception as e:
                print(f"  {RE}Health unavailable: {e}{R}")
            divider()

        elif user=="/services":
            divider()
            try:
                mgr = resolve("service_manager")
                status = mgr.status()
                for name, info in status["services"].items():
                    print(
                        f"  {GO}{name}{R}  {info['state']}  "
                        f"pid={info.get('pid') or '-'}  restarts={info['restart_count']}"
                    )
            except Exception as e:
                print(f"  {RE}Services unavailable: {e}{R}")
            divider()

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
                    import sys
                    from pathlib import Path
                    script = Path(__file__).resolve().parent.parent / "scripts" / "render_capabilities.py"
                    result = subprocess.run(
                        [sys.executable, str(script)],
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
                    from core.config import cfg as _cfg

                    out = delegate_tasks(jobs, engine, cfg=_cfg())
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
            from prompts.system import ANALYST_PROMPT
            target=user.replace("/analyze","").strip()
            if not target:
                print(f"  {RE}Usage: /analyze <describe your system>{R}")
            else:
                spinner.label="Analyzing"
                spinner.start()
                if engine.current_mode=="online":
                    response=generate_complete(engine, target, system=ANALYST_PROMPT, stream=False)
                else:
                    response=generate_complete(engine, target, system=ANALYST_PROMPT, stream=False)
                spinner.stop()
                divider(); ai_header(mode); typewrite(response); divider()

        elif user.startswith("/switch "):
            model=user.replace("/switch ","").strip()
            models={"small":"models/qwen0.5b-q4.gguf","large":"models/model.gguf"}
            if model in models:
                import json
                p="/data/data/com.termux/files/home/offline_ai/config.json"
                with open(p) as f: c=json.load(f)
                c["model_path"]=models[model]
                with open(p,"w") as f: json.dump(c,f,indent=2)
                print(f"  {GR}[ ✓ ] Switched to {model} — restart to apply{R}")
            else:
                print(f"  {GY}Available: small · large{R}")

        elif user.startswith("/learn "):
            memory_upsert(user[7:].strip(), "user_knowledge")
            print(f"  {GR}[ ✓ ] Learned and stored{R}")

        elif user.startswith("/ingest "):
            memory_ingest_file(user[8:].strip())

        elif user=="/sources":
            srcs=memory_list_sources()
            print(f"  {BL}Sources:{R}", ", ".join(srcs) if srcs else f"{GY}None{R}")

        elif user=="/recall" or user.startswith("/recall "):
            from memory.episodic import get_recent_episodes, search_episodes
            query=user.replace("/recall","").strip()
            divider()
            episodes=search_episodes(query) if query else get_recent_episodes(5)
            label=f"Search: {query}" if query else "Recent sessions:"
            print(f"  {BL}{label}{R}")
            if episodes:
                for ep in episodes:
                    print(f"  {GO}#{ep['id']}{R} {GY}{ep['time']}{R}")
                    print(f"  {CY}{ep['summary'][:120]}{R}")
                    if ep.get('tags'): print(f"  {GY}Tags: {', '.join(ep['tags'])}{R}")
                    print()
            else: print(f"  {GY}No episodes found{R}")
            divider()

        elif user.startswith("/search "):
            query = user[8:].strip()
            hits = []
            try:
                mem = resolve("memory_port")
                hits = [(float(s), t, src) for s, t, src in mem.query(query, top_k=3)]
            except Exception:
                from kernel.access import memory_query
                hits = [(float(s), t, src) for s, t, src in memory_query(query, top_k=3)]
            divider()
            if hits:
                for _, text, src in hits:
                    print(f"  {BL}[{src}]{R} {text[:200]}")
            else:
                print(f"  {GY}No results found{R}")
            divider()

        else:
            extract_and_learn(user)
            # Save only the raw user text, never tool-augmented content
            add_message("user", user)
            try:
                from memory.nudges import note_turn, pending_nudges

                note_turn()
                for nudge in pending_nudges():
                    print(f"  {GY}{nudge}{R}")
            except Exception:
                pass

            active_goal = GoalState.load()
            _is_goal_step = False
            if user.strip().lower().startswith("/goal "):
                goal_text = user[6:].strip()
                steps = split_goal_steps(goal_text)
                active_goal = GoalState.start(goal_text, steps)
                print(f"  {GO}[goal] started — {len(steps)} step(s){R}")
                print(active_goal.summary())
                user = active_goal.current_step()["desc"]
                _is_goal_step = True
            elif active_goal and not active_goal.is_complete():
                if active_goal.is_stuck():
                    print(f"  {RE}[goal] stuck on: {active_goal.current_step()['desc']}{R}")
                    print(active_goal.summary())
                    active_goal.clear()
                    active_goal = None
                else:
                    user = active_goal.current_step()["desc"]
                    _is_goal_step = True

            domain=detect_domain(user)
            if domain: print(f"  {PU}◈ Domain: {domain}{R}")

            tool_result=None
            claw_name, claw_args = detect_claw_tool(user)
            if claw_name:
                print(f"  {GR}◈ Claw: {claw_name}{R}")
                spinner.label = "Executing"
                spinner.start()
                spinner.stop()
                tool_result = run_claw_tool(claw_name, claw_args)
                divider()
                for line in tool_result.split("\n"):
                    print(f"  {GY}{line}{R}")
                divider()
                add_message("assistant", tool_result[:800])
                continue

            tool,args=detect_tool(user, bypass_gate=_is_goal_step)
            if tool:
                print(f"  {GR}◈ Tool: {tool}{R}")

                from tools.scope_gate import check as _scope_check, add_target as _scope_add
                allowed, reason = _scope_check(tool, args)

                from tools.scope_gate import DEPLOY_TOOLS, arm_deploy
                if tool in DEPLOY_TOOLS:
                    if not allowed:
                        print(f"  {RE}◈ Scope: {reason}{R}")
                        proceed = input(f"  {YL}Arm deploy tools for 5 minutes and run '{tool}' now? [y/n]{R} ").strip().lower()
                        if proceed == "y":
                            arm_deploy(5)
                            print(f"  {GR}[ ✓ ] Deploy armed for 5 minute(s){R}")
                        else:
                            print(f"  {GY}Cancelled.{R}")
                            continue
                    from kernel.access import run_tool as _run_devops_tool
                    tool_result = _run_devops_tool(tool, args)
                    divider(); ai_header(mode); typewrite(tool_result); divider()
                    add_message("assistant", tool_result)
                    continue

                if not allowed:
                    target_str = args[0] if isinstance(args,(list,tuple)) else args
                    print(f"  {RE}◈ Scope: {reason}{R}")
                    proceed = input(f"  {YL}Target not authorized. Run '{tool}' on '{target_str}' anyway? [y/n]{R} ").strip().lower()
                    if proceed == "y":
                        _scope_add(str(target_str))
                        print(f"  {GR}[ ✓ ] Authorized for this session{R}")
                    else:
                        print(f"  {GY}Skipped.{R}")
                        tool = None

            if tool:
                spinner.label="Executing"
                spinner.start()
                spinner.stop()
                tool_result=run_tool(tool,args)
                try:
                    from tools.skill_experience import maybe_create_skill, set_task_hint

                    set_task_hint(user)
                    skill_path = maybe_create_skill(min_tools=5)
                    if skill_path:
                        print(f"  {GR}[skill] learned → {skill_path}{R}")
                except Exception:
                    pass

                if active_goal and not active_goal.is_complete():
                    _fail_markers = ("error", "fail", "traceback", "not found", "[✗]")
                    _ok = bool(tool_result) and not any(m in str(tool_result).lower() for m in _fail_markers)
                    active_goal.record_result(ToolResult(
                        status="ok" if _ok else "fail",
                        tool=tool,
                        stdout=str(tool_result)[:500],
                    ))
                    print(active_goal.summary())
                    if active_goal.is_complete():
                        print(f"  {GR}[goal] complete!{R}")
                        active_goal.clear()

                if tool_result.startswith("__EXPLAIN_REQUEST__"):
                    _, fpath, code = tool_result.split("__SPLIT__", 1)[0], None, None
                    raw = tool_result[len("__EXPLAIN_REQUEST__"):]
                    fpath, code = raw.split("__SPLIT__", 1)
                    explain_prompt = f"Explain what this code does, in 3-5 concise sentences. File: {fpath}\n\nCode:\n{code}"
                    spinner.label="Explaining"; spinner.start()
                    try:
                        explanation = generate_complete(engine, explain_prompt, stream=False)
                    except Exception as e:
                        explanation = f"[Error generating explanation: {e}]"
                    spinner.stop()
                    divider(); ai_header(mode); typewrite(explanation); divider()
                    add_message("assistant", explanation[:800])
                    continue
                else:
                    divider()
                    for line in tool_result.split("\n"):
                        print(f"  {GY}{line}{R}")
                    divider()

            elif active_goal and not active_goal.is_complete():
                _stuck_desc = active_goal.current_step()["desc"]
                active_goal.record_result(ToolResult(
                    status="fail",
                    tool="none",
                    stderr=f"No tool matched for step: {_stuck_desc}",
                ))
                print(f"  {RE}[goal] stuck — no tool matched for: {_stuck_desc}{R}")
                print(active_goal.summary())

            from prompts.system import SYSTEM_PROMPT
            spinner.label="Thinking"
            spinner.start()

            system_p, user_p = build_chat(user, tool_result=tool_result, domain=domain)
            if tool_result:
                user_p += "\nAnalyze the tool output and explain what it means."
            # Use only current session turns (no cross-session bleed)
            raw_hist = get_recent(4)
            clean_hist = []
            for m in raw_hist:
                c = m.get("content","").strip()
                bad = ["[Domain:","[Tool output]","Analyze the tool",
                       "<|im_start|>","User: ","Assistant: ",
                       "PING ","bytes from","icmp_seq","packets transmitted"]
                if c and len(c)>3 and len(c)<500 and not any(b in c for b in bad):
                    clean_hist.append({"role":m["role"],"content":c})
            try:
                from core.config import cfg as _cfg
                from core.context_compressor import compress_context
                from core.message_policy import prepare_history, should_compress

                _c = _cfg()
                _ctx = int(_c.get("context_size") or 4096)
                _max = int(_c.get("max_tokens") or 512)
                if should_compress(clean_hist, context_size=_ctx, max_tokens=_max):
                    clean_hist, _meta = compress_context(
                        clean_hist,
                        keep_last=6,
                        engine=engine,
                        context_size=_ctx,
                        max_tokens=_max,
                    )
                else:
                    clean_hist, _meta = prepare_history(
                        clean_hist,
                        context_size=_ctx,
                        max_tokens=_max,
                    )
            except Exception:
                pass
            response = generate_complete(engine, 
                user_message=user_p,
                system=system_p,
                history=clean_hist,
                stream=False
            )

            spinner.stop()
            # Strip any leaked ChatML tokens from response
            for tok in ["<|im_start|>","<|im_end|>","<|endoftext|>"]:
                response = response.replace(tok,"")
            # Strip thinking artifacts
            if "Now give your final answer:" in response:
                response = response.split("Now give your final answer:")[-1]
            if "[Your reasoning:" in response:
                response = response.split("]")[-1]
            response = response.strip()
            divider(); ai_header(mode); typewrite(response); divider()

            # Interactive "[code] Found N… Save to file? [y/n]" — hidden by default.
            # Opt in: KERROS_CODE_SAVE_PROMPT=1
            _code_save_prompt = os.environ.get("KERROS_CODE_SAVE_PROMPT", "").strip().lower() in (
                "1", "true", "yes", "on",
            )
            saved_files = save_code_blocks(response) if _code_save_prompt else []
            if saved_files:
                print(f"  [code] Found {len(saved_files)} code block(s).")
                choice = input("  Save to file? [y/n] ").strip().lower()
                if choice == "y":
                    import time
                    default_folder = "project_" + time.strftime("%Y%m%d_%H%M%S")
                    folder_input = input(f"  Folder name [{default_folder}]: ").strip()
                    folder = folder_input if folder_input else default_folder
                    saved_files = save_code_blocks(response, folder=folder)
                    _goal_step_ok = True
                    for f in saved_files:
                        print(f"  [saved] {f}")
                        result = run_and_verify(f)
                        if result.get("ran"):
                            status = "PASS" if result["ok"] else "FAIL"
                            print(f"  [run:{status}] {f}")
                            if result["stdout"]:
                                print(f"    stdout: {result['stdout'][:300]}")
                            if result["stderr"]:
                                print(f"    stderr: {result['stderr'][:300]}")

                            attempts = 0
                            while not result["ok"] and attempts < 2:
                                attempts += 1
                                print(f"  [fix] Attempt {attempts}/2 — asking AI to fix...")
                                with open(f) as cf:
                                    broken_code = cf.read()
                                fix_prompt = (
                                    f"This code failed when run.\n\nCode:\n{broken_code}\n\n"
                                    f"Error:\n{result['stderr'][:1000]}\n\n"
                                    f"Return ONLY the corrected full code in a single code block, no explanation."
                                )
                                try:
                                    fix_response = generate_complete(engine, fix_prompt, stream=False)
                                except Exception as e:
                                    print(f"  [fix] Failed to call engine: {e}")
                                    break
                                fixed_blocks = extract_code_blocks(fix_response)
                                if not fixed_blocks:
                                    print("  [fix] No code returned — stopping retries.")
                                    break
                                _, fixed_code = fixed_blocks[0]
                                with open(f, "w") as wf:
                                    wf.write(fixed_code.strip() + "\n")
                                result = run_and_verify(f)
                                status = "PASS" if result["ok"] else "FAIL"
                                print(f"  [run:{status}] {f} (attempt {attempts})")
                                if result["stdout"]:
                                    print(f"    stdout: {result['stdout'][:300]}")
                                if result["stderr"]:
                                    print(f"    stderr: {result['stderr'][:300]}")

                            if result["ok"]:
                                print(f"  [fixed] {f} now passes.")
                            elif attempts > 0:
                                print(f"  [unresolved] {f} still failing after {attempts} attempt(s).")
                            if not result["ok"]:
                                _goal_step_ok = False
                        else:
                            print(f"  [run:skip] {result.get('reason')}")
                else:
                    import os
                    for f in saved_files:
                        os.remove(f)

                if active_goal and not active_goal.is_complete():
                    _step_desc = active_goal.current_step()["desc"]
                    if choice == "y":
                        active_goal.record_result(ToolResult(
                            status="ok" if _goal_step_ok else "fail",
                            tool="code_saver",
                            path=folder,
                            stdout=f"Saved {len(saved_files)} file(s) to {folder}",
                        ))
                    else:
                        active_goal.record_result(ToolResult(
                            status="fail",
                            tool="code_saver",
                            stderr="User declined to save generated code",
                        ))
                    print(active_goal.summary())
                    if active_goal.is_complete():
                        print(f"  {GR}[goal] complete!{R}")
                        active_goal.clear()
                    elif active_goal.is_stuck():
                        print(f"  {RE}[goal] still stuck on: {_step_desc}{R}")

            # Only save clean short responses
            clean_resp = response.strip()
            if clean_resp and len(clean_resp) < 800:
                add_message("assistant", clean_resp)

if __name__=="__main__":
    main()
