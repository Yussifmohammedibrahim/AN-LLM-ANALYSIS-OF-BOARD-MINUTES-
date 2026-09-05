"""Test theme-trends API endpoint"""
import requests
import json
import sys

# Test the API locally
BASE_URL = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:5001'

# Login first to get token
login_data = {
    'username': 'admin',
    'password': 'admin123'
}

try:
    # Login
    login_resp = requests.post(f'{BASE_URL}/api/auth/login', json=login_data)
    if login_resp.status_code != 200:
        print(f'Login failed: {login_resp.status_code} - {login_resp.text}')
        sys.exit(1)
    
    token = login_resp.json().get('access_token')
    if not token:
        print('No token received')
        sys.exit(1)
    
    print(f'Got token: {token[:20]}...')
    
    headers = {'Authorization': f'Bearer {token}'}
    
    # Test theme-trends API
    trends_resp = requests.get(f'{BASE_URL}/api/ai/theme-trends?year=2024', headers=headers)
    print(f'\ntheme-trends API status: {trends_resp.status_code}')
    print(f'Response: {json.dumps(trends_resp.json(), indent=2)}')
    
    # Test themes API
    themes_resp = requests.get(f'{BASE_URL}/api/ai/themes', headers=headers)
    print(f'\nthemes API status: {themes_resp.status_code}')
    print(f'Response: {json.dumps(themes_resp.json(), indent=2)}')
    
except Exception as e:
    print(f'Error: {e}')
