import requests
import jwt

# Test login
r = requests.post('http://localhost:5000/api/auth/login', json={'username':'admin','password':'admin123'})
print('Login status:', r.status_code)
data = r.json()
print('Response:', data)

# Decode token to see what's inside
token = data.get('access_token')
if token:
    decoded = jwt.decode(token, options={"verify_signature": False})
    print('JWT payload:', decoded)

