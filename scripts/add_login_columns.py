import sqlite3
import os

# Relative path from project root
DB_PATH = os.path.join('itds_env', 'itds_minutes.db')

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

try:
    # Check Users table
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Users'")
    if not cursor.fetchone():
        print("Error: Users table not found!")
        exit(1)
    
    cursor.execute("PRAGMA table_info(Users)")
    columns = [row[1] for row in cursor.fetchall()]
    print("Current columns:", columns)
    
    if 'login_attempts' not in columns:
        cursor.execute("ALTER TABLE Users ADD COLUMN login_attempts INTEGER DEFAULT 0")
        print("Added login_attempts")
    
    if 'locked_until' not in columns:
        cursor.execute("ALTER TABLE Users ADD COLUMN locked_until TEXT")
        print("Added locked_until")
    
    cursor.execute("UPDATE Users SET login_attempts = 0, locked_until = NULL")
    print(f'Initialized {cursor.rowcount} users')
    
    conn.commit()
    print("✅ Login security columns ready!")
    
except Exception as e:
    print(f"Error: {e}")
finally:
    conn.close()

