"""
Trend Analysis Feature
Detects and analyzes how meeting topics and themes evolve over time.
Identifies emerging issues, recurring problems, and strategic shifts.
"""
import logging
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
import json
import time
import os
import re

# Optional Redis-backed cache for multi-worker persistence. Falls back to in-memory.
_redis_client = None
logger = logging.getLogger(__name__)
try:
    import redis as _redis
    _redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    try:
        _redis_client = _redis.from_url(_redis_url, decode_responses=True)
        # test connection
        _redis_client.ping()
        logger.info(f"Using Redis cache at {_redis_url}")
    except Exception as redis_error:
        logger.warning(f"Redis not available at {_redis_url}: {redis_error}. Falling back to in-memory cache.")
        _redis_client = None
except Exception:
    _redis_client = None

from ..models import get_db, DB_PATH

logger = logging.getLogger(__name__)

# Create a cache directory for individual trend results to avoid O(N) disk writes
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.trends_cache_dir')
os.makedirs(CACHE_DIR, exist_ok=True)

def _get_cache_path(key):
    # Ensure key is a safe filename
    safe_key = re.sub(r'[^a-zA-Z0-9_-]', '_', str(key))
    return os.path.join(CACHE_DIR, f"{safe_key}.json")

_TRENDS_CACHE = {} # Memory cache (L1)

def _cache_get(key, ttl=3600):
    # 1. Redis (L0)
    if _redis_client:
        try:
            raw = _redis_client.get(key)
            if raw: return json.loads(raw)
        except Exception: pass

    # 2. In-memory (L1)
    entry = _TRENDS_CACHE.get(key)
    if entry:
        ts, value = entry
        if time.time() - ts < ttl:
            return value

    # 3. Disk (L2 - individual files)
    path = _get_cache_path(key)
    if os.path.exists(path):
        try:
            mtime = os.path.getmtime(path)
            if time.time() - mtime < ttl:
                with open(path, 'r') as f:
                    value = json.load(f)
                    _TRENDS_CACHE[key] = (mtime, value)
                    return value
            else:
                os.remove(path)
        except Exception: pass
    return None

def _cache_set(key, value, ttl=3600):
    if _redis_client:
        try:
            _redis_client.set(key, json.dumps(value), ex=ttl)
            return
        except Exception: pass
    
    # In-memory
    _TRENDS_CACHE[key] = (time.time(), value)
    
    # Disk (write individual file immediately for persistence)
    path = _get_cache_path(key)
    try:
        with open(path, 'w') as f:
            json.dump(value, f)
    except Exception: pass

def _cache_delete(key):
    if _redis_client:
        try: _redis_client.delete(key)
        except Exception: pass
    _TRENDS_CACHE.pop(key, None)
    path = _get_cache_path(key)
    if os.path.exists(path):
        try: os.remove(path)
        except Exception: pass

# Bump this when theme extraction logic changes to invalidate stale cached results
_THEME_FREQ_CACHE_VERSION = 3




def clear_trend_caches(year=None):
    """Clear cached trend, frequency, sentiment, and anomaly results."""
    prefixes = []
    if year is not None:
        prefixes.extend([
            f'theme_trends:{year}',
            f'theme_freq:v{_THEME_FREQ_CACHE_VERSION}:year{year}:',
            f'sentiment_trends:{year}',
        ])
    else:
        prefixes.extend([
            'theme_trends:',
            f'theme_freq:v{_THEME_FREQ_CACHE_VERSION}:',
            'sentiment_trends:',
        ])

    keys = list(_TRENDS_CACHE.keys())
    for key in keys:
        if any(str(key).startswith(prefix) for prefix in prefixes):
            _cache_delete(key)

    if _redis_client:
        try:
            for prefix in prefixes:
                for key in _redis_client.keys(f'{prefix}*'):
                    _redis_client.delete(key)
        except Exception:
            pass


def _get_year_filter_sql(year_value):
    """
    Generate SQL date range for a given year that uses indices.
    Instead of strftime('%Y', col) = ?, use direct comparison.
    Returns (sql_fragment, [param1, param2])
    """
    year_str = str(year_value)
    year_start = f"{year_str}-01-01"
    year_end = f"{int(year_str) + 1}-01-01"
    # Use >= and < to get all records in the year, and let index optimize it
    return "(col >= ? AND col < ?)", [year_start, year_end]


