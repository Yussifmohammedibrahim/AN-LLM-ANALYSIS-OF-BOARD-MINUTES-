import requests

# Login as admin
r = requests.post('http://localhost:5000/api/auth/login', json={'username':'admin','password':'admin123'})
token = r.json()['access_token']
h = {'Authorization': 'Bearer ' + token}

# Create user with email
r2 = requests.post('http://localhost:5000/api/admin/users', headers=h, json={
    'username': 'emailtest1',
    'email': 'degeneral.ib115@gmail.com',
    'role': 'viewer'
})
print('Status:', r2.status_code)
print('Response:', r2.text)

