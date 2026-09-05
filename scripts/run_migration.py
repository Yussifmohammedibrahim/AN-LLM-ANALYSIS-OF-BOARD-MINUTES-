import sqlite3
import os

DB_PATH = os.path.join('itds_env', 'itds_minutes.db')
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

try:
    c.execute('ALTER TABLE Users ADD COLUMN login_attempts INTEGER DEFAULT 0')
    print('login_attempts added')
    c.execute('ALTER TABLE Users ADD COLUMN locked_until TEXT')
    print('locked_until added')
    c.execute('UPDATE Users SET login_attempts = 0, locked_until = NULL')
    print('Users initialized:', c.rowcount)
    conn.commit()
    print('✅ Migration complete!')
except Exception as e:
    print(f'Error: {e}')
finally:
    conn.close()

