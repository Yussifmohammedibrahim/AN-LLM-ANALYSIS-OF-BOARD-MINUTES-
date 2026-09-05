"""
Semantic topic extraction using lightweight NLP fallbacks.
Returns short, meeting-style topic names that avoid sentence-like output.
"""

import logging
import re

import numpy as np
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer


DOMAIN_STOPWORDS = {
    'meeting', 'meetings', 'minutes', 'minute', 'discussion', 'discussed', 'agenda', 'item',
    'items', 'today', 'team', 'update', 'updates', 'note', 'notes', 'review', 'reviews',
    'follow', 'followup', 'follow-up', 'action', 'actions', 'point', 'points',
    'mr', 'mrs', 'ms', 'dr', 'prof', 'professor', 'lecturer', 'chairman', 'chairperson',
    'assistant', 'member', 'members', 'department', 'students', 'student', 'university',
    'staff', 'the', 'and', 'for', 'from', 'into', 'during', 'regarding', 'about',
    'talk', 'talking', 'spoke', 'speaking', 'said', 'says', 'was', 'were', 'will'
}

CUSTOM_STOPWORDS = set(ENGLISH_STOP_WORDS).union(DOMAIN_STOPWORDS)

TRASH_THEME_WORDS = {
    'the', 'the of', 'the of the', 'the and', 'and the', 'of the', 'for the',
    'mr', 'dr', 'lecturer', 'chairman', 'assistant lecturer', 'department chairman',
    'meeting', 'minutes', 'discussion', 'general discussion', 'topic', 'themes',
    'students chairman mr department', 'mr dr chairman member', 'mr department assistant lecturer',
    'mr assistant lecturer dr', 'mr assistant jacob lecturer', 'department chairman mr lecturer',
    'chairman department students members'
}


def _normalize_term(value):
    value = re.sub(r'[^a-z0-9\s-]', ' ', str(value or '').lower())
    value = re.sub(r'\s+', ' ', value).strip(' -/,.')
    return value


