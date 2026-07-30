import re, subprocess, os, json, shutil

from tools import fs_tool
from tools.command_gate import is_explicit_command
from tools.safe_math import SafeMathError, safe_eval
from tools.shell_utils import (
    ShellCommandError,
    grep_lines,
    head_lines,
    run_argv,
    sanitize_target,
    sanitize_token,
    split_command,
)

BASE = os.path.expanduser("~/offline_ai")

def cfg():
    from kernel.config import load_config
    return load_config().values

def _audit_verification(tool: str, subject: str) -> None:
    import hashlib
    try:
        from kernel.decision_log import record_decision
        digest = hashlib.sha256((subject or "").encode()).hexdigest()[:16]
        record_decision(
            "router",
            "verification",
            f"{tool}:hash:{digest}",
            "requested",
            "",
        )
    except Exception:
        pass

def detect_domain(text):
    lower = text.lower()
    domains = {
        "network":["nmap","scan","port","ip","subnet","traceroute","ping","dns"],
        "web_security":["burp","owasp","xss","sqli","injection","api","http"],
        "forensics":["forensic","memory dump","artifact","evidence","timeline"],
        "pentest":["pentest","exploit","metasploit","payload","privilege"],
        "soc":["siem","alert","log","splunk","elk","incident","triage"],
        "mikrotik":["mikrotik","routeros","winbox","ospf","bgp","routersploit"],
        "cloud":["aws","azure","gcp","s3","iam","cloud","kubernetes","docker"],
        "iot":["arduino","esp32","esp8266","esptool","uart","serial","firmware"],
        "ai_security":["prompt injection","llm","garak","promptfoo","jailbreak"],
        "osint":["osint","geoint","sigint","humint","investigate","recon","metadata","trace","track"],
        "investigation":["fake","identity","verify","source","propaganda","psyop","social engineering"],
    }
    for d, kw in domains.items():
        if any(k in lower for k in kw): return d
    return None

