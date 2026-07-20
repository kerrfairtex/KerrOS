import re, subprocess, os, json, math, shutil
from tools.command_gate import is_explicit_command
from tools import fs_tool

BASE = os.path.expanduser("~/offline_ai")

def cfg():
    with open(f"{BASE}/config.json") as f: return json.load(f)

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

    return (None, None)

def run_tool(tool, args):
    from tools.scope_gate import check as _scope_check
    allowed, reason = _scope_check(tool, args)
    if not allowed:
        return f"[SCOPE GATE] {reason}"

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

    }
    fn = dispatch.get(tool)
    return fn(args) if fn else "[Unknown tool]"

def _run(cmd, timeout=15):
    try:
        r = subprocess.run(cmd,shell=True,capture_output=True,text=True,timeout=timeout)
        return (r.stdout or r.stderr or "[No output]").strip()[:2000]
    except subprocess.TimeoutExpired: return "[Timeout]"
    except Exception as e: return f"[Error: {e}]"

# ── Network ──────────────────────────────────────────────
def _bash(cmd):
    base = cmd.strip().split()[0] if cmd.strip() else ""
    if base not in cfg().get("safe_commands",[]):
        return f"[BLOCKED] '{base}' not in safe list"
    return _run(cmd)

def _nmap(t): return _run(f"nmap -sV -T4 --top-ports 100 {t}",60) if shutil.which("nmap") else "[nmap: pkg install nmap]"
def _nmap_help(): return "[nmap] Usage: 'scan 192.168.1.1'\n⚠️ Only scan networks you own."
def _ping(t): return _run(f"ping -c 4 {t}",10)
def _traceroute(t): return _run(f"traceroute {t}",20) if shutil.which("traceroute") else "[pkg install traceroute]"
def _nikto(t): return _run(f"nikto -h {t} -maxtime 60",90) if shutil.which("nikto") else "[nikto: pkg install nikto]"
def _whois(d): return _run(f"whois {d}",10)
def _dig(d): return _run(f"dig {d} +short",10)

# ── OSINT & Investigation ─────────────────────────────────
def _osint(target):
    """Full OSINT profile: WHOIS + DNS + GeoIP + Headers + Cert"""
    out = [f"=== OSINT REPORT: {target} ==="]
    out.append("--- WHOIS ---")
    out.append(_run(f"whois {target}", 10))
    out.append("--- DNS RECORDS ---")
    out.append(_run(f"dig {target} ANY +short", 10))
    out.append("--- IP GEOLOCATION ---")
    out.append(_run(f"curl -s 'http://ip-api.com/json/{target}'", 8))
    out.append("--- HTTP HEADERS ---")
    out.append(_run(f"curl -sI https://{target} 2>/dev/null || curl -sI http://{target}", 8))
    out.append("--- SSL CERTIFICATE ---")
    out.append(_run(f"echo | openssl s_client -connect {target}:443 2>/dev/null | openssl x509 -noout -subject -issuer -dates 2>/dev/null", 8))
    return "\n".join(out)[:2000]

def _recon(target):
    """Quick recon: ping + DNS + WHOIS"""
    out = [f"=== RECON: {target} ==="]
    out.append(_run(f"ping -c 2 {target}", 8))
    out.append(_run(f"dig {target} +short", 8))
    out.append(_run(f"whois {target} | head -20", 8))
    return "\n".join(out)[:2000]

def _geoip(ip):
    """Geolocate an IP address"""
    return _run(f"curl -s 'http://ip-api.com/json/{ip}'", 8)

def _geoint(target):
    """GEOINT: IP geolocation + ASN + network info"""
    out = [f"=== GEOINT: {target} ==="]
    out.append(_run(f"curl -s 'http://ip-api.com/json/{target}?fields=status,country,regionName,city,isp,org,as,lat,lon,query'", 8))
    out.append(_run(f"curl -s 'https://ipapi.co/{target}/json/' 2>/dev/null | head -20", 8))
    return "\n".join(out)[:2000]

def _metadata(filepath):
    """Extract file metadata and strings"""
    filepath = os.path.expanduser(filepath)
    if not os.path.exists(filepath):
        return f"[File not found: {filepath}]"
    out = [f"=== METADATA: {filepath} ==="]
    out.append(_run(f"file '{filepath}'"))
    out.append(_run(f"ls -lah '{filepath}'"))
    out.append("--- STRINGS (first 30) ---")
    out.append(_run(f"strings '{filepath}' | head -30"))
    if filepath.lower().endswith(('.jpg','.jpeg','.png','.tiff')):
        if shutil.which("exiftool"):
            out.append("--- EXIF ---")
            out.append(_run(f"exiftool '{filepath}'", 10))
        else:
            out.append("[exiftool not installed: pkg install exiftool]")
    return "\n".join(out)[:2000]

def _headers(url):
    """Analyze HTTP response headers"""
    out = [f"=== HTTP HEADERS: {url} ==="]
    out.append(_run(f"curl -sI '{url}'", 10))
    out.append("--- Security Headers Check ---")
    result = _run(f"curl -sI '{url}'", 10)
    checks = ["Strict-Transport-Security","X-Frame-Options","X-Content-Type-Options",
              "Content-Security-Policy","X-XSS-Protection","Referrer-Policy"]
    for h in checks:
        status = "✅ Present" if h.lower() in result.lower() else "❌ Missing"
        out.append(f"{h}: {status}")
    return "\n".join(out)[:2000]

