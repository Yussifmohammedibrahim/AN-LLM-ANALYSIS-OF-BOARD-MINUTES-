"""
Full Speech Analysis Pipeline - Same as Document Upload
Uses transform_text segmentation and complete AI analysis suite.
"""
import logging
import os
import re
import subprocess
import tempfile
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np

from app.models import execute_safe_query
from ..model_manager import get_model_cache


SUPPORTED_AUDIO_EXTENSIONS = {'.wav', '.mp3', '.m4a', '.webm', '.mp4'}
TARGET_ASR_SAMPLE_RATE = 16000
DEFAULT_MAX_AUDIO_SECONDS = int(os.getenv('ITDS_AUDIO_MAX_SECONDS', '180') or 180)
FAST_AUDIO_SECONDS = int(os.getenv('ITDS_FAST_AUDIO_SECONDS', '90') or 90)
DEFAULT_SILENCE_THRESHOLD = float(os.getenv('ITDS_AUDIO_SILENCE_THRESHOLD', '0.012') or 0.012)
DEFAULT_MIN_SPEECH_SECONDS = float(os.getenv('ITDS_AUDIO_MIN_SPEECH_SECONDS', '0.20') or 0.20)
ASR_CHUNK_LENGTH_S = float(os.getenv('ITDS_ASR_CHUNK_LENGTH_S', '20') or 20)
ASR_BATCH_SIZE = int(os.getenv('ITDS_ASR_BATCH_SIZE', '8') or 8)


def _resolve_ffmpeg_executable():
    """Resolve FFmpeg executable across env vars, PATH, and common Windows install paths."""
    user_profile = os.path.expanduser('~')
    candidates = [
        os.getenv('FFMPEG_CMD', '').strip(),
        os.getenv('FFMPEG_PATH', '').strip(),
        shutil.which('ffmpeg') or '',
        r'C:\ffmpeg\bin\ffmpeg.exe',
        r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
        r'C:\Program Files\FFmpeg\bin\ffmpeg.exe',
        r'C:\ProgramData\chocolatey\bin\ffmpeg.exe',
        os.path.join(user_profile, 'AppData', 'Local', 'Microsoft', 'WinGet', 'Links', 'ffmpeg.exe'),
    ]

    for candidate in candidates:
        if not candidate:
            continue
        # Allow setting env vars to either the executable or its parent folder.
        if os.path.isdir(candidate):
            candidate = os.path.join(candidate, 'ffmpeg.exe')
        if os.path.isfile(candidate):
            return candidate

    return None


def transform_text_speech(text):
    """
    Simplified text transformation for speech transcripts.
    Same segmentation as documents but skips heavy NER anonymization.
    """
    # Remove metadata (less relevant for speech)
    text = re.sub(r'(Attendance|Signatures|Header|Footer).*?\n', '', text, flags=re.IGNORECASE)
    # Remove special characters for security
    text = re.sub(r'[^\w\s.,!?-]', '', text)
    # Skip NER anonymization for speech (assume already anonymized or not needed)
    # Segment into chunks (same as document processing)
    words = text.split()
    segments = [' '.join(words[i:i+500]) for i in range(0, len(words), 500)]
    return segments

# Simple English stopwords
STOPWORDS = {
    'the', 'be', 'to', 'of', 'and', 'a', 'in', 'that', 'have', 'i', 'it', 'for', 
    'not', 'on', 'with', 'he', 'as', 'you', 'do', 'at', 'this', 'but', 'his', 
    'by', 'from', 'they', 'she', 'or', 'an', 'will', 'my', 'one', 'all', 'would',
    'there', 'their', 'what', 'so', 'up', 'out', 'if', 'about', 'who', 'get', 
    'which', 'go', 'me', 'when', 'make', 'can', 'like', 'time', 'no', 'just',
    'him', 'know', 'take', 'people', 'into', 'year', 'your', 'good', 'some', 
    'could', 'them', 'see', 'other', 'than', 'then', 'now', 'look', 'only',
    'come', 'its', 'over', 'think', 'also', 'back', 'after', 'use', 'two', 'how',
    'our', 'work', 'first', 'well', 'way', 'even', 'new', 'want', 'because',
    'any', 'these', 'give', 'day', 'most', 'us'
}

