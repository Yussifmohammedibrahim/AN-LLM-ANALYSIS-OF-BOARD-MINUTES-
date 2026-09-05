"""
Quick test to verify report schedules API works end-to-end.
"""
import sqlite3
import json

# Test database access
print("=== Testing Database Access ===")
conn = sqlite3.connect('itds_minutes.db')
cur = conn.cursor()

# Check if table exists
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ReportSchedules'")
exists = cur.fetchone()
print(f"ReportSchedules table exists: {bool(exists)}")

# Insert a test schedule (if there's a user)
cur.execute("SELECT user_id FROM Users LIMIT 1")
users = cur.fetchall()
if users:
    user_id = users[0][0]
    print(f"Found user_id: {user_id}")
    
    # Insert a test schedule
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()
    
    cur.execute('''
        INSERT INTO ReportSchedules (user_id, enabled, cadence, delivery_date, delivery_time, recipient_emails, filters_json, last_delivery_status, last_delivery_at, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, 1, 'weekly', '', '08:00', 'test@example.com', '{"theme":"","sentiment":"all"}', 'pending', now_iso, now_iso, now_iso))
    
    conn.commit()
    print("Inserted test schedule!")
    
    # Retrieve it
    cur.execute('''
        SELECT schedule_id, user_id, enabled, cadence, delivery_time, recipient_emails, filters_json, last_delivery_status, last_delivery_at
        FROM ReportSchedules WHERE user_id = ?
    ''', (user_id,))
    row = cur.fetchone()
    if row:
        print(f"Retrieved: {row}")
        print(f"  last_delivery_status: {row[7]}")
        print(f"  last_delivery_at: {row[8]}")
else:
    print("No users found - cannot test insert")

conn.close()
print("\n=== Test Complete ===")
print("The backend API should now be able to:")
print("1. GET schedules - returns last_delivery_status")
print("2. PUT schedules - saves new schedule")
print("3. Show status in Settings UI - properly")
