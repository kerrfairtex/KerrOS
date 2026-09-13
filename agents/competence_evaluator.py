import sqlite3

class CompetenceEvaluator:
    def __init__(self, db_path='/data/data/com.termux/files/home/offline_ai/data/failure_patterns.db'):
        self.db_path = db_path

    def get_specialist(self, worker_name, error_code):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute('SELECT suggested_specialist FROM failure_patterns '
                    'WHERE worker_name=? AND error_code=?', (worker_name, error_code))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None

    def check_for_promotion(self, worker_name, error_code, specialist_name, threshold=3):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute('SELECT success_count FROM failure_patterns '
                    'WHERE worker_name=? AND error_code=? AND suggested_specialist=?',
                    (worker_name, error_code, specialist_name))
        row = cur.fetchone()
        conn.close()
        return row and row[0] >= threshold
