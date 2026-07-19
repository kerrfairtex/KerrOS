"""
agents/react.py
===============
ReAct agent with forced first action + model reasoning loop.
Works with small 1.5B models by being more directive.
"""

import re, os, sys
sys.path.insert(0, os.path.expanduser("~/offline_ai"))
from core.complete import generate_complete

from tools.router import detect_tool, run_tool
from prompts.system import SYSTEM_PROMPT

MAX_STEPS = 4

# Color codes
R="\033[0m"; GO="\033[33m"; GR="\033[92m"; BL="\033[94m"
CY="\033[96m"; GY="\033[90m"; YL="\033[93m"; RE="\033[91m"

# Task → first tool mapping (no LLM needed for step 1)
TASK_MAP = [
    (["scan","port","nmap"],          "nmap",      r'([\d\.]+|[\w\-]+\.[\w\.]+)'),
    (["ping","reachable","latency"],  "ping",      r'([\w\.\-]+\.[a-z]{2,})'),
    (["osint","investigate","find"],  "osint",     r'([\d\.]+|[\w\-]+\.[\w\.]+)'),
    (["recon","reconnaissance"],      "recon",     r'([\d\.]+|[\w\-]+\.[\w\.]+)'),
    (["whois","registrar","owner"],   "whois",     r'([\w\-]+\.[\w\.]+)'),
    (["dns","subdomain","records"],   "dnsenum",   r'([\w\-]+\.[\w\.]+)'),
    (["ip","location","geoip"],       "geoip",     r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'),
    (["headers","http","web"],        "headers",   r'(https?://[\w\.\-/]+|[\w\-]+\.[\w\.]+)'),
    (["cert","ssl","certificate"],    "cert",      r'([\w\-]+\.[\w\.]+)'),
    (["network","status","internet"], "sysinfo",   None),
    (["speed","bandwidth"],           "speedtest", None),
]

ANALYZE_PROMPT = """You are a cybersecurity analyst. Analyze this tool output and decide:
1. What did we find?
2. Is there anything suspicious or noteworthy?
3. What should we check next? (pick ONE: {tools})
4. Or are we DONE?

Task: {task}
Tool used: {tool} on {args}
Output:
{observation}

Respond in this format:
FINDING: <what you found in 1-2 sentences>
NEXT: <tool_name> | <target>  OR  DONE
REASON: <why>"""

TOOLS = "ping, nmap, whois, dig, osint, recon, geoip, headers, cert, dnsenum, sysinfo, DONE"


class ReactAgent:
    def __init__(self, engine):
        self.engine = engine

    def _detect_first_action(self, task):
        """Rule-based first action — no LLM needed."""
        lower = task.lower()
        for keywords, tool, pattern in TASK_MAP:
            if any(k in lower for k in keywords):
                target = ""
                if pattern:
                    m = re.search(pattern, task)
                    target = m.group(1) if m else ""
                if not target and tool not in ("sysinfo","speedtest"):
                    # Try to extract any domain/IP
                    m = re.search(r'([\d\.]+|[\w\-]+\.[\w]{2,})', task)
                    target = m.group(1) if m else "unknown"
                return tool, target
        # Default fallback
        m = re.search(r'([\d\.]+|[\w\-]+\.[\w]{2,})', task)
        target = m.group(1) if m else ""
        return ("osint", target) if target else ("sysinfo", "")

    def _execute(self, tool, args):
        """Execute tool via router."""
        tool_map = {
            "ping":"ping","nmap":"nmap","whois":"whois","dig":"dig",
            "osint":"osint","recon":"recon","geoip":"geoip",
            "headers":"headers","cert":"cert","dnsenum":"dnsenum",
            "sysinfo":"sysinfo","speedtest":"speedtest","calc":"calc","bash":"bash",
        }
        mapped = tool_map.get(tool.lower())
        if mapped:
            return run_tool(mapped, args)
        return f"[Unknown tool: {tool}]"

    def _analyze(self, task, tool, args, observation, step):
        """Ask model to analyze observation and decide next step."""
        prompt = ANALYZE_PROMPT.format(
            task=task,
            tool=tool,
            args=args,
            observation=observation[:800],
            tools=TOOLS,
        )
        response = generate_complete(self.engine, 
            user_message=prompt,
            system=SYSTEM_PROMPT,
            history=[],
            stream=False,
        )
        return response

    def _parse_next(self, analysis):
        """Parse NEXT: tool | target from analysis."""
        match = re.search(r'NEXT:\s*(\w+)\s*\|\s*(.+)', analysis, re.IGNORECASE)
        if match:
            tool = match.group(1).strip().lower()
            args = match.group(2).strip()
            if tool == "done":
                return "done", args
            return tool, args
        if re.search(r'NEXT:\s*DONE', analysis, re.IGNORECASE):
            return "done", ""
        if "DONE" in analysis.upper() and "NEXT" in analysis.upper():
            return "done", ""
        return None, None

    def _parse_finding(self, analysis):
        """Extract FINDING: from analysis."""
        match = re.search(r'FINDING:\s*(.+?)(?=NEXT:|REASON:|$)', analysis, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return analysis.strip()[:200]

    def run(self, task, on_step=None, stream=True):
        history = []
        findings = []
        final_answer = None

        if stream:
            print(f"\n  {YL}⚡ ReAct Agent — {MAX_STEPS} max steps{R}")
            print(f"  {GY}Task: {task}{R}\n")

        # Step 1: forced first action
        tool, args = self._detect_first_action(task)

        for step in range(1, MAX_STEPS + 1):
            if stream:
                print(f"  {GO}⚔ Step {step}/{MAX_STEPS}{R}")
                print(f"  {GY}Action:{R} {GR}{tool}{R} | {args}")

            # Execute
            observation = self._execute(tool, args)
            obs_preview = observation[:150].replace('\n',' ')

            if stream:
                print(f"  {BL}Result:{R} {obs_preview}...")
                print()

            history.append({
                "step": step,
                "tool": tool,
                "args": args,
                "observation": observation,
            })

            if on_step:
                on_step(step, tool, args, observation)

            # Analyze
            if stream:
                print(f"  {GY}Analyzing...{R}")

            analysis = self._analyze(task, tool, args, observation, step)
            finding = self._parse_finding(analysis)
            findings.append(f"Step {step} ({tool}): {finding}")

            if stream:
                print(f"  {CY}Finding:{R} {finding}")
                print()

            # Next action?
            next_tool, next_args = self._parse_next(analysis)

            if next_tool == "done" or step == MAX_STEPS:
                final_answer = next_args or finding
                if stream:
                    print(f"  {GR}✓ Investigation complete{R}\n")
                break

            if next_tool:
                tool, args = next_tool, next_args
            else:
                # Model didn't follow format — stop
                final_answer = finding
                break

        # Build final report
        if not final_answer or len(final_answer) < 10:
            final_answer = "\n".join(findings)

        report = f"ReAct Investigation Report:\n\n"
        for f in findings:
            report += f"• {f}\n"
        report += f"\nConclusion: {final_answer}"

        return report