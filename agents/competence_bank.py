import sqlite3

DB_PATH = '/data/data/com.termux/files/home/offline_ai/data/failure_patterns.db'

def init_failure_bank():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS failure_patterns (
        worker_name TEXT,
        error_code TEXT,
        description TEXT,
        suggested_specialist TEXT,
        success_count INTEGER DEFAULT 0,
        PRIMARY KEY (worker_name, error_code)
    )''')
    conn.commit()
    conn.close()

def log_specialist_success(worker_name, error_code, specialist_name):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''UPDATE failure_patterns 
                   SET success_count = success_count + 1 
                   WHERE worker_name=? AND error_code=? AND suggested_specialist=?''',
                (worker_name, error_code, specialist_name))
    conn.commit()
    conn.close()
