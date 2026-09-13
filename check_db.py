import sqlite3, os
db = os.path.expanduser('~/offline_ai/data/rag_store.db')
print('path:', db)
print('size:', os.path.getsize(db))

con = sqlite3.connect(db)
tables = con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
for (t,) in tables:
    count = con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
    print(f'  table {t}: {count} rows')