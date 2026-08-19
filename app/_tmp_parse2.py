import re, json
path = r"C:\xampp\htdocs\odds_monitor\app\debug_betano_live.html"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    html = f.read()
# find TABL / tenis-de-mesa structures
for pat in [r'"sportId"\s*:\s*"TABL"[^}]{0,200}', r'tenis-de-mesa[^"\']{0,80}', r'Tênis de Mesa.{0,200}', r'data-qa[^>]{0,80}mesa', r'sport-id[^>]{0,80}TABL']:
    ms = list(re.finditer(pat, html, re.I|re.S))
    print("PAT", pat[:40], "count", len(ms))
    for m in ms[:3]:
        print(repr(m.group(0)[:250]))
        print("---")
# sports menu items near mesa
idx = html.lower().find("tênis de mesa")
if idx < 0: idx = html.lower().find("tenis de mesa")
print("idx", idx)
if idx > 0:
    print(html[max(0,idx-300):idx+400])
