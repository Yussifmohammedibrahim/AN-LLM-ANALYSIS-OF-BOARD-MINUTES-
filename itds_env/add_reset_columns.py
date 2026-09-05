import sqlite3
from app.models import get_db
from datetime import datetime, timezone

print("Adding reset_token columns to Users table...")

conn = get_db()
cursor = conn.cursor()

# Add columns if not exist
cursor.execute("PRAGMA table_info(Users)")
columns = [col[1] for col in cursor.fetchall()]

if 'reset_token' not in columns:
    cursor.execute("ALTER TABLE Users ADD COLUMN reset_token TEXT DEFAULT NULL")
    print("✓ Added reset_token")

if 'reset_token_expires' not in columns:
    cursor.execute("ALTER TABLE Users ADD COLUMN reset_token_expires TIMESTAMP DEFAULT NULL")
    print("✓ Added reset_token_expires")

conn.commit()
conn.close()

print("✅ Migration complete! Restart backend: python run.py")

