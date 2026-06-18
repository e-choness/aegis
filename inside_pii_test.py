import requests
r = requests.post(
    'http://localhost:8000/showcase/api/invoke',
    json={"prompt": "My email is user@example.com and my SSN is 123-45-6789", "route": "default"},
    timeout=10
)
print(f"Status: {r.status_code}")
data = r.json()
print(f"Response: {data.get('response')}")
print(f"Status: {data.get('status')}")
print(f"Events: {len(data.get('events', []))} events")
print(f"Mask map: {data.get('mask_map', {})}")