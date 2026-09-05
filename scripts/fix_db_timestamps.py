import sqlite3
from datetime import datetime

conn = sqlite3.connect('itds_env/itds_minutes.db')
c = conn.cursor()

# Fix locked_until: set NULL if empty or invalid
c.execute("UPDATE Users SET locked_until = NULL WHERE locked_until IS NULL OR locked_until = '' OR LENGTH(locked_until) < 10")

# Fix reset_token_expires: set NULL if empty or invalid
# Skip reset_token_expires - column not found


# Ensure created_at has time component (SQLite CURRENT_TIMESTAMP format)
c.execute("UPDATE Users SET created_at = datetime(created_at) WHERE created_at IS NOT NULL")

conn.commit()
conn.close()
print("DB timestamps cleaned.")
