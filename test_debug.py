import requests

# Login
r = requests.post('http://localhost:5000/api/auth/login', json={'username': 'admin', 'password': 'admin123'})
print(f"Login: {r.status_code} - {r.text}")

if r.status_code == 200:
    token = r.json().get('access_token')
    headers = {'Authorization': f'Bearer {token}'}
    
    # Test /api/auth/me
    r2 = requests.get('http://localhost:5000/api/auth/me', headers=headers)
    print(f"/api/auth/me: {r2.status_code} - {r2.text}")
    
    # Test /api/admin/users
    r3 = requests.get('http://localhost:5000/api/admin/users', headers=headers)
    print(f"/api/admin/users: {r3.status_code} - {r3.text}")
