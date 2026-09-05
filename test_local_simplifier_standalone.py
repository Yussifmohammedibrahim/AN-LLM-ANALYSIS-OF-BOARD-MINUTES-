#!/usr/bin/env python3
"""Standalone test of the local rule-based simplifier logic."""

import re

def _local_simplify_rule_based(text, simplification_level="medium"):
    """
    Lightweight local simplifier used as fallback when OpenAI is unavailable.
    """
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


# Test cases
test_texts = [
    "The committee will deliberate on the fiscal allocations for the next quarter and subsequently ratify the proposed budget amendments.",
    "Utilizing a distributed ledger may ameliorate the integrity issues currently observed in centralized repositories.",
    "Due to the fact that the project will commence next week, it is important to note that all team members must endeavour to meet the deadline.",
]

print("=" * 80)
print("LOCAL RULE-BASED SIMPLIFIER TEST")
print("=" * 80)

for i, text in enumerate(test_texts, 1):
    print(f"\n[Test {i}]")
    print(f"Original ({len(text)} chars):")
    print(f"  {text}")
    
    for level in ['basic', 'medium', 'advanced']:
        simplified = _local_simplify_rule_based(text, simplification_level=level)
        reduction = len(text) - len(simplified)
        print(f"\n{level.upper()} ({len(simplified)} chars, -{reduction}):")
        print(f"  {simplified}")

print("\n" + "=" * 80)
print("✅ Test completed successfully!")
print("=" * 80)
