import sqlite3, os
p=os.path.expanduser('~/.jarvis/state/jarvis.sqlite')
out='E:/jarvis/tools/master_dump.txt'
with open(out,'w',encoding='utf-8') as f:
    f.write(f'db path: {p} exists={os.path.exists(p)}\n')
    conn=sqlite3.connect(p)
    for row in conn.execute("SELECT type,name,sql FROM sqlite_master ORDER BY name"):
        f.write('---\n')
        f.write(str(row[0]) + ' ' + str(row[1]) + '\n')
        f.write((row[2] or '')[:2000] + '\n')
    conn.close()
print('wrote', out)
