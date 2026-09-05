import requests
import time
from datetime import datetime, timedelta

BASE_URL = 'http://localhost:5000'
headers = {'Content-Type': 'application/json'}

print('=== Login Security Test ===')
print('Server running: http://localhost:5000')

# Test 1: Normal login
print('\\n1. Normal admin login')
r = requests.post(f'{BASE_URL}/api/auth/login', headers=headers, json={'username': 'admin', 'password': 'admin123'})
print(f'Status: {r.status_code}')
print(f'Response: {r.json()}')

# Test 2: 3 wrong logins
print('\\n2. 3 wrong logins (should lock after 3rd)')
for i in range(3):
    r = requests.post(f'{BASE_URL}/api/auth/login', headers=headers, json={'username': 'admin', 'password': 'wrong'})
    print(f'Wrong #{i+1}: {r.status_code} - {r.json()}')

# Test 3: 4th wrong login (should be locked)
print('\\n3. 4th login (should be LOCKED)')
r = requests.post(f'{BASE_URL}/api/auth/login', headers=headers, json={'username': 'admin', 'password': 'wrong'})
print(f'Locked: {r.status_code} - {r.json()}')

# Test 4: Wait 10s and try again (still locked)
print('\\n4. Try again after 10s (should still be locked)')
time.sleep(10)
r = requests.post(f'{BASE_URL}/api/auth/login', headers=headers, json={'username': 'admin', 'password': 'wrong'})
print(f'Still locked: {r.status_code} - {r.json()}')

# Test 5: Valid login (should reset attempts)
print('\\n5. Valid login (should unlock & reset)')
r = requests.post(f'{BASE_URL}/api/auth/login', headers=headers, json={'username': 'admin', 'password': 'admin123'})
print(f'Unlock: {r.status_code} - {r.json()}')

print('\\n✅ Test Complete! Check app.log for details')
