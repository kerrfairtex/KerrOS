import sqlite3
import json
import hashlib

class ProceduralMemory:
    def __init__(self, db='/data/data/com.termux/files/home/offline_ai/data/procedural_memory.db'):
        self.db = db
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db)
        cur = conn.cursor()
        cur.execute('''CREATE TABLE IF NOT EXISTS sequences
                       (task_hash TEXT PRIMARY KEY,
                        steps TEXT,
                        metadata TEXT)''')
        conn.commit()
        conn.close()

    def _hash_task(self, task):
        # Deterministic hashing of the task string
        return hashlib.sha256(task.encode('utf-8')).hexdigest()

    def store(self, task, steps, metadata=None):
        task_hash = self._hash_task(task)
        conn = sqlite3.connect(self.db)
        cur = conn.cursor()
        cur.execute('INSERT OR REPLACE INTO sequences VALUES (?,?,?)',
                    (task_hash, json.dumps(steps), json.dumps(metadata or {})))
        conn.commit()
        conn.close()

    def retrieve(self, task):
        task_hash = self._hash_task(task)
        conn = sqlite3.connect(self.db)
        cur = conn.cursor()
        cur.execute('SELECT steps FROM sequences WHERE task_hash=?', (task_hash,))
        row = cur.fetchone()
        conn.close()
        return json.loads(row[0]) if row else None
