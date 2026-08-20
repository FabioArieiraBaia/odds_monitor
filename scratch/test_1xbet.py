import requests
import json

url = "https://1xbet.com/LiveFeed/Get1x2_VZip?sports=10&count=50&mode=4"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
try:
    r = requests.get(url, headers=headers, timeout=10)
    print("Status:", r.status_code)
    print("Content preview:", r.text[:500])
except Exception as e:
    print(f"Error: {e}")
