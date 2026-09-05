"""
Summarization Feature
Generates concise summaries of meeting discussions using Google Gemini.
"""
import logging
import os
import re

from sklearn.feature_extraction.text import TfidfVectorizer

from ..models import execute_safe_query
from .semantic_topics import extract_semantic_topics
from ..model_manager import get_model_cache

# Prompt template location
_PROMPT_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), 'prompt_templates', 'meeting_summarization_prompt.md')


def _load_prompt_template(path):
    try:
        if os.path.isfile(path):
            with open(path, 'r', encoding='utf-8') as fh:
                return fh.read().strip()
    except Exception:
        pass
    return None


# Default embedded summarization prompt (used if external template missing)
DEFAULT_SUMMARIZATION_PROMPT = '''
You are an intelligent meeting summarization assistant.

Your task is to clean, restructure, and improve noisy meeting summaries and generated topics.

Requirements for the Summary:
1. Fix grammar, punctuation, spacing, and sentence structure.
2. Remove broken or incomplete sentences.
3. Make the summary meaningful, readable, and professional.
4. Preserve the original meaning and important information.
5. Split long text into clear paragraphs or bullet points where necessary.
6. Avoid repetition.
7. Expand shortened or broken words correctly (e.g. "develop ed" → "developed").
8. Keep the summary concise but complete.
9. Detect section titles such as: Welcome Message, Action Items, Preparation for Level 100.
10. Format the final summary properly.

Requirements for Topic Generation:
1. Generate short, meaningful, and complete topics.
2. Topics must clearly represent the discussion.
3. Avoid incomplete phrases ending with "...".
4. Use simple and professional language.
5. Each topic should contain 5–12 words only.
6. Capitalize properly.
7. Remove unnecessary names unless important.
8. Ensure topics are grammatically correct.

Expected Output Format:

#### Clean Summary

<well-structured meaningful summary>

#### Generated Topics

1. Topic One
2. Topic Two
3. Topic Three

Additional instructions:
- If text is unclear or fragmented, intelligently reconstruct it using context.
- Do not generate random information not found in the meeting text.
- Ensure the output sounds like official meeting minutes.
- Prioritize clarity, readability, and professionalism.

Model settings recommendation: temperature 0.2–0.4, high enough max_tokens to cover complete summaries.
'''

_FILLER_PATTERNS = (
    r'\b(um+|uh+|erm+|ah+|like|you know|basically|actually|literally|sort of|kind of)\b',
)

# Generic summary detection patterns
_GENERIC_PATTERNS = (
    r'^the\s+meeting\s+(was|discussed|covered|focused|about)',
    r'^this\s+(meeting|transcript)\s+(was|discussed|covered)',
    r'^basically\s+',
    r'^in\s+summary\s+',
    r'^to\s+sum\s+up\s+',
    r'^overall\s+',
    r'^the\s+speaker[s]?\s+(discussed|mentioned| talked about)',
    r'^no\s+(specific|important)',
    r'^various\s+(topics|items|issues)\s+(were|were discussed)',
    r'^\s*$',
)

_DEFAULT_SUMMARY_CHUNK_CHARS = int(os.environ.get('SUMMARY_CHUNK_CHARS', '12000'))
_DEFAULT_SUMMARY_CHUNK_OVERLAP = int(os.environ.get('SUMMARY_CHUNK_OVERLAP', '300'))


def _summarizer_debug_enabled():
    return str(os.environ.get('SUMMARIZER_DEBUG', '')).strip().lower() in ('1', 'true', 'yes', 'on')


def _log_debug_preview(stage, text, max_chars=400):
    if not _summarizer_debug_enabled():
        return
    value = (str(text or '') or '').replace('\n', ' ').strip()
    if len(value) > max_chars:
        value = f"{value[:max_chars]}..."
    logging.info(f"[SUMMARIZER_DEBUG] {stage}: {value}")

