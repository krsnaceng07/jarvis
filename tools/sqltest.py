import sqlite3
conn = sqlite3.connect('E:/jarvis/tools/test_schema.db', isolation_level=None)
conn.row_factory = sqlite3.Row
conn.execute('PRAGMA busy_timeout = 5000')
conn.execute('PRAGMA journal_mode = WAL')
conn.execute('PRAGMA foreign_keys = ON')
try:
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS worktrees (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_worktrees_owner ON worktrees (name);
    ''')
    print('executescript OK')
except Exception as e:
    print('executescript ERR', e)
finally:
    conn.close()
