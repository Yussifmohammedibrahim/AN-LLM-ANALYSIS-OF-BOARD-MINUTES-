"""
Text Simplification Feature
Converts complex meeting minutes into accessible, easy-to-read text.
Uses Gemini AI for high-quality simplification and accessibility improvements.
"""
import logging
import os
from threading import Lock
import json

logger = logging.getLogger(__name__)

# Global client and lock for thread-safe initialization
_OPENAI_CLIENT = None
_CLIENT_LOCK = Lock()

def _get_openai_client():
    """Get or create OpenAI API client."""
    global _OPENAI_CLIENT
    
    with _CLIENT_LOCK:
        if _OPENAI_CLIENT is not None:
            return _OPENAI_CLIENT
        
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY not set. Text simplification will be limited.")
            return None
        
        try:
            from openai import OpenAI
            _OPENAI_CLIENT = OpenAI(api_key=api_key)
            logger.info("OpenAI client initialized for text simplification")
            return _OPENAI_CLIENT
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            return None


def _local_simplify_rule_based(text, simplification_level="medium"):
    """
    Lightweight local simplifier used as fallback when OpenAI is unavailable.
    - Applies glossary replacements (e.g., utilize → use)
    - Splits long sentences at commas and conjunctions
    - Removes common filler phrases
    Deterministic and works offline.
    """
    import re
    
    glossary = {
        'utilize': 'use',
        'utilise': 'use',
        'ameliorate': 'improve',
        'subsequently': 'then',
        'endeavour': 'try',
        'commence': 'start',
        'terminate': 'end',
        'fiscal': 'financial',
        'utilisation': 'use',
        'deliberate': 'discuss',
        'ratify': 'approve',
    }

    def replace_glossary(s):
        def _rep(m):
            word = m.group(0)
            lw = word.lower()
            if lw in glossary:
                repl = glossary[lw]
                if word[0].isupper():
                    repl = repl.capitalize()
                return repl
            return word
        return re.sub(r"\b[A-Za-z']+\b", _rep, s)

    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    out_sentences = []
    
    for s in sentences:
        s = replace_glossary(s)
        s = s.replace('\n', ' ').strip()
        
        # Break long sentences at commas or conjunctions
        if len(s) > 140:
            parts = re.split(r',|;|\band\b|\bwhich\b|\bthat\b', s)
            for p in parts:
                p = p.strip()
                if not p:
                    continue
                # Further chunk if still too long
                if len(p) > 140:
                    for i in range(0, len(p), 120):
                        chunk = p[i:i+120].strip()
                        if chunk:
                            out_sentences.append(chunk)
                else:
                    out_sentences.append(p)
        else:
            out_sentences.append(s)
    
    # Remove filler phrases
    simplified = []
    for s in out_sentences:
        s_clean = re.sub(r"\b(in order to|due to the fact that|it is important to note that)\b", '', s, flags=re.IGNORECASE)
        s_clean = re.sub(r'\s{2,}', ' ', s_clean).strip()
        if s_clean:
            simplified.append(s_clean)
    
    # Rejoin with proper punctuation
    result = ' '.join([
        s if s.endswith(('.', '?', '!')) else s + '.' 
        for s in simplified
    ])
    
    # For basic level, enforce stricter length
    if simplification_level == 'basic' and len(result) > 300:
        result = ' '.join(result.split()[:60]) + '...'
    
    return result.strip()


