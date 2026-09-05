import sqlite3
import os

db_path = os.path.normpath('c:/Users/DELL/Documents/itds_frameworks/itds_minutes.db')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute('SELECT user_id, username, role FROM Users WHERE username = "admin"')
user = cursor.fetchone()
print('Admin user:', user)
conn.close()