def analyze_sentiment_fast(text):
    """Analyze sentiment with the cached ML model and a deterministic fallback."""
    cleaned_text = re.sub(r'\s+', ' ', str(text or '')).strip()
    if not cleaned_text:
        return 'NEUTRAL', 0.0

    try:
        cache = get_model_cache()
        result = cache.batch_analyze_sentiment([cleaned_text], truncate=True)
        if result:
            sentiment_result = result[0] or {}
            label = str(sentiment_result.get('label', 'NEUTRAL')).upper()
            score = float(sentiment_result.get('score', 0.0) or 0.0)

            if label not in {'POSITIVE', 'NEGATIVE', 'NEUTRAL'}:
                if 'POS' in label:
                    label = 'POSITIVE'
                elif 'NEG' in label:
                    label = 'NEGATIVE'
                else:
                    label = 'NEUTRAL'

            return label, round(score, 3)
    except Exception as exc:
        logging.warning(f"ML sentiment unavailable, falling back to rules: {exc}")

    text_lower = cleaned_text.lower()
    positive_words = len(re.findall(r'\b(great|excellent|good|amazing|wonderful|fantastic|awesome|love|best|happy|success|win|achieve|improve|positive|benefit|opportunity|progress|forward|excited|thrilled)\b', text_lower))
    negative_words = len(re.findall(r'\b(bad|terrible|awful|poor|worst|fail|problem|issue|challenge|difficult|worry|concern|risk|decline|lose|frustrated|angry|disappointed|negative|crisis)\b', text_lower))

    if positive_words > negative_words:
        return 'POSITIVE', round(0.6 + (positive_words - negative_words) * 0.05, 3)
    if negative_words > positive_words:
        return 'NEGATIVE', round(0.6 + (negative_words - positive_words) * 0.05, 3)
    return 'NEUTRAL', 0.5



