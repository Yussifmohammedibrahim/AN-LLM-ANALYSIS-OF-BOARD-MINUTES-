import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'itds_env'))

from app.app import app, get_db, execute_safe_query
from datetime import datetime, timezone

with app.app_context():
    # Check current notification status
    print("=" * 60)
    print("NOTIFICATION DATABASE STATUS")
    print("=" * 60)
    
    # Count total undeleted notifications
    result = execute_safe_query(
        "SELECT COUNT(*) as cnt FROM NotificationEvents WHERE is_deleted = 0",
        ()
    )
    undeleted_count = result[0]['cnt'] if result else 0
    print(f"\n✓ Undeleted notifications: {undeleted_count}")
    
    # Count deleted notifications
    result = execute_safe_query(
        "SELECT COUNT(*) as cnt FROM NotificationEvents WHERE is_deleted = 1",
        ()
    )
    deleted_count = result[0]['cnt'] if result else 0
    print(f"✓ Deleted notifications: {deleted_count}")
    
    # Get some sample undeleted notifications for user 1
    result = execute_safe_query(
        "SELECT notification_id, title, is_deleted, deleted_at FROM NotificationEvents WHERE user_id = 1 AND is_deleted = 0 LIMIT 5",
        ()
    )
    print(f"\n✓ Sample undeleted notifications for user 1:")
    for row in (result or []):
        print(f"  - ID {row['notification_id']}: {row['title']} (deleted={row['is_deleted']}, deleted_at={row['deleted_at']})")
    
    # Get some sample deleted notifications for user 1
    result = execute_safe_query(
        "SELECT notification_id, title, is_deleted, deleted_at FROM NotificationEvents WHERE user_id = 1 AND is_deleted = 1 LIMIT 5",
        ()
    )
    print(f"\n✓ Sample deleted notifications for user 1:")
    for row in (result or []):
        print(f"  - ID {row['notification_id']}: {row['title']} (deleted={row['is_deleted']}, deleted_at={row['deleted_at']})")
    
    print("\n" + "=" * 60)
