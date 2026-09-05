import sqlite3
import os

db_path = os.path.normpath('c:/Users/DELL/Documents/itds_frameworks/itds_minutes.db')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Update admin role to admin
cursor.execute('UPDATE Users SET role = "admin" WHERE username = "admin"')
conn.commit()

# Verify
cursor.execute('SELECT user_id, username, role FROM Users WHERE username = "admin"')
user = cursor.fetchone()
print('Admin user after fix:', user)
conn.close()

