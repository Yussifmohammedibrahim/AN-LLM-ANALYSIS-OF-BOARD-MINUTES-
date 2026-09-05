# AI Configuration Guide

This document explains the AI and NLP model configuration for the ITDS application.

## Required Environment Variables

### Gemini API Configuration

**`GEMINI_API_KEY`** (Required)
- Used by: Text Simplification, Theme Extraction, Semantic Labeling
- Value: Your Google Gemini API key
- Obtains from: [Google AI Studio](https://aistudio.google.com/app/apikeys)
- If not set: Theme extraction and text simplification will fall back to local models (reduced quality)

### Topic Embedding Model

**`TOPIC_EMBEDDING_MODEL`** (Optional, but recommended)
- Used by: Semantic topic extraction during fallback theme clustering
- Default: `sentence-transformers/all-MiniLM-L6-v2`
- Alternative models:
  - `sentence-transformers/all-MiniLM-L6-v2` (Recommended - fast, ~22MB)
  - `sentence-transformers/all-mpnet-base-v2` (Higher quality, ~430MB)
  - `sentence-transformers/paraphrase-MiniLM-L6-v2`
- If not set: Application uses built-in default, falls back to TF-IDF clustering

### Other Model Variables

**`SENTIMENT_MODEL`** - Sentiment analysis model
- Default: `cardiffnlp/twitter-roberta-base-sentiment-latest`
- Fallback: `distilbert-base-uncased-finetuned-sst-2-english`

**`SUMMARIZER_MODEL`** - Text summarization
- Default: `philschmid/bart-large-cnn-samsum`
- Fallback: `facebook/bart-large-cnn`, `google/pegasus-xsum`

**`ZERO_SHOT_MODEL`** - Zero-shot classification
- Default: `MoritzLaurer/deberta-v3-base-zeroshot-v2.0`
- Fallback: `facebook/bart-large-mnli`, `typeform/distilbert-base-uncased-mnli`

**`ITDS_NER_MODEL`** - Named Entity Recognition
- Default: `dbmdz/bert-large-cased-finetuned-conll03-english`

**`ITDS_QA_MODEL`** - Question Answering
- Default: `distilbert-base-cased-distilled-squad`

**`ITDS_ASR_MODEL`** - Automatic Speech Recognition
- Default: `openai/whisper-tiny.en`

## AI Features Configuration

### Text Simplification

**Endpoint**: `POST /api/ai/simplify`

**Request**:
```json
{
  "text": "Complex text to simplify",
  "max_length": 150,
  "simplification_level": "medium"
}
```

**Simplification Levels**:
- `basic`: Uses very simple words suitable for children
- `medium` (default): Balanced between simplicity and content preservation
- `advanced`: Maintains technical accuracy while simplifying structure

**Model**: Gemini 2.5 Flash
- If `GEMINI_API_KEY` not set: Returns original text with fallback flag

### Theme Extraction

**Models Used** (in order of preference):
1. **Gemini API** (if `GEMINI_API_KEY` is set)
   - High quality, semantically accurate themes
   - Uses advanced prompt engineering for better results

2. **Semantic Topics** (if `TOPIC_EMBEDDING_MODEL` is set or using default)
   - BERTopic + HDBSCAN clustering
   - Gemini API for topic name generation (if available)

3. **Fallback: TF-IDF + K-Means**
   - Local clustering without external APIs
   - Works offline, lower quality than Gemini

**Caching**:
- Theme extraction results are cached for 1 hour
- Cache uses Redis if available (`REDIS_URL`), otherwise in-memory
- Cache key includes meeting ID and number of themes
- Use `?force_refresh=true` query parameter to bypass cache

### Environment Setup

**Complete .env Configuration**:
```bash
# Gemini API (required for best quality)
GEMINI_API_KEY=your_gemini_api_key_here

# Embedding model for semantic topics
TOPIC_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

# Optional: Redis for distributed caching
REDIS_URL=redis://localhost:6379/0

# Other models
SENTIMENT_MODEL=cardiffnlp/twitter-roberta-base-sentiment-latest
SUMMARIZER_MODEL=philschmid/bart-large-cnn-samsum
ZERO_SHOT_MODEL=MoritzLaurer/deberta-v3-base-zeroshot-v2.0
ITDS_NER_MODEL=dbmdz/bert-large-cased-finetuned-conll03-english
ITDS_QA_MODEL=distilbert-base-cased-distilled-squad
ITDS_ASR_MODEL=openai/whisper-tiny.en
```

## Performance Optimization

### Model Download Caching

**HuggingFace Cache**:
- Set `HF_TOKEN` for higher download limits
- Models cached in: `~/.cache/huggingface/hub/`
- First download may take time; subsequent runs use cache

**Environment Variable**:
```bash
TRANSFORMERS_CACHE=/path/to/custom/cache
```

### Theme Consistency

**Ensuring Unique Theme Names**:
- Theme extraction is deterministic with `random_state=42`
- Results cached per year/filter configuration
- All API endpoints use same cached theme set
- Theme names normalized (title case, 2-4 words)

**Cache Invalidation**:
- Automatic after 1 hour (TTL)
- Manual: Clear `_THEMES_CACHE` in application or Redis

## Troubleshooting

### Text Simplification Returns Original Text

**Possible Causes**:
1. `GEMINI_API_KEY` not set → Falls back to returning original text
2. Gemini API quota exceeded → Check rate limits
3. Text too short (< 20 characters) → Minimum length required

**Solution**:
- Verify `GEMINI_API_KEY` is set: `echo $GEMINI_API_KEY`
- Check Gemini API quota: https://aistudio.google.com/app/apikeys
- Ensure text meets minimum length requirement

### Theme Extraction Quality Low

**Possible Causes**:
1. Gemini API not available → Using local clustering
2. Poor quality text data → Segments with low information content
3. Insufficient samples → Need at least 3 segments

**Solution**:
- Set `GEMINI_API_KEY` for high-quality extraction
- Ensure meeting segments contain meaningful content
- Check logs: `logging.getLogger('itds_framework').debug()`

### Models Not Loading

**Possible Causes**:
1. Insufficient disk space for model weights
2. No internet connection during first download
3. Model name typo in environment variable

**Solution**:
- Check available disk space (models ~100MB-1GB)
- Verify internet connectivity
- Validate model names at: https://huggingface.co/models

## Related Files

- Text Simplification: `itds_env/app/ai/simplifier.py`
- Theme Extraction: `itds_env/app/ai/themes.py`
- Semantic Topics: `itds_env/app/ai/semantic_topics.py`
- Trends Analysis: `itds_env/app/ai/trends.py`
- Routes: `itds_env/app/ai_routes.py`
