#!/usr/bin/env python3
"""Test real metadata capture in AuditLogs"""
import sqlite3
from datetime import datetime

DB_PATH = 'itds_env/itds_minutes.db'

def check_recent_logs(n=10):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print(f"\\n=== Recent {n} AuditLogs ===")
    cursor.execute("""
        SELECT timestamp, username, action, location, device_type, browser, os, 
               user_agent, ip_address
        FROM AuditLogs 
        ORDER BY timestamp DESC LIMIT ?
    """, (n,))
    
    rows = cursor.fetchall()
    if not rows:
        print("No logs found. Login first!")
        return
    
    for row in rows:
        print(f"\\n{row['timestamp']} | {row['username']} | {row['action']}")
        print(f"  Location: {row['location']}")
        print(f"  DeviceType: {row['device_type']} | Browser: {row['browser']} | OS: {row['os']}")
        print(f"  IP: {row['ip_address'][:30]}... | UA: {row['user_agent'][:60]}...")
    
    conn.close()

if __name__ == '__main__':
    check_recent_logs()
    print("\\nRun: python test_real_metadata.py")

