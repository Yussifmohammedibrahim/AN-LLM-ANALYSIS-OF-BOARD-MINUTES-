#!/usr/bin/env python3
"""Quick test of the local rule-based simplifier (no OpenAI key needed)."""

import sys
sys.path.insert(0, '.')

import sys
import os
# Add the itds_env directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'itds_env'))

# Import the simplifier module directly to avoid Flask initialization
from app.ai.simplifier import _local_simplify_rule_based, simplify_text

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
print("TESTING simplify_text() WITH NO OPENAI_API_KEY (should use fallback)")
print("=" * 80)

sample = "The committee will deliberate on the fiscal allocations."
result = simplify_text(sample, max_length=100, simplification_level='medium')
print(f"\nOriginal: {result['original_text']}")
print(f"Simplified: {result['simplified_text']}")
print(f"Model used: {result.get('model', 'unknown')}")
print(f"Was simplified: {result['simplified']}")
print(f"Reason/Note: {result.get('reason', 'N/A')}")

print("\n✅ Test completed successfully!")
