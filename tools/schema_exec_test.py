import sqlite3, os
p=os.path.expanduser('~/.jarvis/state/jarvis.sqlite')
print('db', p)
conn=sqlite3.connect(p, isolation_level=None)
conn.row_factory=sqlite3.Row
conn.execute('PRAGMA busy_timeout=5000')
conn.execute('PRAGMA journal_mode=WAL')
conn.execute('PRAGMA foreign_keys=ON')
sql='''
CREATE TABLE IF NOT EXISTS worktrees (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    repo_root TEXT NOT NULL,
    path TEXT NOT NULL,
    branch TEXT NOT NULL,
    base_ref TEXT NOT NULL,
    owner_kind TEXT NOT NULL,
    owner_id TEXT,
    created_at INTEGER NOT NULL,
    last_active_at INTEGER NOT NULL,
    removed_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_worktrees_owner ON worktrees (owner_kind, owner_id);
CREATE INDEX IF NOT EXISTS idx_worktrees_removed_at ON worktrees (removed_at);
'''
try:
    conn.executescript(sql)
    print('executescript OK')
except Exception as e:
    print('ERROR', type(e), e)
    # dump some state
    try:
        for r in conn.execute("SELECT type,name,sql FROM sqlite_master ORDER BY name"):
            print('MASTER:', r[0], r[1], (r[2] or '')[:200])
    except Exception as e2:
        print('MASTER ERR', e2)
finally:
    conn.close()