def detect_tool(text, bypass_gate=False):
    if not bypass_gate and not is_explicit_command(text):
        return (None, None)

    lower = text.lower()

    # Self-run (offline_ai's own .py/.sh files) — must be checked BEFORE...
    # Self-run (offline_ai's own .py/.sh files) — must be checked BEFORE bash passthrough
    rn = re.search(r'^(?:run|execute)\s+([^\s]+\.(?:py|sh))', text, re.IGNORECASE)
    if rn:
        return ("self_run", rn.group(1))
    if lower.startswith("/run "):
        return ("self_run", text[5:].strip())

    # Bash passthrough
    for p in ["run ","execute ","$ ","bash: "]:
        if lower.startswith(p): return ("bash", text[len(p):].strip())

    # Network tools
    # Only trigger nmap if user gives an IP or hostname to scan
    if (re.search(r'\bnmap\b', lower) or "port scan" in lower or re.search(r'^scan\s+', lower)) \
       and not any(w in lower for w in ["folder", "dir ", "directory", "structure", "file"]) \
       and re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|[\w\-]+\.[\w]{2,})', lower):
        t = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|[\w\-]+\.[\w]+)', text)
        return ("nmap", t.group(1)) if t else (None, None)
    if re.match(r'^ping\s+', lower):
        t = re.search(r'ping\s+([\w\.\-]+)', lower)
        return ("ping", t.group(1)) if t else (None,None)
    if "traceroute" in lower:
        t = re.search(r'([\d\.]+|[\w\-]+\.[\w]+)', text)
        return ("traceroute", t.group(1)) if t else (None,None)
    if "nikto" in lower:
        t = re.search(r'(https?://[\w\.\-/]+|[\d\.]+)', text)
        return ("nikto", t.group(1)) if t else (None,None)
    if lower.startswith("whois "):
        t = re.search(r'whois\s+([\w\.\-]+)', lower)
        return ("whois", t.group(1)) if t else (None,None)
    if re.match(r'^dig\s+', lower):
        t = re.search(r'dig\s+([\w\.\-]+)', lower)
        return ("dig", t.group(1)) if t else (None,None)

    # OSINT & Investigation tools
    if "osint" in lower or re.search(r"\binvestigate\b", lower) or "full recon" in lower:
        t = re.search(r'(?:osint|investigate|full recon)\s+(\S+)', lower)
        return ("osint", t.group(1)) if t else (None,None)
    if re.search(r"\brecon\b", lower):
        t = re.search(r'recon\s+(\S+)', lower)
        return ("recon", t.group(1)) if t else (None,None)
    if "geoip" in lower or "locate ip" in lower or "ip location" in lower:
        t = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', text)
        return ("geoip", t.group(1)) if t else (None,None)
    if "geoint" in lower or "geolocate" in lower:
        t = re.search(r'(?:geoint|geolocate)\s+(\S+)', lower)
        return ("geoint", t.group(1)) if t else (None,None)
    if "metadata" in lower or "exif" in lower:
        t = re.search(r'(?:metadata|exif)\s+(\S+)', lower)
        return ("metadata", t.group(1)) if t else (None,None)
    if "headers" in lower or "http header" in lower:
        t = re.search(r'(https?://\S+)', text)
        return ("headers", t.group(1)) if t else (None,None)
    if re.search(r"\bcert\b", lower) or "certificate" in lower or "ssl" in lower:
        t = re.search(r'([\w\.\-]+\.\w+)', text)
        return ("cert", t.group(1)) if t else (None,None)
    if "dns enum" in lower or "dnsenum" in lower or "subdomain" in lower:
        t = re.search(r'([\w\.\-]+\.\w+)', text)
        return ("dnsenum", t.group(1)) if t else (None,None)
    if "reverse ip" in lower or "reverse dns" in lower:
        t = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|[\w\.\-]+\.\w+)', text)
        return ("reversedns", t.group(1)) if t else (None,None)
    if "email" in lower and ("verify" in lower or "check" in lower or "trace" in lower):
        t = re.search(r'[\w\.\-]+@[\w\.\-]+\.\w+', text)
        return ("email_osint", t.group(0)) if t else (None,None)
    if "sigint" in lower or "signal intel" in lower:
        t = re.search(r'sigint\s+(\S+)', lower)
        return ("sigint", t.group(1)) if t else ("sigint_help","")
    if "humint" in lower or "social engineer" in lower:
        return ("humint_guide","")
    if "fake" in lower and ("detect" in lower or "check" in lower or "analyze" in lower):
        t = re.search(r'(?:fake|check|detect|analyze)\s+(\S+)', lower)
        return ("fake_detect", t.group(1)) if t else (None,None)
    if "verify" in lower and ("source" in lower or "site" in lower or "news" in lower):
        t = re.search(r'(https?://\S+|[\w\.\-]+\.\w+)', text)
        return ("verify_source", t.group(1)) if t else (None,None)
    if "business" in lower and ("verify" in lower or "legit" in lower or "registered" in lower or "registration" in lower):
        m = re.search(r'(?:verify|check)?\s*(?:business|company)\s+(?:if\s+)?["\']?([^"\']+?)["\']?(?:\s+is|\s+legit|\s+registered|$)', text, re.IGNORECASE)
        target = m.group(1).strip() if m else ""
        return ("verify_business", target)

    if "business" in lower and ("verify" in lower or "legit" in lower or "registered" in lower or "registration" in lower):
        m = re.search(r'(?:verify|check)?\s*(?:business|company)\s+(?:if\s+)?["\']?([^"\']+?)["\']?(?:\s+is|\s+legit|\s+registered|$)', text, re.IGNORECASE)
        target = m.group(1).strip() if m else ""
        return ("verify_business", target)

    if "legit" in lower or "legitimacy" in lower or \
       (("verify" in lower or "check" in lower) and ("person" in lower or "someone" in lower or "profile" in lower or "identity" in lower)):
        m = re.search(r'(?:verify|check)\s+(?:if\s+)?["\']?([^"\']+?)["\']?(?:\s+is|\s+legit|$)', text, re.IGNORECASE)
        target = m.group(1).strip() if m else ""
        return ("verify_identity", target)

    m = re.search(r'^(?:create|make|new)\s+file\s+["\']?([^"\']+)["\']?$', text.strip(), re.IGNORECASE)
    if m:
        return ("fs_create", m.group(1).strip())
    m = re.search(r'^write\s+["\']?(.+?)["\']?\s+to file\s+["\']?([^"\']+)["\']?$', text.strip(), re.IGNORECASE)
    if m:
        return ("fs_write", f"{m.group(2).strip()}|{m.group(1).strip()}")
    if ("scan" in lower or "list files" in lower or "show structure" in lower) and ("folder" in lower or "dir" in lower or "structure" in lower):
        m = re.search(r'(?:scan|list files? in|show structure of)\s+(?:the\s+)?(?:folder|dir|directory)?\s*["\']?([^"\']+)["\']?', text, re.IGNORECASE)
        target = m.group(1).strip() if m else "."
        return ("fs_scan", target)
    if ("read" in lower or "show me" in lower or lower.startswith("cat ")) and ("file" in lower or lower.startswith("cat ")):
        m = re.search(r'(?:read file|read|show me file|cat)\s+["\']?([^"\']+)["\']?', text, re.IGNORECASE)
        target = m.group(1).strip() if m else ""
        return ("fs_read", target)
    if ("delete" in lower or "remove" in lower) and "file" in lower:
        m = re.search(r'(?:delete|remove)\s+file\s+["\']?([^"\']+)["\']?', text, re.IGNORECASE)
        target = m.group(1).strip() if m else ""
        return ("fs_remove", target)
    if "move" in lower and " to " in lower:
        m = re.search(r'move\s+["\']?([^"\']+?)["\']?\s+to\s+["\']?([^"\']+)["\']?', text, re.IGNORECASE)
        target = f"{m.group(1).strip()}|{m.group(2).strip()}" if m else ""
        return ("fs_move", target)
    if "opsec" in lower or "operational security" in lower:
        return ("opsec_guide","")
    if "psyop" in lower or "propaganda" in lower:
        return ("psyop_guide","")
    if "investigation" in lower and "start" in lower:
        return ("investigation_template","")
    if "netstat" in lower or "connections" in lower or "open ports" in lower:
        return ("netstat","")
    if "speedtest" in lower or "internet speed" in lower:
        return ("speedtest","")
    if "openssl" in lower or "check cert" in lower:
        t = re.search(r'([\w\.\-]+\.\w+)', text)
        return ("cert", t.group(1)) if t else (None,None)

    # Hardware tools
    if "esptool" in lower or "esp32" in lower or "esp8266" in lower:
        return ("esptool_help","")
    if "mikrotik" in lower or "routeros" in lower:
        return ("mikrotik_help","")
    if "at+" in lower or "192.168.254.254" in lower:
        return ("modem", text)

    # Netcat
    if re.match(r'^\s*nc(at)?\b', lower) or "netcat" in lower:
        return ("bash", text.strip())

    # System tools
    if any(w in lower for w in ["my ram","disk space","sysinfo","system info"]):
        return ("sysinfo","")
    m = re.search(r'\d[\d\s\+\-\*\/\^\(\)\.]*\d', text)
    if m and (re.search(r'\d+\s*[\+\*\/\^]\s*\d+', m.group(0)) or re.search(r'\d+\s+-\s+\d+', m.group(0))):
        return ("calc", m.group(0).strip())
    fm = re.search(r'read\s+(?:file\s+)?["\']?([^\s"\']+\.\w+)', text, re.IGNORECASE)
    if fm: return ("file_read", fm.group(1))

    # File / folder write tools
    fc = re.search(r'(?:create|make)\s+(?:a\s+)?folder\s+(?:called\s+)?["\']?([^\s"\']+)', lower)
    if fc: return ("make_folder", fc.group(1))

    fw = re.search(r'(?:write|save)\s+(?:to\s+)?(?:file\s+)?["\']?([^\s"\']+\.\w+)\s*[:\-]\s*(.+)', text, re.IGNORECASE)
    if fw: return ("file_write", (fw.group(1), fw.group(2)))

    nav = re.search(r'(?:navigate|list|show)\s+(?:folder|dir|directory)?\s*["\']?([^\s"\']+)', text, re.IGNORECASE)
    if nav and ("navigate" in lower or "list folder" in lower or "list dir" in lower or "show folder" in lower):
        return ("nav", nav.group(1))

    mv = re.search(r'move\s+["\']?([^\s"\']+)["\']?\s+to\s+["\']?([^\s"\']+)', text, re.IGNORECASE)
    if mv: return ("move", (mv.group(1), mv.group(2)))

    cp = re.search(r'copy\s+["\']?([^\s"\']+)["\']?\s+to\s+["\']?([^\s"\']+)', text, re.IGNORECASE)
    if cp: return ("copy", (cp.group(1), cp.group(2)))

    sc = re.search(r'scan\s+(?:folder|dir|directory)?\s*["\']?([^\s"\']+)', text, re.IGNORECASE)
    if sc and "scan" in lower and not re.search(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', lower):
        return ("scan", sc.group(1))

    if lower.startswith("/explain "):
        return ("self_explain", text[9:].strip())
    ex = re.search(r'(?:what does|explain)\s+([^\s]+\.(?:py|sh))\s*(?:do)?', lower)
    if ex:
        return ("self_explain", ex.group(1))

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

    # Session recall / pipeline / skills (ADR-058..060)
    if lower.startswith("search past sessions ") or lower.startswith("/sessions "):
        q = text.split(" ", 3)[-1].strip() if lower.startswith("/sessions ") else text[len("search past sessions "):].strip()
        return ("search_past_sessions", q)
    if "search past session" in lower or lower.startswith("recall session"):
        q = re.sub(r'^(?:search past sessions?|recall session)\s*', '', text, flags=re.I).strip()
        return ("search_past_sessions", q or text)
    if lower.startswith("execute pipeline ") or lower.startswith("/pipeline "):
        body = text.split(" ", 2)[-1] if lower.startswith("/pipeline ") else text[len("execute pipeline "):]
        return ("execute_pipeline", body)
    if lower.startswith("skills curate") or lower == "/skills curate":
        return ("skills_curate", "")
    if lower.startswith("delegate ") or lower.startswith("/delegate "):
        body = text.split(" ", 1)[1].strip() if " " in text else ""
        return ("delegate_task", body)
    if lower.startswith("delegate_task "):
        return ("delegate_task", text.split(" ", 1)[1].strip())

    # ADR-062 capability expansions
    if lower.startswith("profile memory ") or lower.startswith("/profile-memory "):
        body = text.split(" ", 2)[-1] if lower.startswith("/profile-memory ") else text[len("profile memory "):]
        return ("profile_memory", body)
    if lower.startswith("tool search ") or lower.startswith("/tool-search "):
        q = text.split(" ", 2)[-1] if lower.startswith("/tool-search ") else text[len("tool search "):]
        return ("tool_search", q)
    if lower.startswith("tool describe ") or lower.startswith("/tool-describe "):
        q = text.split(" ", 2)[-1]
        return ("tool_describe", q)
    if lower.startswith("agent cron ") or lower.startswith("/agent-cron "):
        body = text.split(" ", 2)[-1] if " " in text else "list"
        return ("agent_cron", body)
    if lower in ("agent cron", "/agent-cron"):
        return ("agent_cron", "list")
    if lower.startswith("mcp discover") or lower == "/mcp":
        return ("mcp_discover", "")
    if lower.startswith("approve exec") or lower.startswith("/approve-exec"):
        return ("approve_exec", text.split(" ", 1)[-1] if " " in text else "")
    if lower.startswith("browse session ") or lower.startswith("/browse-session "):
        sid = text.split(" ", 2)[-1].strip()
        return ("browse_session", sid)
    if lower in ("list sessions", "/sessions", "sessions list"):
        return ("list_sessions", "")
    if lower in ("/resume", "resume session", "resume"):
        return ("resume_session", "")
    if lower.startswith("/resume ") or lower.startswith("resume session ") or lower.startswith("resume "):
        if lower.startswith("resume session "):
            body = text[len("resume session ") :].strip()
        elif lower.startswith("/resume "):
            body = text[len("/resume ") :].strip()
        else:
            body = text[len("resume ") :].strip()
        return ("resume_session", body)
    if lower.startswith("bg ") or lower.startswith("/bg "):
        return ("bg_process", text.split(" ", 1)[1].strip())
    if lower in ("bg", "/bg"):
        return ("bg_process", "list")
    if lower.startswith("skills hub ") or lower.startswith("/skills-hub "):
        return ("skills_hub", text.split(" ", 2)[-1].strip())
    if lower in ("skills hub", "/skills-hub"):
        return ("skills_hub", "list")
    if lower.startswith("gateway ") or lower.startswith("/gateway "):
        return ("gateway", text.split(" ", 1)[1].strip())
    if lower in ("gateway", "/gateway"):
        return ("gateway", "status")

    return (None, None)

def run_tool(tool, args):
    from tools.tool_hooks import run_post_tool_call, run_pre_tool_call

    allowed, reason, hook = run_pre_tool_call(tool, args)
    if not allowed:
        prefix = "[SCOPE GATE]" if hook == "scope_gate" else f"[TOOL HOOK:{hook}]"
        result = f"{prefix} {reason}"
        run_post_tool_call(tool, args, result)
        return result

    dispatch = {
        # Network
        "bash":_bash,"nmap":_nmap,"nmap_help":lambda _:_nmap_help(),
        "ping":_ping,"traceroute":_traceroute,"nikto":_nikto,
        "whois":_whois,"dig":_dig,
        # OSINT & Investigation
        "osint":_osint,"recon":_recon,"geoip":_geoip,"geoint":_geoint,
        "metadata":_metadata,"headers":_headers,"cert":_cert,
        "dnsenum":_dnsenum,"reversedns":_reversedns,
        "email_osint":_email_osint,"sigint":_sigint,
        "sigint_help":lambda _:_sigint_help(),
        "humint_guide":lambda _:_humint_guide(),
        "fake_detect":_fake_detect,"verify_source":_verify_source,
        "opsec_guide":lambda _:_opsec_guide(),
        "fs_create":_fs_create,
        "fs_write":_fs_write,
        "fs_scan":_fs_scan,
        "fs_read":_fs_read,
        "fs_remove":_fs_remove,
        "fs_move":_fs_move,
        "verify_identity":_verify_identity,
        "verify_business":_verify_business,
        "psyop_guide":lambda _:_psyop_guide(),
        "investigation_template":lambda _:_investigation_template(),
        # Defensive/Diagnostic
        "netstat":lambda _:_netstat(),
        "speedtest":lambda _:_speedtest(),
        # Hardware
        "esptool_help":lambda _:_esptool_help(),
        "mikrotik_help":lambda _:_mikrotik_help(),
        "modem":_modem,
        # System
        "sysinfo":lambda _:_sysinfo(),
        "calc":_calc,"file_read":_file_read,
        "make_folder":_make_folder,"file_write":_file_write,
        "nav":_nav,"move":_move,"copy":_copy,"scan":_scan,
        "self_run":_self_run,"self_explain":_self_explain,
        "github_create_repo":_github_create_repo,
        "github_push":_github_push,
        "supabase_migrate":_supabase_migrate,
        "vercel_deploy":_vercel_deploy,
        "netlify_deploy":_netlify_deploy,
        "railway_deploy":_railway_deploy,
        "cloudflare_deploy":_cloudflare_deploy,
        "stripe_trigger":_stripe_trigger,
        "search_past_sessions": _search_past_sessions,
        "execute_pipeline": _execute_pipeline,
        "skills_curate": _skills_curate,
        "delegate_task": _delegate_task,
        "profile_memory": _profile_memory,
        "tool_search": _tool_search,
        "tool_describe": _tool_describe,
        "agent_cron": _agent_cron,
        "mcp_discover": _mcp_discover,
        "approve_exec": _approve_exec,
        "browse_session": _browse_session,
        "list_sessions": _list_sessions,
        "resume_session": _resume_session,
        "bg_process": _bg_process,
        "skills_hub": _skills_hub,
        "gateway": _gateway,
    }
    fn = dispatch.get(tool)
    result = fn(args) if fn else "[Unknown tool]"
    run_post_tool_call(tool, args, result)
    return result

def _run_argv(argv, timeout=15):
    return run_argv(argv, timeout=timeout)


def _run(cmd, timeout=15):
    """Parse a simple command string and run without a shell."""
    try:
        return _run_argv(split_command(cmd), timeout=timeout)
    except ShellCommandError as exc:
        return f"[Error: {exc}]"


def _curl_headers(target: str, timeout: int = 8) -> str:
    host = sanitize_target(target)
    out = _run_argv(["curl", "-sI", f"https://{host}"], timeout=timeout)
    if not out.strip() or out.startswith("[Error") or out.startswith("[Timeout"):
        out = _run_argv(["curl", "-sI", f"http://{host}"], timeout=timeout)
    return out


def _openssl_cert_info(domain: str, timeout: int = 10, *, full: bool = False) -> str:
    host = sanitize_target(domain, label="domain")
    try:
        proc = subprocess.run(
            ["openssl", "s_client", "-connect", f"{host}:443"],
            input="",
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        args = ["openssl", "x509", "-noout", "-text"] if full else [
            "openssl", "x509", "-noout", "-subject", "-issuer", "-dates"
        ]
        cert = subprocess.run(
            args,
            input=proc.stdout or "",
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return (cert.stdout or cert.stderr or "[No output]").strip()[:2000]
    except subprocess.TimeoutExpired:
        return "[Timeout]"
    except Exception as exc:
        return f"[Error: {exc}]"

# ── Network ──────────────────────────────────────────────
def _bash(cmd):
    base = cmd.strip().split()[0] if cmd.strip() else ""
    if base not in cfg().get("safe_commands",[]):
        return f"[BLOCKED] '{base}' not in safe list"
    try:
        return _run_argv(split_command(cmd))
    except ShellCommandError as exc:
        return f"[Error: {exc}]"

def _nmap(t):
    if not shutil.which("nmap"):
        return "[nmap: pkg install nmap]"
    return _run_argv(["nmap", "-sV", "-T4", "--top-ports", "100", sanitize_target(t)], 60)
def _nmap_help(): return "[nmap] Usage: 'scan 192.168.1.1'\n⚠️ Only scan networks you own."
def _ping(t): return _run_argv(["ping", "-c", "4", sanitize_target(t)], 10)
def _traceroute(t):
    if not shutil.which("traceroute"):
        return "[pkg install traceroute]"
    return _run_argv(["traceroute", sanitize_target(t)], 20)
def _nikto(t):
    if not shutil.which("nikto"):
        return "[nikto: pkg install nikto]"
    return _run_argv(["nikto", "-h", sanitize_target(t), "-maxtime", "60"], 90)
def _whois(d): return _run_argv(["whois", sanitize_target(d, label="domain")], 10)
def _dig(d): return _run_argv(["dig", sanitize_target(d, label="domain"), "+short"], 10)

# ── OSINT & Investigation ─────────────────────────────────
def _osint(target):
    """Full OSINT profile: WHOIS + DNS + GeoIP + Headers + Cert"""
    host = sanitize_target(target)
    out = [f"=== OSINT REPORT: {host} ==="]
    out.append("--- WHOIS ---")
    out.append(_run_argv(["whois", host], 10))
    out.append("--- DNS RECORDS ---")
    out.append(_run_argv(["dig", host, "ANY", "+short"], 10))
    out.append("--- IP GEOLOCATION ---")
    out.append(_run_argv(["curl", "-s", f"http://ip-api.com/json/{host}"], 8))
    out.append("--- HTTP HEADERS ---")
    out.append(_curl_headers(host, 8))
    out.append("--- SSL CERTIFICATE ---")
    out.append(_openssl_cert_info(host, 8))
    return "\n".join(out)[:2000]

def _recon(target):
    """Quick recon: ping + DNS + WHOIS"""
    host = sanitize_target(target)
    out = [f"=== RECON: {host} ==="]
    out.append(_run_argv(["ping", "-c", "2", host], 8))
    out.append(_run_argv(["dig", host, "+short"], 8))
    out.append(head_lines(_run_argv(["whois", host], 8), 20))
    return "\n".join(out)[:2000]

def _geoip(ip):
    """Geolocate an IP address"""
    return _run_argv(["curl", "-s", f"http://ip-api.com/json/{sanitize_target(ip, label='ip')}"], 8)

def _geoint(target):
    """GEOINT: IP geolocation + ASN + network info"""
    host = sanitize_target(target)
    out = [f"=== GEOINT: {host} ==="]
    out.append(_run_argv([
        "curl", "-s",
        f"http://ip-api.com/json/{host}?fields=status,country,regionName,city,isp,org,as,lat,lon,query",
    ], 8))
    out.append(head_lines(_run_argv(["curl", "-s", f"https://ipapi.co/{host}/json/"], 8), 20))
    return "\n".join(out)[:2000]

def _metadata(filepath):
    """Extract file metadata and strings"""
    filepath = os.path.expanduser(filepath)
    if not os.path.exists(filepath):
        return f"[File not found: {filepath}]"
    out = [f"=== METADATA: {filepath} ==="]
    out.append(_run_argv(["file", filepath]))
    out.append(_run_argv(["ls", "-lah", filepath]))
    out.append("--- STRINGS (first 30) ---")
    out.append(head_lines(_run_argv(["strings", filepath]), 30))
    if filepath.lower().endswith(('.jpg','.jpeg','.png','.tiff')):
        if shutil.which("exiftool"):
            out.append("--- EXIF ---")
            out.append(_run_argv(["exiftool", filepath], 10))
        else:
            out.append("[exiftool not installed: pkg install exiftool]")
    return "\n".join(out)[:2000]

def _headers(url):
    """Analyze HTTP response headers"""
    out = [f"=== HTTP HEADERS: {url} ==="]
    result = _run_argv(["curl", "-sI", url], 10)
    out.append(result)
    out.append("--- Security Headers Check ---")
    checks = ["Strict-Transport-Security","X-Frame-Options","X-Content-Type-Options",
              "Content-Security-Policy","X-XSS-Protection","Referrer-Policy"]
    for h in checks:
        status = "✅ Present" if h.lower() in result.lower() else "❌ Missing"
        out.append(f"{h}: {status}")
    return "\n".join(out)[:2000]

def _cert(domain):
    """SSL certificate analysis"""
    domain = re.sub(r'https?://', '', domain).split('/')[0]
    host = sanitize_target(domain, label="domain")
    out = [f"=== SSL CERT: {host} ==="]
    out.append(head_lines(_openssl_cert_info(host, 10, full=True), 40))
    return "\n".join(out)[:2000]

def _dnsenum(domain):
    """DNS enumeration: A, MX, NS, TXT, CNAME records"""
    host = sanitize_target(domain, label="domain")
    out = [f"=== DNS ENUM: {host} ==="]
    for rtype in ["A","MX","NS","TXT","CNAME","AAAA"]:
        result = _run_argv(["dig", host, rtype, "+short"], 8)
        if result and result != "[No output]":
            out.append(f"--- {rtype} ---\n{result}")
    return "\n".join(out)[:2000]

def _reversedns(target):
    """Reverse DNS lookup"""
    host = sanitize_target(target)
    out = [f"=== REVERSE DNS: {host} ==="]
    out.append(_run_argv(["dig", "-x", host, "+short"], 8))
    out.append(_run_argv(["host", host], 8))
    return "\n".join(out)[:2000]

def _email_osint(email):
    """Email OSINT: domain analysis + MX records"""
    domain = email.split("@")[-1] if "@" in email else email
    host = sanitize_target(domain, label="domain")
    out = [f"=== EMAIL OSINT: {email} ==="]
    out.append(f"Domain: {host}")
    out.append("--- MX Records ---")
    out.append(_run_argv(["dig", host, "MX", "+short"], 8))
    out.append("--- Domain WHOIS ---")
    out.append(head_lines(_run_argv(["whois", host], 8), 20))
    out.append("--- SPF/DMARC Records ---")
    out.append(_run_argv(["dig", host, "TXT", "+short"], 8))
    return "\n".join(out)[:2000]

def _sigint(target):
    """SIGINT: network traffic analysis on interface or host"""
    out = [f"=== SIGINT: {target} ==="]
    out.append("--- Active Connections ---")
    out.append(head_lines(_run_argv(["ss", "-tunap"], 8), 20))
    out.append("--- ARP Table ---")
    out.append(_run_argv(["arp", "-a"], 8))
    out.append("--- Network Interfaces ---")
    out.append(_run_argv(["ip", "addr", "show"], 8))
    return "\n".join(out)[:2000]

def _sigint_help():
    return """SIGINT (Signal Intelligence) Guide:
Commands available on this device:
  sigint <target>  — active connections, ARP, interfaces
  run ss -tunap    — all active network connections
  run ip route     — routing table
  run arp -a       — ARP cache (devices on LAN)
  run netstat -an  — all connections

For deeper SIGINT:
  pkg install tcpdump
  run tcpdump -i wlan0 -c 50
⚠️ Only capture traffic on networks you own."""

def _humint_guide():
    return """HUMINT (Human Intelligence) Guide:
ETHICAL OSINT only — never impersonate or deceive.

People Search Techniques:
  • Username search: check social media manually
  • Email: use email_osint <email>
  • Phone: reverse lookup via public directories
  • LinkedIn: search by name + company
  • Google Dorking: site:linkedin.com "John Doe"

Social Engineering Awareness:
  • Pretexting: attacker creates false scenario
  • Phishing: fake emails/sites to steal credentials
  • Vishing: voice-based social engineering
  • Baiting: leaving infected USB drives

Defense:
  • Verify identity before sharing info
  • Use MFA on all accounts
  • Be skeptical of unsolicited contact
  • Train staff on SE awareness

⚠️ HUMINT techniques are for defensive awareness only."""

def _fake_detect(target):
    """Fake identity/site detection"""
    out = [f"=== FAKE DETECTION: {target} ==="]
    if target.startswith("http"):
        out.append("--- Domain Age & Registration ---")
        domain = re.sub(r'https?://', '', target).split('/')[0]
        host = sanitize_target(domain, label="domain")
        whois_out = _run_argv(["whois", host], 8)
        out.append(grep_lines(whois_out, r"creation|created|registered|expir"))
        out.append("--- SSL Certificate ---")
        out.append(_openssl_cert_info(host, 8))
        out.append("--- DNS Records ---")
        out.append(_run_argv(["dig", host, "+short"], 8))
        out.append("--- Redirects ---")
        headers = _run_argv(["curl", "-sI", target], 8)
        out.append(grep_lines(headers, r"location|server"))
    else:
        out.append("Tip: provide a URL for full fake site analysis")
        out.append("Manual checks: domain age, SSL issuer, WHOIS privacy, typosquatting")
    return "\n".join(out)[:2000]

def _verify_source(url):
    """Verify credibility of a news source or website"""
    domain = re.sub(r'https?://', '', url).split('/')[0]
    host = sanitize_target(domain, label="domain")
    out = [f"=== SOURCE VERIFICATION: {url} ==="]
    out.append("--- Domain Info ---")
    whois_out = _run_argv(["whois", host], 8)
    out.append(grep_lines(whois_out, r"creation|registrar|country|name"))
    out.append("--- DNS ---")
    out.append(_run_argv(["dig", host, "+short"], 8))
    out.append("--- HTTP Headers ---")
    out.append(head_lines(_run_argv(["curl", "-sI", url], 8), 15))
    out.append("""--- Manual Verification Checklist ---
✅ Check domain age (older = more credible)
✅ Look for About/Contact page
✅ Cross-reference with Reuters, AP, BBC
✅ Check author credentials
✅ Verify with fact-checkers: snopes.com, factcheck.org
✅ Reverse image search any photos""")
    return "\n".join(out)[:2000]

def _opsec_guide():
    return """OPSEC (Operational Security) Guide:
5-Step OPSEC Process:
  1. Identify critical information
  2. Analyze threats
  3. Analyze vulnerabilities
  4. Assess risk
  5. Apply countermeasures

Personal OPSEC:
  • Use VPN on public WiFi
  • Enable full-disk encryption
  • Use unique passwords + password manager
  • Enable MFA everywhere
  • Minimize digital footprint
  • Use Signal for sensitive comms
  • Regularly audit app permissions

Device OPSEC (Android):
  • run id           — check current user
  • run ip addr      — check network exposure
  • run ss -tunap    — check open connections
  • Disable Bluetooth/WiFi when not in use
  • Keep OS updated"""

def _psyop_guide():
    return """PSYOP & Propaganda Analysis Guide:
Common Techniques:
  • Fear appeals — exaggerate threats
  • Bandwagon — "everyone believes this"
  • False authority — fake experts
  • Cherry picking — selective facts
  • Repetition — repeat until believed
  • Dehumanization — target group as threat
  • Urgency — act now, don't think

How to Detect:
  1. Who created this content? Why?
  2. What emotions does it trigger?
  3. What facts are missing?
  4. Can you verify with primary sources?
  5. Is it designed to divide people?

Fact-Checking Tools (online):
  • snopes.com
  • factcheck.org
  • politifact.com
  • reuters.com/fact-check
  • AP Fact Check

Metadata Analysis:
  → use: metadata <filename>
  → Check creation date, GPS, device info"""

def _investigation_template():
    return """=== INVESTIGATION TEMPLATE ===
Follow this workflow for any investigation:

PHASE 1 — DEFINE
  • What is the target? (person/domain/IP/org)
  • What is the objective?
  • What is the legal authority?

PHASE 2 — PASSIVE RECON (no contact)
  Commands:
  → osint <target>
  → dnsenum <domain>
  → geoip <ip>
  → metadata <file>
  → verify source <url>

PHASE 3 — ACTIVE RECON (creates logs)
  Commands:
  → recon <target>
  → headers <url>
  → cert <domain>
  → email_osint <email>
  ⚠️ Active recon may alert the target

PHASE 4 — ANALYZE
  • Cross-reference all findings
  • Look for inconsistencies
  • Verify with multiple sources
  • Document everything with timestamps

PHASE 5 — DOCUMENT
  Commands:
  → run date
  → read file <your_notes>
  • Screenshot evidence
  • Chain of custody if legal case

PHASE 6 — REPORT
  • Summarize findings
  • List sources
  • State confidence level
  • Include limitations"""
def _fs_create(target):
    if not target:
        return "[fs_create] Usage: 'create file <path>'"
    try:
        path = fs_tool.create_file(target, "")
        return f"[fs_create] created {path}"
    except fs_tool.FsToolError as e:
        return f"[fs_create] error: {e}"

def _fs_write(target):
    if not target or "|" not in target:
        return "[fs_write] Usage: 'write <content> to file <path>'"
    path, content = target.split("|", 1)
    try:
        result = fs_tool.write_file(path, content)
        return f"[fs_write] wrote to {result}"
    except fs_tool.FsToolError as e:
        return f"[fs_write] error: {e}"

def _fs_scan(target):
    try:
        entries = fs_tool.scan(target or ".")
        if not entries:
            return f"[fs_scan] {target} is empty."
        return f"[fs_scan] {target}\n" + "\n".join(entries)
    except fs_tool.FsToolError as e:
        return f"[fs_scan] error: {e}"

def _fs_read(target):
    if not target:
        return "[fs_read] Usage: 'read file <path>'"
    try:
        content = fs_tool.read_file(target)
        return f"[fs_read] {target}\n```\n{content}\n```"
    except fs_tool.FsToolError as e:
        return f"[fs_read] error: {e}"

def _fs_remove(target):
    if not target:
        return "[fs_remove] Usage: 'remove file <path>'"
    try:
        return f"[fs_remove] {fs_tool.remove(target)}"
    except fs_tool.FsToolError as e:
        return f"[fs_remove] error: {e}"

def _fs_move(target):
    if not target or "|" not in target:
        return "[fs_move] Usage: 'move <src> to <dst>'"
    src, dst = target.split("|", 1)
    try:
        return f"[fs_move] {fs_tool.move(src, dst)}"
    except fs_tool.FsToolError as e:
        return f"[fs_move] error: {e}"

def _verify_identity(name):
    """
    Focused business/contact legitimacy checklist — generates search links
    for the platforms that actually matter for verifying a business
    contact, not a comprehensive cross-platform person search.
    """
    _audit_verification("verify_identity", name)
    import urllib.parse
    q = urllib.parse.quote(name) if name else ""
    if not name:
        return "[verify] Usage: 'verify if Acme Corp is legit'"

    out = [f"=== BUSINESS/CONTACT VERIFICATION: {name} ==="]
    out.append("\n[Core Checks]")
    out.append(f"  Google: https://www.google.com/search?q=%22{q}%22")
    out.append(f"  LinkedIn: https://www.linkedin.com/search/results/all/?keywords={q}")
    out.append(f"  Facebook (business page): https://www.facebook.com/search/pages/?q={q}")
    out.append(f"  Instagram: https://www.google.com/search?q=site:instagram.com+{q}")
    out.append(f"  TikTok: https://www.google.com/search?q=site:tiktok.com+{q}")
    out.append(f"  X (Twitter): https://www.google.com/search?q=site:x.com+{q}")
    out.append(f"  Scam report check: https://www.google.com/search?q=%22{q}%22+scam+OR+fraud+OR+complaint")

    out.append("\n[Manual Verification Checklist]")
    out.append("  [ ] Does their name/page match consistently across platforms?")
    out.append("  [ ] Does their claimed role/company match their LinkedIn history?")
    out.append("  [ ] Reverse image search their profile photo — stock/stolen photo?")
    out.append("  [ ] Any scam reports or complaints under this name?")
    out.append("  [ ] Video call before any payment/commitment — hardest thing to fake")
    out.append("  [ ] Also try /verify_business <company name> to check registry/domain")

    out.append("\n[Suspicious Profile Red Flags]")
    out.append("  [ ] Profile locked/private with no public activity at all?")
    out.append("  [ ] No posts, no friends/followers list, or suspiciously low count?")
    out.append("  [ ] No business info, page description, or verified contact details?")
    out.append("  [ ] Account created very recently despite claiming established history?")
    out.append("  [ ] Claimed events/client interactions/ratings not visible or verifiable publicly?")

    return "\n".join(out)

# ── Defensive/Diagnostic ──────────────────────────────────
def _netstat():
    out = _run_argv(["ss", "-tunap"], 10)
    if not out.strip() or out.startswith("[Error") or out.startswith("[Timeout"):
        out = _run_argv(["netstat", "-tunap"], 10)
    return head_lines(out, 30)

def _speedtest():
    out = _run_argv([
        "curl", "-s",
        "https://speed.cloudflare.com/__down?bytes=1000000",
        "-o", "/dev/null",
        "-w", "Download: %{speed_download} bytes/sec\nTime: %{time_total}s\n",
    ], 30)
    return out or "[speedtest unavailable]"

# ── Hardware ──────────────────────────────────────────────
def _esptool_help(): return "ESPTool:\n  pip install esptool\n  esptool.py --port /dev/ttyUSB0 flash_id\n  esptool.py --port /dev/ttyUSB0 read_flash 0 ALL backup.bin"
def _mikrotik_help(): return "MikroTik:\n  SSH: run ssh admin@192.168.88.1\n  API: pip install librouteros\n  Routersploit: git clone https://github.com/threat9/routersploit"
def _modem(q):
    return _run_argv([
        "curl", "-s",
        "http://192.168.254.254/goform/goform_get_cmd_process?cmd=modem_main_state,sim_lock_status",
    ], 5)

# ── System ────────────────────────────────────────────────
def _sysinfo():
    lines = []
    mem = _run_argv(["free", "-m"], 10)
    mem_line = next((l for l in mem.splitlines() if l.startswith("Mem") or "Mem:" in l), "")
    if mem_line:
        lines.append(mem_line)
    df = _run_argv(["df", "-h", "/data"], 10)
    if df.splitlines():
        lines.append(df.splitlines()[-1])
    ip_out = _run_argv(["ip", "addr", "show"], 10)
    lines.extend([l for l in ip_out.splitlines() if "inet " in l][:3])
    return "\n".join(lines) if lines else "[No output]"
def _calc(e):
    try:
        return f"= {safe_eval(e)}"
    except (SafeMathError, ZeroDivisionError, OverflowError, ValueError, TypeError):
        return "[Invalid expression]"
def _file_read(p):
    p = os.path.expanduser(p)
    if not os.path.exists(p): return f"[Not found: {p}]"
    try:
        with open(p) as f: return f.read()[:2000]
    except Exception as e: return f"[Error: {e}]"

STORAGE_SHORTCUTS = {
    "downloads": "~/storage/downloads",
    "download": "~/storage/downloads",
    "dcim": "~/storage/dcim",
    "pictures": "~/storage/pictures",
    "music": "~/storage/music",
    "movies": "~/storage/movies",
    "shared": "~/storage/shared",
}

def _resolve_path(p):
    parts = p.replace("\\", "/").split("/", 1)
    key = parts[0].lower()
    if key in STORAGE_SHORTCUTS:
        base = os.path.expanduser(STORAGE_SHORTCUTS[key])
        rest = parts[1] if len(parts) > 1 else ""
        return os.path.join(base, rest) if rest else base
    return os.path.expanduser(p)

def _make_folder(name):
    path = _resolve_path(name)
    try:
        os.makedirs(path, exist_ok=True)
        return f"[created] {path}"
    except Exception as e:
        return f"[Error: {e}]"

def _file_write(args):
    filename, content_text = args
    path = _resolve_path(filename)
    ok, msg = _confirm_action("write", path)
    if not ok:
        return msg
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content_text.strip() + "\n")
        return f"[saved] {path}"
    except Exception as e:
        return f"[Error: {e}]"


def _nav(path):
    p = _resolve_path(path)
    if not os.path.isdir(p):
        return f"[Not a folder: {p}]"
    try:
        entries = os.listdir(p)
        if not entries:
            return f"[empty] {p}"
        lines = [f"{p}/"]
        for e in sorted(entries):
            full = os.path.join(p, e)
            tag = "DIR " if os.path.isdir(full) else "FILE"
            lines.append(f"  [{tag}] {e}")
        return "\n".join(lines)
    except Exception as e:
        return f"[Error: {e}]"

def _move(args):
    src, dst = args
    src_p, dst_p = _resolve_path(src), _resolve_path(dst)
    ok, msg = _confirm_action("move", src_p, dst_p)
    if not ok:
        return msg
    try:
        import shutil
        os.makedirs(os.path.dirname(dst_p) or ".", exist_ok=True)
        shutil.move(src_p, dst_p)
        return f"[moved] {src_p} -> {dst_p}"
    except Exception as e:
        return f"[Error: {e}]"

def _copy(args):
    src, dst = args
    src_p, dst_p = _resolve_path(src), _resolve_path(dst)
    ok, msg = _confirm_action("copy", src_p, dst_p)
    if not ok:
        return msg
    try:
        import shutil
        if os.path.isdir(src_p):
            shutil.copytree(src_p, dst_p, dirs_exist_ok=True)
        else:
            os.makedirs(os.path.dirname(dst_p) or ".", exist_ok=True)
            shutil.copy2(src_p, dst_p)
        return f"[copied] {src_p} -> {dst_p}"
    except Exception as e:
        return f"[Error: {e}]"

def _scan(path):
    p = _resolve_path(path)
    if not os.path.isdir(p):
        return f"[Not a folder: {p}]"
    lines = []
    count = 0
    for root, dirs, files in os.walk(p):
        depth = root.replace(p, "").count(os.sep)
        indent = "  " * depth
        lines.append(f"{indent}{os.path.basename(root) or root}/")
        for f in files:
            lines.append(f"{indent}  {f}")
            count += 1
        if count > 200:
            lines.append("  ... [truncated, too many files]")
            break
    return "\n".join(lines)


OFFLINE_AI_ROOT = os.path.expanduser("~/offline_ai")
PROTECTED_PATHS = [
    os.path.expanduser("~/.termux"),
    os.path.expanduser("~/storage/dcim"),
    os.path.expanduser("~/storage/pictures"),
    os.path.expanduser("~/storage/movies"),
    os.path.expanduser("~/storage/music"),
]

def _is_protected(path):
    real = os.path.realpath(path)
    for p in PROTECTED_PATHS:
        if real == os.path.realpath(p) or real.startswith(os.path.realpath(p) + os.sep):
            return True
    return False

def _is_outside_project(path):
    real = os.path.realpath(path)
    root = os.path.realpath(OFFLINE_AI_ROOT)
    return not real.startswith(root + os.sep) and real != root

def _confirm_action(action, src, dst=None):
    if _is_protected(src) or (dst and _is_protected(dst)):
        return False, f"[blocked] Protected path involved: {src}{' -> ' + dst if dst else ''}"

    outside = _is_outside_project(src) or (dst and _is_outside_project(dst))
    if outside:
        try:
            ans = input(f"  [confirm] {action} touches a path outside offline_ai/: {src}{' -> ' + dst if dst else ''}. Proceed? [y/n] ").strip().lower()
        except EOFError:
            ans = "n"
        if ans != "y":
            return False, f"[cancelled] {action} not performed."
    return True, None

def _self_run(rel_path):
    p = os.path.expanduser(os.path.join(OFFLINE_AI_ROOT, rel_path)) if not rel_path.startswith("/") else rel_path
    if not os.path.exists(p):
        return f"[Not found: {p}]"
    if _is_outside_project(p):
        return f"[blocked] {p} is outside offline_ai/ — use 'execute <cmd>' instead."
    ext = p.rsplit(".", 1)[-1]
    cmd = {"py": ["python3"], "sh": ["bash"]}.get(ext)
    if not cmd:
        return f"[Unsupported file type: .{ext}]"
    try:
        r = subprocess.run(cmd + [p], capture_output=True, text=True, timeout=30, cwd=OFFLINE_AI_ROOT)
        out = r.stdout.strip()[:1500]
        err = r.stderr.strip()[:1500]
        status = "PASS" if r.returncode == 0 else "FAIL"
        result = f"[run:{status}] {p}"
        if out: result += f"\nstdout: {out}"
        if err: result += f"\nstderr: {err}"
        return result
    except subprocess.TimeoutExpired:
        return f"[run:FAIL] {p}\nstderr: [Timeout after 30s]"
    except Exception as e:
        return f"[Error: {e}]"

def _self_explain(rel_path):
    p = os.path.expanduser(os.path.join(OFFLINE_AI_ROOT, rel_path)) if not rel_path.startswith("/") else rel_path
    if not os.path.exists(p):
        return f"[Not found: {p}]"
    try:
        with open(p) as f:
            code = f.read()[:3000]
        return f"__EXPLAIN_REQUEST__{p}__SPLIT__{code}"
    except Exception as e:
        return f"[Error: {e}]"

def _verify_business(name):
    """
    Generates links to check if a company is legally registered —
    business registry, domain WHOIS, and official verification sources.
    Philippines-focused (SEC/DTI) since that's the primary jurisdiction,
    with generic fallback search links for other countries.
    """
    _audit_verification("verify_business", name)
    import urllib.parse
    q = urllib.parse.quote(name) if name else ""
    if not name:
        return "[verify_business] Usage: 'verify business Acme Corp' or check company registration"

    out = [f"=== BUSINESS REGISTRATION VERIFICATION: {name} ==="]

    out.append("\n[Philippines — Official Registries]")
    out.append(f"  SEC Company Registration: https://crs.sec.gov.ph/CRS/#!/company-search (search manually: \"{name}\")")
    out.append(f"  DTI Business Name Search: https://bnrs.dti.gov.ph/ (search manually: \"{name}\")")
    out.append(f"  BIR TIN Verification: https://www.bir.gov.ph/index.php/eservices.html (requires business details)")

    out.append("\n[Domain / Online Presence]")
    out.append(f"  WHOIS lookup: use 'whois <their-domain.com>' command if they gave you a website")
    out.append(f"  Google (registration/complaints): https://www.google.com/search?q=%22{q}%22+SEC+OR+DTI+OR+registered")

    out.append("\n[Other Countries — Generic]")
    out.append(f"  US: https://www.sec.gov/cgi-bin/browse-edgar (SEC EDGAR company search)")
    out.append(f"  UK: https://find-and-update.company-information.service.gov.uk/ (Companies House)")
    out.append(f"  Generic search: https://www.google.com/search?q=%22{q}%22+company+registration+number")

    out.append("\n[Red Flags to Check]")
    out.append("  [ ] Domain registered very recently despite claiming to be established? (use whois)")
    out.append("  [ ] No entry found in SEC/DTI despite claiming to be a registered company?")
    out.append("  [ ] Business address doesn't exist or matches a residential address only?")
    out.append("  [ ] Payment requested via personal account instead of business account?")

    return "\n".join(out)

# ── DevOps / Deploy pipeline ─────────────────────────────
def _deploy_preflight(tool_name: str):
    """Block deploy CLIs when credentials are missing or over-privileged."""
    try:
        from tools.devops_tokens import preflight
    except Exception:
        return None
    return preflight(tool_name)


def _github_create_repo(args):
    blocked = _deploy_preflight("github_create_repo")
    if blocked:
        return blocked
    reponame = sanitize_token(args.strip(), label="repo name")
    if not reponame: return "[Usage: create repo <name>]"
    if not shutil.which("gh"): return "[gh CLI not installed: pkg install gh]"
    return _run_argv(["gh", "repo", "create", reponame, "--private", "--source=.", "--push"], 30)

def _github_push(args):
    blocked = _deploy_preflight("github_push")
    if blocked:
        return blocked
    branch = sanitize_token((args.strip() or "main"), label="branch")
    return _run_argv(["git", "push", "origin", branch], 30)

def _supabase_migrate(args):
    blocked = _deploy_preflight("supabase_migrate")
    if blocked:
        return blocked
    if not shutil.which("supabase"): return "[supabase CLI not installed]"
    return _run_argv(["supabase", "db", "push"], 30)

def _vercel_deploy(args):
    blocked = _deploy_preflight("vercel_deploy")
    if blocked:
        return blocked
    if not shutil.which("vercel"): return "[vercel CLI not installed]"
    argv = ["vercel", "deploy", "--yes"]
    if "prod" in args.lower():
        argv.insert(2, "--prod")
    return _run_argv(argv, 90)

def _netlify_deploy(args):
    blocked = _deploy_preflight("netlify_deploy")
    if blocked:
        return blocked
    if not shutil.which("netlify"): return "[netlify CLI not installed]"
    argv = ["netlify", "deploy"]
    if "prod" in args.lower():
        argv.append("--prod")
    return _run_argv(argv, 90)

def _railway_deploy(args):
    blocked = _deploy_preflight("railway_deploy")
    if blocked:
        return blocked
    if not shutil.which("railway"): return "[railway CLI not installed]"
    return _run_argv(["railway", "up"], 90)

def _cloudflare_deploy(args):
    blocked = _deploy_preflight("cloudflare_deploy")
    if blocked:
        return blocked
    if not shutil.which("wrangler"): return "[wrangler CLI not installed]"
    return _run_argv(["wrangler", "deploy"], 60)

def _stripe_trigger(args):
    blocked = _deploy_preflight("stripe_trigger")
    if blocked:
        return blocked
    event = sanitize_token(args.strip(), label="event")
    if not event: return "[Usage: stripe trigger <event_name>]"
    if not shutil.which("stripe"): return "[stripe CLI not installed]"
    return _run_argv(["stripe", "trigger", event], 20)


def _search_past_sessions(query):
    from memory.session_fts import format_search_results, search_past_sessions
    from memory.session_store import format_session_hits, search_sessions, summarize_hits

    q = str(query or "")
    hits = search_sessions(q, top_k=8)
    if hits:
        body = format_session_hits(hits)
        try:
            extra = summarize_hits(hits)
            if extra and extra not in body:
                body = body + "\n" + extra
        except Exception:
            pass
        return body
    # Fallback to ADR-058 flat FTS
    hits2 = search_past_sessions(q, top_k=8)
    return format_search_results(hits2)


def _browse_session(raw):
    import json
    from memory.session_store import browse_session

    return json.dumps(browse_session(str(raw or "").strip()), indent=2)


def _list_sessions(_raw):
    import json
    from memory.session_store import list_sessions

    return json.dumps({"ok": True, "sessions": list_sessions()}, indent=2)


def _resume_session(raw):
    import json
    from memory.manager import format_resume_picker, resume_session

    arg = str(raw or "").strip()
    if not arg:
        return format_resume_picker()
    return json.dumps(resume_session(arg), indent=2)


def _bg_process(raw):
    from tools.process_registry import bg_process

    text = str(raw or "list").strip()
    parts = text.split(None, 1)
    action = parts[0]
    rest = parts[1] if len(parts) > 1 else ""
    return bg_process(action, rest)


def _skills_hub(raw):
    from tools.skills_hub import skills_hub

    text = str(raw or "list").strip()
    parts = text.split(None, 1)
    action = parts[0]
    rest = parts[1] if len(parts) > 1 else ""
    if rest.startswith("::"):
        rest = rest[2:].strip()
    return skills_hub(action, rest)


def _gateway(raw):
    from gateway.webhook import gateway_cmd

    text = str(raw or "status").strip()
    parts = text.split(None, 1)
    action = parts[0]
    rest = parts[1] if len(parts) > 1 else ""
    return gateway_cmd(action, rest)


def _execute_pipeline(script):
    from tools.pipeline_exec import execute_pipeline

    return execute_pipeline(str(script or ""))


def _skills_curate(_args=""):
    from tools.skill_experience import curate_skills

    out = curate_skills()
    return (
        f"[skills curate] archived={len(out.get('archived') or [])} "
        f"dupes={len(out.get('dupes') or [])}"
    )


def _bootstrap_skill_experience_hooks():
    """Register experience recorder post-hook and exec approval once."""
    try:
        from tools.tool_hooks import list_hooks, register_post_tool_call

        if "skill_experience" not in list_hooks().get("post", []):

            def _post(tool, args, result):
                try:
                    from tools.skill_experience import record_tool_call

                    record_tool_call(tool, result)
                except Exception:
                    pass

            register_post_tool_call("skill_experience", _post)
    except Exception:
        pass
    try:
        from tools.exec_approval import register_exec_approval_hook
        from tools.tool_hooks import list_hooks

        if "exec_approval" not in list_hooks().get("pre", []):
            register_exec_approval_hook()
    except Exception:
        pass
    try:
        from tools.shell_hooks import register_shell_hooks

        register_shell_hooks()
    except Exception:
        pass


_bootstrap_skill_experience_hooks()


def _delegate_task(raw):
    """Native KerrOS parallel subagents (ADR-061). Requires KERROS_SUBAGENTS=1."""
    from agents.subagents import delegate_tasks, get_bound_engine, parse_delegate_args

    jobs = parse_delegate_args(str(raw or ""))
    if not jobs:
        return (
            "[delegate] usage: delegate knowledge: <q> || research: <q2>\n"
            "Enable with KERROS_SUBAGENTS=1 (RAM-aware; max 2 workers)."
        )

    class _StubEngine:
        current_mode = "offline"

        def generate(self, *a, **k):
            return "[subagent] no engine bound"

        def chat(self, *a, **k):
            return "[subagent] no engine bound"

    engine = get_bound_engine() or _StubEngine()
    cfg = None
    try:
        from core.config import cfg as _cfg

        cfg = _cfg()
    except Exception:
        cfg = None
    out = delegate_tasks(jobs, engine, cfg=cfg)
    if out.get("summary"):
        return out["summary"]
    return str(out.get("error") or out)


def _profile_memory(raw):
    """profile memory add|replace|remove|list :: target :: content[:: old]"""
    from memory.profile_store import profile_memory

    parts = [p.strip() for p in str(raw or "").split("::")]
    action = (parts[0] if parts else "list").split()[0] if parts else "list"
    # allow "add user hello" without ::
    if len(parts) == 1:
        toks = parts[0].split(None, 2)
        action = toks[0] if toks else "list"
        target = toks[1] if len(toks) > 1 else "memory"
        content = toks[2] if len(toks) > 2 else ""
        return profile_memory(action, target, content, "")
    target = parts[1] if len(parts) > 1 else "memory"
    content = parts[2] if len(parts) > 2 else ""
    old = parts[3] if len(parts) > 3 else ""
    return profile_memory(action, target, content, old)


def _tool_search(raw):
    import json
    from tools.tool_search import search_tools

    return json.dumps(search_tools(str(raw or "")), indent=2)


def _tool_describe(raw):
    import json
    from tools.tool_search import describe_tool

    return json.dumps(describe_tool(str(raw or "").strip()), indent=2)


def _agent_cron(raw):
    from tools.agent_cron import agent_cron

    text = str(raw or "list").strip()
    if text.startswith("create"):
        rest = text[len("create") :].strip()
        if rest.startswith("::"):
            rest = rest[2:].strip()
        return agent_cron("create", rest)
    parts = text.split(None, 1)
    action = parts[0]
    rest = parts[1] if len(parts) > 1 else ""
    if rest.startswith("::"):
        rest = rest[2:].strip()
    return agent_cron(action, rest)


def _mcp_discover(_raw):
    import json
    from adapters.mcp.bridge import discover_tools

    return json.dumps(discover_tools(), indent=2)


def _approve_exec(raw):
    from tools.exec_approval import allow_for_session, detect_dangerous_command

    cmd = str(raw or "").strip()
    if cmd.lower().startswith("exec"):
        cmd = cmd.split(" ", 1)[-1].strip()
    if not cmd:
        return "[approve_exec] usage: approve exec <command>"
    reason = detect_dangerous_command(cmd)
    allow_for_session(cmd)
    if reason:
        return f"[approve_exec] session-allowed ({reason}): {cmd[:120]}"
    return f"[approve_exec] session-allowed (no pattern hit): {cmd[:120]}"
