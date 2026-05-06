"""Test admin login"""
import requests

BASE_URL = "http://localhost:8000"

# Try different password formats
passwords = ["admin123", "admin", "password", "123456"]

for pwd in passwords:
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        data=f"username=admin&password={pwd}",
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    print(f"Password '{pwd}': {resp.status_code}")
    if resp.status_code == 200:
        print(f"  Token: {resp.json().get('access_token', '')[:50]}...")
        break
