import requests

urls = [
    "https://22bet.com/LiveFeed/Get1x2_VZip?sports=10&count=50&mode=4",
    "https://br.1xbet.com/LiveFeed/Get1x2_VZip?sports=10&count=50&mode=4",
    "https://1xbet.mobi/LiveFeed/Get1x2_VZip?sports=10&count=50&mode=4",
    "https://api.1xbet.com/LiveFeed/Get1x2_VZip?sports=10&count=50&mode=4"
]

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

for url in urls:
    try:
        r = requests.get(url, headers=headers, timeout=5)
        print(f"{url} -> Status: {r.status_code}")
        if r.status_code == 200 and r.text.startswith("{"):
            print("  [SUCCESS] JSON returned!")
        else:
            print(f"  Preview: {r.text[:100]}")
    except Exception as e:
        print(f"{url} -> Error: {e}")
