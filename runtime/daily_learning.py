import time, os, json
from memory.summarizer import summarize_session
from memory.semantic import extract_and_store, store

LAST_RUN_FILE = os.path.expanduser("~/offline_ai/data/last_learning_run.json")

def _should_run_today():
    if not os.path.exists(LAST_RUN_FILE):
        return True
    with open(LAST_RUN_FILE) as f:
        data = json.load(f)
    return (time.time() - data.get("last_run", 0)) > 86400

def _mark_run():
    os.makedirs(os.path.dirname(LAST_RUN_FILE), exist_ok=True)
    with open(LAST_RUN_FILE, "w") as f:
        json.dump({"last_run": time.time()}, f)

def daily_learning_job(engine=None):
    if not _should_run_today():
        return False
    try:
        summary = summarize_session(engine)
        if summary:
            extract_and_store(summary)
            store("last_daily_summary", summary, category="learning_log")
        _mark_run()
        print("[daily_learning] Consolidation complete.")
        return True
    except Exception as e:
        print(f"[daily_learning] Failed: {e}")
        return False
