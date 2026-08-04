"""
Example plugin — plugins/example_message.py

This is the ONLY place real-world actions (like actually sending a
message) get wired in. Notice: this code only runs AFTER a human has
already approved the action in the approval queue. There is no path
in assistant.py that calls execute() before approval.

To make this real: replace the print() with an actual API call to
whatever messaging service you use, then rename this file to match
the action_type you want it to handle (e.g. plugins/message.py for
action_type="message").
"""

def execute(action: dict):
    # action is the full approval_queue row as a dict:
    # id, action_type, summary, details, reasoning, evidence, status, ...
    print(f"[PLUGIN] Would send message now: {action['details']}")
    print("[PLUGIN] Replace this print() with a real API call to actually send it.")
