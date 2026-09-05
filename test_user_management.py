"""Test User Management Functionality"""
import sys
import os
import requests
import json

# Add itds_env to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'itds_env'))

BASE_URL = 'http://localhost:5000'

def test_auth_flow():
    """Test authentication and user management flow"""
    print("=" * 60)
    print("Testing User Management Functionality")
    print("=" * 60)
    
    # Test 1: Login as admin
    print("\n1. Testing Login as admin...")
    try:
        response = requests.post(f'{BASE_URL}/api/auth/login', json={
            'username': 'admin',
            'password': 'admin123'
        })
        if response.status_code == 200:
            data = response.json()
            token = data.get('access_token')
            print(f"   ✅ Login successful! Token received.")
            print(f"   Role: {data.get('role')}, Username: {data.get('username')}")
        else:
            print(f"   ❌ Login failed: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return None
    
    # Test 2: Get current user info
    print("\n2. Testing /api/auth/me (Get current user)...")
    try:
        response = requests.get(f'{BASE_URL}/api/auth/me', 
            headers={'Authorization': f'Bearer {token}'})
        if response.status_code == 200:
            print(f"   ✅ Current user: {response.json()}")
        else:
            print(f"   ❌ Failed: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 3: Get all users (admin only)
    print("\n3. Testing /api/admin/users (Get all users)...")
    try:
        response = requests.get(f'{BASE_URL}/api/admin/users',
            headers={'Authorization': f'Bearer {token}'})
        if response.status_code == 200:
            users = response.json()
            print(f"   ✅ Found {len(users)} user(s):")
            for u in users:
                print(f"      - {u['username']} ({u['role']})")
        else:
            print(f"   ❌ Failed: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 4: Create new user
    print("\n4. Testing /api/admin/users (Create new user)...")
    try:
        response = requests.post(f'{BASE_URL}/api/admin/users',
            headers={'Authorization': f'Bearer {token}'},
            json={
                'username': 'testuser',
                'email': 'test@example.com',
                'role': 'viewer'
            })
        if response.status_code == 201:
            data = response.json()
            print(f"   ✅ User created successfully!")
            print(f"   Username: {data.get('username')}")
            print(f"   Temp Password: {data.get('temp_password')}")
            print(f"   Role: {data.get('role')}")
            test_user_id = data.get('user_id')
        else:
            print(f"   ❌ Failed: {response.status_code} - {response.text}")
            test_user_id = None
    except Exception as e:
        print(f"   ❌ Error: {e}")
        test_user_id = None
    
    # Test 5: Try to create duplicate user (should fail)
    if test_user_id:
        print("\n5. Testing duplicate username (should fail)...")
        try:
            response = requests.post(f'{BASE_URL}/api/admin/users',
                headers={'Authorization': f'Bearer {token}'},
                json={
                    'username': 'testuser',
                    'role': 'viewer'
                })
            if response.status_code == 400:
                print(f"   ✅ Correctly rejected duplicate: {response.json()}")
            else:
                print(f"   ❌ Should have failed: {response.status_code}")
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    # Test 6: Update user role
    if test_user_id:
        print("\n6. Testing /api/admin/users/<id> (Update user role)...")
        try:
            response = requests.put(f'{BASE_URL}/api/admin/users/{test_user_id}',
                headers={'Authorization': f'Bearer {token}'},
                json={'role': 'editor'})
            if response.status_code == 200:
                print(f"   ✅ User role updated: {response.json()}")
            else:
                print(f"   ❌ Failed: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    # Test 7: Get all users again to verify changes
    print("\n7. Verifying users after changes...")
    try:
        response = requests.get(f'{BASE_URL}/api/admin/users',
            headers={'Authorization': f'Bearer {token}'})
        if response.status_code == 200:
            users = response.json()
            print(f"   ✅ Found {len(users)} user(s):")
            for u in users:
                print(f"      - {u['username']} ({u['role']})")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 8: Delete test user
    if test_user_id:
        print("\n8. Testing /api/admin/users/<id> (Delete user)...")
        try:
            response = requests.delete(f'{BASE_URL}/api/admin/users/{test_user_id}',
                headers={'Authorization': f'Bearer {token}'})
            if response.status_code == 200:
                print(f"   ✅ User deleted: {response.json()}")
            else:
                print(f"   ❌ Failed: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    # Test 9: Try accessing admin endpoint without token (should fail)
    print("\n9. Testing unauthorized access (should fail)...")
    try:
        response = requests.get(f'{BASE_URL}/api/admin/users')
        if response.status_code == 401:
            print(f"   ✅ Correctly rejected: {response.status_code}")
        else:
            print(f"   ⚠️ Expected 401, got {response.status_code}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 10: Register a new user directly
    print("\n10. Testing /api/auth/register (Self registration)...")
    try:
        response = requests.post(f'{BASE_URL}/api/auth/register', json={
            'username': 'newuser123',
            'password': 'password123',
            'role': 'viewer'
        })
        if response.status_code == 201:
            print(f"   ✅ User registered: {response.json()}")
        else:
            print(f"   ⚠️ Status: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    print("\n" + "=" * 60)
    print("Testing Complete!")
    print("=" * 60)

if __name__ == '__main__':
    test_auth_flow()

