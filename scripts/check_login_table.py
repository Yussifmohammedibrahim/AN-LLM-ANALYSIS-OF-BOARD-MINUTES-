import sqlite3
conn = sqlite3.connect('itds_env/itds_minutes.db')
cursor = conn.cursor()
cursor.execute("PRAGMA table_info(Users)")
columns = [row[1] for row in cursor.fetchall()]
print('Users table columns:', columns)
if 'login_attempts' in columns:
    print('✅ login_attempts exists')
else:
    print('❌ login_attempts missing')
cursor.execute("SELECT * FROM Users LIMIT 1")
row = cursor.fetchone()
print('Sample row (tuple):', row)
print('Sample row columns index:', list(range(len(row))) if row else 'No rows')
conn.close()
print('Run this then paste output here.')

