import sqlite3
import os
from werkzeug.security import generate_password_hash

conn = sqlite3.connect('itds_minutes.db')
c = conn.cursor()

admin_username = os.getenv('ADMIN_USERNAME', 'admin')
admin_password = os.getenv('ADMIN_PASSWORD', 'admin123')
super_admin_username = os.getenv('SUPER_ADMIN_USERNAME', 'superadmin')
super_admin_password = os.getenv('SUPER_ADMIN_PASSWORD', 'SuperAdmin123!')

c.execute('DELETE FROM Users WHERE username IN (?, ?)', (admin_username, super_admin_username))

admin_pw = generate_password_hash(admin_password)
super_admin_pw = generate_password_hash(super_admin_password)

c.execute('INSERT INTO Users (username, password_hash, role) VALUES (?, ?, ?)', (admin_username, admin_pw, 'admin'))
c.execute('INSERT INTO Users (username, password_hash, role) VALUES (?, ?, ?)', (super_admin_username, super_admin_pw, 'super_admin'))
conn.commit()
print(f'Admin user created: {admin_username}/{admin_password}')
print(f'Super admin created: {super_admin_username}/{super_admin_password}')
conn.close()

