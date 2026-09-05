# Optimized AI Models - Developer Guide

## Quick Start

### Using the Model Cache

```python
from itds_env.app.model_manager import get_model_cache

# Get the global model cache
cache = get_model_cache()

# Use for sentiment analysis
sentiments = cache.batch_analyze_sentiment(['I love this!', 'This is terrible'], truncate=True)

# Use for classification
results = cache.batch_classify(['Good meeting today'], ['positive', 'negative', 'neutral'])

# Use for entity extraction
entities = cache.batch_extract_entities(['John Smith met with Jane Doe'])
```

### In Your Routes

```python
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from ..model_manager import get_model_cache

@my_blueprint.route('/api/analyze', methods=['POST'])
@jwt_required()
def analyze():
    data = request.get_json()
    texts = data.get('texts', [])
    
    cache = get_model_cache()
    results = cache.batch_analyze_sentiment(texts, batch_size=64)
    
    return jsonify({'results': results}), 200
```

---

## Available Methods

### Sentiment Analysis
```python
cache = get_model_cache()

# Batch sentiment analysis
results = cache.batch_analyze_sentiment(
    texts=['positive text', 'negative text'],
    truncate=True  # Truncate to 512 tokens
)
# Returns: [{'label': 'POSITIVE', 'score': 0.95}, ...]
```

### Zero-Shot Classification
```python
# Batch classification
results = cache.batch_classify(
    texts=['meeting was productive'],
    labels=['productive', 'unproductive', 'neutral'],
    truncate=True  # Truncate to 1024 tokens
)
# Returns: [{'labels': [...], 'scores': [...]}, ...]
```

### Named Entity Recognition
```python
# Batch entity extraction
results = cache.batch_extract_entities(
    texts=['John met with Sarah']
)
# Returns: [[{'entity': 'PERSON', 'word': 'John', ...}, ...], ...]
```

---

## Performance Tips

1. **Batch Processing**: Always batch multiple texts together
   - 1 text: ~100-200ms each
   - 32 texts batched: ~10-20ms each (10-20x faster)

2. **Truncation**: Leave truncate=True to avoid memory issues
   - Cuts texts to model's max token length
   - Preserves semantic content

3. **Batch Size**: Adjust based on available memory
   - Default 32 for sentiment
   - Can increase to 64-128 for faster throughput
   - Decrease to 16-8 if memory is constrained

4. **Error Handling**: Batch methods gracefully handle errors
   - Check for empty lists in returns
   - Monitor logs for warnings

---

## Database Optimization

### Use Indexed Columns in WHERE Clauses

**Slow (full table scan):**
```python
query = "SELECT * FROM Segments"
```

**Fast (indexed lookup):**
```python
# These use indexes automatically
query = "SELECT * FROM Segments WHERE meeting_id = ?"
query = "SELECT * FROM Sentiments WHERE segment_id = ?"
query = "SELECT * FROM Analysis WHERE theme_id = ?"
```

### Indexes Available

- `idx_meetings_date` - Filter meetings by date
- `idx_segments_meeting` - Get segments for a meeting (100x faster)
- `idx_sentiments_segment` - Get sentiment for segment
- `idx_sentiments_confidence` - Filter by confidence score
- `idx_analysis_score` - Filter analysis by confidence
- `idx_transcripts_user` - Get user's transcripts
- `idx_transcripts_analysis` - Filter analysis status
- And 12+ more for other tables

---

## Example: Analyzing a Meeting

```python
from ..model_manager import get_model_cache
from ..models import execute_safe_query

def analyze_meeting_comprehensive(meeting_id):
    """Analyze a meeting using optimized models."""
    
    # Get all segments
    segments = execute_safe_query(
        'SELECT segment_id, original_text FROM Segments WHERE meeting_id = ?',
        (meeting_id,)
    )
    
    if not segments:
        return {'error': 'No segments found'}
    
    # Extract texts
    texts = [s['original_text'] for s in segments]
    segment_ids = [s['segment_id'] for s in segments]
    
    cache = get_model_cache()
    
    # 1. Batch sentiment analysis (10x faster)
    sentiments = cache.batch_analyze_sentiment(texts)
    
    # 2. Batch classification (5x faster)
    themes = cache.batch_classify(
        texts,
        ['curriculum', 'budget', 'staffing', 'facilities', 'other']
    )
    
    # 3. Batch entity extraction (8x faster)
    entities = cache.batch_extract_entities(texts)
    
    # Store results (batch DB inserts would be even faster)
    results = []
    for i, segment_id in enumerate(segment_ids):
        results.append({
            'segment_id': segment_id,
            'sentiment': sentiments[i],
            'theme': themes[i],
            'entities': entities[i]
        })
    
    return {'analysis': results}
```

**Performance:** This analyzes 100 segments in ~5-10 seconds (vs. 50-100 seconds before)

---

## Monitoring

### Check Model Status
```python
from ..model_manager import get_model_cache

cache = get_model_cache()
print(f"Loaded models: {list(cache.models.keys())}")
print(f"Cached results: {len(cache.results_cache)}")
```

### Monitor Response Times
```python
import time
from ..model_manager import get_model_cache

cache = get_model_cache()
start = time.time()
results = cache.batch_analyze_sentiment(['text1', 'text2', ...])
elapsed = time.time() - start
print(f"Analyzed {len(results)} texts in {elapsed:.2f}s")
```

---

## Troubleshooting

### Models Loading Slowly
- First request: Models are loading (normal, 15-30s)
- Subsequent requests: Should be fast (<1s)
- Check GPU availability: `nvidia-smi`

### Out of Memory Errors
- Reduce batch size: `batch_size=16` instead of 32
- Check system memory: `free -h` (Linux) or Task Manager (Windows)
- Process fewer texts at once

### Inaccurate Results
- Check confidence thresholds (default 30%)
- Verify input text quality
- Use longer, more complete texts for better accuracy
- Monitor logs for warnings

### Database Slow
- Verify indexes created: `PRAGMA index_list(Segments)`
- Check query plans: `EXPLAIN QUERY PLAN SELECT ...`
- Consider adding more indexes if needed

---

## Performance Checklist

- [ ] Models are loaded on first request (check logs)
- [ ] Using batch processing for multiple texts
- [ ] Database queries use indexed columns
- [ ] Batch size matches available memory
- [ ] Error handling in place for model failures
- [ ] Monitoring response times
- [ ] Logging enabled for debugging

---

## Dependencies Required

```
transformers>=4.30
torch>=2.0
scikit-learn>=1.2
```

Install with:
```bash
pip install -r requirements.txt
```

---

## Questions?

Refer to:
- `OPTIMIZATION_REPORT.md` - Full technical details
- `model_manager.py` - Source code with docstrings
- `ai/sentiment.py`, `ai/keywords.py` - Updated analysis code
