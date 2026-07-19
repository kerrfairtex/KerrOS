"""
agents/planner.py
Planner — classifies a task and dispatches to the right agent
(Security, Code, Research, Knowledge, ReAct).
"""
import os, sys
sys.path.insert(0, os.path.expanduser("~/offline_ai"))

R="\033[0m"; GO="\033[33m"; YL="\033[93m"; GY="\033[90m"

RULES = [
    (["write code","write a script","write a python","write a program",
      "build a script","create a program","generate code","fix this code",
      "code that","script that","program that"], "code"),
    (["scan","assess risk","check target","recon","pentest","vulnerability of"], "security"),
    (["research","compare","survey","overview of","broad question"], "research"),
    (["cve-","cwe-","capec-","what is","explain","mitre","owasp","sigma","yara"], "knowledge"),
]

class Planner:
    def __init__(self, engine):
        self.engine = engine

    def classify(self, task):
        lower = task.lower()
        for keywords, agent in RULES:
            if any(k in lower for k in keywords):
                return agent
        return "knowledge"  # safest default: grounded Q&A

    def run(self, task, stream=True):
        agent_name = self.classify(task)
        if stream:
            print(f"\n  {YL}🧭 Planner{R} → routing to {GO}{agent_name}{R} agent\n")

        if agent_name == "code":
            from agents.code import CodeAgent
            return CodeAgent(self.engine).run(task, stream=stream)
        elif agent_name == "security":
            from agents.security import SecurityAgent
            # extract a target (domain/IP) if present, else pass raw task
            import re
            m = re.search(r'([\d\.]+|[\w\-]+\.[\w\.]+)', task)
            target = m.group(1) if m else task
            return SecurityAgent(self.engine).run(target, stream=stream)
        elif agent_name == "research":
            from agents.research import ResearchAgent
            return ResearchAgent(self.engine).run(task, stream=stream)
        else:
            from agents.knowledge import KnowledgeAgent
            return KnowledgeAgent(self.engine).run(task, stream=stream)