def analyze_theme_trends(year=None, theme=None, months_back=12, force_refresh=False):
    """
    Analyze trend patterns for themes over time.
    
    Args:
        year: Specific year to analyze (defaults to current)
        theme: Specific theme to focus on (filters data to show only meetings/topics matching this theme)
        months_back: How many months to analyze
    
    Returns:
        Dictionary with trend analysis and insights
    """
    if year is None:
        year = datetime.now().year
    
# Clean theme parameter for filtering
    theme_filter = None
    if theme and str(theme).strip():
        theme_filter = str(theme).strip().lower()
    
    cache_key = f"theme_trends:{year}:{theme_filter or ''}:{months_back}"
    if force_refresh:
        _cache_delete(cache_key)

    cached = _cache_get(cache_key, ttl=3600)
    if cached is not None:
        logger.debug(f"Returning cached theme trends for {cache_key}")
        return cached

    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Prefer meeting_date, then meeting created_at, then segment created_at.
        date_expr = "COALESCE(NULLIF(TRIM(m.meeting_date), ''), m.created_at, s.created_at)"
        selected_year = str(year)
        sorted_months = [f"{selected_year}-{m:02d}" for m in range(1, 13)]

        # Monthly meeting frequency for selected year.
        meeting_query = '''
        SELECT
            strftime('%Y-%m', ''' + date_expr + ''') as month,
            COUNT(DISTINCT COALESCE(m.meeting_id, s.meeting_id)) as count
        FROM Segments s
        LEFT JOIN Meetings m ON m.meeting_id = s.meeting_id
        WHERE strftime('%Y', ''' + date_expr + ''') = ?
        GROUP BY strftime('%Y-%m', ''' + date_expr + ''')
        ORDER BY month
        '''
        cursor.execute(meeting_query, (selected_year,))
        monthly_meetings = {month: 0 for month in sorted_months}
        for row in cursor.fetchall():
            if row['month'] in monthly_meetings:
                monthly_meetings[row['month']] = int(row['count'] or 0)

        # Monthly selected-theme mention counts (separate line on chart).
        monthly_theme_mentions = {month: 0 for month in sorted_months}
        if theme_filter:
            # Improve matching by splitting the theme into tokens and matching any token.
            import re
            tokens = [t for t in re.split(r"\W+", theme_filter) if t]
            if not tokens:
                tokens = [theme_filter]

            like_clauses = ' OR '.join(["LOWER(COALESCE(s.original_text, '')) LIKE ?" for _ in tokens])
            theme_query = f'''
            SELECT
                strftime('%Y-%m', {date_expr}) as month,
                COUNT(*) as count
            FROM Segments s
            LEFT JOIN Meetings m ON m.meeting_id = s.meeting_id
            WHERE strftime('%Y', {date_expr}) = ?
              AND ({like_clauses})
            GROUP BY strftime('%Y-%m', {date_expr})
            ORDER BY month
            '''
            params = [selected_year] + [f"%{t}%" for t in tokens]
            cursor.execute(theme_query, params)
            for row in cursor.fetchall():
                if row['month'] in monthly_theme_mentions:
                    monthly_theme_mentions[row['month']] = int(row['count'] or 0)
            logger.info(f"[TRENDS] Theme monthly counts computed for '{theme_filter}' in {selected_year}")

        # Compute unique themes from Analysis/Topics tables quickly (avoid heavy theme extraction)
        unique_theme_count = 0
        try:
            # Prefer Analysis table (fast indexed counts)
            cursor.execute(
                "SELECT COUNT(DISTINCT theme_id) as cnt FROM Analysis WHERE strftime('%Y', created_at) = ?",
                (str(year),)
            )
            row = cursor.fetchone()
            if row and row['cnt'] is not None:
                unique_theme_count = int(row['cnt'])
            else:
                # Fallback to Topics table
                cursor.execute(
                    "SELECT COUNT(DISTINCT topic_name) as cnt FROM Topics WHERE strftime('%Y', created_at) = ?",
                    (str(year),)
                )
                row2 = cursor.fetchone()
                if row2 and row2['cnt'] is not None:
                    unique_theme_count = int(row2['cnt'])
        except Exception as theme_count_error:
            logger.warning(f"Unable to compute unique themes for {year}: {theme_count_error}")

        # Calculate month-over-month trend
        trends = []
        for i, month in enumerate(sorted_months):
            current_count = monthly_meetings[month]
            if i > 0:
                prev_count = monthly_meetings[sorted_months[i-1]]
                growth = ((current_count - prev_count) / prev_count * 100) if prev_count > 0 else 0
            else:
                growth = 0
            trends.append({
                'month': month,
                'meeting_count': current_count,
                'growth_rate': round(growth, 1),
                'trend': 'up' if growth > 5 else 'down' if growth < -5 else 'stable'
            })

        # Calculate statistics  
        counts = [monthly_meetings[m] for m in sorted_months]
        theme_counts = [monthly_theme_mentions[m] for m in sorted_months]
        total_meetings = sum(counts)
        avg_meetings = sum(counts) / len(counts) if counts else 0
        max_meetings = max(counts) if counts else 0
        peak_month = sorted_months[counts.index(max_meetings)] if counts and max_meetings > 0 else None
        logger.info(f"[TRENDS] Stats: total={total_meetings}, avg={avg_meetings:.1f}, months={len(sorted_months)}")

        conn.close()

        result = {
            'monthly_trends': dict(sorted(monthly_meetings.items())),
            'theme_monthly_trends': dict(sorted(monthly_theme_mentions.items())) if theme_filter else {},
            'selected_theme': theme_filter,
            'year': year,
            'period': f"{selected_year}-01 to {selected_year}-12",
            'trends': trends,
            'unique_themes': unique_theme_count,
            'statistics': {
                'total_meetings': total_meetings,
                'average_per_month': round(avg_meetings, 1),
                'theme_total_mentions': sum(theme_counts),
                'peak_month': peak_month,
                'peak_count': max_meetings,
                'lowest_month': sorted_months[counts.index(min(counts))] if counts else None,
                'lowest_count': min(counts) if counts else 0
            },
            'insight': generate_trend_insight(trends, avg_meetings)
        }
        _cache_set(cache_key, result, ttl=3600)
        return result
    except Exception as e:
        logger.error(f"Error analyzing theme trends: {e}")
        conn.close()
        return {
            'year': year,
            'trends': [],
            'unique_themes': 0,
            'error': str(e)
        }


