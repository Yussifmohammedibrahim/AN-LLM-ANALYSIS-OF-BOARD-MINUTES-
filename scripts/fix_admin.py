import sqlite3
import werkzeug.security
import os

db_path = r'c:/Users/DELL/Documents/itds_frameworks/itds_minutes.db'

# Generate correct hash
ph = werkzeug.security.generate_password_hash('admin123', method='pbkdf2:sha256')

conn = sqlite3.connect(db_path)
c = conn.cursor()
c.execute('DELETE FROM Users WHERE username=?', ('admin',))
c.execute('INSERT INTO Users (username, password_hash, role, created_at) VALUES (?, ?, ?, datetime("now"))', ('admin', ph, 'admin'))
conn.commit()
print('✅ Admin user added: admin/admin123')

# Verify
c.execute('SELECT username, role FROM Users WHERE username="admin"')
print('Users:', c.fetchall())
conn.close()
print('Done! Run "python fix_admin.py" then restart backend.')

