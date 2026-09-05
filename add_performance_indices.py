#!/usr/bin/env python3
"""
Add performance indices to speed up dashboard queries.
This should be run once to optimize the database.
"""
import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join('itds_env', 'itds_minutes.db')

def add_indices():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Get existing indices
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        existing_indices = {row[0] for row in cursor.fetchall()}
        
        indices_to_create = [
            ("idx_segments_created_at", "CREATE INDEX idx_segments_created_at ON Segments(created_at)"),
            ("idx_segments_meeting_id", "CREATE INDEX idx_segments_meeting_id ON Segments(meeting_id)"),
            ("idx_sentiments_created_at", "CREATE INDEX idx_sentiments_created_at ON Sentiments(created_at)"),
            ("idx_sentiments_sentiment", "CREATE INDEX idx_sentiments_sentiment ON Sentiments(sentiment)"),
            ("idx_meetings_created_at", "CREATE INDEX idx_meetings_created_at ON Meetings(created_at)"),
            ("idx_meetings_meeting_date", "CREATE INDEX idx_meetings_meeting_date ON Meetings(meeting_date)"),
        ]
        
        created = 0
        for idx_name, sql in indices_to_create:
            if idx_name in existing_indices:
                print(f"✓ Index {idx_name} already exists")
            else:
                cursor.execute(sql)
                print(f"✓ Created index {idx_name}")
                created += 1
        
        if created > 0:
            conn.commit()
            print(f"\n✅ Added {created} performance indices")
        else:
            print("\n✓ All indices already exist")
            
    except Exception as e:
        print(f"❌ Error creating indices: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    add_indices()
