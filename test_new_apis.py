import requests
import json

base_url = 'http://localhost:5000/api'

# Test 1: AI Summarize
print('=== Testing /api/ai/summarize ===')
response = requests.post(f'{base_url}/ai/summarize', json={
    'text': 'This is a test meeting. We discussed curriculum development and budget planning. The meeting was successful.'
})
print(f'Status: {response.status_code}')
print(f'Response: {json.dumps(response.json(), indent=2)}')

# Test 2: AI Sentiment
print('\n=== Testing /api/ai/sentiment ===')
response = requests.post(f'{base_url}/ai/sentiment', json={
    'text': 'We had an excellent meeting with great progress on all initiatives.'
})
print(f'Status: {response.status_code}')
print(f'Response: {json.dumps(response.json(), indent=2)}')

# Test 3: AI Keywords
print('\n=== Testing /api/ai/keywords ===')
response = requests.post(f'{base_url}/ai/keywords', json={
    'text': 'Curriculum development student internship tech fair faculty research budget planning'
})
print(f'Status: {response.status_code}')
print(f'Response: {json.dumps(response.json(), indent=2)}')

# Test 4: Model Evaluation
print('\n=== Testing /api/evaluate ===')
response = requests.post(f'{base_url}/evaluate', json={})
print(f'Status: {response.status_code}')
print(f'Response: {json.dumps(response.json(), indent=2)}')

# Test 5: Action Items
print('\n=== Testing /api/ai/action-items ===')
response = requests.post(f'{base_url}/ai/action-items', json={
    'text': 'We need to follow up on the budget approval. The team should complete the curriculum review by next week.'
})
print(f'Status: {response.status_code}')
print(f'Response: {json.dumps(response.json(), indent=2)}')

print('\n=== All tests completed ===')
