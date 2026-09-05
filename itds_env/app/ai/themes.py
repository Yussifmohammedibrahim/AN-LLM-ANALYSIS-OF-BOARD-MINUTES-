"""
Dynamic Theme Extraction and Analysis
Extracts themes from transcripts without relying on predefined themes.
Uses topic modeling and NLP techniques.
"""
from sklearn.feature_extraction.text import TfidfVectorizer, ENGLISH_STOP_WORDS
from sklearn.cluster import KMeans
from sklearn.decomposition import LatentDirichletAllocation
from sklearn.metrics import silhouette_score
import sqlite3
import logging
from collections import defaultdict
import datetime
import warnings
import numpy as np
import re
import os
import json
import time
from threading import Lock
from ..models import DB_PATH, get_db
from .semantic_topics import extract_semantic_topics, build_topic_name

try:
    from .ner import extract_entities
except Exception:
    extract_entities = None

try:
    from bertopic import BERTopic
    from sentence_transformers import SentenceTransformer
    BERTOPIC_AVAILABLE = True
except ImportError:
    BERTOPIC_AVAILABLE = False
    BERTopic = None
    SentenceTransformer = None

DOMAIN_STOPWORDS = {
    'meeting', 'meetings', 'minutes', 'minute', 'discussion', 'discussed', 'agenda', 'item',
    'items', 'today', 'team', 'update', 'updates', 'note', 'notes', 'review', 'reviews',
    'follow', 'followup', 'follow-up', 'action', 'actions', 'point', 'points',
    'mr', 'mrs', 'ms', 'dr', 'prof', 'professor', 'lecturer', 'chairman', 'chairperson',
    'assistant', 'member', 'members', 'department', 'students', 'student', 'university',
    'staff', 'the', 'and', 'for', 'from', 'into', 'during', 'regarding', 'about',
    'talk', 'talking', 'spoke', 'speaking', 'said', 'says', 'was', 'were', 'will',
    'snr', 'sn', 'jacob', 'seconded', 'weekend', 'regular', 'marking', 'inft', 'technology',
    'discussed', 'discussion', 'minutes', 'meeting', 'page', 'project'
}

CUSTOM_STOPWORDS = set(ENGLISH_STOP_WORDS).union(DOMAIN_STOPWORDS)

TRASH_THEME_WORDS = {
    'mr', 'dr', 'lecturer', 'chairman', 'assistant lecturer', 'department chairman',
    'meeting', 'minutes', 'discussion', 'general discussion', 'topic', 'themes',
    'snr', 'sn', 'jacob', 'seconded', 'inft', 'weekend', 'regular', 'marking'
}

# Theme extraction cache (Redis-backed with in-memory fallback)
_REDIS_CLIENT = None
_THEMES_CACHE_FILE = os.path.join(os.path.dirname(__file__), '.themes_cache.json')

