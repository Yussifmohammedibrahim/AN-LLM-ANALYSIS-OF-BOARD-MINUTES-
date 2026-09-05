#!/usr/bin/env python3
"""
MIGRATION SCRIPT: Add security columns to Users table
Fixes 'no such column: login_attempts' error
Run: python add_security_columns.py
"""

import sqlite3
import logging
from datetime import datetime

DB_PATH = 'itds_minutes.db'

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def check_columns():
    """Check current Users table columns"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(Users)")
    columns = [row[1] for row in cursor.fetchall()]
    conn.close()
    return columns

def migrate():
    """Add missing security columns"""
    columns = check_columns()
    missing = []
    
    needed = ['must_change_password', 'login_attempts', 'locked_until']
    
    for col in needed:
        if col not in columns:
            missing.append(col)
    
    if not missing:
        print("✅ All security columns already exist")
        return True
    
    print(f"🔄 Adding missing columns: {', '.join(missing)}")
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        if 'must_change_password' in missing:
            cursor.execute("ALTER TABLE Users ADD COLUMN must_change_password INTEGER DEFAULT 0")
            print("   ✅ Added must_change_password")
        
        if 'login_attempts' in missing:
            cursor.execute("ALTER TABLE Users ADD COLUMN login_attempts INTEGER DEFAULT 0")
            print("   ✅ Added login_attempts")
        
        if 'locked_until' in missing:
            cursor.execute("ALTER TABLE Users ADD COLUMN locked_until TIMESTAMP DEFAULT NULL")
            print("   ✅ Added locked_until")
        
        # Update existing users
        cursor.execute("UPDATE Users SET must_change_password = 0 WHERE must_change_password IS NULL")
        
        conn.commit()
        print("✅ Migration completed successfully!")
        print("📋 New schema:")
        cursor.execute("PRAGMA table_info(Users)")
        for row in cursor.fetchall():
            print(f"   {row[1]} {row[2]}")
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def verify():
    """Verify migration worked"""
    print("\n🔍 Verifying Users table...")
    columns = check_columns()
    needed = ['must_change_password', 'login_attempts', 'locked_until']
    
    for col in needed:
        if col in columns:
            print(f"✅ {col}: OK")
        else:
            print(f"❌ {col}: MISSING")
            return False
    
    print("\n✅ Database ready for login with security!")
    print("Next: python run.py")
    return True

if __name__ == "__main__":
    print("🔧 ITDS Security Migration")
    print("=" * 50)
    
    logging.basicConfig(level=logging.INFO)
    
    if migrate():
        verify()
    else:
        print("❌ Migration failed. Check logs above.")

