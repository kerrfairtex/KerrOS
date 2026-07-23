import logging
logging.basicConfig(filename="kerros.log", level=logging.DEBUG)
import sys, os, time, threading, random
sys.path.insert(0, os.path.expanduser("~/offline_ai"))

from core.adaptive_engine import AdaptiveEngine, check_internet
from core.context import build, build_chat
from core.thinking import needs_thinking
from core.complete import generate_complete
from memory.manager import (add_message, clear_session, init_session,
    get_history, get_recent, extract_and_learn, get_profile, update_profile)
from rag.store import ingest_file, ingest_text, list_sources, search
from tools.router import detect_tool, run_tool, detect_domain
from tools.goal_state import ToolResult, GoalState, split_goal_steps
from tools.code_saver import save_code_blocks, run_and_verify, extract_code_blocks
from tools.claw_cli import detect_claw_tool, run_claw_tool, claw_tool_help_lines, claw_tools_summary
from kernel import boot as kernel_boot, get_kernel

# ── Markdown stripper ────────────────────────────────────
def strip_md(text):
    import re
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*[\*\-]\s+', '  • ', text, flags=re.MULTILINE)
    text = re.sub(r'`{1,3}([^`]+)`{1,3}', r'\1', text)
    return text.strip()

# ── ANSI ─────────────────────────────────────────────────
R="\033[0m"; BOL="\033[1m"; DIM="\033[2m"; ITA="\033[3m"
CY="\033[96m"; YL="\033[93m"; GR="\033[92m"; RE="\033[91m"
BL="\033[94m"; PU="\033[95m"; WH="\033[97m"; GY="\033[90m"
GO="\033[33m"

# ── Logo ─────────────────────────────────────────────────
RD="\033[31m"
ANGEL_LOGO = f"""
{RD}{BOL}  ╲╲╲╲╲╲╲___                          ___╱╱╱╱╱╱╱
{RD}{BOL}   ╲╲╲╲╲╲╲╲╲___                  ___╱╱╱╱╱╱╱╱╱
{GO}{BOL}    ╲╲╲╲╲╲╲╲╲╲╲___          ___╱╱╱╱╱╱╱╱╱╱╱
{GO}{BOL}     ╲╲╲╲╲╲╲╲╲╲╲╲╲__      __╱╱╱╱╱╱╱╱╱╱╱╱╱
{RD}{BOL}        ╲╲╲╲╲╲╲╲╲╲ ╲    ╱ ╱╱╱╱╱╱╱╱╱╱╱
{RD}{BOL}            ╲╲╲╲╲╲ │  │ ╱╱╱╱╱╱
{GO}{BOL}    ██╗  ██╗███████╗██████╗ ██████╗  ██████╗ ███████╗
{GO}{BOL}    ██║ ██╔╝██╔════╝██╔══██╗██╔══██╗██╔═══██╗██╔════╝
{GO}{BOL}    █████╔╝ █████╗  ██████╔╝██████╔╝██║   ██║███████╗
{GO}{BOL}    ██╔═██╗ ██╔══╝  ██╔══██╗██╔══██╗██║   ██║╚════██║
{RD}{BOL}    ██║  ██╗███████╗██║  ██║██║  ██║╚██████╔╝███████║
{RD}{BOL}    ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝
{GO}         ════════════════════════════════
{GO}{BOL}                   v 1 . 0
{GO}         ════════════════════════════════
"""

# ── Spinner ───────────────────────────────────────────────
class Spinner:
    FRAMES=["⚔ · · ·","· ⚔ · ·","· · ⚔ ·","· · · ⚔","· · ⚔ ·","· ⚔ · ·"]
    def __init__(self, label="Processing"):
        self.label=label; self._stop=False; self._t=None
    def start(self):
        self._stop=False
        self._t=threading.Thread(target=self._spin,daemon=True)
        self._t.start()
    def _spin(self):
        i=0
        while not self._stop:
            print(f"\r  {CY}{self.label}{R} {GO}{self.FRAMES[i%len(self.FRAMES)]}{R}  ",
                  end="",flush=True)
            time.sleep(0.12); i+=1
    def stop(self):
        self._stop=True
        if self._t: self._t.join()
        print("\r"+" "*50+"\r",end="",flush=True)

# ── Typewriter ────────────────────────────────────────────
def typewrite(text, color=CY, delay=0.010):
    for ch in text:
        print(f"{color}{ch}{R}",end="",flush=True)
        if ch in ".!?": time.sleep(0.07)
        elif ch==",": time.sleep(0.03)
        else: time.sleep(delay)
    print()

def divider(): print(f"  {GY}{'·'*44}{R}")
def ai_header(mode): 
    icon = "🌐" if mode=="online" else "⚔"
    print(f"\n  {GO}{icon}{R} {CY}{BOL}KerrOS{R} {GO}〉{R} ",end="")
def prompt_input():
    return input(f"\n  {GO}⚔{R} {YL}{BOL}You{R}  {GO}〉{R} ").strip()

# ── Mode banner ───────────────────────────────────────────
def mode_badge(mode):
    if mode=="online":
        return f"{GR}{BOL}[ ONLINE ]{R}"
    return f"{BL}{BOL}[ OFFLINE ]{R}"

# ── Boot ──────────────────────────────────────────────────
def boot_sequence():
    os.system("clear")
    os.system("chafa --size=80x40 --symbols=block ~/offline_ai/assets/boot_logo.png")
    print()
    time.sleep(0.2)
    time.sleep(0.2)

