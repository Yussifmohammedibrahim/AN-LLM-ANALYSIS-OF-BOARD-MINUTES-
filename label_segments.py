"""
Interactive script to label segments for model evaluation.
Run this to fetch segments from the database and create MANUAL_LABELS.
"""
import sqlite3
import json

# Connect to database
conn = sqlite3.connect('itds_minutes.db')
cur = conn.cursor()

# Check schema
cur.execute("PRAGMA table_info(Segments)")
cols = cur.fetchall()
print('\n' + '='*70)
print('SEGMENTS TABLE SCHEMA')
print('='*70)
for c in cols:
    print(f'  {c[1]:20s} ({c[2]})')

# Get all segments
print('\n' + '='*70)
print('FETCHING SEGMENTS FROM DATABASE')
print('='*70)
cur.execute("SELECT * FROM Segments")
rows = cur.fetchall()
print(f'Total segments: {len(rows)}\n')

# Display first 15 segments for labeling
print('AVAILABLE SEGMENTS (first 15):')
print('-'*70)
segment_ids = []
for i, r in enumerate(rows[:15]):
    segment_id = r[0]
    segment_ids.append(segment_id)
    # Column names depend on schema; show what we have
    print(f'Segment {segment_id}:')
    for j, col in enumerate(cols):
        col_name = col[1]
        val = r[j]
        if isinstance(val, str) and len(str(val)) > 60:
            print(f'  {col_name}: {str(val)[:60]}...')
        else:
            print(f'  {col_name}: {val}')
    print()

conn.close()

# Available themes
THEMES = [
    "Curriculum Development", 
    "Student Internships", 
    "Tech Fair",
    "Faculty Research", 
    "Examinations", 
    "Infrastructure Development",
    "Accreditation", 
    "Budget Planning", 
    "Staff Development", 
    "Student Affairs"
]

print('='*70)
print('AVAILABLE THEMES FOR LABELING:')
print('='*70)
for i, theme in enumerate(THEMES, 1):
    print(f'  {i:2d}. {theme}')
print()

print('='*70)
print('INSTRUCTIONS:')
print('='*70)
print('''
To create labels for evaluation:

1. Review the segments above
2. Edit "evaluate_model.py" and update MANUAL_LABELS dict like this:

    MANUAL_LABELS = {
        1: "Curriculum Development",      # segment_id 1 => this theme
        2: "Infrastructure Development",  # segment_id 2 => this theme
        3: "Student Internships",
        4: "Tech Fair",
        5: "Faculty Research",
        6: "Examinations",
        7: "Accreditation",
        8: "Budget Planning",
        9: "Staff Development",
        10: "Student Affairs",
    }

3. Add more segment IDs and their correct themes (20-50+ recommended for better evaluation)

4. Then run:
   python itds_env/Scripts/evaluate_model.py

The script will:
  - Use your MANUAL_LABELS as ground truth
  - Fetch predictions from the database Analysis table
  - Calculate Precision, Recall, F1-Score per theme
''')

print('='*70)
print('SEGMENT IDs AVAILABLE FOR LABELING:', segment_ids[:15])
print('='*70)
