"""
Question Answering Feature
Allows users to ask questions about meeting minutes, utilizing Google Gemini API via OpenAI compatible endpoint.
"""
import os
import logging
from openai import OpenAI
from ..models import execute_safe_query

def answer_question(question, history=None):
    """Answer a question about meeting minutes using Google Gemini via OpenAI SDK."""
    if history is None:
        history = []
        
    if not question.strip():
        return {'answer': 'Question too short', 'confidence': 0.0}
    
    q_lower = question.lower()

    # Gather comprehensive App Context to feed to Gemini
    u_cnt, m_cnt, r_cnt = 0, 0, 0
    t_names, m_list, s_texts, specific_snippets = "", "", "", ""
    
    try:
        users = execute_safe_query('SELECT COUNT(*) as cnt FROM Users', ())
        u_cnt = users[0]['cnt'] if users else 0
    except Exception: pass
    
    try:
        meetings_count = execute_safe_query('SELECT COUNT(*) as cnt FROM Meetings', ())
        m_cnt = meetings_count[0]['cnt'] if meetings_count else 0
    except Exception: pass

    try:
        # VoiceRecordings table may not exist - handle gracefully
        recordings = execute_safe_query('SELECT COUNT(*) as cnt FROM VoiceRecordings', ())
        r_cnt = recordings[0]['cnt'] if recordings else 0
    except Exception:
        r_cnt = 0  # Table doesn't exist or other error - default to 0

    try:
        themes = execute_safe_query('SELECT theme_name FROM Themes LIMIT 20', ())
        t_names = ", ".join([str(dict(r).get('theme_name', '')) for r in (themes or [])])
    except Exception: pass

    try:
        meetings = execute_safe_query('SELECT source_filename as title, meeting_date FROM Meetings ORDER BY created_at ASC LIMIT 10', ())
        m_list = "\n".join([f"Meeting: {dict(m).get('title')} on {dict(m).get('meeting_date')}" for m in (meetings or [])])
    except Exception: pass
    
    try:
        summaries = execute_safe_query('SELECT summary_text FROM Summaries ORDER BY created_at DESC LIMIT 3', ())
        s_texts = "\n---\n".join([dict(s).get('summary_text', '') for s in (summaries or [])])
    except Exception: pass

    try:
        # Semantic snippet fetching for specific details
        segments = execute_safe_query('SELECT original_text FROM Segments LIMIT 500', ()) or []
        query_words = [w for w in q_lower.split() if w.isalnum() and len(w) > 3]
        scored_segments = []
        for row in segments:
            text = dict(row).get('original_text', '')
            score = sum(1 for word in query_words if word in text.lower())
            if score > 0:
                scored_segments.append((text, score))
        scored_segments.sort(key=lambda x: x[1], reverse=True)
        specific_snippets = "\n".join([seg[0] for seg in scored_segments[:5]])
    except Exception: pass

    context = f"""
APP DATABASE METADATA & STATS:
- Total Registered Users: {u_cnt}
- Total Meetings (Minutes) Uploaded: {m_cnt}
- Total Voice Recordings: {r_cnt}
- Key Themes in App: {t_names}

LIST OF UPLOADED MEETINGS:
{m_list}

RECENT MEETING SUMMARIES (For broader context):
{s_texts}

SPECIFIC TRANSCRIPT SNIPPETS MATCHING QUESTION:
{specific_snippets}
"""

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logging.warning("OPENAI_API_KEY not set. Using fallback message.")
        return {
            'answer': 'Please configure your OPENAI_API_KEY environment variable to enable the AI chatbox!',
            'confidence': 0.0,
            'context': 'Configuration required'
        }

    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    system_prompt = f"""You are a helpful AI assistant for the ITDS Board Minutes application.
Answer the user's question accurately based on the provided context.
If the question is not about the application data, you can answer it generally but keep it professional.
    
CONTEXT FROM APP DATABASE:
{context}
"""

    messages = [{"role": "system", "content": system_prompt}]
    
    for msg in history:
        role = "user" if msg.get("role") == "user" else "assistant"
        messages.append({
            "role": role,
            "content": msg.get("content", "")
        })
        
    messages.append({"role": "user", "content": question})
        
    # OpenAI Fallback Models
    fallback_models = ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo-preview", "gpt-3.5-turbo-0125"]
    last_error = None
    
    for model_id in fallback_models:
        try:
            response = client.chat.completions.create(
                model=model_id,
                messages=messages,
                temperature=0.7,
                max_tokens=800
            )
            answer_text = response.choices[0].message.content
            
            return {
                'answer': answer_text,
                'confidence': 1.0,
                'context': context[:200] + "..." if context else "General Knowledge"
            }
        except Exception as e:
            last_error = str(e)
            if "401" in last_error or "invalid_api_key" in last_error.lower():
                break
            continue
            
    # If all fail:
    if last_error and ("429" in last_error or "quota" in last_error.lower()):
        logging.warning("All OpenAI Models hit Quota 429.")
        return {
            'answer': 'We are sorry, but the application has currently exhausted its OpenAI API quota! Please wait a few minutes before asking another question.',
            'confidence': 0.0,
            'context': 'Quota Limit Reached'
        }
        
    logging.error(f"OpenAI API Error: {last_error}")
    return {
         'answer': f'Sorry, there was an issue communicating with the AI service: {last_error}',
         'confidence': 0.0,
         'context': 'OpenAI Error'
    }
