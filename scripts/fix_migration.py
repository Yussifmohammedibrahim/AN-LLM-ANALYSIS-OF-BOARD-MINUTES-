import sqlite3
import os

# Use relative path from project root
DB_PATH = os.path.join('itds_env', 'itds_minutes.db')

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

try:
    # Check if Users table exists and get columns
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Users'")
    if not cursor.fetchone():
        print("Users table not found!")
        conn.close()
        exit(1)
    
    # Check columns
    cursor.execute("PRAGMA table_info(Users)")
    columns = [row[1] for row in cursor.fetchall()]
    print("Current Users columns:", columns)
    
    # Add login_attempts if missing
    if 'login_attempts' not in columns:
        cursor.execute("ALTER TABLE Users ADD COLUMN login_attempts INTEGER DEFAULT 0")
        print("Added login_attempts column")
    
    # Add locked_until if missing (TEXT for ISO datetime strings)
    if 'locked_until' not in columns:
        cursor.execute("ALTER TABLE Users ADD COLUMN locked_until TEXT")
        print("Added locked_until column")
    
    # Reset existing users
    cursor.execute("UPDATE Users SET login_attempts = 0, locked_until = NULL WHERE login_attempts IS NOT NULL OR locked_until IS NOT NULL")
    reset_count = cursor.rowcount
    print(f"Reset login state for {reset_count} users")
    
    conn.commit()
    print("DB migration complete! Ready for login protection.")
    
except sqlite3.Error as e:
    print(f"Database error: {e}")
    conn.rollback()
except Exception as e:
    print(f"Error: {e}")
finally:
    conn.close()

