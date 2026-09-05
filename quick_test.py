import requests

r = requests.post('http://localhost:5000/api/auth/login', json={'username':'admin','password':'admin123'})
print('Status:', r.status_code)
print('Response:', r.text)
if r.status_code == 200:
  token = r.json()['access_token']
  print('Token OK')
else:
  print('Login FAILED')
  exit(1)
h = {'Authorization': 'Bearer ' + token}

# Test get users
r2 = requests.get('http://localhost:5000/api/admin/users', headers=h)
print('GET users:', r2.status_code)

# Test create user
r3 = requests.post('http://localhost:5000/api/admin/users', headers=h, json={'username': 'quicktest', 'role': 'viewer'})
print('POST user:', r3.status_code)
print('Response:', r3.text[:200])
