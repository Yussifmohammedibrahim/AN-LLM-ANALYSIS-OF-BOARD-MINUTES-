import sqlite3
import os

# App's exact DB path
base_dir = os.path.dirname(os.path.abspath('itds_env/app'))
db_path = os.path.normpath(os.path.join(base_dir, '..', '..', 'itds_minutes.db'))
print(f'Migrating app DB: {db_path}')

conn = sqlite3.connect(db_path)
c = conn.cursor()

try:
    # Setup full DB if needed
    c.execute('''CREATE TABLE IF NOT EXISTS Users (
        user_id INTEGER PRIMARY KEY,
        username TEXT UNIQUE,
        password_hash TEXT,
        role TEXT,
        created_at TIMESTAMP,
        login_attempts INTEGER DEFAULT 0,
        locked_until TEXT,
        must_change_password INTEGER DEFAULT 0
    )''')
    
    # Add missing columns safely
    c.execute("PRAGMA table_info(Users)")
    columns = [row[1] for row in c.fetchall()]
    
    if 'login_attempts' not in columns:
        c.execute('ALTER TABLE Users ADD COLUMN login_attempts INTEGER DEFAULT 0')
    
    if 'locked_until' not in columns:
        c.execute('ALTER TABLE Users ADD COLUMN locked_until TEXT')
    
    if 'must_change_password' not in columns:
        c.execute('ALTER TABLE Users ADD COLUMN must_change_password INTEGER DEFAULT 0')
    
    # Ensure admin exists
    c.execute("SELECT user_id FROM Users WHERE username = ?", ("admin",))
    if not c.fetchone():
        from werkzeug.security import generate_password_hash
        from datetime import datetime, timezone
        hash_val = generate_password_hash("admin123", method='pbkdf2:sha256')
        c.execute("INSERT INTO Users (username, password_hash, role, created_at, login_attempts, locked_until, must_change_password) VALUES (?, ?, ?, ?, 0, NULL, 0)", 
                 ("admin", hash_val, "admin", datetime.now(timezone.utc)))
    
    # Reset all users
    c.execute('UPDATE Users SET login_attempts = 0, locked_until = NULL, must_change_password = 0')
    
    conn.commit()
    print('✅ Migration COMPLETE - admin/admin123 ready!')
    print('Users table columns:', [row[1] for row in c.execute('PRAGMA table_info(Users)').fetchall()])
    
except Exception as e:
    print(f'Error: {e}')
    conn.rollback()
finally:
    conn.close()

