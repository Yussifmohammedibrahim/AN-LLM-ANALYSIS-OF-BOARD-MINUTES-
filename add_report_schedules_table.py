"""
Migration script to create ReportSchedules table for Data & Reporting functionality.
This fixes the delivery status and reporting issues.

NOTE: Uses the same DB path as the application (itds_minutes.db at root)
"""
import sqlite3
import os
from datetime import datetime, timezone

def add_report_schedules_table():
    # Use the same DB path as the application - itds_minutes.db at root
    # This mirrors how app.py's models.py gets the DB path
    db_path = 'itds_minutes.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create ReportSchedules table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ReportSchedules (
            schedule_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            enabled INTEGER DEFAULT 1,
            cadence TEXT DEFAULT 'weekly',
            delivery_date TEXT DEFAULT NULL,
            delivery_time TEXT DEFAULT '08:00',
            recipient_emails TEXT DEFAULT NULL,
            filters_json TEXT DEFAULT NULL,
            last_delivery_status TEXT DEFAULT NULL,
            last_delivery_error TEXT DEFAULT NULL,
            last_delivery_at TEXT DEFAULT NULL,
            is_deleted INTEGER DEFAULT 0,
            deleted_at TEXT DEFAULT NULL,
            created_at TEXT DEFAULT NULL,
            updated_at TEXT DEFAULT NULL,
            FOREIGN KEY (user_id) REFERENCES Users(user_id)
        )
    ''')
    
    # Create index for faster queries
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_report_schedules_user ON ReportSchedules(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_report_schedules_enabled ON ReportSchedules(enabled)')
    
    conn.commit()
    
    # Verify the table was created
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ReportSchedules'")
    if cursor.fetchone():
        print("✓ ReportSchedules table created successfully!")
        
        # Show table structure
        cursor.execute("PRAGMA table_info(ReportSchedules)")
        columns = [row[1] for row in cursor.fetchall()]
        print(f"Columns: {columns}")
        
        # Check delivery columns exist
        for col in ['last_delivery_status', 'last_delivery_error', 'last_delivery_at']:
            print(f"  {col}: {'✓' if col in columns else '✗'}")
    else:
        print("✗ Failed to create table")
    
    conn.close()

if __name__ == '__main__':
    add_report_schedules_table()
