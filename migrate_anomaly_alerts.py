#!/usr/bin/env python
"""
Migration script to add anomaly_email_alerts_enabled column to Users table
Run this once to ensure the column exists for existing deployments
"""
import sqlite3
import os

DB_PATH = os.environ.get(
    'ITDS_DB_PATH',
    os.path.join(os.path.dirname(__file__), 'itds_env', 'itds_minutes.db')
)

def migrate():
    conn = sqlite3.connect(DB_PATH, timeout=60)
    cursor = conn.cursor()
    
    # Check if column exists
    cursor.execute('PRAGMA table_info(Users)')
    existing_columns = {row[1] for row in cursor.fetchall()}
    
    if 'anomaly_email_alerts_enabled' not in existing_columns:
        print("Adding anomaly_email_alerts_enabled column to Users...")
        cursor.execute('ALTER TABLE Users ADD COLUMN anomaly_email_alerts_enabled INTEGER DEFAULT 1')
        conn.commit()
        print("✓ Column added successfully")
    else:
        print("✓ Column already exists")
    
    conn.close()

if __name__ == '__main__':
    migrate()
