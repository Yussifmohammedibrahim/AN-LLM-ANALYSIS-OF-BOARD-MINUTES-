import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'itds_env'))

from app.app import app, get_db
from datetime import datetime, timezone

with app.app_context():
    db = get_db()
    # Insert test notifications
    for i in range(5):
        db.execute('''
            INSERT INTO NotificationEvents (
                user_id, channel, direction, notification_type, 
                title, body, status, created_at, is_read, is_deleted
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            1, 'email', 'received', 'test',
            f'Test Notification {i+1}',
            f'This is a test notification for testing clear-all functionality.',
            'delivered',
            datetime.now(timezone.utc).isoformat(),
            0, 0
        ))
    db.commit()
    print('✓ Created 5 test notifications')
