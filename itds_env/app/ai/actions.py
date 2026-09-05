"""
Action Item and Decision Extraction
Identifies decisions, action items, and responsible persons.
"""
import sqlite3
import re
import logging
from .ner import extract_entities
from ..models import DB_PATH, get_db

def extract_action_items_from_text(text):
    """Extract action items and decisions from text."""
    action_items = []
    decisions = []
    
    # Keywords
    action_keywords = ['will', 'should', 'must', 'need to', 'required to', 'assigned to', 'responsible for']
    decision_keywords = ['decided', 'agreed', 'approved', 'confirmed', 'resolved', 'concluded']
    
    # Split into sentences
    sentences = re.split(r'[.!?]', text)
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        
        sentence_lower = sentence.lower()
        
        # Check for action items
        for keyword in action_keywords:
            if keyword in sentence_lower:
                entities = extract_entities(sentence, min_score=0.55)
                persons = [e['word'] for e in entities if e['entity_group'] == 'PER']
                
                action_items.append({
                    'text': sentence,
                    'keyword': keyword,
                    'persons': persons
                })
                break
        
        # Check for decisions
        for keyword in decision_keywords:
            if keyword in sentence_lower:
                decisions.append({
                    'text': sentence,
                    'keyword': keyword
                })
                break
    
    return action_items, decisions

def extract_action_items(meeting_id=None):
    """Process all segments and extract action items."""
    conn = get_db()
    cursor = conn.cursor()
    
    if meeting_id:
        cursor.execute(
            'SELECT segment_id, original_text FROM Segments WHERE meeting_id = ?',
            (meeting_id,)
        )
    else:
        cursor.execute(
            'SELECT segment_id, original_text FROM Segments LIMIT 50',
            ()
        )
    
    rows = cursor.fetchall()
    conn.close()
    
    all_items = []
    inserts = []
    
    for row in rows:
        segment_id = row['segment_id']
        text = row['original_text']
        
        actions, decisions = extract_action_items_from_text(text)
        
        for action in actions:
            inserts.append((
                segment_id, 
                'action_item', 
                action['text'], 
                action['keyword'], 
                ','.join(action['persons'])
            ))
            all_items.append({'type': 'action_item', 'text': action['text'], 'keyword': action['keyword']})
        
        for decision in decisions:
            inserts.append((
                segment_id, 
                'decision', 
                decision['text'], 
                decision['keyword'], 
                ''
            ))
            all_items.append({'type': 'decision', 'text': decision['text'], 'keyword': decision['keyword']})
            
    if inserts:
        conn = get_db()
        cursor = conn.cursor()
        cursor.executemany(
            'INSERT INTO ActionItems (segment_id, item_type, item_text, keyword, persons) VALUES (?, ?, ?, ?, ?)',
            inserts
        )
        conn.commit()
        conn.close()
        
    return all_items

def get_action_items(meeting_id=None):
    """Get extracted action items and decisions."""
    conn = get_db()
    cursor = conn.cursor()
    
    if meeting_id:
        cursor.execute('''
            SELECT * FROM ActionItems WHERE segment_id IN 
            (SELECT segment_id FROM Segments WHERE meeting_id = ?)
        ''', (meeting_id,))
    else:
        cursor.execute('SELECT * FROM ActionItems', ())
    
    decisions = []
    action_items = []
    
    for row in cursor.fetchall():
        item = dict(row)
        if item['item_type'] == 'decision':
            decisions.append(item)
        else:
            action_items.append(item)
    
    conn.close()
    
    return {'decisions': decisions, 'action_items': action_items, 'total': len(decisions) + len(action_items)}