def simplify_text(text, max_length=150, simplification_level="medium"):
    """
    Simplify complex text for accessibility using Gemini AI.
    
    Args:
        text: Text to simplify (min 20 characters)
        max_length: Maximum length of simplified output
        simplification_level: 'basic', 'medium', or 'advanced'
    
    Returns:
        Dictionary with original_text and simplified_text
    """
    if not text:
        raise ValueError("Text cannot be empty")
    
    text = str(text).strip()
    if len(text) < 20:
        return {
            'original_text': text,
            'simplified_text': text,
            'simplified': False,
            'reason': 'Text too short to simplify'
        }
    
    client = _get_openai_client()
    if not client:
        # Fallback: use local rule-based simplifier
        simplified = _local_simplify_rule_based(text, simplification_level=simplification_level)
        return {
            'original_text': text,
            'simplified_text': simplified,
            'simplified': simplified != text,
            'reason': 'Used local rule-based fallback',
            'model': 'local-rule'
        }
    
    try:
        # Build simplification prompt based on level with few-shot examples for better consistency
        model_name = os.getenv('SIMPLIFICATION_MODEL', 'gpt-4o-mini')
        if simplification_level == "basic":
            level_instruction = "Use very simple words that a 10-year-old would understand. Keep sentences very short (<=12 words)."
        elif simplification_level == "advanced":
            level_instruction = "Simplify while maintaining technical accuracy and professional terminology. Use clear phrasing but keep necessary terms."
        else:  # medium
            level_instruction = "Use common, everyday words while preserving the core meaning. Prefer active voice and shorter sentences."

        # Few-shot examples to guide the model
        examples = [
            {
                'input': 'The committee will deliberate on the fiscal allocations for the next quarter and subsequently ratify the proposed budget amendments.',
                'basic': 'The committee will discuss next quarter\'s budget and then approve changes.',
                'medium': 'The committee will discuss budget allocations for next quarter and approve any changes.',
                'advanced': 'The committee will review fiscal allocations for the next quarter and approve the proposed budget amendments.'
            },
            {
                'input': 'Utilizing a distributed ledger may ameliorate the integrity issues currently observed in centralized repositories.',
                'basic': 'Using a shared ledger can fix problems with central databases.',
                'medium': 'Using a distributed ledger can improve data integrity compared to centralized storage.',
                'advanced': 'A distributed ledger can improve integrity issues present in centralized repositories.'
            }
        ]

        example_block = '\n\n'.join([
            f"EXAMPLE INPUT: {e['input']}\nSIMPLIFIED ({simplification_level}): {e[simplification_level]}" for e in examples
        ])

        system_prompt = (
            "You are an expert assistant that rewrites complex text into simpler, clearer language without changing meaning. "
            "Follow the level instruction exactly and produce only the simplified text (no commentary, no headings, no extra notes)."
            f"\nLevel instruction: {level_instruction}\n\nExamples:\n{example_block}\n\n"
        )

        # Use deterministic settings for reproducible simplification
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Simplify this text:\n\n{text}"}
                ],
                temperature=0.0,
                max_tokens=max_length + 250
            )

            simplified_text = response.choices[0].message.content.strip()
        except Exception as e:
            # As a minor retry, try a slightly higher temperature to encourage rewriting
            try:
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Simplify this text:\n\n{text}"}
                    ],
                    temperature=0.2,
                    max_tokens=max_length + 250
                )
                simplified_text = response.choices[0].message.content.strip()
            except Exception as retry_error:
                logger.warning(f"OpenAI simplification failed, using local fallback: {retry_error}")
                simplified_text = _local_simplify_rule_based(text, simplification_level=simplification_level)
        
        # Post-process: ensure output length and reasonable reduction
        if len(simplified_text) > max_length * 1.5:
            simplified_text = simplified_text[:max_length].rstrip() + "..."

        # If the model returned the original text (no change), attempt a stronger simplification pass
        if simplified_text.strip() == text.strip():
            stronger_instruction = "Make the text significantly simpler: shorten sentences, replace uncommon words with common alternatives, and remove redundancy."
            try:
                response2 = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system_prompt + "\nAdditional: " + stronger_instruction},
                        {"role": "user", "content": f"Simplify this text:\n\n{text}"}
                    ],
                    temperature=0.0,
                    max_tokens=max_length + 200
                )
                alt_text = response2.choices[0].message.content.strip()
                if alt_text and alt_text != text:
                    simplified_text = alt_text
            except Exception:
                pass
        
        return {
            'original_text': text,
            'simplified_text': simplified_text,
            'simplified': simplified_text != text,
            'length_original': len(text),
            'length_simplified': len(simplified_text),
            'length_reduction': max(0, len(text) - len(simplified_text)),
            'model': 'gpt-4o-mini',
            'simplification_level': simplification_level
        }
    
    except Exception as e:
        logger.warning(f"Text simplification error, using local fallback: {e}")
        simplified_text = _local_simplify_rule_based(text, simplification_level=simplification_level)
        return {
            'original_text': text,
            'simplified_text': simplified_text,
            'simplified': simplified_text != text,
            'reason': 'Used local rule-based fallback after API error',
            'model': 'local-rule'
        }


