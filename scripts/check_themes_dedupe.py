import sys, json, os
# Force the fallback extractor (avoid calling external LLM during checks)
os.environ['GEMINI_API_KEY'] = ''
sys.path.insert(0, r'C:\Users\DELL\Documents\itds_frameworks\itds_env')
from app.ai.trends import analyze_theme_frequency
res = analyze_theme_frequency(year=2026, top_n=6)
print('fetched:', len(res))
# simulate frontend uniqueThemes dedupe
mapd = {}
for t in res:
    key = str((t.get('theme_id') or t.get('name') or '')).lower()
    if not key: continue
    if key not in mapd:
        mapd[key] = t
uni = list(mapd.values())
print('unique count:', len(uni))
print(json.dumps([{'theme_id':u.get('theme_id'),'name':u.get('name'),'total_mentions':u.get('total_mentions', u.get('frequency', None))} for u in uni], indent=2, ensure_ascii=False))