def _load_disk_cache():
    if os.path.exists(_THEMES_CACHE_FILE):
        try:
            with open(_THEMES_CACHE_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _save_disk_cache(cache):
    try:
        with open(_THEMES_CACHE_FILE, 'w') as f:
            json.dump(cache, f)
    except Exception:
        pass

_CACHE_LOCK = Lock()
_THEMES_CACHE = _load_disk_cache()

logger = logging.getLogger(__name__)
THEMES_CACHE_VERSION = 4

try:
    import redis as _redis
    _redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    try:
        _REDIS_CLIENT = _redis.from_url(_redis_url, decode_responses=True)
        _REDIS_CLIENT.ping()
        logger.info(f"Using Redis cache for themes at {_redis_url}")
    except Exception as e:
        logger.warning(f"Redis not available for themes cache: {e}. Using in-memory cache.")
        _REDIS_CLIENT = None
except Exception:
    _REDIS_CLIENT = None


def _get_cache_key(meeting_id=None, num_themes=5, year=None):
    """Generate cache key for theme extraction."""
    if year is None:
        year = datetime.datetime.now().year
    
    if meeting_id:
        return f"themes:v{THEMES_CACHE_VERSION}:meeting:{meeting_id}:n{num_themes}"
    else:
        return f"themes:v{THEMES_CACHE_VERSION}:global:year{year}:n{num_themes}"


def _is_generic_theme_label(value):
    label = str(value or '').strip().lower()
    return label in {'theme', 'themes', 'general', 'general topic', 'topic', 'unknown', 'unknown theme', 'governance cluster'}


def _get_cached_themes(cache_key, ttl=3600):
    """Retrieve cached themes. TTL default is 1 hour."""
    with _CACHE_LOCK:
        # Try Redis first
        if _REDIS_CLIENT:
            try:
                cached = _REDIS_CLIENT.get(cache_key)
                if cached:
                    logger.debug(f"Cache hit (Redis): {cache_key}")
                    return json.loads(cached)
            except Exception as e:
                logger.warning(f"Redis cache retrieval failed: {e}")
        
        # Fall back to in-memory
        if cache_key in _THEMES_CACHE:
            ts, themes = _THEMES_CACHE[cache_key]
            if time.time() - ts < ttl:
                logger.debug(f"Cache hit (in-memory): {cache_key}")
                return themes
            else:
                # Expired
                del _THEMES_CACHE[cache_key]
                _save_disk_cache(_THEMES_CACHE)
    
    return None


def _set_cached_themes(cache_key, themes, ttl=3600):
    """Store extracted themes in cache."""
    with _CACHE_LOCK:
        # Try Redis first
        if _REDIS_CLIENT:
            try:
                _REDIS_CLIENT.set(cache_key, json.dumps(themes), ex=ttl)
                logger.debug(f"Cached themes (Redis): {cache_key}")
                return
            except Exception as e:
                logger.warning(f"Redis cache storage failed: {e}")
        
        # Fall back to in-memory
        _THEMES_CACHE[cache_key] = (time.time(), themes)
        _save_disk_cache(_THEMES_CACHE)
        logger.debug(f"Cached themes (in-memory): {cache_key}")


def _clear_cache_key(cache_key):
    """Clear a specific cache key."""
    with _CACHE_LOCK:
        if _REDIS_CLIENT:
            try:
                _REDIS_CLIENT.delete(cache_key)
            except Exception:
                pass
        try:
            if cache_key in _THEMES_CACHE:
                del _THEMES_CACHE[cache_key]
                _save_disk_cache(_THEMES_CACHE)
        except KeyError:
            pass


def clear_theme_cache(year=None, meeting_id=None):
    """Clear cached theme extraction results for a year or meeting (all variations)."""
    with _CACHE_LOCK:
        prefixes = []
        if meeting_id is not None:
            prefixes.append(f"themes:v{THEMES_CACHE_VERSION}:meeting:{meeting_id}:")
        elif year is not None:
            # Clear all counts (:n5, :n8, etc.) for this year
            prefixes.append(f"themes:v{THEMES_CACHE_VERSION}:global:year{year}:")
        else:
            prefixes.extend([
                f"themes:v{THEMES_CACHE_VERSION}:global:",
                f"themes:v{THEMES_CACHE_VERSION}:meeting:",
            ])

        # Clear in-memory cache using prefix matching
        keys_to_delete = [
            k for k in _THEMES_CACHE.keys() 
            if any(str(k).startswith(p) for p in prefixes)
        ]
        for k in keys_to_delete:
            _THEMES_CACHE.pop(k, None)
        
        _save_disk_cache(_THEMES_CACHE)

        # Clear Redis cache using SCAN to avoid blocking
        if _REDIS_CLIENT:
            try:
                for prefix in prefixes:
                    cursor = 0
                    while True:
                        cursor, keys = _REDIS_CLIENT.scan(cursor=cursor, match=f"{prefix}*", count=100)
                        if keys:
                            _REDIS_CLIENT.delete(*keys)
                        if cursor == 0:
                            break
            except Exception as e:
                logger.warning(f"Failed to clear Redis themes: {e}")


def _clean_text(text):
    text = str(text or '').lower()
    text = re.sub(r'[^a-z0-9\s-]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# Theme normalization dictionary for handling terminology variants
THEME_ALIASES = {
    "curriculum": {
        "aliases": ["curriculum", "curriculum change", "curriculum revamp", "new courses", "program review", 
                   "course development", "academic update", "education plan", "syllabus review", "academic programs"],
        "canonical": "Curriculum Development & Review"
    },
    "infrastructure": {
        "aliases": ["facilities", "campus improvements", "building upgrades", "facility maintenance",
                   "construction", "equipment repair", "infrastructure upgrade", "estates", "security"],
        "canonical": "Infrastructure & Estate"
    },
    "budget": {
        "aliases": ["budget constraint", "financial planning", "funding", "cost allocation",
                   "resource allocation", "financial risk", "spending", "audit", "expenditure"],
        "canonical": "Budget & Finance"
    },
    "staff": {
        "aliases": ["personnel", "employee", "hiring", "recruitment", "staffing", "human resources",
                   "promotion", "tenure", "faculty affairs", "labor relations"],
        "canonical": "Staff Development"
    },
    "accreditation": {
        "aliases": ["quality assurance", "compliance audit", "standards review", "regulatory", "external review"],
        "canonical": "Accreditation"
    },
    "research": {
        "aliases": ["research project", "grant", "publication", "research initiative", "innovation", "lab setup"],
        "canonical": "Research & Grants"
    },
    "governance": {
        "aliases": ["board decision", "policy update", "by-laws", "committee structure", "legal", "compliance"],
        "canonical": "Governance & Policy"
    },
    "student_affairs": {
        "aliases": ["student welfare", "enrollment", "admission", "student support", "scholarship", "discipline"],
        "canonical": "Student Affairs"
    },
    "technology": {
        "aliases": ["it systems", "software", "digitalization", "server", "cybersecurity", "tech infrastructure"],
        "canonical": "IT & Digital Strategy"
    }
}


def _normalize_theme_name(theme_name, keywords=None):
    """
    Normalize theme names by detecting aliases and returning canonical form.
    Helps with terminology variant matching (e.g., "curriculum revamp" → "Curriculum Development").
    
    Args:
        theme_name: Raw theme name from LLM
        keywords: List of keywords to check for aliases
    
    Returns:
        Tuple of (canonical_name, is_normalized)
    """
    if not theme_name:
        return theme_name, False
    
    clean_name = _clean_text(theme_name)
    clean_keywords = [_clean_text(k) for k in (keywords or [])]
    all_words = clean_name.split() + clean_keywords
    
    # Check each theme group for matches
    for canonical_key, theme_group in THEME_ALIASES.items():
        # Check against category key or any alias
        if canonical_key in all_words or any(_clean_text(alias) in all_words or alias.lower() in clean_name for alias in theme_group["aliases"]):
            return theme_group["canonical"], True
    
    # Reject "Trash" themes or those consisting only of noise words
    if clean_name in TRASH_THEME_WORDS:
        return None, True
    
    # If the theme is just a list of stopwords, reject it
    name_words = clean_name.split()
    if all(word in CUSTOM_STOPWORDS for word in name_words):
        return None, True

    if len(clean_name) < 3:
        return None, True
    
    return theme_name, False


def _collapse_duplicate_words(text):
    words = [word for word in re.findall(r'[A-Za-z0-9-]+', str(text or '')) if word]
    collapsed = []
    for word in words:
        if collapsed and collapsed[-1].lower() == word.lower():
            continue
        collapsed.append(word)
    return ' '.join(collapsed).strip()


def _collect_blocked_terms(texts, max_samples=12):
    if not extract_entities:
        return set()

    sample_texts = []
    for text in texts or []:
        raw_text = str(text or '').strip()
        if raw_text:
            sample_texts.append(raw_text)
        if len(sample_texts) >= max_samples:
            break

    sample = ' '.join(sample_texts).strip()
    if not sample:
        return set()

    blocked_terms = set()
    try:
        for entity in extract_entities(sample, min_score=0.65):
            if entity.get('entity_group') != 'PER':
                continue
            word = _clean_text(entity.get('word') or '')
            if not word:
                continue
            blocked_terms.add(word)
            for token in word.split():
                blocked_terms.add(token)
    except Exception:
        return set()

    return blocked_terms


def _normalize_theme_record(theme, theme_id, min_frequency=1, blocked_terms=None):
    """Normalize a theme-like object into the API response shape."""
    if not isinstance(theme, dict):
        theme = {}

    blocked_terms = {
        _clean_text(term)
        for term in (blocked_terms or [])
        if _clean_text(term)
    }

    keywords = theme.get('keywords', []) or []
    if isinstance(keywords, str):
        keywords = [part.strip() for part in keywords.split(',') if part.strip()]

    normalized_keywords = []
    for keyword in keywords:
        keyword_text = str(keyword).strip().lower()
        # Remove any trash words from inside multi-word keywords
        for trash in TRASH_THEME_WORDS:
            keyword_text = re.sub(rf'\b{re.escape(trash)}\b', '', keyword_text).strip()
            
        if keyword_text and len(keyword_text) > 1:
            if keyword_text not in normalized_keywords \
               and keyword_text not in blocked_terms \
               and keyword_text not in TRASH_THEME_WORDS \
               and keyword_text not in DOMAIN_STOPWORDS:
                normalized_keywords.append(keyword_text)
        if len(normalized_keywords) >= 6:
            break

    raw_name = str(theme.get('name') or theme.get('theme') or '').strip()
    if raw_name:
        raw_name = re.sub(r'\s+', ' ', raw_name)
        # Normalize theme name to canonical form (handles terminology variants)
        raw_name, was_normalized = _normalize_theme_name(raw_name, keywords=keywords)
        if was_normalized:
            logger.debug(f"Normalized theme: {theme.get('name')} → {raw_name}")

    generic_names = {
        'general discussion', 'general', 'updates', 'update', 'planning', 'review', 'strategy',
        'miscellaneous', 'other', 'operations', 'discussion', 'meeting summary', 'summary'
    }
    # Scrub TRASH_THEME_WORDS and DOMAIN_STOPWORDS from the theme name
    raw_words = [word for word in raw_name.split() if word]
    cleaned_words = [
        word for word in raw_words 
        if word.lower() not in TRASH_THEME_WORDS 
        and word.lower() not in DOMAIN_STOPWORDS 
        and len(word) > 1
    ]
    raw_name = ' '.join(cleaned_words).strip()
    
    raw_is_suspicious = (
        not raw_name
        or raw_name.lower() in generic_names
        or len(cleaned_words) > 5
        or bool(re.search(r'\d', raw_name) and re.search(r'\b(page|of|section|chapter)\b', raw_name, re.I))
        or len(cleaned_words) < 1
        or len(set(word.lower() for word in cleaned_words)) < 1
        or any(_clean_text(word) in blocked_terms for word in cleaned_words)
    )
    if raw_is_suspicious:
        fallback_keywords = [keyword for keyword in keywords[:4] if _clean_text(keyword) not in blocked_terms]
        raw_name = build_topic_name(fallback_keywords or keywords[:4], blocked_terms=blocked_terms) if (fallback_keywords or keywords) else f'Theme {theme_id}'

    name = _collapse_duplicate_words(raw_name).title()
    # Ensure at least 2 words for clarity if it's not a known canonical category
    if len(name.split()) == 1:
        is_canonical = any(name.lower() == g["canonical"].lower() for g in THEME_ALIASES.values())
        if not is_canonical and keywords:
            best_keyword = keywords[0].title()
            if best_keyword.lower() != name.lower():
                name = f"{name} {best_keyword}"
            elif len(keywords) > 1:
                name = f"{name} {keywords[1].title()}"
    if not name or _is_generic_theme_label(name):
        if keywords:
            name = build_topic_name(keywords, blocked_terms=blocked_terms)
        if not name or _is_generic_theme_label(name):
            name = f'Cluster {theme_id}'

    frequency = theme.get('frequency', min_frequency)
    try:
        frequency = max(int(min_frequency), int(frequency))
    except Exception:
        frequency = int(min_frequency)

    confidence = theme.get('confidence', 0.8)
    try:
        confidence = float(confidence)
    except Exception:
        confidence = 0.8

    confidence = max(0.5, min(1.0, confidence))

    return {
        'theme_id': theme_id,
        'name': name,
        'keywords': normalized_keywords[:4],
        'frequency': frequency,
        'confidence': confidence,
    }


def _repair_json(json_str):
    """
    Attempt to repair malformed JSON string from LLM output.
    Handles common issues like unclosed strings, missing commas, etc.
    
    Args:
        json_str: Potentially malformed JSON string
        
    Returns:
        Parsed JSON list if successful, None otherwise
    """
    if not json_str:
        return None
        
    original = json_str
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass
    
    # Strategy 1: Extract JSON array using regex
    import re
    # Find content between [ and ]
    match = re.search(r'\[.*\]', json_str, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    
    # Strategy 2: Try to fix common issues
    repaired = json_str
    
    # Remove any leading/trailing whitespace and non-json characters
    repaired = repaired.strip()
    
    # If it starts with ```, remove the fences
    if repaired.startswith("```"):
        repaired = repaired[3:]
    if repaired.endswith("```"):
        repaired = repaired[:-3]
    repaired = repaired.strip()
    
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass
    
    # Strategy 3: Try to fix unclosed strings by finding complete objects
    # This is a simplistic approach - findbalanced brackets
    try:
        # Simple attempt: find the first [ and last ] to extract array
        start_idx = repaired.find('[')
        end_idx = repaired.rfind(']')
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            possible = repaired[start_idx:end_idx+1]
            return json.loads(possible)
    except:
        pass
    
    # If all else fails, log and return None
    logging.warning(f"Failed to repair JSON: {original[:200]}...")
    return None


def _extract_themes_from_partial_output(raw_output, max_items=5):
    """Best-effort extraction of complete theme objects from truncated model output."""
    text = str(raw_output or '').strip()
    if not text:
        return []

    # Focus on the themes array region if present.
    themes_anchor = text.find('"themes"')
    scan_text = text[themes_anchor:] if themes_anchor >= 0 else text

    # Capture complete object blocks that at least include name/keywords/frequency/confidence keys.
    object_candidates = re.findall(r'\{[^{}]*\}', scan_text, flags=re.DOTALL)
    extracted = []

    for candidate in object_candidates:
        if '"name"' not in candidate or '"keywords"' not in candidate:
            continue
        if '"frequency"' not in candidate or '"confidence"' not in candidate:
            continue
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                extracted.append(parsed)
        except Exception:
            continue
        if len(extracted) >= int(max_items):
            break

    return extracted

# Using get_db imported from ..models

def _determine_optimal_clusters(tfidf_matrix, max_clusters=8):
    """
    Determine optimal number of clusters using silhouette score.
    Falls back to reasonable default if computation fails.
    
    Args:
        tfidf_matrix: Sparse TF-IDF matrix
        max_clusters: Maximum clusters to test
    
    Returns:
        Optimal number of clusters
    """
    n_samples = tfidf_matrix.shape[0]
    max_clusters = min(max_clusters, max(2, n_samples // 3))  # At least 3 samples per cluster
    
    if n_samples < 3:
        return min(2, n_samples)
    
    try:
        best_score = -1
        best_k = 2
        
        for k in range(2, max_clusters + 1):
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore')
                kmeans = KMeans(n_clusters=k, random_state=42, n_init=5)
                labels = kmeans.fit_predict(tfidf_matrix)
                
                if len(np.unique(labels)) > 1:  # Need at least 2 clusters for silhouette
                    score = silhouette_score(tfidf_matrix, labels)
                    if score > best_score:
                        best_score = score
                        best_k = k
        
        return best_k
    except Exception as e:
        logging.debug(f"Optimal cluster determination failed: {e}, using default")
        return min(3, max_clusters, n_samples)

def _extract_bertopic_themes(texts, num_themes=5, blocked_terms=None):
    """
    Advanced theme extraction using BERTopic (Sentence Embeddings + HDBSCAN).
    Provides superior semantic coherence compared to K-Means.
    """
    if not BERTOPIC_AVAILABLE or not texts or len(texts) < 10:
        return []

    try:
        logger.info(f"Extracting themes using BERTopic from {len(texts)} segments...")
        
        # Use a lightweight but high-quality embedding model
        model_name = os.environ.get('TOPIC_EMBEDDING_MODEL', 'all-MiniLM-L6-v2')
        
        # Initialize BERTopic with sensible defaults for meeting data
        # We use a simple configuration to keep it fast but accurate
        topic_model = BERTopic(
            embedding_model=model_name,
            nr_topics=num_themes + 1, # +1 to account for outlier topic (-1)
            calculate_probabilities=False,
            verbose=False
        )
        
        topics, probs = topic_model.fit_transform(texts)
        
        # Get topic information
        topic_info = topic_model.get_topic_info()
        
        extracted_themes = []
        for i, row in topic_info.iterrows():
            topic_id = row['Topic']
            if topic_id == -1: # Skip outliers
                continue
            
            # Get keywords for this topic
            words = [w[0] for w in topic_model.get_topic(topic_id)]
            
            # Filter blocked terms
            words = [w for w in words if _clean_text(w) not in set(_clean_text(term) for term in (blocked_terms or []))]
            
            if not words:
                continue
                
            theme_name = row.get('Name', words[0].title())
            # Clean up the BERTopic name which often looks like "0_word1_word2"
            if '_' in theme_name:
                theme_name = ' '.join(theme_name.split('_')[1:]).title()
            
            extracted_themes.append(_normalize_theme_record({
                'name': theme_name,
                'keywords': words[:8],
                'frequency': int(row['Count']),
                'confidence': 0.9,
                'bertopic_id': int(topic_id)
            }, len(extracted_themes), blocked_terms=blocked_terms))
            
            if len(extracted_themes) >= num_themes:
                break
                
        return extracted_themes
    except Exception as e:
        logger.warning(f"BERTopic extraction failed: {e}. Falling back to TF-IDF.")
        return []

def _extract_fallback_themes(texts, num_themes=5, min_frequency=1, blocked_terms=None):
    """
    Fallback theme extraction using BERTopic (if available) or TF-IDF/K-Means.
    """
    if not texts or len(texts) < 2:
        return []

    # Strategy 1: Attempt BERTopic (Best quality local option)
    if BERTOPIC_AVAILABLE and len(texts) >= 10:
        try:
            bertopic_themes = _extract_bertopic_themes(texts, num_themes=num_themes, blocked_terms=blocked_terms)
            if bertopic_themes:
                return bertopic_themes
        except Exception as e:
            logger.debug(f"BERTopic fallback attempt failed: {e}")

    try:
        semantic_topics = extract_semantic_topics(texts, max_topics=num_themes, min_topic_size=2)
        if semantic_topics:
            themes = []
            for index, topic in enumerate(semantic_topics[:num_themes]):
                topic_keywords = [
                    keyword for keyword in (topic.get('keywords', []) or [])
                    if _clean_text(keyword) not in set(_clean_text(term) for term in (blocked_terms or []))
                ]
                themes.append(_normalize_theme_record({
                    'name': topic.get('name'),
                    'keywords': topic_keywords or topic.get('keywords', []),
                    'frequency': topic.get('segment_count', min_frequency),
                    'confidence': topic.get('confidence', 0.8),
                }, index, min_frequency=min_frequency, blocked_terms=blocked_terms))
            if themes:
                return themes
    except Exception as exc:
        logging.debug(f"Semantic topic fallback unavailable, using TF-IDF clustering: {exc}")
    
    try:
        # Use TF-IDF for feature extraction
        vectorizer = TfidfVectorizer(
            max_features=100,
            stop_words=list(CUSTOM_STOPWORDS),
            ngram_range=(1, 2),
            min_df=1,
            max_df=0.85,
            token_pattern=r'(?u)\b[a-z][a-z0-9-]{2,}\b'
        )
        
        tfidf_matrix = vectorizer.fit_transform(texts)
        feature_names = vectorizer.get_feature_names_out()
        
        if len(feature_names) < 3:
            return []
        
        # Determine optimal clusters
        n_clusters = min(num_themes, max(2, len(texts) // 3), tfidf_matrix.shape[1])
        n_clusters = max(1, n_clusters)
        
        # Apply K-Means clustering
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=5, max_iter=200)
        labels = kmeans.fit_predict(tfidf_matrix)
        
        # Extract top keywords per cluster as themes
        themes = []
        order_centroids = kmeans.cluster_centers_.argsort()[:, ::-1]
        
        for cluster_id in range(n_clusters):
            # Get top keywords for this cluster
            cluster_indices = np.where(labels == cluster_id)[0]
            if len(cluster_indices) == 0:
                continue
            
            # Get top keywords from centroid
            top_keywords = []
            for idx in order_centroids[cluster_id, :8]:
                if idx < len(feature_names):
                    keyword = str(feature_names[idx])
                    if len(keyword) >= 3 and keyword not in CUSTOM_STOPWORDS:
                        top_keywords.append(keyword)
                if len(top_keywords) >= 4:
                    break
            
            if not top_keywords:
                continue
            
            # Generate a short executive-level theme name from the top keywords.
            theme_name = build_topic_name(top_keywords, blocked_terms=blocked_terms) if top_keywords else "General"
            
            # Calculate frequency (how many segments belong to this cluster)
            frequency = len(cluster_indices)
            
            themes.append(_normalize_theme_record({
                'name': theme_name,
                'keywords': top_keywords[:4],
                'frequency': frequency,
                'confidence': min(0.95, 0.55 + (frequency / max(1, len(texts))))
            }, cluster_id, min_frequency=min_frequency, blocked_terms=blocked_terms))
        
        # Sort by frequency
        themes = sorted(themes, key=lambda x: x['frequency'], reverse=True)
        return themes[:num_themes]
        
    except Exception as e:
        logging.warning(f"Fallback theme extraction failed: {e}")
        return []


def _condense_transcript_for_themes(texts, max_words=1000):
    """
    Condense a large transcript into 'Key Discussion Points' to reduce noise
    before theme extraction.
    """
    from .summarizer import summarize_text
    
    combined_text = "\n".join(texts)
    if len(combined_text.split()) <= max_words:
        return texts
        
    logging.info(f"Condensing transcript ({len(combined_text.split())} words) for theme extraction...")
    
    # We use a special instruction to keep discussion points rather than a narrative summary
    condense_instruction = """
    Extract only the core discussion points and decisions from the following transcript.
    Remove all filler words, greetings, and technical noise.
    Keep the key themes intact.
    Return a bulleted list of discussion points.
    """
    
    try:
        condensed = summarize_text(combined_text, max_length=1500)
        if condensed:
            # Split back into small 'pseudo-segments' for theme extraction
            return [line.strip() for line in condensed.split('\n') if line.strip()]
    except Exception as e:
        logging.warning(f"Condensation failed, using raw segments: {e}")
        
    return texts


def extract_dynamic_themes(meeting_id=None, min_frequency=1, num_themes=5, texts_override=None, force_refresh=False, year=None):
    """
    Extract themes dynamically from meeting segments or transcripts using Gemini AI.
    Results are cached to ensure consistency across multiple API calls.
    Falls back to sklearn-based clustering when API is unavailable.
    
    Args:
        meeting_id: Optional meeting ID to extract themes for
        min_frequency: Minimum frequency for a theme to be considered
        num_themes: Number of themes to extract
        texts_override: Optional direct list of texts
        force_refresh: Force re-extraction even if cached
        year: Optional year to scope cache
    
    Returns:
        List of extracted themes with keywords and frequency
    """
    # Check cache first (unless forcing refresh)
    if texts_override is not None:
        import hashlib
        # Create a stable fingerprint of texts_override
        text_sample = "".join(texts_override[:50]) + f"__len__{len(texts_override)}"
        texts_hash = hashlib.md5(text_sample.encode('utf-8')).hexdigest()[:16]
        cache_key = f"themes:v{THEMES_CACHE_VERSION}:override:{texts_hash}:year{year or 'none'}:n{num_themes}"
    else:
        cache_key = _get_cache_key(meeting_id=meeting_id, num_themes=num_themes, year=year)

    if not force_refresh:
        cached_themes = _get_cached_themes(cache_key, ttl=3600)  # 1 hour cache
        if cached_themes:
            return cached_themes
    if texts_override is not None:
        raw_texts = [str(t or '').strip() for t in texts_override if str(t or '').strip()]
        texts = [_clean_text(t) for t in raw_texts if _clean_text(t)]
        if not texts:
            return []
        conn = None
    else:
        conn = get_db()
        cursor = conn.cursor()

        if meeting_id:
            cursor.execute(
                'SELECT segment_id, original_text FROM Segments WHERE meeting_id = ? ORDER BY segment_id',
                (meeting_id,)
            )
        else:
            cursor.execute(
                'SELECT segment_id, original_text FROM Segments ORDER BY segment_id LIMIT 100',
                ()
            )

        segments = cursor.fetchall()

        if not segments:
            conn.close()
            return []

        raw_texts = [str(row['original_text'] or '').strip() for row in segments if str(row['original_text'] or '').strip()]
        texts = [_clean_text(row['original_text']) for row in segments if _clean_text(row['original_text'])]
        if conn:
            conn.close()

    raw_texts = [str(t or '').strip() for t in texts if t and len(str(t or '').strip()) > 10]
    if not raw_texts:
        return []

    # Reliability Improvement: Condense transcript if too long to reduce noise
    # This ensures OpenAI focuses on 'Substance' rather than 'Filler'
    if len(raw_texts) > 25:
        texts = _condense_transcript_for_themes(raw_texts)
    else:
        texts = raw_texts

    blocked_terms = _collect_blocked_terms(raw_texts)

    # Primary: OpenAI (Human-secretary style narrative)
    openai_key = os.environ.get("OPENAI_API_KEY")
    
    # If no OpenAI key is available
    if not openai_key:
        logging.warning("No OpenAI API key set. Using BERTopic (BERT + HDBSCAN) fallback.")
        fallback_themes = _extract_fallback_themes(texts, num_themes=num_themes, min_frequency=min_frequency, blocked_terms=blocked_terms)
        if fallback_themes:
            _set_cached_themes(cache_key, fallback_themes, ttl=3600)
        return fallback_themes

    combined_text = " ".join(texts)
    # Truncate if insanely large to fit comfortably in standard input context
    combined_text = combined_text[:300000]

    system_prompt = f"""
You are an expert qualitative data analyst for meeting minutes.
Analyze only the provided transcript text and extract exactly {num_themes} high-value themes that a manager would actually use.
Prefer concrete business concepts, recurring issues, decisions, risks, initiatives, and constraints.
Merge overlapping phrases into one meaningful theme label.
Avoid generic labels such as "General Discussion", "Updates", "Planning", "Review", or "Operations" unless the content truly centers on them.

Return ONLY valid JSON with this exact shape:
{{
    "themes": [
        {{
            "name": "Budget Constraints",
            "keywords": ["budget", "cost", "funding", "spending"],
            "frequency": 5,
            "confidence": 0.91
        }}
    ]
}}

Rules:
- The top-level value must be a JSON object with a single key named "themes".
- "themes" must contain exactly {num_themes} objects.
- Each theme name must be a concise 2 to 4 word executive-style label grounded in the meeting text.
- Each keywords array must contain exactly 4 short lowercase keywords or phrases that actually appear in or closely reflect the text.
- "frequency" must be an integer between {min_frequency} and 20.
- "confidence" must be a number between 0.5 and 1.0.
- DO NOT use generic titles, names, or uninformative labels such as "The", "Meetings", "Mr Chairman", "Lecturer", or "Discussion".
- DO NOT use person names or organizational titles as theme names.
- Do not include markdown, code fences, or commentary.
"""

    try:
        from openai import OpenAI
        import json
        
        client = OpenAI(api_key=openai_key)
        # Prioritize gpt-4o-mini as it is widely available, fast, and high quality.
        # Fall back to gpt-3.5-turbo if the account has no GPT-4 access at all.
        candidate_models = ['gpt-4o-mini', 'gpt-4o', 'gpt-4-turbo-preview', 'gpt-3.5-turbo-0125']

        response = None
        last_error = None
        for model_name in candidate_models:
            try:
                env_temp = os.environ.get('AI_TEMPERATURE', '').strip()
                try:
                    final_temp = float(env_temp) if env_temp else 0.15
                except ValueError:
                    final_temp = 0.15

                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": "Here is the raw meeting text:\n" + combined_text}
                    ],
                    response_format={"type": "json_object"},
                    temperature=final_temp,
                    max_tokens=1600,
                )
                last_error = None
                break
            except Exception as exc:
                last_error = str(exc)
                if any(code in last_error for code in ('400', '401', '403')):
                    break
                continue
        if response is None:
            raise RuntimeError(last_error or 'Theme generation model unavailable')
        
        raw_output = response.choices[0].message.content.strip()
        
        # Step 1: Clean up any potential markdown backticks returned by the LLM
        if raw_output.startswith("```json"):
            raw_output = raw_output[7:].strip()
            if raw_output.endswith("```"):
                raw_output = raw_output[:-3].strip()
        elif raw_output.startswith("```"):
            raw_output = raw_output[3:].strip()
            if raw_output.endswith("```"):
                raw_output = raw_output[:-3].strip()
        
        # Step 2: Try exact JSON parse first
        try:
            parsed_themes = json.loads(raw_output)
        except json.JSONDecodeError as json_err:
            # Step 3: Try to repair malformed JSON
            repaired = _repair_json(raw_output)
            if repaired:
                parsed_themes = repaired
            else:
                # Step 4: Try salvaging complete theme objects from a truncated output.
                salvaged = _extract_themes_from_partial_output(raw_output, max_items=num_themes)
                if salvaged:
                    logging.warning(
                        "OpenAI returned malformed JSON; salvaged %s theme objects. "
                        "JSON Error: %s",
                        len(salvaged),
                        json_err,
                    )
                    parsed_themes = salvaged
                else:
                    # Step 5: Fall back without breaking API response shape.
                    logging.warning(
                        "OpenAI dynamic theme extraction parse failure. "
                        "JSON Error: %s. Raw output (first 500 chars): %s",
                        json_err,
                        raw_output[:500],
                    )
                    fallback_themes = _extract_fallback_themes(texts, num_themes=num_themes, min_frequency=min_frequency, blocked_terms=blocked_terms)
                    if fallback_themes:
                        _set_cached_themes(cache_key, fallback_themes, ttl=3600)
                    return fallback_themes or []
        
        if isinstance(parsed_themes, dict):
            parsed_themes = parsed_themes.get('themes', [])

        # Validate we got a list
        if not isinstance(parsed_themes, list):
            logging.error(f"OpenAI dynamic theme extraction error: Expected list, got {type(parsed_themes)}. Raw: {raw_output[:200]}")
            fallback_themes = _extract_fallback_themes(texts, num_themes=num_themes, min_frequency=min_frequency, blocked_terms=blocked_terms)
            if fallback_themes:
                _set_cached_themes(cache_key, fallback_themes, ttl=3600)
            return fallback_themes
        
        themes = []
        for i, t in enumerate(parsed_themes):
            theme_record = _normalize_theme_record(t, i, min_frequency=min_frequency, blocked_terms=blocked_terms)
            themes.append(theme_record)
        
        # Merge themes with the same name (deduplication)
        merged_map = {} # name -> merged_theme
        for t in themes:
            name = t['name']
            if name in merged_map:
                existing = merged_map[name]
                # Merge keywords (unique set)
                all_k = set(existing.get('keywords', [])) | set(t.get('keywords', []))
                existing['keywords'] = list(all_k)[:8]
                existing['frequency'] += t.get('frequency', 0)
                existing['confidence'] = max(existing['confidence'], t['confidence'])
            else:
                merged_map[name] = t
        
        final_themes = sorted(merged_map.values(), key=lambda x: x['frequency'], reverse=True)
        final_themes = final_themes[:num_themes]
        
        # Add confidence threshold flags and verification status
        reviewed_themes = []
        for theme in final_themes:
            confidence = float(theme.get('confidence', 0.75))
            theme_name = theme.get('name')
            theme['meeting_id'] = meeting_id
            
            # Check if this theme was already verified in the DB for this meeting
            is_verified = 0
            if meeting_id:
                try:
                    res = execute_safe_query(
                        '''
                        SELECT a.is_verified 
                        FROM Analysis a
                        JOIN Themes t ON a.theme_id = t.theme_id
                        JOIN Segments s ON a.segment_id = s.segment_id
                        WHERE t.theme_name = ? AND s.meeting_id = ?
                        LIMIT 1
                        ''',
                        (theme_name, meeting_id)
                    )
                    if res:
                        is_verified = int(res[0].get('is_verified', 0))
                except Exception:
                    pass
            
            theme['is_verified'] = bool(is_verified)
            
            if is_verified:
                theme['trusted'] = True
                theme['review_required'] = False
                theme['review_severity'] = None
            elif confidence < 0.70: # Stricter threshold for reliability
                theme['review_required'] = True
                theme['review_reason'] = 'Low confidence - requires human validation'
                theme['review_severity'] = 'high'
                theme['trusted'] = False
            elif confidence >= 0.85:
                theme['trusted'] = True
                theme['review_required'] = False
                theme['review_severity'] = None
            else:
                theme['requires_validation'] = True
                theme['validation_note'] = 'Medium confidence - recommended for review'
                theme['review_severity'] = 'medium'
                theme['trusted'] = False
                
            reviewed_themes.append(theme)
        
        # Cache the result for consistency across API calls
        _set_cached_themes(cache_key, reviewed_themes, ttl=3600)
        return reviewed_themes
    
    except Exception as e:
        error_msg = str(e)
        # Check for quota errors and fall back to sklearn method
        if '429' in error_msg or 'quota' in error_msg.lower() or 'insufficient_quota' in error_msg:
            logging.warning(f"OpenAI API quota exceeded ({e}). Using BERTopic fallback.")
            fallback_themes = _extract_fallback_themes(texts, num_themes=num_themes, min_frequency=min_frequency, blocked_terms=blocked_terms)
            if fallback_themes:
                _set_cached_themes(cache_key, fallback_themes, ttl=3600)
            return fallback_themes
        
        logging.error(f"OpenAI dynamic theme extraction error: {e}")
        fallback_themes = _extract_fallback_themes(texts, num_themes=num_themes, min_frequency=min_frequency, blocked_terms=blocked_terms)
        if fallback_themes:
            _set_cached_themes(cache_key, fallback_themes, ttl=3600)
        return fallback_themes


def get_theme_trends_by_year(year=None, theme_name=None):
    """
    Get theme trends and statistics by year.
    
    Args:
        year: Optional year to filter (defaults to current year)
    
    Returns:
        Dictionary with theme statistics and trends
    """
    if year is None:
        year = datetime.datetime.now().year
    
    conn = get_db()
    cursor = conn.cursor()

    # Canonical meeting counts (distinct meetings), grouped by month.
    cursor.execute(
        '''SELECT
               strftime('%Y-%m', COALESCE(meeting_date, created_at)) AS month_key,
               COUNT(DISTINCT meeting_id) AS meeting_count
           FROM Meetings
           WHERE strftime('%Y', COALESCE(meeting_date, created_at)) = ?
           GROUP BY strftime('%Y-%m', COALESCE(meeting_date, created_at))
           ORDER BY month_key''',
        (str(year),)
    )
    meeting_rows = cursor.fetchall()
    monthly_meeting_trends = {
        str(row['month_key'] or ''): int(row['meeting_count'] or 0)
        for row in meeting_rows
        if row['month_key']
    }
    total_meetings = int(sum(monthly_meeting_trends.values()))
    
    # Get segments from specified year for theme extraction.
    cursor.execute(
        '''SELECT meeting_id, original_text, created_at
           FROM Segments
           WHERE strftime('%Y', created_at) = ?
           ORDER BY created_at''',
        (str(year),)
    )
    
    segments = cursor.fetchall()
    
    if not segments:
        conn.close()
        return {
            'year': year,
            'themes': [],
            'monthly_trends': dict(sorted(monthly_meeting_trends.items())),
            'monthly_theme_trends': {},
            'total_meetings': total_meetings,
            'total_segments': 0,
            'unique_themes': 0
        }
    
    texts = [_clean_text(row['original_text']) for row in segments if _clean_text(row['original_text'])]

    # Extract themes strictly from this year's segment corpus.
    themes = extract_dynamic_themes(num_themes=8, texts_override=texts, year=year)
    
    # Build month-by-month unique theme presence count.
    selected_themes = []
    if theme_name:
        target = str(theme_name or '').strip().lower()
        matched_theme = next((theme for theme in themes if str(theme.get('name') or '').strip().lower() == target), None)
        if matched_theme is None:
            matched_theme = next((theme for theme in themes if target and target in str(theme.get('name') or '').strip().lower()), None)

        if matched_theme:
            selected_themes = [matched_theme]
        else:
            # Fallback: create one synthetic theme from selected label tokens.
            fallback_keywords = [
                token for token in re.findall(r'[a-z0-9-]+', target)
                if token and token not in CUSTOM_STOPWORDS and len(token) >= 3
            ]
            selected_themes = [{'name': str(theme_name), 'keywords': fallback_keywords}]
    else:
        selected_themes = themes

    monthly_theme_sets = defaultdict(set)
    for row in segments:
        row_data = dict(row)
        created_at = str(row_data.get('created_at') or '')
        if not created_at:
            continue

        month_key = created_at[:7]
        text = _clean_text(row_data.get('original_text') or '')
        if not text or not selected_themes:
            continue

        token_set = set(text.split())
        for theme in selected_themes:
            theme_label = str(theme.get('name') or '').strip()
            keywords = [str(keyword).strip().lower() for keyword in (theme.get('keywords') or []) if str(keyword).strip()]
            if not keywords:
                continue

            for keyword in keywords:
                if (' ' in keyword and keyword in text) or (keyword in token_set):
                    if theme_label:
                        monthly_theme_sets[month_key].add(theme_label)
                    break

    monthly_theme_trends = {month: len(theme_names) for month, theme_names in monthly_theme_sets.items()}
    
    conn.close()
    
    return {
        'year': year,
        'theme': theme_name,
        'themes': themes,
        'monthly_trends': dict(sorted(monthly_meeting_trends.items())),
        'monthly_theme_trends': dict(sorted(monthly_theme_trends.items())),
        'selected_theme_pool': len(selected_themes),
        'total_meetings': total_meetings,
        'total_segments': len(segments),
        'unique_themes': len(themes)
    }


def get_all_themes_from_meetings():
    """
    Get all unique themes from all meetings across all years.
    Used for historical theme dropdowns and settings.
    
    Returns:
        List of theme dictionaries with stable theme_id
    """
    import hashlib
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get all segments across all years (not year-filtered)
    cursor.execute('SELECT segment_id, original_text, meeting_id FROM Segments ORDER BY meeting_id')
    segments = cursor.fetchall()
    
    if not segments:
        conn.close()
        return []
    
    texts = [row['original_text'] for row in segments]
    
    # Extract dynamic themes from entire corpus (all years)
    themes = extract_dynamic_themes(num_themes=10, texts_override=texts)
    
    # Enhance with meeting statistics when we have a usable keyword.
    for theme in themes:
        keywords = [str(keyword).strip() for keyword in (theme.get('keywords') or []) if str(keyword).strip()]
        if not keywords:
            theme['meeting_count'] = int(theme.get('meeting_count') or 0)
            continue

        # Use the first keyword as a lightweight proxy for theme presence.
        cursor.execute(
            '''SELECT COUNT(DISTINCT meeting_id) as meeting_count 
               FROM Segments WHERE LOWER(COALESCE(original_text, '')) LIKE ?''',
            (f"%{keywords[0].lower()}%",)
        )
        result = cursor.fetchone()
        theme['meeting_count'] = result['meeting_count'] if result else 0

    # Deduplicate theme names and keep the strongest live themes first.
    deduped = {}
    for theme in themes:
        normalized_name = str(theme.get('name') or '').strip().lower()
        if not normalized_name:
            continue
        current = deduped.get(normalized_name)
        if current is None or int(theme.get('meeting_count') or 0) > int(current.get('meeting_count') or 0):
            deduped[normalized_name] = theme

    themes = sorted(deduped.values(), key=lambda item: int(item.get('meeting_count') or 0), reverse=True)
    
    # Add stable theme_id based on theme name + keywords hash
    for idx, theme in enumerate(themes):
        name = theme.get('name', '')
        keywords_str = ','.join(str(k) for k in theme.get('keywords', []))
        hash_input = f"{name}|{keywords_str}".encode('utf-8')
        stable_hash = hashlib.md5(hash_input).hexdigest()[:8]
        theme['theme_id'] = f"theme-{stable_hash}"
    
    conn.close()
    return themes  # Return all unique themes for backward compatibility with Settings/Search/ScheduledReports


def get_theme_sentiment_distribution(theme_name=None, year=None):
    """
    Get sentiment distribution for a specific theme or all themes.
    
    Args:
        theme_name: Optional theme name to filter
        year: Optional year to filter
    
    Returns:
        Sentiment distribution data
    """
    conn = get_db()
    cursor = conn.cursor()

    params = []
    where_parts = ['1=1']

    if year:
        where_parts.append('strftime("%Y", COALESCE(seg.created_at, s.created_at)) = ?')
        params.append(str(year))

    normalized_theme = str(theme_name or '').strip().lower()
    if normalized_theme and normalized_theme not in {'all themes', 'all'}:
        tokens = [
            token for token in re.findall(r'[a-z0-9-]+', normalized_theme)
            if token and token not in CUSTOM_STOPWORDS and len(token) >= 3
        ]
        if tokens:
            token_clauses = []
            for token in tokens:
                token_clauses.append('LOWER(COALESCE(seg.original_text, "")) LIKE ?')
                params.append(f'%{token}%')
            where_parts.append(f"({' OR '.join(token_clauses)})")

    query = f'''
        SELECT
            strftime('%Y-%m', COALESCE(seg.created_at, s.created_at)) AS month,
            UPPER(COALESCE(s.sentiment, 'NEUTRAL')) AS sentiment,
            COUNT(*) AS count
        FROM Sentiments s
        JOIN Segments seg ON s.segment_id = seg.segment_id
        WHERE {' AND '.join(where_parts)}
        GROUP BY strftime('%Y-%m', COALESCE(seg.created_at, s.created_at)), UPPER(COALESCE(s.sentiment, 'NEUTRAL'))
        ORDER BY month
    '''

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    monthly_counts = defaultdict(lambda: {'positive': 0, 'neutral': 0, 'negative': 0})
    overall_counts = {'positive': 0, 'neutral': 0, 'negative': 0}

    for row in rows:
        row_data = dict(row)
        month = str(row_data.get('month') or '').strip()
        sentiment_key = str(row_data.get('sentiment') or 'NEUTRAL').strip().lower()
        count = int(row_data.get('count') or 0)

        if sentiment_key not in overall_counts:
            sentiment_key = 'neutral'

        if month:
            monthly_counts[month][sentiment_key] += count
        overall_counts[sentiment_key] += count

    total = sum(overall_counts.values())

    monthly_distribution = {}
    for month, counts in sorted(monthly_counts.items()):
        month_total = sum(counts.values())
        monthly_distribution[month] = {
            'positive': (counts['positive'] / month_total * 100) if month_total else 0,
            'neutral': (counts['neutral'] / month_total * 100) if month_total else 0,
            'negative': (counts['negative'] / month_total * 100) if month_total else 0,
            'total': month_total,
        }

    return {
        'theme': theme_name,
        'year': year,
        'distribution': {
            'positive': (overall_counts['positive'] / total * 100) if total else 0,
            'neutral': (overall_counts['neutral'] / total * 100) if total else 0,
            'negative': (overall_counts['negative'] / total * 100) if total else 0,
        },
        'monthly_distribution': monthly_distribution,
        'total_analyzed': total
    }
