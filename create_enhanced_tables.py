#!/usr/bin/env python3
"""
Database migration script for Enhanced Presentation features.
Creates ScheduledReports and PresentationBranding tables.
"""

import sqlite3
import os
import sys
from datetime import datetime

def migrate_database():
    """Create required tables for enhanced presentation features."""
    
    # Find database
    db_paths = [
        os.path.join('itds_env', 'itds_minutes.db'),
        'itds_minutes.db',
        os.path.join('..', 'itds_minutes.db'),
    ]
    
    db_path = None
    for path in db_paths:
        if os.path.exists(path):
            db_path = path
            break
    
    if not db_path:
        print("❌ Error: Could not find itds_minutes.db")
        sys.exit(1)
    
    print(f"✓ Found database: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Create ScheduledReports table
        print("\n📋 Creating ScheduledReports table...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ScheduledReports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                report_name TEXT,
                email_recipients TEXT NOT NULL,
                frequency TEXT DEFAULT 'monthly',
                day_of_week INTEGER,
                day_of_month INTEGER,
                send_time TEXT DEFAULT '09:00',
                template_theme TEXT DEFAULT 'corporate',
                include_anomalies BOOLEAN DEFAULT 1,
                include_notes BOOLEAN DEFAULT 1,
                include_sentiment_trends BOOLEAN DEFAULT 1,
                include_growth_analysis BOOLEAN DEFAULT 1,
                include_key_metrics BOOLEAN DEFAULT 1,
                include_prioritized_recs BOOLEAN DEFAULT 1,
                year INTEGER,
                is_active BOOLEAN DEFAULT 1,
                last_sent TIMESTAMP,
                next_send TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES Users(id) ON DELETE CASCADE
            )
        ''')
        print("✓ ScheduledReports table created")
        
        # Create index for faster queries
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_scheduled_reports_user_active
            ON ScheduledReports(user_id, is_active)
        ''')
        print("✓ Index created on ScheduledReports(user_id, is_active)")
        
        # Create PresentationBranding table
        print("\n🎨 Creating PresentationBranding table...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS PresentationBranding (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                organization_name TEXT,
                logo_url TEXT,
                primary_color TEXT DEFAULT '#667eea',
                secondary_color TEXT DEFAULT '#764ba2',
                accent_color TEXT DEFAULT '#f59e0b',
                watermark TEXT,
                footer_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES Users(id) ON DELETE CASCADE,
                UNIQUE(user_id)
            )
        ''')
        print("✓ PresentationBranding table created")
        
        # Create EmailLogs table for tracking delivery
        print("\n📧 Creating EmailLogs table...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS EmailLogs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                schedule_id INTEGER,
                recipient_email TEXT NOT NULL,
                subject TEXT,
                status TEXT DEFAULT 'pending',
                sent_at TIMESTAMP,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(schedule_id) REFERENCES ScheduledReports(id) ON DELETE CASCADE
            )
        ''')
        print("✓ EmailLogs table created")
        
        # Create index for email logs
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_email_logs_schedule
            ON EmailLogs(schedule_id, status)
        ''')
        print("✓ Index created on EmailLogs(schedule_id, status)")
        
        conn.commit()
        print("\n✅ All tables created successfully!")
        
        # Verify tables
        print("\n🔍 Verifying tables...")
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('ScheduledReports', 'PresentationBranding', 'EmailLogs')")
        tables = cursor.fetchall()
        for table in tables:
            print(f"  ✓ {table[0]}")
        
        return True
        
    except sqlite3.OperationalError as e:
        if "already exists" in str(e):
            print("⚠️  Tables already exist - skipping creation")
            return True
        else:
            print(f"❌ Error creating tables: {e}")
            conn.rollback()
            return False
    
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        conn.rollback()
        return False
    
    finally:
        conn.close()

if __name__ == '__main__':
    success = migrate_database()
    sys.exit(0 if success else 1)
