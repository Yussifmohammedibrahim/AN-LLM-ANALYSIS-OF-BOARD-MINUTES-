#!/usr/bin/env python
"""Test chart endpoint response times to diagnose slow load issues."""
import requests
import time
import json

BASE_URL = 'http://localhost:5001'

# Test basic connectivity
endpoints = [
    ('/api/_routecheck', 'Basic route check'),
    ('/api/dashboard', 'Dashboard endpoint (requires auth)'),
    ('/api/ai/theme-frequency?year=2024&top_n=8', 'Theme frequency (requires auth)'),
    ('/api/ai/theme-trends?year=2024', 'Theme trends (requires auth)'),
]

print("=" * 80)
print("CHART DATA LOAD TEST - Diagnosing slow responses")
print("=" * 80)

for endpoint, desc in endpoints:
    url = BASE_URL + endpoint
    print(f"\n[TEST] {desc}")
    print(f"       URL: {url}")
    
    start = time.time()
    try:
        resp = requests.get(url, timeout=15)
        elapsed = time.time() - start
        
        print(f"       Status: {resp.status_code}")
        print(f"       Time: {elapsed:.2f}s")
        
        if resp.status_code == 401:
            print(f"       Note: Auth required. This is expected.")
        elif resp.status_code == 200:
            try:
                data = resp.json()
                if isinstance(data, dict):
                    print(f"       Response keys: {list(data.keys())[:5]}")
                    if 'error' in data:
                        print(f"       ERROR in response: {data['error']}")
                elif isinstance(data, list):
                    print(f"       Response: list with {len(data)} items")
                else:
                    print(f"       Response type: {type(data)}")
            except:
                print(f"       Response (first 200 chars): {resp.text[:200]}")
        else:
            print(f"       Response (first 200 chars): {resp.text[:200]}")
            
    except requests.exceptions.Timeout:
        elapsed = time.time() - start
        print(f"       ERROR: Request timeout after {elapsed:.2f}s")
        print(f"       ACTION: Backend is not responding - check if server is running")
    except requests.exceptions.ConnectionError as e:
        print(f"       ERROR: Connection refused - {str(e)[:100]}")
        print(f"       ACTION: Ensure backend server (Flask) is running on port 5001")
    except Exception as e:
        elapsed = time.time() - start
        print(f"       ERROR: {type(e).__name__}: {str(e)[:100]}")

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print("""
If you see:
1. Connection refused / Connection error → Backend server is NOT running. Start with: python run.py
2. Timeout after 15s → Backend is running but the chart query is very slow (likely slow DB query or AI model)
3. 401 Unauthorized → Auth is required. Need to login first and get a token.
4. 200 OK but with 'error' in response → Backend accepted request but query failed.

For SLOW responses (5+ seconds):
- Check database query performance with sqlite3 for Segments table
- Check if AI model extraction (BERTopic, theme extraction) is running on first load
- Consider adding caching layer or moving analysis to background job
""")