def _cert(domain):
    """SSL certificate analysis"""
    domain = re.sub(r'https?://', '', domain).split('/')[0]
    out = [f"=== SSL CERT: {domain} ==="]
    out.append(_run(f"echo | openssl s_client -connect {domain}:443 2>/dev/null | openssl x509 -noout -text 2>/dev/null | head -40", 10))
    return "\n".join(out)[:2000]

def _dnsenum(domain):
    """DNS enumeration: A, MX, NS, TXT, CNAME records"""
    out = [f"=== DNS ENUM: {domain} ==="]
    for rtype in ["A","MX","NS","TXT","CNAME","AAAA"]:
        result = _run(f"dig {domain} {rtype} +short", 8)
        if result and result != "[No output]":
            out.append(f"--- {rtype} ---\n{result}")
    return "\n".join(out)[:2000]

def _reversedns(target):
    """Reverse DNS lookup"""
    out = [f"=== REVERSE DNS: {target} ==="]
    out.append(_run(f"dig -x {target} +short", 8))
    out.append(_run(f"host {target}", 8))
    return "\n".join(out)[:2000]

def _email_osint(email):
    """Email OSINT: domain analysis + MX records"""
    domain = email.split("@")[-1] if "@" in email else email
    out = [f"=== EMAIL OSINT: {email} ==="]
    out.append(f"Domain: {domain}")
    out.append("--- MX Records ---")
    out.append(_run(f"dig {domain} MX +short", 8))
    out.append("--- Domain WHOIS ---")
    out.append(_run(f"whois {domain} | head -20", 8))
    out.append("--- SPF/DMARC Records ---")
    out.append(_run(f"dig {domain} TXT +short", 8))
    return "\n".join(out)[:2000]

def _sigint(target):
    """SIGINT: network traffic analysis on interface or host"""
    out = [f"=== SIGINT: {target} ==="]
    out.append("--- Active Connections ---")
    out.append(_run("ss -tunap | head -20", 8))
    out.append("--- ARP Table ---")
    out.append(_run("arp -a", 8))
    out.append("--- Network Interfaces ---")
    out.append(_run("ip addr show", 8))
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
        out.append(_run(f"whois {domain} | grep -i 'creation\\|created\\|registered\\|expir'", 8))
        out.append("--- SSL Certificate ---")
        out.append(_run(f"echo | openssl s_client -connect {domain}:443 2>/dev/null | openssl x509 -noout -subject -issuer 2>/dev/null", 8))
        out.append("--- DNS Records ---")
        out.append(_run(f"dig {domain} +short", 8))
        out.append("--- Redirects ---")
        out.append(_run(f"curl -sI '{target}' | grep -i 'location\\|server'", 8))
    else:
        out.append("Tip: provide a URL for full fake site analysis")
        out.append("Manual checks: domain age, SSL issuer, WHOIS privacy, typosquatting")
    return "\n".join(out)[:2000]

def _verify_source(url):
    """Verify credibility of a news source or website"""
    domain = re.sub(r'https?://', '', url).split('/')[0]
    out = [f"=== SOURCE VERIFICATION: {url} ==="]
    out.append("--- Domain Info ---")
    out.append(_run(f"whois {domain} | grep -i 'creation\\|registrar\\|country\\|name'", 8))
    out.append("--- DNS ---")
    out.append(_run(f"dig {domain} +short", 8))
    out.append("--- HTTP Headers ---")
    out.append(_run(f"curl -sI '{url}' | head -15", 8))
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
    return _run("ss -tunap 2>/dev/null || netstat -tunap 2>/dev/null | head -30", 10)

def _speedtest():
    return _run("curl -s https://raw.githubusercontent.com/sivel/speedtest-cli/master/speedtest.py | python3 - --simple 2>/dev/null || curl -s 'https://speed.cloudflare.com/__down?bytes=1000000' -o /dev/null -w 'Download: %{speed_download} bytes/sec\nTime: %{time_total}s\n'", 30)

# ── Hardware ──────────────────────────────────────────────
def _esptool_help(): return "ESPTool:\n  pip install esptool\n  esptool.py --port /dev/ttyUSB0 flash_id\n  esptool.py --port /dev/ttyUSB0 read_flash 0 ALL backup.bin"
def _mikrotik_help(): return "MikroTik:\n  SSH: run ssh admin@192.168.88.1\n  API: pip install librouteros\n  Routersploit: git clone https://github.com/threat9/routersploit"
def _modem(q): return _run('curl -s "http://192.168.254.254/goform/goform_get_cmd_process?cmd=modem_main_state,sim_lock_status"',5)

# ── System ────────────────────────────────────────────────
def _sysinfo(): return _run("free -m | grep Mem && df -h /data | tail -1 && ip addr | grep 'inet ' | head -3")
def _calc(e):
    try: return f"= {eval(e.replace('^','**'),{'__builtins__':{}},{'math':math})}"
    except: return "[Invalid expression]"
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

def _verify_business(name):
    """
    Generates links to check if a company is legally registered —
    business registry, domain WHOIS, and official verification sources.
    Philippines-focused (SEC/DTI) since that's the primary jurisdiction,
    with generic fallback search links for other countries.
    """
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
