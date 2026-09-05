import sys
import os
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'itds_env'))

from app.app import app, get_db
from flask_jwt_extended import create_access_token

print("=" * 60)
print("TESTING CLEAR-ALL ENDPOINT")
print("=" * 60)

with app.app_context():
    # Create a test JWT token for user 1 (root user)
    access_token = create_access_token(identity='1')  # Must be string, not integer
    print(f"\n✓ Generated JWT token for user_id=1")
    
    # Create a test client
    client = app.test_client()
    
    # Test the clear-all endpoint
    print("\n✓ Testing POST /api/notifications/clear-all")
    print("  Payload: {'scope': 'mine', 'tab': 'all', 'channel': 'all'}")
    
    response = client.post(
        '/api/notifications/clear-all',
        headers={'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'},
        json={'scope': 'mine', 'tab': 'all', 'channel': 'all'}
    )
    
    print(f"\n  Status code: {response.status_code}")
    print(f"  Response: {response.get_json()}")
    
    # Check the database again after the call
    result = get_db().execute(
        "SELECT COUNT(*) as cnt FROM NotificationEvents WHERE user_id = 1 AND is_deleted = 0"
    ).fetchone()
    undeleted_after = result['cnt'] if result else 0
    
    print(f"\n✓ After clear-all call:")
    print(f"  Undeleted notifications for user 1: {undeleted_after}")
    
    result = get_db().execute(
        "SELECT COUNT(*) as cnt FROM NotificationEvents WHERE user_id = 1 AND is_deleted = 1"
    ).fetchone()
    deleted_after = result['cnt'] if result else 0
    print(f"  Deleted notifications for user 1: {deleted_after}")
    
    print("\n" + "=" * 60)
