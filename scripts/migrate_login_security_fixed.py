import sqlite3
import os
from datetime import datetime

# Relative path from cwd
DB_PATH = os.path.join('itds_env', 'itds_minutes.db')

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Verify table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Users'")
        if not cursor.fetchone():
            print("Users table missing!")
            return False
        
        # Check existing columns
        cursor.execute("PRAGMA table_info(Users)")
        columns = {row[1] for row in cursor.fetchall()}
        print("Existing columns:", columns)
        
        # Add login_attempts
        if 'login_attempts' not in columns:
            cursor.execute("ALTER TABLE Users ADD COLUMN login_attempts INTEGER DEFAULT 0")
            print("✓ Added login_attempts")
        
        # Add locked_until
        if 'locked_until' not in columns:
            cursor.execute("ALTER TABLE Users ADD COLUMN locked_until TEXT")
            print("✓ Added locked_until")
        
        # Reset security fields
        cursor.execute("UPDATE Users SET login_attempts = 0, locked_until = NULL")
        print(f"✓ Reset {cursor.rowcount} users")
        
        conn.commit()
        print("Migration successful!")
        return True
        
    except sqlite3.Error as e:
        print(f"DB Error: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    if migrate():
        print("✅ Login security migration complete!")
    else:
        print("❌ Migration failed")

