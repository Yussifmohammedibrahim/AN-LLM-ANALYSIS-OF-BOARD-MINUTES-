"""
Document Classification Feature
Automatically classifies meeting types.
"""
import sqlite3
import logging
import ast
import re
from collections import defaultdict
from ..models import DB_PATH, get_db
from ..model_manager import get_model_cache

# Document types
DOCUMENT_TYPES = [
    "Curriculum Review Meeting",
    "Budget Planning Meeting",
    "Staff Development Meeting",
    "Student Affairs Meeting",
    "Infrastructure Meeting",
    "Accreditation Meeting",
    "Research Committee Meeting",
    "Examination Board Meeting",
    "General Staff Meeting",
    "Tech Fair Planning Meeting"
]

LABEL_KEYWORDS = {
    "Curriculum Review Meeting": ["curriculum", "course", "academic", "education", "learning", "review"],
    "Budget Planning Meeting": ["budget", "funding", "finance", "financial", "cost", "expense", "planning"],
    "Staff Development Meeting": ["staff", "development", "training", "personnel", "workshop", "professional"],
    "Student Affairs Meeting": ["student", "admission", "enrollment", "affairs", "support", "discipline"],
    "Infrastructure Meeting": ["infrastructure", "facility", "maintenance", "building", "equipment", "repair"],
    "Accreditation Meeting": ["accreditation", "quality", "compliance", "audit", "standards", "review"],
    "Research Committee Meeting": ["research", "committee", "proposal", "grant", "publication", "innovation"],
    "Examination Board Meeting": ["exam", "examination", "assessment", "board", "grading", "results"],
    "General Staff Meeting": ["staff", "general", "operations", "update", "agenda", "meeting"],
    "Tech Fair Planning Meeting": ["tech", "technology", "fair", "planning", "event", "demo"],
}

_STOPWORDS = {
    'meeting', 'meetings', 'minutes', 'minute', 'discussion', 'discussed', 'agenda', 'item',
    'items', 'today', 'team', 'update', 'updates', 'note', 'notes', 'review', 'reviews',
    'follow', 'followup', 'follow-up', 'action', 'actions', 'point', 'points'
}


def _tokenize(text):
    tokens = re.findall(r'[a-z0-9]+', str(text or '').lower())
    return [token for token in tokens if len(token) >= 3 and token not in _STOPWORDS]


def _label_profile(label):
    profile = set(_tokenize(label))
    profile.update(LABEL_KEYWORDS.get(label, []))
    return profile


def _semantic_classify(texts, labels):
    """Classify a text collection by mapping BERTopic topics onto label keywords."""
    try:
        from .semantic_topics import extract_semantic_topics

        semantic_topics = extract_semantic_topics(
            texts,
            max_topics=min(8, max(2, len(texts) // 5 or 2)),
            min_topic_size=2,
        )
    except Exception as exc:
        logging.warning(f"Semantic topic classification unavailable: {exc}")
        return None

    if not semantic_topics:
        return None

    label_scores = defaultdict(float)
    for topic in semantic_topics:
        topic_tokens = set(_tokenize(topic.get('name')))
        topic_tokens.update(_tokenize(' '.join(topic.get('keywords') or [])))

        topic_confidence = float(topic.get('confidence') or 0.5)
        topic_weight = max(0.25, topic_confidence)

        for label in labels:
            overlap = len(topic_tokens & _label_profile(label))
            if overlap:
                label_scores[label] += overlap * topic_weight

    if not label_scores:
        return None

    ordered = sorted(label_scores.items(), key=lambda item: item[1], reverse=True)
    total = sum(score for _, score in ordered) or 1.0

    return {
        'labels': [label for label, _ in ordered],
        'scores': [round(score / total, 4) for _, score in ordered],
    }

def classify_document(meeting_id=None):
    """Classify meeting document type."""
    conn = get_db()
    cursor = conn.cursor()
    
    if meeting_id:
        cursor.execute(
            'SELECT meeting_id, original_text FROM Segments WHERE meeting_id = ?',
            (meeting_id,)
        )
    else:
        cursor.execute(
            'SELECT meeting_id, original_text FROM Segments ORDER BY meeting_id LIMIT 10',
            ()
        )
    
    segments = cursor.fetchall()
    conn.close()
    
    if not segments:
        return []
    
    # Group segments by meeting
    meetings = {}
    for row in segments:
        mid = row['meeting_id']
        text = row['original_text']
        if mid not in meetings:
            meetings[mid] = []
        meetings[mid].append(text)
    
    classifications = []
    inserts = []
    
    # Classify each meeting
    for mid, texts in meetings.items():
        combined_text = " ".join(texts)[:2000]
        
        try:
            result = _semantic_classify(texts, DOCUMENT_TYPES)
            if result is None:
                classifier = get_model_cache().get_zero_shot_pipeline()
                result = classifier(
                    combined_text,
                    candidate_labels=DOCUMENT_TYPES,
                    multi_label=False
                )
            
            document_type = result['labels'][0]
            confidence = result['scores'][0]
            all_scores = {label: round(score, 4) for label, score in 
                         zip(result['labels'], result['scores'])}
            
            inserts.append((mid, document_type, confidence, str(all_scores)))
            
            classifications.append({
                'meeting_id': mid,
                'document_type': document_type,
                'confidence': confidence,
                'all_scores': all_scores
            })
        except Exception as e:
            logging.error(f"Classification error: {e}")
            continue
            
    if inserts:
        conn = get_db()
        cursor = conn.cursor()
        cursor.executemany(
            '''INSERT INTO DocumentClassifications 
               (meeting_id, document_type, confidence, all_scores) 
               VALUES (?, ?, ?, ?)''',
            inserts
        )
        conn.commit()
        conn.close()
    
    return classifications

def get_classifications(meeting_id=None):
    """Get document classification results."""
    conn = get_db()
    cursor = conn.cursor()
    
    if meeting_id:
        cursor.execute('''
            SELECT dc.*, m.meeting_date 
            FROM DocumentClassifications dc
            JOIN Meetings m ON dc.meeting_id = m.meeting_id
            WHERE dc.meeting_id = ?
        ''', (meeting_id,))
    else:
        cursor.execute('''
            SELECT dc.*, m.meeting_date 
            FROM DocumentClassifications dc
            JOIN Meetings m ON dc.meeting_id = m.meeting_id
            ORDER BY m.meeting_date DESC
        ''', ())
    
    classifications = []
    for row in cursor.fetchall():
        item = dict(row)
        try:
            item['all_scores'] = ast.literal_eval(item['all_scores'])
        except:
            item['all_scores'] = {}
        classifications.append(item)
    
    conn.close()
    
    # Summary
    type_counts = {}
    for c in classifications:
        doc_type = c['document_type']
        type_counts[doc_type] = type_counts.get(doc_type, 0) + 1
    
    return {'classifications': classifications, 'summary': type_counts}

def classify_custom(text, custom_labels):
    """Classify text with custom labels."""
    if not text or not custom_labels:
        return None
    
    try:
        semantic_result = _semantic_classify([text], custom_labels)
        if semantic_result is not None:
            result = semantic_result
        else:
            classifier = get_model_cache().get_zero_shot_pipeline()
            result = classifier(
                text,
                candidate_labels=custom_labels,
                multi_label=False
            )
        
        return {
            'classification': result['labels'][0],
            'confidence': result['scores'][0],
            'all_scores': {label: round(score, 4) for label, score in 
                          zip(result['labels'], result['scores'])}
        }
    except Exception as e:
        logging.error(f"Custom classification error: {e}")
        return None