def batch_simplify_texts(texts, max_length=150, simplification_level="medium"):
    """
    Simplify multiple texts efficiently using Gemini.
    
    Args:
        texts: List of text strings
        max_length: Max output length per text
        simplification_level: 'basic', 'medium', or 'advanced'
    
    Returns:
        List of simplified text dictionaries
    """
    results = []
    
    client = _get_openai_client()
    if not client:
        # Fallback: use local rule-based simplifier for batch
        return [{
            'original_text': str(t).strip() if t else '',
            'simplified_text': _local_simplify_rule_based(str(t).strip(), simplification_level=simplification_level) if (t and len(str(t).strip()) >= 20) else (str(t).strip() if t else ''),
            'simplified': False if len(str(t).strip()) < 20 else (_local_simplify_rule_based(str(t).strip(), simplification_level=simplification_level) != str(t).strip()),
            'model': 'local-rule'
        } for t in texts]
    
    try:
        # Filter valid texts
        valid_texts = [str(t).strip() for t in texts if t and len(str(t).strip()) >= 20]
        
        if not valid_texts:
            return [{'original_text': t, 'simplified_text': t, 'simplified': False} for t in texts]
        
        # Build level instruction
        if simplification_level == "basic":
            level_instruction = "Use very simple words that a 10-year-old would understand."
        elif simplification_level == "advanced":
            level_instruction = "Simplify while maintaining technical accuracy."
        else:
            level_instruction = "Use common, everyday words while preserving meaning."
        
        system_prompt = f"""Simplify complex text for accessibility.
{level_instruction}
Rules: Break long sentences, remove jargon, use active voice, eliminate redundancy.
Output ONLY simplified versions."""
        
        # Batch texts: combine into single prompt for efficiency
        combined_texts = "\n---\n".join([f"TEXT {i+1}:\n{t}" for i, t in enumerate(valid_texts)])
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Simplify these texts:\n\n{combined_texts}"}
            ],
            temperature=0.3,
            max_tokens=max_length * len(valid_texts) + 200
        )
        
        response_text = response.choices[0].message.content.strip()
        
        # Parse response: split back by text boundaries
        simplified_list = []
        lines = response_text.split("---")
        for line in lines:
            line = line.strip()
            if line:
                # Remove "TEXT N:" prefix if present
                if ":" in line:
                    line = line.split(":", 1)[1].strip()
                simplified_list.append(line)
        
        # Map results back to original list
        result_index = 0
        for original_text in texts:
            original_text = str(original_text).strip() if original_text else ""
            
            if len(original_text) < 20:
                results.append({
                    'original_text': original_text,
                    'simplified_text': original_text,
                    'simplified': False,
                    'model': 'gpt-4o-mini'
                })
            else:
                if result_index < len(simplified_list):
                    simplified_text = simplified_list[result_index]
                    result_index += 1
                else:
                    simplified_text = original_text
                
                results.append({
                    'original_text': original_text,
                    'simplified_text': simplified_text,
                    'simplified': simplified_text != original_text,
                    'model': 'gpt-4o-mini'
                })
        
        return results
    
    except Exception as e:
        logger.warning(f"Batch simplification error, using local fallback: {e}")
        return [{
            'original_text': str(t).strip() if t else '',
            'simplified_text': _local_simplify_rule_based(str(t).strip(), simplification_level=simplification_level) if (t and len(str(t).strip()) >= 20) else (str(t).strip() if t else ''),
            'simplified': False if len(str(t).strip()) < 20 else (_local_simplify_rule_based(str(t).strip(), simplification_level=simplification_level) != str(t).strip()),
            'model': 'local-rule',
            'reason': 'Used local rule-based fallback after API error'
        } for t in texts]


def simplify_meeting_minutes(meeting_id):
    """
    Simplify all segments from a specific meeting.
    Stores simplified versions in database.
    
    Args:
        meeting_id: Meeting ID
    
    Returns:
        Count of simplified segments
    """
    from ..models import get_db, execute_safe_query
    import json
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Get all segments for meeting
        cursor.execute(
            'SELECT segment_id, original_text FROM Segments WHERE meeting_id = ? ORDER BY segment_id',
            (meeting_id,)
        )
        segments = cursor.fetchall()
        
        if not segments:
            conn.close()
            return 0
        
        texts = [row['original_text'] for row in segments]
        segment_ids = [row['segment_id'] for row in segments]
        
        # Simplify batch
        simplified_results = batch_simplify_texts(texts)
        
        # Store in database (create table if needed)
        execute_safe_query(
            '''
            CREATE TABLE IF NOT EXISTS SimplifiedSegments (
                simplified_id INTEGER PRIMARY KEY,
                segment_id INTEGER UNIQUE,
                original_text TEXT,
                simplified_text TEXT,
                simplified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (segment_id) REFERENCES Segments(segment_id)
            )
            ''',
            fetch=False
        )
        
        # Insert simplified texts
        count = 0
        for seg_id, result in zip(segment_ids, simplified_results):
            if result.get('simplified'):
                execute_safe_query(
                    '''
                    INSERT OR REPLACE INTO SimplifiedSegments 
                    (segment_id, original_text, simplified_text, simplified_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    ''',
                    (seg_id, result['original_text'], result['simplified_text']),
                    fetch=False
                )
                count += 1
        
        conn.close()
        logger.info(f"Simplified {count} segments for meeting {meeting_id}")
        return count
    
    except Exception as e:
        logger.error(f"Error simplifying meeting {meeting_id}: {e}")
        conn.close()
        return 0


def get_simplified_segments(meeting_id):
    """Get simplified versions of segments for a meeting."""
    from ..models import get_db
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            '''
            SELECT segment_id, original_text, simplified_text 
            FROM SimplifiedSegments 
            WHERE segment_id IN (SELECT segment_id FROM Segments WHERE meeting_id = ?)
            ORDER BY segment_id
            ''',
            (meeting_id,)
        )
        
        rows = cursor.fetchall()
        results = [dict(row) for row in rows]
        
        conn.close()
        return results
    
    except Exception as e:
        logger.error(f"Error getting simplified segments: {e}")
        conn.close()
        return []
