import requests

r = requests.get("http://localhost:8000/showcase", timeout=5)
print(f"Status: {r.status_code}")
print(f'Has Pipeline Showcase: {"Pipeline Showcase" in r.text}')
print(f'Has verdict: {"verdict" in r.text}')
print(f'Has eventLog: {"eventLog" in r.text}')
print(f'Has piiPanel: {"piiPanel" in r.text}')