def _unique_preserve_order(values):
    seen = set()
    unique_values = []
    for value in values:
        normalized = _normalize_term(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique_values.append(normalized)
    return unique_values


def clean_text(text):
    value = str(text or '').lower()
    value = re.sub(r'[^a-z0-9\s-]', ' ', value)
    value = re.sub(r'\s+', ' ', value).strip()
    return value


def _short_topic_label(text, fallback='General', max_words=4):
    value = clean_text(text)
    if not value:
        return fallback

    noise_words = CUSTOM_STOPWORDS.union({
        'with', 'about', 'regarding', 'regards', 'regard', 'discussion', 'discuss',
        'discusses', 'topics', 'topic', 'the', 'and', 'for', 'from', 'into', 'during',
        'meeting', 'minutes'
    })
    parts = [part for part in value.split() if part not in noise_words]
    if not parts:
        return fallback

    short = ' '.join(parts[:max_words]).strip()
    short = re.sub(r'\s+', ' ', short).strip(' -/,.')
    if not short:
        return fallback

    words = short.split()
    if len(words) < 2 and len(parts) > 1:
        short = ' '.join(parts[:2]).strip()
        short = re.sub(r'\s+', ' ', short).strip(' -/,.')
    return short[:1].upper() + short[1:] if short else fallback


def build_topic_name(keywords, blocked_terms=None):
    if not keywords:
        return 'Governance Cluster'

    blocked_terms = {
        _normalize_term(term)
        for term in (blocked_terms or [])
        if _normalize_term(term)
    }

    topic_patterns = {
        'budget': ('Budget Planning', ['budget', 'funding', 'financial', 'cost', 'expense']),
        'curriculum': ('Curriculum Review', ['curriculum', 'course', 'program', 'education', 'academic']),
        'staff': ('Staff Updates', ['staff', 'personnel', 'employee', 'hiring', 'recruitment']),
        'student': ('Student Matters', ['student', 'enrollment', 'admission', 'academic']),
        'infrastructure': ('Infrastructure Update', ['facility', 'building', 'maintenance', 'construction']),
        'policy': ('Policy Review', ['policy', 'procedure', 'guideline', 'regulation']),
        'strategy': ('Strategy Planning', ['strategy', 'planning', 'roadmap', 'priority']),
    }

    top_words = []
    for word in keywords[:6]:
        normalized = _normalize_term(word)
        if not normalized or normalized in CUSTOM_STOPWORDS or normalized in blocked_terms:
            continue
        for token in normalized.split():
            if token and token not in CUSTOM_STOPWORDS and token not in blocked_terms:
                top_words.append(token)
    top_words = _unique_preserve_order(top_words)

    for label, pattern_words in topic_patterns.values():
        if any(word in top_words for word in pattern_words):
            return label

    # Check for trash labels before returning fallback
    fallback_source = ' '.join(top_words[:4]) if top_words else ' '.join(keywords[:3])
    if _normalize_term(fallback_source) in TRASH_THEME_WORDS:
        return 'General Discussion'
    fallback_label = str(keywords[0]).strip().title() if str(keywords[0]).strip() else 'Governance Cluster'
    if fallback_label.lower() in {'theme', 'themes', 'general', 'topic', 'general topic'}:
        fallback_label = 'Governance Cluster'
    fallback = _short_topic_label(fallback_source, fallback=fallback_label, max_words=4)
    fallback_words = _unique_preserve_order(fallback.split())
    if len(fallback_words) > 1:
        fallback = ' '.join(fallback_words[:4])
    elif len(top_words) > 1:
        fallback = ' '.join(top_words[:4]).title()
    if fallback.lower() in {'theme', 'themes', 'general', 'topic', 'general topic'}:
        fallback = 'Governance Cluster' if top_words else fallback_label
    return fallback


def extract_semantic_topics(texts, max_topics=8, min_topic_size=2):
    """Extract short topics from text snippets using TF-IDF + KMeans."""
    cleaned_texts = [clean_text(t) for t in texts if clean_text(t)]
    cleaned_texts = [t for t in cleaned_texts if len(t) >= 20]
    if len(cleaned_texts) < 3:
        return []

    try:
        vectorizer = TfidfVectorizer(
            stop_words=list(CUSTOM_STOPWORDS),
            ngram_range=(1, 2),
            max_features=1500,
            min_df=1,
        )
        matrix = vectorizer.fit_transform(cleaned_texts)
        feature_names = vectorizer.get_feature_names_out()
        if matrix.shape[0] < 3 or matrix.shape[1] == 0:
            return []

        n_clusters = min(max(2, int(max_topics or 8)), matrix.shape[0])
        if n_clusters < 2:
            n_clusters = 1

        if n_clusters == 1:
            top_indices = np.asarray(matrix.sum(axis=0)).ravel().argsort()[::-1][:6]
            keywords = [str(feature_names[i]) for i in top_indices if i < len(feature_names)]
            name = build_topic_name(keywords)
            return [{
                'name': name,
                'confidence': 0.65,
                'keywords': keywords[:5],
                'segment_count': len(cleaned_texts),
            }]

        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=5, max_iter=200)
        labels = kmeans.fit_predict(matrix)
        centers = kmeans.cluster_centers_

        topics = []
        for cluster_id in range(n_clusters):
            member_indices = np.where(labels == cluster_id)[0]
            if len(member_indices) < min_topic_size:
                continue

            top_indices = centers[cluster_id].argsort()[::-1][:8]
            keywords = [str(feature_names[i]) for i in top_indices if i < len(feature_names)]
            keywords = [word for word in keywords if word and word not in CUSTOM_STOPWORDS]
            if not keywords:
                continue

            topic_name = build_topic_name(keywords)
            cluster_strength = float(np.mean(np.max(matrix[member_indices].toarray(), axis=1))) if len(member_indices) else 0.5

            topics.append({
                'name': topic_name,
                'confidence': round(max(0.05, min(0.95, cluster_strength)), 3),
                'keywords': keywords[:5],
                'segment_count': int(len(member_indices)),
            })

        topics.sort(key=lambda item: (item['segment_count'], item['confidence']), reverse=True)
        return topics[:max_topics]
    except Exception as exc:
        logging.warning(f"Semantic topic extraction unavailable. Falling back: {exc}")
        return []
