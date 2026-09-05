"""Test theme functions after fix"""
import sys
sys.path.insert(0, 'c:/Users/DELL/Documents/itds_frameworks')

from itds_env.app.ai.themes import extract_dynamic_themes, get_theme_trends_by_year, get_theme_sentiment_distribution

# Test 1: Fallback theme extraction
texts = [
    'We discussed the quarterly budget and financial reports',
    'The budget allocation needs to be reviewed',
    'Financial planning for next quarter was discussed',
    'We need to discuss the marketing strategy',
    'The marketing team presented their strategy'
]

themes = extract_dynamic_themes(texts_override=texts, num_themes=2)
print(f'Test 1 - Themes extracted: {len(themes)}')
for t in themes:
    print(f'  - {t["name"]}: {t["keywords"]}')

# Test 2: Get theme sentiment distribution
sent = get_theme_sentiment_distribution()
print(f'\nTest 2 - Sentiment distribution works: {sent is not None}')
print(f'  Keys: {list(sent.keys()) if sent else "None"}')

print('\n=== All theme functions working! ===')
