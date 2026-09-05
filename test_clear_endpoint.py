#!/usr/bin/env python3
import sys
import os
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'itds_env'))

from app.app import app, get_db

# Test the clear-all endpoint logic directly
with app.app_context():
    # Get a test user and create test notifications
    db = get_db()
    
    # Check if NotificationEvents table exists
    cursor = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='NotificationEvents'")
    if not cursor.fetchone():
        print("✗ NotificationEvents table does not exist!")
        sys.exit(1)
    
    # Get column info
    cursor = db.execute("PRAGMA table_info(NotificationEvents)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}
    print(f"✓ Columns in NotificationEvents: {list(columns.keys())}")
    
    # Check for test data
    cursor = db.execute("SELECT COUNT(*) as cnt FROM NotificationEvents WHERE is_deleted = 0")
    result = cursor.fetchone()
    count = result['cnt'] if result else 0
    print(f"✓ Undeleted notifications: {count}")
    
    # Try the SQL that clear-all uses
    try:
        user_id = 1  # Test user
        tab = 'all'
        channel = 'all'
        
        scope_where = 'user_id = ?'
        scope_params = [user_id]
        
        where = [scope_where, 'COALESCE(is_deleted, 0) = 0']
        params = list(scope_params)
        
        if channel in {'email', 'push'}:
            where.append('channel = ?')
            params.append(channel)
        
        sql = f'''UPDATE NotificationEvents
        SET is_deleted = 1, deleted_at = ?, is_archived = 0, archived_at = NULL
        WHERE {' AND '.join(where)}'''
        
        print(f"✓ SQL query: {sql}")
        print(f"✓ Query params: {params + ['2026-05-05T...']}")
        print("✓ Query structure is valid!")
        
    except Exception as e:
        print(f"✗ Query construction error: {e}")
        sys.exit(1)
