import sys,json,os
sys.path.insert(0, r'C:\Users\DELL\Documents\itds_frameworks\itds_env')
from app.ai.trends import analyze_theme_frequency
from app.report_generator import _get_top_themes, get_executive_summary

# Force fallback to avoid LLM delays
os.environ['GEMINI_API_KEY']=''

print('Calling analyze_theme_frequency...')
a = analyze_theme_frequency(year=2026, top_n=6)
print([t.get('theme_id') or t.get('name') for t in a])

print('\nCalling _get_top_themes...')
b = _get_top_themes(year=2026, limit=6)
print([t.get('name') for t in b])

print('\nCalling get_executive_summary (wrapped)')
try:
    resp = get_executive_summary.__wrapped__()
    js = resp[0].get_json()
    print([t.get('theme') for t in js.get('top_themes', [])])
except Exception as e:
    print('Could not call get_executive_summary directly:', e)
