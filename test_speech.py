#!/usr/bin/env python3
"""
Test /api/ai/analyze-speech endpoint directly.
Requires server running on http://localhost:5000 and valid JWT token.
"""
import requests
import json
from flask_jwt_extended import create_access_token
# Note: For testing, get token from login or create manually

SERVER_URL = 'http://localhost:5000'
TEST_TEXT = "Hello this is a test speech analysis. Great progress achieved today."
TEST_USER_ID = 1  # Use your logged-in user ID

def test_analyze_speech(token):
    """Test the analyze-speech endpoint."""
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    data = {'text': TEST_TEXT}
    
    try:
        response = requests.post(
            f'{SERVER_URL}/api/ai/analyze-speech',
            json=data,
            headers=headers,
            timeout=10
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            print("✅ SUCCESS: Speech analysis works!")
            return True
        else:
            print("❌ FAILED")
            return False
    except Exception as e:
        print(f"❌ Request failed: {e}")
        return False

if __name__ == "__main__":
    # Replace with your JWT token (from browser devtools or login response)
    TOKEN = input("Enter JWT token (or press Enter to skip): ").strip()
    if TOKEN:
        success = test_analyze_speech(TOKEN)
        if success:
            print("\nNext steps: Check itds_env/itds_minutes.db Transcripts table")
            print("sqlite3 itds_env/itds_minutes.db 'SELECT * FROM Transcripts ORDER BY created_at DESC LIMIT 5;'")
    else:
        print("Get token: Login via frontend, check Network tab -> /login response -> token field.")