def _clean_summary_text(text):
    """Normalize transcript text before summarization."""
    cleaned = re.sub(r'\s+', ' ', str(text or '')).strip()
    for pattern in _FILLER_PATTERNS:
        cleaned = re.sub(pattern, ' ', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

def _looks_too_generic(text):
    """
    Check if generated summary is too generic/unhelpful.
    Returns True if summary matches common generic patterns.
    """
    if not text or not isinstance(text, str):
        return True
    
    text_lower = text.lower().strip()
    
    # Check against pattern list
    for pattern in _GENERIC_PATTERNS:
        try:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return True
        except re.error:
            continue
    
    # Also reject very short summaries (less than 3 words)
    word_count = len(text_lower.split())
    if word_count < 3:
        return True
    
    return False

def _split_sentences(text):
    """Split text into lightweight sentence-like units."""
    chunks = re.split(r'(?<=[.!?])\s+', str(text or '').strip())
    return [chunk.strip() for chunk in chunks if chunk and chunk.strip()]


def _chunk_text(text, max_chars=None, overlap_chars=None):
    """Chunk long text into overlapping windows to improve long-transcript quality."""
    source = str(text or '').strip()
    if not source:
        return []

    max_chars = max_chars or _DEFAULT_SUMMARY_CHUNK_CHARS
    overlap_chars = overlap_chars if overlap_chars is not None else _DEFAULT_SUMMARY_CHUNK_OVERLAP

    if len(source) <= max_chars:
        return [source]

    chunks = []
    start = 0
    text_len = len(source)
    while start < text_len:
        end = min(start + max_chars, text_len)
        chunk = source[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= text_len:
            break
        start = max(0, end - overlap_chars)
    return chunks


def _extract_executive_summary(raw_text):
    """Extract the Executive Summary section when the model returns multi-section output."""
    text = str(raw_text or '').strip()
    if not text:
        return ''

    patterns = (
        r'##\s*Executive\s+Summary\s*(.*?)(?=##\s*Key\s+Topics|##\s*Action\s+Items|$)',
        r'####\s*Clean\s+Summary\s*(.*?)(?=####\s*Generated\s+Topics|$)',
        r'Executive\s+Summary\s*[:\-]\s*(.*?)(?=Key\s+Topics|Action\s+Items|$)',
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            extracted = re.sub(r'\n{3,}', '\n\n', match.group(1)).strip()
            if extracted:
                return extracted
    return text


def _chat_completion(client, model_name, messages, temperature=0.2, max_tokens=1000, top_p=0.8):
    env_temp = os.environ.get('AI_TEMPERATURE', '').strip()
    try:
        final_temp = float(env_temp) if env_temp else temperature
    except ValueError:
        final_temp = temperature
    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=final_temp,
        top_p=top_p,
        max_tokens=max_tokens,
    )
    return (response.choices[0].message.content or '').strip()


def _summarize_with_local_model(text):
    """
    Generate a summary using a local Hugging Face transformer model.
    Used as a high-quality fallback when Gemini is unavailable.
    """
    if not text or len(text.strip()) < 50:
        return text
        
    try:
        logger.info("Attempting local summarization...")
        cache = get_model_cache()
        summarizer = cache.get_summarization_pipeline()
        
        # Split text into manageable chunks if very long (transformers have limits)
        # 1024 tokens is typical for many summarization models
        # We'll use a conservative char limit for the local model
        max_chars = 3000 
        
        if len(text) > max_chars:
            chunks = [text[i:i+max_chars] for i in range(0, len(text), max_chars)]
            chunk_summaries = []
            for chunk in chunks:
                res = summarizer(chunk, max_length=150, min_length=30, do_sample=False)
                if res and len(res) > 0:
                    chunk_summaries.append(res[0]['summary_text'])
            
            combined = " ".join(chunk_summaries)
            # Final pass if combined is still long
            if len(combined) > 1000:
                res = summarizer(combined[:max_chars], max_length=250, min_length=100, do_sample=False)
                return res[0]['summary_text']
            return combined
        else:
            res = summarizer(text, max_length=250, min_length=100, do_sample=False)
            return res[0]['summary_text']
            
    except Exception as e:
        logger.warning(f"Local summarization failed: {e}")
        return None

def _clean_transcript_with_llm(client, model_name, text):
    cleaner_prompt = (
        "You clean noisy meeting transcripts before summarization. "
        "Fix grammar, spacing, punctuation, broken words, and fragmented sentences while preserving meaning. "
        "Do not add facts. Remove obvious filler/noise and return only clean transcript text."
    )
    cleaned = _chat_completion(
        client,
        model_name,
        [
            {"role": "system", "content": cleaner_prompt},
            {"role": "user", "content": text},
        ],
        temperature=0.1,
        max_tokens=1800,
        top_p=0.8,
    )
    return cleaned


def _summarize_chunk_with_llm(client, model_name, system_prompt, chunk_text):
    return _chat_completion(
        client,
        model_name,
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": chunk_text},
        ],
        temperature=0.2,
        max_tokens=1200,
        top_p=0.8,
    )


def _merge_chunk_summaries_with_llm(client, model_name, system_prompt, summaries):
    merged_input = '\n\n'.join(
        f"Section {index + 1}:\n{value}" for index, value in enumerate(summaries) if value
    ).strip()
    if not merged_input:
        return ''
    merge_prompt = (
        f"{system_prompt}\n\n"
        "You are given section-level summaries from one meeting. "
        "Merge them into one coherent final output without repetition and with consistent structure."
    )
    return _chat_completion(
        client,
        model_name,
        [
            {"role": "system", "content": merge_prompt},
            {"role": "user", "content": merged_input},
        ],
        temperature=0.2,
        max_tokens=1400,
        top_p=0.8,
    )


def _validate_summary_with_llm(client, model_name, candidate):
    validation_system = (
        "You are a professional editor specialized in meeting minutes. "
        "Clean and improve the following meeting summary without adding new facts. "
        "Fix grammar, punctuation, spacing, and broken sentences; remove filler and trailing ellipses; "
        "ensure all sentences are complete and the output reads like official meeting minutes. "
        "Return only the cleaned summary (no commentary)."
    )
    return _chat_completion(
        client,
        model_name,
        [
            {"role": "system", "content": validation_system},
            {"role": "user", "content": candidate},
        ],
        temperature=0.1,
        max_tokens=800,
        top_p=0.8,
    )

def _extractive_summary(text, max_sentences=3):
    """Create a short extractive summary from the most informative sentences as a fallback."""
    sentences = _split_sentences(text)
    if not sentences:
        return ''
    if len(sentences) <= max_sentences:
        return ' '.join(sentences)

    try:
        vectorizer = TfidfVectorizer(stop_words='english', ngram_range=(1, 2), max_features=500)
        matrix = vectorizer.fit_transform(sentences)
        scores = matrix.sum(axis=1).A1
        ranked_indices = sorted(range(len(sentences)), key=lambda idx: (-scores[idx], idx))[:max_sentences]
        ranked_indices.sort()
        return ' '.join(sentences[idx] for idx in ranked_indices)
    except Exception as exc:
        logging.debug(f"Extractive summary fallback failed: {exc}")
        return ' '.join(sentences[:max_sentences])

def _structural_topic_summary(text):
    """
    Generate a structured summary by extracting topics and their representative sentences.
    This is the 'Best Way' local fallback that avoids simple keyword matching.
    """
    sentences = _split_sentences(text)
    if len(sentences) < 5:
        return _extractive_summary(text, max_sentences=3)

    try:
        topics = extract_semantic_topics(sentences, max_topics=5)
        lead_summary = _extractive_summary(text, max_sentences=3)
        if not topics:
            return f"Executive Summary: {lead_summary}" if lead_summary else ''

        topic_labels = []
        for topic in topics[:5]:
            name = str(topic.get('name', 'General Discussion')).strip()
            if name:
                topic_labels.append(name)

        labels_text = '; '.join(topic_labels)
        return f"Executive Summary: {lead_summary} Key Themes: {labels_text}."
    except Exception as exc:
        logging.warning(f"Structural summary failed: {exc}")
        return _extractive_summary(text, max_sentences=4)


def _get_summary_model_candidates():
    candidate_models = []
    for env_key in ('AI_SUMMARY_MODEL', 'SUMMARY_MODEL'):
        value = os.environ.get(env_key, '').strip()
        if value and value not in candidate_models:
            candidate_models.append(value)
    for model_name in ('gpt-4o-mini', 'gpt-4o', 'gpt-4-turbo-preview', 'gpt-3.5-turbo-0125'):
        if model_name not in candidate_models:
            candidate_models.append(model_name)
    return candidate_models

def summarize_text(text):
    """Summarize the meeting text using Gemini API."""
    text = _clean_summary_text(text)
    if not text:
        return ""

    openai_key = os.environ.get("OPENAI_API_KEY")

    if not openai_key:
        logging.warning("No OpenAI API key set. Using structural topic summary fallback.")
        return _structural_topic_summary(text)

    try:
        from openai import OpenAI
        
        client = OpenAI(api_key=openai_key)
        model_candidates = _get_summary_model_candidates()
        # Prefer an external prompt template if present (allows iterative improvements without code changes)
        system_prompt = _load_prompt_template(_PROMPT_TEMPLATE_PATH)
        if not system_prompt:
            # Use the embedded default advanced prompt to guarantee behavior when external file is missing
            system_prompt = DEFAULT_SUMMARIZATION_PROMPT

        last_error = None
        for model_name in model_candidates:
            try:
                _log_debug_preview('raw_input', text)

                # Pass 1: clean transcript text before summarization.
                precleaned_text = text
                try:
                    cleaned_candidate = _clean_transcript_with_llm(client, model_name, text)
                    if cleaned_candidate:
                        precleaned_text = cleaned_candidate
                except Exception as exc:
                    logging.debug(f"Pre-clean pass failed: {exc}")

                _log_debug_preview('precleaned_input', precleaned_text)

                # Pass 2: summarize each chunk for long transcripts, then merge.
                chunks = _chunk_text(precleaned_text)
                chunk_summaries = []
                for idx, chunk in enumerate(chunks):
                    chunk_summary = _summarize_chunk_with_llm(client, model_name, system_prompt, chunk)
                    if chunk_summary:
                        _log_debug_preview(f'chunk_{idx + 1}_summary_raw', chunk_summary)
                        chunk_summaries.append(chunk_summary)

                if not chunk_summaries:
                    continue

                if len(chunk_summaries) > 1:
                    candidate = _merge_chunk_summaries_with_llm(client, model_name, system_prompt, chunk_summaries)
                else:
                    candidate = chunk_summaries[0]

                candidate = (candidate or '').strip()
                _log_debug_preview('merged_summary_raw', candidate)

                if not candidate:
                    continue

                # Extract only the summary body if the model also returns topics/actions.
                candidate = _extract_executive_summary(candidate)

                # If the candidate looks generic, skip it.
                if _looks_too_generic(candidate):
                    continue

                # Pass 3: post-process / validate generated summary.
                try:
                    cleaned = _validate_summary_with_llm(client, model_name, candidate)
                    cleaned = _extract_executive_summary(cleaned)
                    _log_debug_preview('validated_summary_clean', cleaned)
                    if cleaned and not _looks_too_generic(cleaned):
                        return cleaned
                except Exception as exc:
                    logging.debug(f"Validation pass failed: {exc}")

                # Fallback to merged candidate if validation is unavailable or not better.
                _log_debug_preview('validated_summary_fallback_candidate', candidate)
                return candidate
            except Exception as exc:
                last_error = str(exc)
                if any(code in last_error for code in ('400', '401', '403')):
                    break
                continue
        logging.warning(f"Summary model unavailable or generic; falling back to structural summary: {last_error}")
        return _structural_topic_summary(text)
    except Exception as e:
        error_msg = str(e)
        if '429' in error_msg or 'quota' in error_msg.lower() or 'insufficient_quota' in error_msg:
            logging.warning(f"OpenAI API issue ({e}). Attempting local model summarization.")
            local_summary = _summarize_with_local_model(text)
            if local_summary:
                return local_summary
        
        logging.error(f"OpenAI summarization failed: {e}. Falling back to structural.")
        return _structural_topic_summary(text)

def _build_meeting_text(segments):
    """Build a compact meeting-level text block from segment rows."""
    cleaned = []
    for row in segments:
        text = _clean_summary_text(dict(row).get('original_text') or '')
        if text:
            cleaned.append(text)

    # Gemini can handle millions of context tokens, so we no longer need to chunk the text!
    return ' '.join(cleaned)


def _get_meeting_confidence(meeting_id):
    """Compute an overall confidence score for a meeting from segment analysis rows."""
    rows = execute_safe_query(
        '''
            SELECT AVG(COALESCE(a.confidence_score, 0)) AS confidence_score
            FROM Analysis a
            JOIN Segments s ON a.segment_id = s.segment_id
            WHERE s.meeting_id = ?
        ''',
        (meeting_id,)
    )
    if not rows:
        return None

    confidence = rows[0].get('confidence_score')
    return float(confidence) if confidence is not None else None

def summarize_segments(meeting_id=None):
    """Generate a single meeting-level summary."""
    if meeting_id:
        result = execute_safe_query(
            'SELECT segment_id, original_text FROM Segments WHERE meeting_id = ? ORDER BY segment_id',
            (meeting_id,)
        )
    else:
        result = execute_safe_query(
            'SELECT segment_id, original_text FROM Segments ORDER BY meeting_id, segment_id LIMIT 50',
            ()
        )

    summaries = []

    if not result:
        return summaries

    segments = [dict(row) for row in result]
    target_meeting_id = meeting_id
    if target_meeting_id is None and segments:
        # Resolve the meeting ID from the first segment so the summary is persisted against a meeting.
        meeting_rows = execute_safe_query(
            'SELECT meeting_id FROM Segments WHERE segment_id = ? LIMIT 1',
            (segments[0].get('segment_id'),)
        )
        if meeting_rows:
            target_meeting_id = meeting_rows[0].get('meeting_id')

    try:
        meeting_text = _build_meeting_text(segments)
        summary_text = summarize_text(meeting_text)
        if not summary_text:
            return summaries

        summary_text = _clean_summary_text(summary_text)
        if _looks_too_generic(summary_text):
            summary_text = _extractive_summary(meeting_text, max_sentences=3)

        summary_text = re.sub(r'\s+', ' ', summary_text).strip()

        confidence_score = _get_meeting_confidence(target_meeting_id) if target_meeting_id is not None else None

        # Keep one summary row per meeting.
        if target_meeting_id is not None:
            execute_safe_query(
                '''
                    INSERT INTO Summaries (meeting_id, segment_id, summary_text, confidence_score, created_at)
                    VALUES (?, ?, ?, ?, datetime('now'))
                    ON CONFLICT(meeting_id) DO UPDATE SET
                        segment_id = excluded.segment_id,
                        summary_text = excluded.summary_text,
                        confidence_score = excluded.confidence_score,
                        created_at = excluded.created_at
                ''',
                (target_meeting_id, segments[-1].get('segment_id'), summary_text, confidence_score),
                fetch=False
            )
        else:
            # Fallback for legacy rows without a resolvable meeting id.
            execute_safe_query(
                'INSERT INTO Summaries (segment_id, summary_text, confidence_score) VALUES (?, ?, ?)',
                (segments[-1].get('segment_id'), summary_text, confidence_score),
                fetch=False
            )

        summaries.append({
            'meeting_id': target_meeting_id,
            'segment_id': segments[-1].get('segment_id'),
            'summary': summary_text,
            'confidence': confidence_score,
            'segment_count': len(segments),
        })
    except Exception as e:
        logging.error(f"Summarization error: {e}")

    return summaries