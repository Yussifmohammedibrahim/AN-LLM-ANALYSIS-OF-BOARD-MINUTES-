"""
Named Entity Recognition Feature
Extracts persons, organizations, locations from text.
"""
from transformers import pipeline
import sqlite3
import logging
import os
import re
import threading
from ..models import DB_PATH, get_db

logger = logging.getLogger(__name__)

MAX_CHUNK_CHARS = int(os.getenv('ITDS_NER_MAX_CHARS', '900'))
DEFAULT_MIN_SCORE = float(os.getenv('ITDS_NER_MIN_SCORE', '0.55'))

_NER_PIPELINE = None
_NER_PIPELINE_LOCK = threading.Lock()

LABEL_MAP = {
    'PERSON': 'PER',
    'PER': 'PER',
    'ORG': 'ORG',
    'ORGANIZATION': 'ORG',
    'LOC': 'LOC',
    'LOCATION': 'LOC',
    'GPE': 'LOC',
    'MISC': 'MISC',
}

# Using get_db imported from ..models


def get_ner_pipeline():
    """Load NER pipeline lazily to avoid expensive import-time model startup."""
    global _NER_PIPELINE
    if _NER_PIPELINE is not None:
        return _NER_PIPELINE

    with _NER_PIPELINE_LOCK:
        if _NER_PIPELINE is None:
            try:
                model_name = os.getenv('ITDS_NER_MODEL', '').strip()
                if not model_name:
                    raise RuntimeError('Missing required environment variable: ITDS_NER_MODEL')
                _NER_PIPELINE = pipeline(
                    "ner",
                    model=model_name,
                    aggregation_strategy="simple"
                )
                logger.info("NER pipeline initialized: %s", model_name)
            except Exception as exc:
                logger.warning("NER pipeline unavailable: %s", exc)
                _NER_PIPELINE = False
    return _NER_PIPELINE


def _split_text_for_ner(text):
    """Split long text into inference-safe chunks while keeping sentence boundaries when possible."""
    text = str(text or '').strip()
    if not text:
        return []
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]

    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current = []
    current_len = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) > MAX_CHUNK_CHARS:
            for i in range(0, len(sentence), MAX_CHUNK_CHARS):
                part = sentence[i:i + MAX_CHUNK_CHARS].strip()
                if part:
                    chunks.append(part)
            continue

        if current_len + len(sentence) + 1 > MAX_CHUNK_CHARS:
            if current:
                chunks.append(' '.join(current))
            current = [sentence]
            current_len = len(sentence)
        else:
            current.append(sentence)
            current_len += len(sentence) + 1

    if current:
        chunks.append(' '.join(current))

    return chunks


def _normalize_label(raw_label):
    label = str(raw_label or '').upper()
    if label.startswith('B-') or label.startswith('I-'):
        label = label[2:]
    return LABEL_MAP.get(label, label or 'MISC')


def _normalize_entity(entity):
    word = str(entity.get('word') or entity.get('entity') or '').strip()
    label = _normalize_label(entity.get('entity_group') or entity.get('entity'))
    score = float(entity.get('score') or 0.0)

    if not word:
        return None

    return {
        'word': word,
        'entity_group': label,
        'score': score,
    }


def _dedupe_entities(entities):
    """Keep highest-confidence entity for each (label, token) pair."""
    best_by_key = {}
    for entity in entities:
        key = (entity['entity_group'], entity['word'].lower())
        if key not in best_by_key or entity['score'] > best_by_key[key]['score']:
            best_by_key[key] = entity
    return sorted(best_by_key.values(), key=lambda x: (-x['score'], x['word']))


def extract_entities(text, min_score=DEFAULT_MIN_SCORE):
    """Extract named entities from text with confidence filtering and chunked inference."""
    ner = get_ner_pipeline()
    if not ner:
        return []

    chunks = _split_text_for_ner(text)
    if not chunks:
        return []

    collected = []
    try:
        for chunk in chunks:
            raw_entities = ner(chunk)
            for raw in raw_entities:
                normalized = _normalize_entity(raw)
                if not normalized:
                    continue
                if normalized['score'] >= float(min_score):
                    collected.append(normalized)
    except Exception as e:
        logger.error("NER error: %s", e)
        return []

    return _dedupe_entities(collected)


def extract_entities_batch(texts, min_score=DEFAULT_MIN_SCORE):
    """Batch-friendly NER for multiple texts."""
    return [extract_entities(text, min_score=min_score) for text in texts]


def anonymize_text(text, min_score=DEFAULT_MIN_SCORE):
    """Anonymize personal names in text using reliable entity extraction."""
    text = str(text or '')
    if not text.strip():
        return text, []

    entities = extract_entities(text, min_score=min_score)
    anonymized_text = text

    person_entities = [e for e in entities if e['entity_group'] == 'PER']

    for i, entity in enumerate(person_entities):
        pattern = r'\b{}\b'.format(re.escape(entity['word']))
        anonymized_text = re.sub(pattern, f'[PERSON_{i+1}]', anonymized_text)

    return anonymized_text, person_entities


def get_entities(meeting_id=None):
    """Get all entities from meeting segments using batched extraction."""
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

    segment_ids = [row['segment_id'] for row in rows]
    texts = [row['original_text'] for row in rows]

    all_entities = []
    entities_by_segment = extract_entities_batch(texts)
    for segment_id, entities in zip(segment_ids, entities_by_segment):
        for entity in entities:
            all_entities.append({
                'segment_id': segment_id,
                'entity': entity['word'],
                'type': entity['entity_group'],
                'confidence': round(float(entity['score']), 4)
            })

    # Group by type
    entity_types = {}
    for entity in all_entities:
        entity_type = entity['type']
        if entity_type not in entity_types:
            entity_types[entity_type] = []
        entity_types[entity_type].append(entity)

    return {'entities': all_entities, 'summary': {k: len(v) for k, v in entity_types.items()}}