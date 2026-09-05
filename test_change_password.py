"""Test Password Change Email"""
import requests
import time
import json

BASE_URL = 'http://localhost:5000'

print("1. Login admin")
r = requests.post(f'{BASE_URL}/api/auth/login', json={'username':'admin','password':'admin123'})
print("Admin response:", r.json())
token = r.json()['access_token']
headers = {'Authorization': f'Bearer {token}'}
print(f"Admin token OK")

print("\n2. Create test user with email")
r2 = requests.post(f'{BASE_URL}/api/admin/users', headers=headers, json={
    'username': f'testchange{int(time.time())}',
    'email': f'test{int(time.time())}@example.com',
    'role': 'viewer'

})
data2 = r2.json()
print("Create response:", data2)
user_username = data2['username']  # Wait, response doesn't have username? Use input
temp_pass = data2['temp_password']
user_username = data2['username']  # Use actual created username
print(f"Created, temp pass: {temp_pass}")

print("\n3. Login as test user")
r3 = requests.post(f'{BASE_URL}/api/auth/login', json={'username': user_username, 'password': temp_pass})
print("Test user login response:", r3.json())
if 'access_token' in r3.json():
    user_token = r3.json()['access_token']
    user_headers = {'Authorization': f'Bearer {user_token}'}
    print("Test user login OK")
    
    print("\n4. Change password")
    r4 = requests.post(f'{BASE_URL}/api/auth/change-password', headers=user_headers, json={
        'current_password': temp_pass,
        'new_password': 'NewPass123!'
    })
    print(f"Change status: {r4.status_code}")
    print(f"Change response: {r4.json()}")
    
    print("\n5. Check app.log:")
    print("tail -n 20 app.log")
else:
    print("Test user login failed - check username/temp_pass")

print("\nDone. Server must be running at localhost:5000.")
