"""
Keyword and Phrase Extraction
Extracts important keywords and phrases from meeting minutes.
Optimized for batch processing and accuracy.
"""
from sklearn.feature_extraction.text import TfidfVectorizer
import logging
from ..models import get_db, execute_safe_query

logger = logging.getLogger(__name__)

def extract_keywords(meeting_id=None, max_keywords=50, ngram_range=(1, 2)):
    """
    Extract keywords using TF-IDF with optimization.
    
    Args:
        meeting_id: Optional meeting ID
        max_keywords: Maximum keyword features to extract
        ngram_range: N-gram range (1-grams, 1-2 grams, etc.)
    
    Returns:
        List of extracted keywords
    """
    try:
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
        conn.close()
        
        if not segments:
            return []
        
        texts = [row['original_text'] for row in segments]
        segment_ids = [row['segment_id'] for row in segments]

        # For tiny corpora (especially 1 document), fractional max_df can become < min_df.
        doc_count = len(texts)
        max_df_value = 1.0 if doc_count <= 1 else 0.95
        
        # Batch TF-IDF computation
        vectorizer = TfidfVectorizer(
            max_features=max_keywords,
            stop_words='english',
            ngram_range=ngram_range,
            min_df=1,
            max_df=max_df_value  # Avoid max_df/min_df conflicts on very small corpora
        )
        tfidf_matrix = vectorizer.fit_transform(texts)
        feature_names = vectorizer.get_feature_names_out()
        
        all_keywords = []
        insert_params = []
        
        # Extract keywords for each segment
        for i, segment_id in enumerate(segment_ids):
            tfidf_vector = tfidf_matrix[i].toarray().flatten()
            
            # Get top keywords by TF-IDF score
            top_indices = tfidf_vector.argsort()[-20:][::-1]  # Get top 20
            keywords = [
                feature_names[idx] 
                for idx in top_indices 
                if idx < len(feature_names) and tfidf_vector[idx] > 0.01  # Only significant keywords
            ]
            
            if keywords:
                keywords_str = ','.join(keywords[:15])  # Store top 15
                insert_params.append((segment_id, keywords_str))
                
                all_keywords.append({
                    'segment_id': segment_id,
                    'keywords': keywords[:10]  # Return top 10
                })
        
        if insert_params:
            conn = get_db()
            cursor = conn.cursor()
            try:
                cursor.executemany(
                    '''
                    INSERT OR REPLACE INTO Keywords 
                    (segment_id, keywords, created_at) 
                    VALUES (?, ?, datetime('now'))
                    ''',
                    insert_params
                )
                conn.commit()
            except Exception as write_err:
                conn.rollback()
                logger.error(f"Failed to commit batch keywords: {write_err}")
                raise
            finally:
                conn.close()
                
        logger.info(f"Extracted keywords for {len(all_keywords)} segments")
        return all_keywords
        
    except Exception as e:
        logger.error(f"Keyword extraction error: {e}", exc_info=True)
        raise

def get_aggregated_keywords(meeting_id=None, top_n=20):
    """
    Get aggregated keywords across all segments with frequency counts.
    
    Args:
        meeting_id: Optional meeting ID filter
        top_n: Number of top keywords to return
    
    Returns:
        Dict with aggregated keywords and frequency statistics
    """
    try:
        if meeting_id:
            query = '''
                SELECT keywords FROM Keywords
                WHERE segment_id IN (
                    SELECT segment_id FROM Segments WHERE meeting_id = ?
                )
            '''
            results = execute_safe_query(query, (meeting_id,), fetch=True)
        else:
            query = 'SELECT keywords FROM Keywords LIMIT 500'
            results = execute_safe_query(query, (), fetch=True)
        
        # Aggregate and count keywords
        keyword_counts = {}
        for row in results:
            if row and row.get('keywords'):
                # Split comma-separated keywords
                keywords = [k.strip() for k in row['keywords'].split(',') if k.strip()]
                for keyword in keywords:
                    keyword_counts[keyword] = keyword_counts.get(keyword, 0) + 1
        
        # Sort by frequency
        top_keywords = sorted(
            keyword_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:top_n]
        
        return {
            'keywords': [{'keyword': k, 'frequency': f} for k, f in top_keywords],
            'total_unique': len(keyword_counts),
            'total_mentions': sum(keyword_counts.values())
        }
    except Exception as e:
        logger.error(f"Get aggregated keywords error: {e}", exc_info=True)
        return {
            'keywords': [],
            'total_unique': 0,
            'total_mentions': 0
        }