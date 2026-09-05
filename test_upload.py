import urllib.request
import urllib.error
import json

# Test OCR upload with image file
url = 'http://localhost:5000/api/upload'

# Read the test image
with open('uploads/test_ocr.png', 'rb') as f:
    image_data = f.read()

# Create multipart form data
boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
body = b'--' + boundary.encode() + b'\r\n'
body += b'Content-Disposition: form-data; name="file"; filename="test_ocr.png"\r\n'
body += b'Content-Type: image/png\r\n\r\n'
body = body + image_data + ('\r\n--' + boundary + '--\r\n').encode()

req = urllib.request.Request(url, data=body, method='POST')
req.add_header('Content-Type', 'multipart/form-data; boundary=' + boundary)

try:
    r = urllib.request.urlopen(req)
    print('Status:', r.status)
    print('Response:', json.loads(r.read().decode()))
except urllib.error.HTTPError as e:
    print('Status:', e.code)
    print('Error:', e.read().decode())
except Exception as e:
    print('Error:', str(e))
