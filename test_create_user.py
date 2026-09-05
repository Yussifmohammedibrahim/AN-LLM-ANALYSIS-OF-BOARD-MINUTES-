import requests
import json

# First login to get token
login_url = 'http://localhost:5000/api/auth/login'
login_data = {'username': 'admin', 'password': 'admin123'}
login_response = requests.post(login_url, json=login_data)
print('Login Status:', login_response.status_code)
print('Login Response:', login_response.text)

if login_response.status_code == 200:
    token = login_response.json()['access_token']
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    # Test create user
    create_url = 'http://localhost:5000/api/admin/users'
    create_data = {
        'username': 'testuser',
        'email': 'test@test.com',
        'full_name': 'Test User',
        'contact_number': '123456',
        'role': 'viewer'
    }
    
    create_response = requests.post(create_url, headers=headers, json=create_data)
    print('\nCreate User Status:', create_response.status_code)
    print('Create User Response:', create_response.text)
    print('Create User Headers:', dict(create_response.headers))
else:
    print('Login failed')

