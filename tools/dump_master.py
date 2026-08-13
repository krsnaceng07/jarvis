import sqlite3, os
p=os.path.expanduser('~/.jarvis/state/jarvis.sqlite')
print('db path', p, os.path.exists(p))
conn=sqlite3.connect(p)
for row in conn.execute("SELECT type,name,sql FROM sqlite_master ORDER BY name").fetchall():
    print('---')
    print(row[0], row[1])
    print(row[2])
conn.close()
