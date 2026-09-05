import sqlite3
import os

base_dir = os.path.dirname(os.path.abspath('itds_env/app'))
db_path = os.path.normpath(os.path.join(base_dir, '..', '..', 'itds_minutes.db'))
print(f'Fixing app DB: {db_path}')

conn = sqlite3.connect(db_path)
c = conn.cursor()

# Check columns
c.execute('PRAGMA table_info(Users)')
columns = [row[1] for row in c.fetchall()]
print('Current columns:', columns)

if 'login_attempts' not in columns:
  c.execute('ALTER TABLE Users ADD COLUMN login_attempts INTEGER DEFAULT 0')
  print('Added login_attempts')

if 'locked_until' not in columns:
  c.execute('ALTER TABLE Users ADD COLUMN locked_until TEXT')
  print('Added locked_until')

if 'must_change_password' not in columns:
  c.execute('ALTER TABLE Users ADD COLUMN must_change_password INTEGER DEFAULT 0')
  print('Added must_change_password')

# Reset admin
c.execute("UPDATE Users SET login_attempts=0, locked_until=NULL, must_change_password=0 WHERE username='admin'")
print('Reset admin:', c.rowcount, 'rows')

conn.commit()
conn.close()
print('✅ App DB FIXED!')

