import re
with open('debug_bet365.html', encoding='utf-8') as f:
    html = f.read()
links = set(re.findall(r'href=["\'](.*?)["\']', html))
print(list(links)[:50])
