import sqlite3

def add_profile_image_column():
    conn = sqlite3.connect('itds_minutes.db')
    cursor = conn.cursor()
    
    # Check if column exists
    cursor.execute("PRAGMA table_info(Users)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'profile_image' not in columns:
        cursor.execute("ALTER TABLE Users ADD COLUMN profile_image TEXT DEFAULT NULL")
        print("✓ Added profile_image column")
    else:
        print("✓ profile_image column already exists")
    
    # Create uploads directory if missing
    import os
    os.makedirs('uploads/profile_images', exist_ok=True)
    print("✓ Created uploads/profile_images directory")
    
    conn.commit()
    conn.close()
    print("Migration complete!")

if __name__ == "__main__":
    add_profile_image_column()