# ── Internet prompt ───────────────────────────────────────
def ask_mode(engine, spinner):
    has_net = check_internet()
    print()
    if has_net:
        choice = input(f"\n  {GO}⚔{R} {YL}Online mode?{R} {GY}[y/n]{R} ").strip().lower()
        if choice == "y":
            spinner.label = "Connecting to KerrOS"
            spinner.start()
            ok, msg = engine.switch_online()
            spinner.stop()
            if ok:
                print(f"  {GR}[ ✓ ] Online mode active{R}")
                return "online"
            else:
                logging.debug(f"Online failed: {msg}")
                print(f"  {BL}[ ⚔ ] Falling back to offline mode{R}")
                engine.init_offline()
                return "offline"
        else:
            print(f"  {BL}[ ⚔ ] Offline mode selected{R}")
            engine.init_offline()
            return "offline"
    else:
        print(f"  {BL}[ ⚔ ] No internet — offline mode active{R}")
        engine.init_offline()
        return "offline"

# ── Main ──────────────────────────────────────────────────
def main():
    boot_sequence()
    kernel = kernel_boot()
    kcfg = kernel.config
    print(f"  {GR}[kernel]{R} {CY}{kernel.phase.value}{R}  {GY}workspace={kcfg.workspace}{R}")
    init_session()  # reset in-memory session
    engine = AdaptiveEngine()
    spinner = Spinner()

    mode = ask_mode(engine, spinner)

    print(f"\n  {GY}{'─'*44}{R}")
    print(f"  {mode_badge(mode)}")
    print(f"  {GY}{'─'*44}{R}")
    print(f"\n  {GO}⚔{R}  {BOL}KerrOS online. Type {YL}/help{R}{BOL} for commands.{R}\n")

    while True:
        try:
            user = prompt_input()
        except (KeyboardInterrupt, EOFError):
            print(f"\n\n  {GO}⚔{R}  {GR}KerrOS session terminated. Stay secure.{R}\n")
            break

        if not user: continue

        if user=="/exit":
            print(f"\n  {GO}⚔{R}  {GR}KerrOS session terminated. Stay secure.{R}\n")
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
            from tools.scope_gate import arm_deploy
            parts = user.split()
            minutes = 5
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

        elif user=="/scope":
            from tools.scope_gate import list_scope
            targets, cidrs = list_scope()
            divider()
            print(f"  {BL}Authorized targets:{R} {', '.join(targets) if targets else 'none'}")
            print(f"  {BL}Authorized CIDRs:{R} {', '.join(cidrs) if cidrs else 'none'}")
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
                print(f"  {GY}Online mode not initialized yet.{R}")
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
            print(f"  {BL}[ ⚔ ] Switched to offline mode{R}")

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
                ("/apistatus",         "Show online API health/dead status"),
                ("/scope",             "Show authorized scan/recon targets"),
                ("/scope add <t>",     "Authorize a target for active tools"),
                ("/scope remove <t>",  "Remove a target from scope"),
                ("/setkey groq <key>", "Set Groq API key"),
                ("/switch small|large","Switch local model"),
                ("/react <task>",      "ReAct agent — multi-step reasoning"),
                ("/knowledge <q>",     "Knowledge Agent — RAG-grounded Q&A + live tools"),
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

            from agents.document import DocumentAgent
            topic = user.split(" ",1)[1].strip()
            spinner.stop()
            doc, path = DocumentAgent(engine).run(topic, stream=True)
            if path:
                print(f"  {GR}[saved]{R} {path}")
            add_message("assistant", f"Document generated and saved to {path}" if path else "Document generated.")

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
            ingest_text(user[7:].strip(),"user_knowledge")
            print(f"  {GR}[ ✓ ] Learned and stored{R}")

        elif user.startswith("/ingest "):
            ingest_file(user[8:].strip())

        elif user=="/sources":
            srcs=list_sources()
            print(f"  {BL}Sources:{R}", ", ".join(srcs) if srcs else f"{GY}None{R}")

        elif user.startswith("/search "):
            hits=search(user[8:].strip(),top_k=3)
            divider()
            if hits:
                for _,text,src in hits:
                    print(f"  {BL}[{src}]{R} {text[:200]}")
            else: print(f"  {GY}No results found{R}")
            divider()

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

        elif user=="/sources":
            srcs=list_sources()

        elif user=="/recall" or user.startswith("/recall "):
            from memory.episodic import get_recent_episodes, search_episodes
            query=user.replace("/recall","").strip()
            divider()
            episodes=search_episodes(query) if query else get_recent_episodes(5)
            label=f"Search: {query}" if query else "Recent sessions:"
            print(f"  {BL}{label}{R}")
            if episodes:
                for ep in episodes:
                    print()
            else: print(f"  {GY}No episodes found{R}")
            divider()


        elif user.startswith("/search "):
            hits=search(user[8:].strip(),top_k=3); divider()
            if hits:
                for _,text,src in hits:
                    print(f"  {BL}[{src}]{R} {text[:200]}")
            else: print(f"  {GY}No results found{R}")
            divider()

        else:
            extract_and_learn(user)
            # Save only the raw user text, never tool-augmented content
            add_message("user", user)

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
                    from tools.router import run_tool as _run_devops_tool
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

            saved_files = save_code_blocks(response)
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
