import requests

# Test login
r = requests.post('http://localhost:5000/api/auth/login', json={'username':'admin','password':'admin123'})
if r.status_code != 200:
    print('Login failed')
    exit(1)
    
token = r.json()['access_token']
print('Login OK')

# Test getting users
headers = {'Authorization': 'Bearer ' + token}
r2 = requests.get('http://localhost:5000/api/admin/users', headers=headers)
print('GET users - Status:', r2.status_code)

# Test creating user
import time
new_user = {'username': 'test_' + str(int(time.time())), 'role': 'viewer'}
r3 = requests.post('http://localhost:5000/api/admin/users', headers=headers, json=new_user)
print('POST user - Status:', r3.status_code)
print('Response:', r3.text[:200])

print('All tests passed!')