def save_transcript(transcript_text, user_id, meeting_id=None, sentiment=None, keywords=None, analysis_complete=0):
    """Save live transcript + analysis output to DB - best-effort, non-blocking."""
    if not transcript_text.strip() or user_id is None:
        logging.warning(f"Skipping transcript save: empty text or invalid user_id {user_id}")
        return None
        
    try:
        result = execute_safe_query(
            '''
            INSERT INTO Transcripts (user_id, transcript_text, meeting_id, sentiment, keywords, analysis_complete)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            (
                user_id,
                transcript_text,
                meeting_id,
                sentiment,
                ', '.join(keywords) if isinstance(keywords, list) else keywords,
                1 if analysis_complete else 0,
            ),
            fetch=False
        )
        logging.info(f"Transcript saved: ID={result}, user={user_id}, len={len(transcript_text)}")
        return result
    except Exception as e:
        logging.error(f"Transcript save failed (non-blocking): {e}", exc_info=True)
        return None


def _segment_recording_text(text):
    """Use the same segmentation approach as uploaded documents when available."""
    try:
        from app.app import transform_text as transform_document_text
        segments = transform_document_text(text)
        if segments:
            return segments
    except Exception as exc:
        logging.warning(f"Document-style segmentation unavailable for speech transcript: {exc}")

    return transform_text_speech(text)


def _store_meeting_segments(meeting_id, segments):
    """Persist segmented transcript text for downstream analysis."""
    if not segments:
        return 0

    inserted = 0
    for segment_text in segments:
        cleaned = str(segment_text or '').strip()
        if not cleaned:
            continue
        execute_safe_query(
            'INSERT INTO Segments (meeting_id, original_text) VALUES (?, ?)',
            (meeting_id, cleaned),
            fetch=False
        )
        inserted += 1
    return inserted


def _store_topics(meeting_id, topics):
    """Persist dynamic topics for a meeting."""
    if not topics:
        return 0

    execute_safe_query('DELETE FROM Topics WHERE meeting_id = ?', (meeting_id,), fetch=False)
    stored = 0
    for topic in topics:
        execute_safe_query(
            'INSERT INTO Topics (meeting_id, topic_name, confidence_score, keywords) VALUES (?, ?, ?, ?)',
            (
                meeting_id,
                topic.get('name'),
                float(topic.get('confidence') or 0),
                ','.join(topic.get('keywords', []) or []),
            ),
            fetch=False
        )
        stored += 1
    return stored


def _aggregate_keywords(keyword_rows, max_items=10):
    """Flatten keyword rows into a deduplicated list for UI display."""
    keyword_list = []
    seen = set()
    for row in keyword_rows or []:
        for keyword in row.get('keywords', []) or []:
            normalized = str(keyword or '').strip().lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            keyword_list.append(normalized)
            if len(keyword_list) >= max_items:
                return keyword_list
    return keyword_list


def _derive_overall_sentiment(sentiment_rows):
    """Derive one overall sentiment label/confidence from segment-level results."""
    if not sentiment_rows:
        return 'NEUTRAL', 0.0

    labels = [str(row.get('sentiment') or 'NEUTRAL').upper() for row in sentiment_rows]
    label = Counter(labels).most_common(1)[0][0] if labels else 'NEUTRAL'

    confidence_values = [float(row.get('confidence') or 0.0) for row in sentiment_rows]
    confidence = sum(confidence_values) / len(confidence_values) if confidence_values else 0.0
    return label, round(confidence, 3)


def _extract_fast_keywords(text, max_items=10):
    """Extract lightweight keywords without invoking heavy model pipelines."""
    tokens = re.findall(r'\b[a-zA-Z]{4,}\b', str(text or '').lower())
    filtered = [t for t in tokens if t not in STOPWORDS]
    counts = Counter(filtered)
    return [word for word, _ in counts.most_common(max_items)]


def _resample_audio_linear(audio, source_rate, target_rate=TARGET_ASR_SAMPLE_RATE):
    """Resample mono audio using linear interpolation to the model target rate."""
    if source_rate <= 0 or target_rate <= 0:
        raise ValueError('Invalid sample rate for resampling.')
    if source_rate == target_rate or audio.size == 0:
        return audio.astype(np.float32), int(source_rate)

    duration = float(audio.size) / float(source_rate)
    target_size = max(1, int(round(duration * target_rate)))
    source_positions = np.arange(audio.size, dtype=np.float32)
    target_positions = np.linspace(0, max(audio.size - 1, 0), num=target_size, dtype=np.float32)
    resampled = np.interp(target_positions, source_positions, audio).astype(np.float32)
    return resampled, int(target_rate)


def _trim_silence(audio, sample_rate, threshold=DEFAULT_SILENCE_THRESHOLD, min_speech_seconds=DEFAULT_MIN_SPEECH_SECONDS):
    """Trim leading/trailing low-energy regions to reduce transcription time."""
    if audio.size == 0:
        return audio

    abs_audio = np.abs(audio)
    speech_idx = np.flatnonzero(abs_audio >= float(threshold))
    if speech_idx.size == 0:
        return audio

    start = int(speech_idx[0])
    end = int(speech_idx[-1]) + 1

    # Keep a small context margin to avoid clipping words at edges.
    margin = int(sample_rate * 0.20)
    start = max(0, start - margin)
    end = min(audio.size, end + margin)

    trimmed = audio[start:end]
    min_samples = int(sample_rate * max(0.05, float(min_speech_seconds)))
    if trimmed.size < min_samples:
        return audio
    return trimmed.astype(np.float32)


def _cap_audio_duration(audio, sample_rate, max_seconds=DEFAULT_MAX_AUDIO_SECONDS):
    """Cap max audio duration to bound worst-case latency for uploads."""
    if max_seconds <= 0:
        return audio, False
    max_samples = int(sample_rate * max_seconds)
    if audio.size <= max_samples:
        return audio, False
    return audio[:max_samples], True


def _call_asr(asr, audio, sample_rate, return_timestamps=False):
    """Call ASR with fast options and gracefully fallback if kwargs are unsupported."""
    payload = {'array': audio, 'sampling_rate': sample_rate}
    kwargs = {
        'return_timestamps': return_timestamps,
        'chunk_length_s': ASR_CHUNK_LENGTH_S,
        'batch_size': ASR_BATCH_SIZE,
    }

    try:
        return asr(payload, **kwargs)
    except TypeError:
        # Older transformers versions may not support one or more kwargs.
        try:
            return asr(payload, return_timestamps=return_timestamps)
        except TypeError:
            return asr(payload)


def _transcribe_audio_with_fallback(asr, audio, sample_rate):
    """Transcribe audio with a long-audio-safe fallback for Whisper pipelines."""
    duration_seconds = float(audio.size) / float(sample_rate or 1)

    try:
        # Whisper expects timestamp prediction for long-form inputs.
        result = _call_asr(asr, audio, sample_rate, return_timestamps=duration_seconds > 30)
        transcript = (result or {}).get('text', '') if isinstance(result, dict) else ''
        transcript = str(transcript or '').strip()
        if transcript:
            return transcript
    except Exception as exc:
        error_text = str(exc)
        long_audio_error = '3000 mel input features' in error_text or 'return_timestamps=True' in error_text
        if not long_audio_error:
            raise
        logging.warning(f"Long-form ASR path triggered fallback chunking: {exc}")

    # Fallback: chunk audio into <=25s windows to avoid long-form generation constraints.
    chunk_seconds = 15
    overlap_seconds = 1
    chunk_samples = int(sample_rate * chunk_seconds)
    overlap_samples = int(sample_rate * overlap_seconds)
    min_chunk_samples = int(sample_rate * 0.25)

    parts = []
    start = 0
    total_samples = int(audio.size)

    while start < total_samples:
        end = min(start + chunk_samples, total_samples)
        chunk = audio[start:end]
        if chunk.size < min_chunk_samples:
            break

        chunk_result = _call_asr(asr, chunk, sample_rate, return_timestamps=False)
        chunk_text = (chunk_result or {}).get('text', '') if isinstance(chunk_result, dict) else ''
        chunk_text = str(chunk_text or '').strip()
        if chunk_text:
            parts.append(chunk_text)

        if end >= total_samples:
            break
        start = max(end - overlap_samples, start + 1)

    transcript = ' '.join(parts).strip()
    if not transcript:
        raise ValueError('No speech could be transcribed from the uploaded audio.')
    return transcript


def transcribe_audio_file(file_path, max_seconds=DEFAULT_MAX_AUDIO_SECONDS):
    """Transcribe an uploaded audio file into plain text."""
    import wave

    path = Path(file_path)
    extension = path.suffix.lower()
    if extension not in SUPPORTED_AUDIO_EXTENSIONS:
        raise ValueError('Unsupported audio format. Use WAV, MP3, M4A, WEBM, or MP4.')

    wav_path = str(path)
    temp_wav_path = None

    # Normalize non-WAV inputs with ffmpeg for consistent ASR ingestion.
    if extension != '.wav':
        ffmpeg_executable = _resolve_ffmpeg_executable()
        if not ffmpeg_executable:
            raise ValueError(
                'FFmpeg is required for MP3/M4A/WEBM/MP4 uploads. '
                'Please install FFmpeg or set FFMPEG_CMD in .env (example: C:\\ffmpeg\\bin\\ffmpeg.exe).'
            )

        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_wav:
            temp_wav_path = temp_wav.name

        command = [
            ffmpeg_executable,
            '-y',
            '-i',
            str(path),
            '-ac',
            '1',
            '-ar',
            '16000',
            temp_wav_path,
        ]
        process = subprocess.run(command, capture_output=True, text=True, check=False)
        if process.returncode != 0:
            raise RuntimeError(process.stderr.strip() or process.stdout.strip() or 'ffmpeg conversion failed')

        wav_path = temp_wav_path

    try:
        with wave.open(wav_path, 'rb') as wav_file:
            channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            sample_rate = wav_file.getframerate()
            frame_count = wav_file.getnframes()
            raw_frames = wav_file.readframes(frame_count)

        if sample_width == 1:
            audio = np.frombuffer(raw_frames, dtype=np.uint8).astype(np.float32)
            audio = (audio - 128.0) / 128.0
        elif sample_width == 2:
            audio = np.frombuffer(raw_frames, dtype=np.int16).astype(np.float32) / 32768.0
        elif sample_width == 4:
            audio = np.frombuffer(raw_frames, dtype=np.int32).astype(np.float32) / 2147483648.0
        else:
            raise ValueError(f'Unsupported WAV bit depth: {sample_width * 8}-bit')

        if channels > 1:
            audio = audio.reshape(-1, channels).mean(axis=1)

        if audio.size == 0:
            raise ValueError('Uploaded audio is empty.')

        audio, sample_rate = _resample_audio_linear(audio, sample_rate, TARGET_ASR_SAMPLE_RATE)
        trimmed = _trim_silence(audio, sample_rate)
        if trimmed.size and trimmed.size < audio.size:
            audio = trimmed

        audio, was_capped = _cap_audio_duration(audio, sample_rate, max_seconds)
        if was_capped:
            logging.info(
                f"Audio duration capped to {max_seconds}s for faster processing. "
                f"Set ITDS_AUDIO_MAX_SECONDS=0 to disable cap."
            )

        cache = get_model_cache()
        asr = cache.get_asr_pipeline()
        transcript = _transcribe_audio_with_fallback(asr, audio, sample_rate)
        if not transcript:
            raise ValueError('No speech could be transcribed from the uploaded audio.')

        return transcript
    finally:
        if temp_wav_path and os.path.exists(temp_wav_path):
            try:
                os.remove(temp_wav_path)
            except Exception:
                pass


def process_recording_transcript(transcript_text, user_id, source_filename='voice_recording', full_pipeline=True):
    """Promote a transcript into a meeting record and run the full analysis pipeline."""
    if not transcript_text.strip():
        return {'error': 'Empty transcript', 'transcript_id': None, 'meeting_id': None}

    try:
        meeting_id = execute_safe_query(
            'INSERT INTO Meetings (meeting_date, source_filename) VALUES (?, ?)',
            (datetime.now().date().isoformat(), source_filename),
            fetch=False
        )

        segments = _segment_recording_text(transcript_text)
        segment_count = _store_meeting_segments(meeting_id, segments)

        transcript_id = save_transcript(
            transcript_text,
            user_id,
            meeting_id=meeting_id,
            analysis_complete=0,
        )

        summaries = []
        sentiments = []
        action_items = []
        keywords = []
        topics = []

        if full_pipeline:
            from .summarizer import summarize_segments
            from .sentiment import analyze_sentiment
            from .actions import extract_action_items
            from .keywords import extract_keywords

            summaries = summarize_segments(meeting_id) or []
            sentiments = analyze_sentiment(meeting_id) or []
            action_items = extract_action_items(meeting_id) or []
            keywords = extract_keywords(meeting_id) or []

            overall_sentiment, sentiment_confidence = _derive_overall_sentiment(sentiments)
            summary_text = str((summaries[0] or {}).get('summary') or '').strip() if summaries else ''
            keyword_list = _aggregate_keywords(keywords, max_items=10)

            try:
                from app.ai_routes import extract_topics_from_segments
                segment_rows = execute_safe_query(
                    'SELECT segment_id, original_text FROM Segments WHERE meeting_id = ? ORDER BY segment_id',
                    (meeting_id,)
                )
                topics = extract_topics_from_segments(segment_rows) if segment_rows else []
                _store_topics(meeting_id, topics)
            except Exception as exc:
                logging.warning(f"Topic extraction failed for recording meeting {meeting_id}: {exc}")
        else:
            overall_sentiment, sentiment_confidence = analyze_sentiment_fast(transcript_text)
            keyword_list = _extract_fast_keywords(transcript_text, max_items=10)
            sentences = re.split(r'(?<=[.!?])\s+', str(transcript_text or '').strip())
            summary_text = ' '.join(sentences[:2]).strip() or f"Audio transcript processed ({segment_count} segments)."

        execute_safe_query(
            'UPDATE Transcripts SET analysis_complete = 1, sentiment = ?, keywords = ? WHERE transcript_id = ?',
            (overall_sentiment, ', '.join(keyword_list), transcript_id),
            fetch=False
        )

        return {
            'transcript_id': transcript_id,
            'meeting_id': meeting_id,
            'transcript': transcript_text,
            'segment_count': segment_count,
            'summary_count': len(summaries),
            'sentiment_count': len(sentiments),
            'action_item_count': len(action_items),
            'keyword_count': len(keywords),
            'topic_count': len(topics),
            'summary': summary_text,
            'sentiment': overall_sentiment,
            'confidence': sentiment_confidence,
            'keywords': keyword_list,
            'topics': topics,
            'message': 'Recording transcript promoted to meeting and analyzed successfully' if full_pipeline else 'Audio uploaded and fast analysis completed successfully',
        }
    except Exception as e:
        logging.error(f"Recording transcript pipeline error: {e}", exc_info=True)
        raise

def analyze_speech_text(text, user_id):
    """
    Analyze transcript using same pipeline as document uploads:
    1. Segment text (same as transform_text)
    2. Create meeting entry
    3. Store segments
    4. Run full AI analysis suite
    5. Update transcript with results
    """
    if not text.strip():
        return {'error': 'Empty transcript', 'sentiment': None, 'keywords': []}
    
    try:
        segments = transform_text_speech(text)
        all_text = ' '.join(segments)

        # Use the same cached sentiment classifier as the rest of the app.
        sentiment, confidence = analyze_sentiment_fast(all_text)

        # Keep a small keyword snapshot for history, but don't block on the heavier pipeline here.
        words = re.findall(r'\b\w{4,}\b', all_text.lower())
        keywords = list(dict.fromkeys(words))[:10]

        summary = f"Speech analysis complete: {sentiment} sentiment detected."
        
        # Save transcript (light DB only, non-blocking)
        transcript_id = save_transcript(
            text,
            user_id,
            sentiment=sentiment,
            keywords=keywords,
            analysis_complete=1,
        )
        
        return {
            'transcript_id': transcript_id,
            'segments_count': len(segments),
            'sentiment': sentiment,
            'confidence': confidence,
            'keywords': keywords,
            'summary': summary,
            'message': f'Fast live analysis complete - optimized for real-time voice. DB save: {"OK" if transcript_id else "skipped"}'
        }
    except Exception as e:
        logging.error(f"Speech analysis pipeline error: {e}", exc_info=True)
        raise


