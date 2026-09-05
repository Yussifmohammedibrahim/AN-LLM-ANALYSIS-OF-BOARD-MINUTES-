"""Fix database path and test API"""
import sys
import os

# Fix path to find database
os.chdir('itds_env')
sys.path.insert(0, '.')

from app.app import app

def test_api():
    client = app.test_client()
    
    print("=" * 60)
    print("TESTING BACKEND API ENDPOINTS (Fixed Paths)")
    print("=" * 60)
    
    # Test 1: Get themes
    print("\n1. GET /api/themes")
    response = client.get('/api/themes')
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.get_json()
        print(f"   ✅ Works - {len(data)} themes found")
    else:
        print(f"   Response: {response.get_json()}")
    
    # Test 2: Get meetings
    print("\n2. GET /api/meetings")
    response = client.get('/api/meetings')
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.get_json()
        print(f"   ✅ Works - {len(data)} meetings found")
    else:
        print(f"   Response: {response.get_json()}")
    
    # Test 3: Login
    print("\n3. POST /api/auth/login")
    response = client.post('/api/auth/login', 
        json={'username': 'admin', 'password': 'admin123'})
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.get_json()
        print(f"   ✅ Login successful!")
        print(f"   Token received: {'access_token' in data}")
    else:
        print(f"   Response: {response.get_json()}")
    
    # Test 4: Get analysis
    print("\n4. GET /api/analysis")
    response = client.get('/api/analysis')
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.get_json()
        print(f"   ✅ Works - {len(data)} records")
    
    print("\n" + "=" * 60)
    print("API TESTING COMPLETE")
    print("=" * 60)

if __name__ == '__main__':
    test_api()
