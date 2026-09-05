import sqlite3
from itds_env.app.models import get_db  # Use app's DB connection

print("Verifying reset_token columns in Users table...")

try:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(Users)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'reset_token' in columns:
        print("✓ reset_token: PRESENT")
    else:
        print("✗ reset_token: MISSING")
    
    if 'reset_token_expires' in columns:
        print("✓ reset_token_expires: PRESENT")
    else:
        print("✗ reset_token_expires: MISSING")
    
    print("\n✅ Verification complete!")
    conn.close()
except Exception as e:
    print(f"Error: {e}")

