"""
Migration script to safely add missing columns to existing Users table

Run: python migrate_users_schema.py
"""
import sqlite3
from itds_env.app.models import get_db

def migrate_users_table():
    """Add missing columns to existing Users table safely"""
    conn = get_db()
    cursor = conn.cursor()
    
    print("🔍 Checking current Users table schema...")
    
    # Get current columns
    cursor.execute("PRAGMA table_info(Users)")
    columns = {column[1] for column in cursor.fetchall()}
    print(f"Current columns: {sorted(columns)}")
    
    # Add missing columns safely
    migrations = [
        ('email', 'ALTER TABLE Users ADD COLUMN email TEXT DEFAULT NULL'),
        ('full_name', 'ALTER TABLE Users ADD COLUMN full_name TEXT DEFAULT NULL'),
        ('contact_number', 'ALTER TABLE Users ADD COLUMN contact_number TEXT DEFAULT NULL'),
        ('must_change_password', 'ALTER TABLE Users ADD COLUMN must_change_password INTEGER DEFAULT 0')
    ]

    
    added_columns = []
    for col_name, alter_sql in migrations:
        if col_name not in columns:
            print(f"➕ Adding column: {col_name}")
            cursor.execute(alter_sql)
            added_columns.append(col_name)
        else:
            print(f"✅ Column exists: {col_name}")
    
    # Add UNIQUE constraint to email after column exists (safe with NULLs)
    try:
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON Users(email)")
        print("✅ Added UNIQUE index on email")
    except sqlite3.Error as e:
        print(f"ℹ️ UNIQUE index already exists or minor error: {e}")
    
    # Update admin user email if needed
    cursor.execute("UPDATE Users SET email = 'admin@itds.local' WHERE username = 'admin' AND (email IS NULL OR email = '')")
    updated = cursor.rowcount
    if updated > 0:
        print(f"📧 Updated admin email")

    
    conn.commit()
    conn.close()
    
    print("\n✅ Migration complete!")
    print(f"Added columns: {', '.join(added_columns) if added_columns else 'None (already up-to-date)'}")
    print("\nVerify schema:")
    print("sqlite3 itds_minutes.db \"PRAGMA table_info(Users);\"")

if __name__ == '__main__':
    migrate_users_table()