def analyze_theme_frequency(year=None, theme=None, top_n=8):
    """
    Analyze which themes appear most frequently.
    
    Args:
        year: Year to analyze
        theme: Specific theme to filter by (optional)
        top_n: Number of top themes to return
    
    Returns:
        List of themes with frequency and growth
    """
    if year is None:
        year = datetime.now().year
    
    # Clean theme parameter for filtering
    theme_filter = None
    if theme and str(theme).strip():
        theme_filter = str(theme).strip().lower()
    
    # Fast, cache-backed frequency analysis with optimized queries
    cache_key = f"theme_freq:v{_THEME_FREQ_CACHE_VERSION}:{year}:{theme_filter or ''}:{top_n}"
    cached = _cache_get(cache_key, ttl=3600)
    if cached is not None:
        logger.debug(f"Returning cached theme frequency for {cache_key}")
        return cached

    conn = get_db()
    cursor = conn.cursor()

    try:
        from .themes import extract_dynamic_themes, _clean_text

        # Use direct date comparison instead of strftime for index optimization
        year_int = int(year)
        year_start = f"{year_int}-01-01"
        year_end = f"{year_int + 1}-01-01"

        # Scan limit increased since indices now optimize the query
        scan_limit = 10000

        if theme_filter:
            query = f'''
            SELECT
                   s.segment_id,
                   s.original_text,
                   strftime('%Y-%m', s.created_at) as month_key
               FROM Segments s
               WHERE s.created_at >= ?
               AND s.created_at < ?
               AND LOWER(COALESCE(s.original_text, '')) LIKE ?
               ORDER BY s.created_at DESC
               LIMIT {scan_limit}
            '''
            theme_search = f'%{theme_filter}%'
            cursor.execute(query, (year_start, year_end, theme_search))
        else:
            query = f'''
            SELECT
                   s.segment_id,
                   s.original_text,
                   strftime('%Y-%m', s.created_at) as month_key
               FROM Segments s
               WHERE s.created_at >= ?
               AND s.created_at < ?
               ORDER BY s.created_at DESC
               LIMIT {scan_limit}
            '''
            cursor.execute(query, (year_start, year_end))

        segments = cursor.fetchall()
        conn.close()
        
        if not segments:
            return []

        def _text_matches_keyword(text, keyword):
            keyword = str(keyword or '').strip().lower()
            if not keyword:
                return False
            text = str(text or '').lower()
            if ' ' in keyword or '-' in keyword:
                return keyword in text
            return keyword in text.split()

        # 1. Extract themes from segment text
        texts = [_clean_text(row['original_text']) for row in segments if _clean_text(row['original_text'])]
        themes = extract_dynamic_themes(num_themes=top_n, texts_override=texts, year=year)

        # 2. Persist themes and prepare patterns
        conn = get_db()
        cursor = conn.cursor()
        
        theme_patterns = {} # theme_name -> compiled regex
        theme_db_ids = {}
        for theme in themes:
            name = theme['name']
            keywords = theme.get('keywords', [])
            theme_db_ids[name] = _ensure_theme_in_db(cursor, name, keywords)
            
            # Create a regex pattern for faster matching
            patterns = []
            for k in keywords:
                k_clean = str(k).strip().lower()
                if k_clean:
                    # Match whole words or phrases
                    patterns.append(rf'\b{re.escape(k_clean)}\b')
            if patterns:
                theme_patterns[name] = re.compile('|'.join(patterns), re.IGNORECASE)

        # 3. Calculate distribution with optimized matching
        theme_monthly = defaultdict(lambda: defaultdict(int))
        analysis_to_insert = []
        
        for row in segments:
            month = row['month_key']
            seg_id = row['segment_id']
            if not month: continue
            text = str(row['original_text'] or '')

            for theme in themes:
                name = theme['name']
                pattern = theme_patterns.get(name)
                
                if pattern and pattern.search(text):
                    theme_monthly[name][month] += 1
                    t_id = theme_db_ids.get(name)
                    if t_id:
                        analysis_to_insert.append((seg_id, t_id, theme.get('confidence', 0.8), datetime.now().isoformat()))
        
        # Batch insert analysis mappings for performance
        if analysis_to_insert:
            cursor.executemany(
                'INSERT OR IGNORE INTO Analysis (segment_id, theme_id, confidence_score, created_at) VALUES (?, ?, ?, ?)',
                analysis_to_insert
            )
        
        conn.commit()

        # Build result with trend indicators
        result = []
        for theme in themes:
            monthly_counts = sorted(theme_monthly[theme['name']].items())
            total = sum(count for _, count in monthly_counts)

            if monthly_counts:
                first_count = monthly_counts[0][1]
                last_count = monthly_counts[-1][1]
                growth = ((last_count - first_count) / first_count * 100) if first_count > 0 else 0
            else:
                growth = 0

            result.append({
                'theme_id': theme.get('theme_id') or f"theme-{themes.index(theme)}",
                'name': theme['name'],
                'keywords': theme.get('keywords', [])[:5],
                'confidence': float(theme.get('confidence') or 0.0),
                'review_required': bool(theme.get('review_required')),
                'requires_validation': bool(theme.get('requires_validation')),
                'trusted': bool(theme.get('trusted')),
                'total_mentions': total,
                'monthly_distribution': dict(monthly_counts),
                'growth_trend': 'increasing' if growth > 10 else 'decreasing' if growth < -10 else 'stable',
                'growth_rate': round(growth, 1)
            })

        # Sort by mention count, cache and return - only cache non-empty results
        result.sort(key=lambda x: x['total_mentions'], reverse=True)
        conn.close()
        if result:
            _cache_set(cache_key, result, ttl=3600)
        return result

    except Exception as e:
        logger.error(f"Error analyzing theme frequency: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return []

def analyze_sentiment_trends(year=None, force_refresh=False):
    """
    Analyze sentiment trends over time.
    
    Args:
        year: Year to analyze
    
    Returns:
        Sentiment distribution by month
    """
    if year is None:
        year = datetime.now().year
    
    cache_key = f"sentiment_trends:{year}"
    if force_refresh:
        _cache_delete(cache_key)

    cached = _cache_get(cache_key, ttl=3600)
    if cached is not None:
        logger.debug(f"Returning cached sentiment trends for {cache_key}")
        return cached
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Use direct date comparison for index optimization (no strftime in WHERE)
        year_int = int(year)
        year_start = f"{year_int}-01-01"
        year_end = f"{year_int + 1}-01-01"
        
        # Get sentiment data grouped by month using indices
        cursor.execute(
            '''
            SELECT 
                strftime('%Y-%m', created_at) as month,
                sentiment,
                COUNT(*) as count
            FROM Sentiments
            WHERE created_at >= ?
            AND created_at < ?
            GROUP BY strftime('%Y-%m', created_at), sentiment
            ORDER BY month, sentiment
            ''',
            (year_start, year_end)
        )

        sentiment_data = defaultdict(lambda: {'positive': 0, 'negative': 0, 'neutral': 0})
        
        for row in cursor.fetchall():
            month = row['month']
            sentiment = str(row['sentiment']).lower()
            count = row['count']
            
            if sentiment in sentiment_data[month]:
                sentiment_data[month][sentiment] = count
        
        # Calculate statistics
        result = []
        for month in sorted(sentiment_data.keys()):
            data = sentiment_data[month]
            total = sum(data.values())
            
            result.append({
                'month': month,
                'positive': data['positive'],
                'negative': data['negative'],
                'neutral': data['neutral'],
                'total': total,
                'positive_rate': round((data['positive'] / total * 100) if total > 0 else 0, 1)
            })
        
        conn.close()
        _cache_set(cache_key, result, ttl=3600)
        return result
    
    except Exception as e:
        logger.error(f"Error analyzing sentiment trends: {e}")
        conn.close()
        return []


def get_emerging_themes(year=None, sensitivity=0.20):
    """
    Identify newly emerging or rapidly growing themes.
    
    Args:
        year: Year to analyze
        sensitivity: Growth rate threshold (0-1, default 0.2 = 20%)
    
    Returns:
        List of emerging themes with growth indicators
    """
    all_themes = analyze_theme_frequency(year=year, top_n=20)
    
    emerging = []
    for theme in all_themes:
        if theme['growth_rate'] > (sensitivity * 100):
            emerging.append(theme)
    
    # Sort by growth rate
    emerging.sort(key=lambda x: x['growth_rate'], reverse=True)
    return emerging


def detect_theme_anomalies(year=None, sensitivity=2.0):
    """
    Detect anomalous theme spikes that might indicate hallucinations or data quality issues.
    Uses statistical outlier detection (Z-score method) to identify unusual patterns.
    
    Args:
        year: Year to analyze
        sensitivity: Z-score threshold (higher = stricter). Default 2.0 = 95% confidence
                     Typical values: 1.5 (90%), 2.0 (95%), 3.0 (99%)
    
    Returns:
        List of anomalies with context for human review, sorted by severity
    """
    if year is None:
        year = datetime.now().year
    
    conn = get_db()  
    cursor = conn.cursor()
    anomalies = []
    
    try:
        import numpy as np
        
        # Get monthly theme mention counts for statistical analysis
        query = '''
        SELECT
            strftime('%Y-%m', COALESCE(s.created_at, m.created_at)) as month,
            LOWER(COALESCE(a.theme_id, 'unknown')) as theme_name,
            COUNT(*) as mention_count
        FROM Segments s
        LEFT JOIN Meetings m ON m.meeting_id = s.meeting_id
        LEFT JOIN Analysis a ON a.segment_id = s.segment_id
        WHERE strftime('%Y', COALESCE(s.created_at, m.created_at)) = ?
        GROUP BY month, theme_name
        ORDER BY month, theme_name
        '''
        
        cursor.execute(query, (str(year),))
        rows = cursor.fetchall()
        
        # Group by theme to build time series
        theme_series = defaultdict(list)
        for row in rows:
            theme_name = str(row['theme_name'] or 'unknown')
            if theme_name:
                theme_series[theme_name].append({
                    'month': row['month'],
                    'count': int(row['mention_count'])
                })
        
        # Calculate anomalies per theme using Z-score
        for theme_name, monthly_data in theme_series.items():
            if len(monthly_data) < 3:
                continue  # Need at least 3 data points for meaningful statistics
            
            counts = np.array([d['count'] for d in monthly_data])
            months = [d['month'] for d in monthly_data]
            
            # Calculate Z-scores
            mean_count = np.mean(counts)
            std_count = np.std(counts)
            
            if std_count == 0:
                continue  # No variation, no anomalies
            
            for i, (month, count) in enumerate(zip(months, counts)):
                z_score = float(abs((count - mean_count) / std_count))
                
                if z_score > sensitivity:
                    anomalies.append({
                        'theme': theme_name,
                        'month': month,
                        'mention_count': int(count),
                        'expected_baseline': round(float(mean_count), 1),
                        'z_score': round(z_score, 2),
                        'severity': 'critical' if z_score > 3.5 else ('high' if z_score > 3 else 'medium'),
                        'note': f'Unusual spike detected ({count} mentions vs baseline {mean_count:.0f}). Recommend manual review to validate theme assignment.'
                    })
        
        logger.info(f"Detected {len(anomalies)} potential theme anomalies for {year}")
        # Sort by Z-score descending (most anomalous first)
        anomalies_sorted = sorted(anomalies, key=lambda x: x['z_score'], reverse=True)
        return anomalies_sorted
        
    except Exception as e:
        logger.error(f"Error detecting theme anomalies: {e}")
        return []
    finally:
        conn.close()


def get_recurring_issues(year=None, min_frequency=3):
    """
    Identify recurring issues that appear in multiple meetings.
    
    Args:
        year: Year to analyze
        min_frequency: Minimum meetings where issue must appear
    
    Returns:
        List of recurring themes
    """
    if year is None:
        year = datetime.now().year
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        from .themes import extract_dynamic_themes, _clean_text

        def _text_matches_keyword(text, keyword):
            keyword = str(keyword or '').strip().lower()
            if not keyword:
                return False
            text = str(text or '').lower()
            if ' ' in keyword or '-' in keyword:
                return keyword in text
            return keyword in text.split()
        
        # Get segments
        cursor.execute(
            '''
            SELECT meeting_id, original_text
            FROM Segments
            WHERE strftime('%Y', created_at) = ?
            ''',
            (str(year),)
        )
        
        # Group by meeting
        meeting_texts = defaultdict(list)
        for row in cursor.fetchall():
            meeting_id = row['meeting_id']
            text = _clean_text(row['original_text'])
            if text:
                meeting_texts[meeting_id].append(text)
        
        # Extract themes
        all_texts = []
        for texts in meeting_texts.values():
            all_texts.extend(texts)
        
        if not all_texts:
            conn.close()
            return []
        
        themes = extract_dynamic_themes(num_themes=10, texts_override=all_texts, year=year)
        
        # Count meetings where each theme appears
        recurring = []
        for theme in themes:
            keywords = [str(k).strip().lower() for k in (theme.get('keywords', []) or []) if k]
            meeting_count = 0
            
            for meeting_id, texts in meeting_texts.items():
                found_in_meeting = False
                for text in texts:
                    for keyword in keywords:
                        if _text_matches_keyword(text, keyword):
                            meeting_count += 1
                            found_in_meeting = True
                            break
                    if found_in_meeting:
                        break
            
            if meeting_count >= min_frequency:
                recurring.append({
                    'name': theme['name'],
                    'keywords': theme.get('keywords', [])[:5],
                    'meeting_count': meeting_count,
                    'total_meetings': len(meeting_texts),
                    'frequency': round(meeting_count / len(meeting_texts) * 100, 1)
                })
        
        # Sort by frequency
        recurring.sort(key=lambda x: x['meeting_count'], reverse=True)
        conn.close()
        return recurring
    
    except Exception as e:
        logger.error(f"Error finding recurring issues: {e}")
        conn.close()
        return []


def generate_trend_insight(trends, avg_meetings):
    """Generate human-readable insight from trend data."""
    if not trends:
        return "No trend data available."
    
    up_count = sum(1 for t in trends if t['trend'] == 'up')
    down_count = sum(1 for t in trends if t['trend'] == 'down')
    
    latest = trends[-1]
    
    if up_count > down_count:
        return f"Meetings are increasing. Latest month ({latest['month']}) had {latest['meeting_count']} meetings ({latest['growth_rate']:+.1f}% vs previous)."
    elif down_count > up_count:
        return f"Meetings are decreasing. Latest month ({latest['month']}) had {latest['meeting_count']} meetings ({latest['growth_rate']:+.1f}% vs previous)."
    else:
        return f"Meetings remain stable. Average {avg_meetings:.1f} per month."


def _ensure_theme_in_db(cursor, name, keywords_list):
    """Upsert theme and return its ID."""
    keywords = ",".join(keywords_list) if isinstance(keywords_list, list) else str(keywords_list)
    cursor.execute("SELECT theme_id FROM Themes WHERE LOWER(theme_name) = LOWER(?)", (name,))
    row = cursor.fetchone()
    if row:
        t_id = row["theme_id"]
        cursor.execute("UPDATE Themes SET keywords = ? WHERE theme_id = ?", (keywords, t_id))
        return t_id
    else:
        try:
            cursor.execute("INSERT INTO Themes (theme_name, keywords) VALUES (?, ?)", (name, keywords))
            return cursor.lastrowid
        except Exception:
            # Fallback for race conditions
            cursor.execute("SELECT theme_id FROM Themes WHERE LOWER(theme_name) = LOWER(?)", (name,))
            row = cursor.fetchone()
            return row["theme_id"] if row else None
