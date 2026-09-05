"""
Sentiment Analysis Feature
Analyzes the tone of discussions (positive, negative, neutral).
Optimized for batch processing with model caching.
"""
import logging
from ..models import get_db, execute_safe_query
from ..model_manager import get_model_cache

logger = logging.getLogger(__name__)


def _store_segment_confidence(segment_id, confidence):
    """Store/update a segment-level confidence score in Analysis for reports."""
    try:
        # Keep a single generic (theme_id NULL) confidence row per segment.
        execute_safe_query(
            'DELETE FROM Analysis WHERE segment_id = ? AND theme_id IS NULL',
            (segment_id,),
            fetch=False,
        )
        execute_safe_query(
            '''
                INSERT INTO Analysis (segment_id, theme_id, confidence_score, created_at)
                VALUES (?, NULL, ?, datetime('now'))
            ''',
            (segment_id, float(confidence)),
            fetch=False,
        )
    except Exception as exc:
        logger.warning(f"Could not store analysis confidence for segment {segment_id}: {exc}")

def analyze_sentiment(meeting_id=None, batch_size=50):
    """
    Run sentiment analysis on meeting segments with batch processing.
    
    Args:
        meeting_id: Optional meeting ID to analyze
        batch_size: Number of segments to process at once
    
    Returns:
        List of sentiment analysis results
    """
    cache = get_model_cache()
    batch_size = max(1, min(batch_size, 128))  # Reasonable batch size for memory
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
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
        
        results = []
        delete_analysis_params = []
        insert_analysis_params = []
        insert_sentiment_params = []
        
        # Process segments in batches for efficiency
        for i in range(0, len(segments), batch_size):
            batch = segments[i:i + batch_size]
            segment_ids = [row['segment_id'] for row in batch]
            texts = [row['original_text'] for row in batch]
            
            # Batch sentiment analysis
            batch_results = cache.batch_analyze_sentiment(texts, truncate=True)
            
            for segment_id, sentiment_result in zip(segment_ids, batch_results):
                try:
                    sentiment = sentiment_result.get('label', 'NEUTRAL')
                    confidence = float(sentiment_result.get('score', 0.0))

                    # Collect parameters for batch database operations
                    delete_analysis_params.append((segment_id,))
                    insert_analysis_params.append((segment_id, confidence))
                    
                    # Flag low-confidence sentiments for governance contexts (especially negative)
                    # This improves trust in automated results by flagging uncertain classifications
                    is_low_confidence = False
                    sentiment_note = None
                    if sentiment == 'NEGATIVE' and confidence < 0.7:
                        # Negative sentiment needs high confidence in formal governance contexts
                        is_low_confidence = True
                        sentiment_note = 'Low confidence negative sentiment - recommend LLM review'
                    elif sentiment != 'NEUTRAL' and confidence < 0.6:
                        # Other non-neutral sentiments have slightly lower threshold
                        is_low_confidence = True
                        sentiment_note = 'Medium confidence sentiment - recommend review'
                    
                    # Only store if confidence is reasonable (>30%)
                    if confidence > 0.3:
                        insert_sentiment_params.append((segment_id, sentiment, confidence))
                    
                    results.append({
                        'segment_id': segment_id,
                        'sentiment': sentiment,
                        'confidence': confidence,
                        'requires_review': is_low_confidence,
                        'review_note': sentiment_note
                    })
                except Exception as e:
                    logger.error(f"Error processing sentiment for segment {segment_id}: {e}")
                    continue
        
        # Run all collected database operations in a single transaction
        if results:
            conn = get_db()
            cursor = conn.cursor()
            try:
                if delete_analysis_params:
                    cursor.executemany(
                        'DELETE FROM Analysis WHERE segment_id = ? AND theme_id IS NULL',
                        delete_analysis_params
                    )
                if insert_analysis_params:
                    cursor.executemany(
                        "INSERT INTO Analysis (segment_id, theme_id, confidence_score, created_at) VALUES (?, NULL, ?, datetime('now'))",
                        insert_analysis_params
                    )
                if insert_sentiment_params:
                    cursor.executemany(
                        "INSERT OR REPLACE INTO Sentiments (segment_id, sentiment, confidence, created_at) VALUES (?, ?, ?, datetime('now'))",
                        insert_sentiment_params
                    )
                conn.commit()
            except Exception as write_err:
                conn.rollback()
                logger.error(f"Failed to commit batch sentiment results: {write_err}")
                raise
            finally:
                conn.close()
                
        logger.info(f"Successfully analyzed sentiment for {len(results)} segments")
        return results
        
    except Exception as e:
        logger.error(f"Sentiment analysis error: {e}", exc_info=True)
        raise

def get_sentiment_results(meeting_id=None, limit=100):
    """
    Get sentiment analysis results with aggregation.
    
    Args:
        meeting_id: Optional meeting ID filter
        limit: Max results to return
    
    Returns:
        Dict with sentiments list and summary statistics
    """
    try:
        if meeting_id:
            query = '''
                SELECT s.segment_id, s.original_text, sn.sentiment, sn.confidence
                FROM Segments s
                LEFT JOIN Sentiments sn ON s.segment_id = sn.segment_id
                WHERE s.meeting_id = ?
                ORDER BY s.segment_id
                LIMIT ?
            '''
            results = execute_safe_query(query, (meeting_id, limit), fetch=True)
        else:
            query = '''
                SELECT s.segment_id, s.original_text, sn.sentiment, sn.confidence
                FROM Segments s
                LEFT JOIN Sentiments sn ON s.segment_id = sn.segment_id
                ORDER BY s.segment_id
                LIMIT ?
            '''
            results = execute_safe_query(query, (limit,), fetch=True)
        
        # Build summary statistics
        sentiment_counts = {'POSITIVE': 0, 'NEGATIVE': 0, 'NEUTRAL': 0}
        avg_confidence = 0.0
        sentiments = []
        
        for row in results:
            sentiment = row.get('sentiment', 'NEUTRAL') or 'NEUTRAL'
            confidence = float(row.get('confidence') or 0.0)
            
            if sentiment in sentiment_counts:
                sentiment_counts[sentiment] += 1
                avg_confidence += confidence
            
            sentiments.append({
                'segment_id': row['segment_id'],
                'sentiment': sentiment,
                'confidence': confidence
            })
        
        if sentiments:
            avg_confidence /= len(sentiments)
        
        return {
            'sentiments': sentiments,
            'summary': {
                'counts': sentiment_counts,
                'total': len(sentiments),
                'avg_confidence': round(avg_confidence, 3),
                'positive_ratio': round(sentiment_counts['POSITIVE'] / len(sentiments) if sentiments else 0, 2),
                'negative_ratio': round(sentiment_counts['NEGATIVE'] / len(sentiments) if sentiments else 0, 2)
            }
        }
    except Exception as e:
        logger.error(f"Get sentiment results error: {e}", exc_info=True)
        raise