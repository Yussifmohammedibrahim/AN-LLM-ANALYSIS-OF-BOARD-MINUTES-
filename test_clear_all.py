import sqlite3
import sys
import os

# Add the app directory to the path
sys.path.insert(0, '/c/Users/DELL/Documents/itds_frameworks/itds_env')

from app.app import app, get_db, execute_safe_query

# Test the clear-all endpoint logic
with app.app_context():
    # Check if NotificationEvents table exists and has data
    result = execute_safe_query(
        'SELECT COUNT(*) as cnt FROM NotificationEvents WHERE is_deleted = 0',
        ()
    )
    print(f"Undeleted notifications: {result[0]['cnt'] if result else 0}")
    
    # Check if we can see notification schema
    result = execute_safe_query(
        "PRAGMA table_info(NotificationEvents)",
        ()
    )
    print(f"NotificationEvents columns: {[r['name'] for r in result] if result else 'Table not found'}")
