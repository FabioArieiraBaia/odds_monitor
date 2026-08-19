import re
path = r"C:\xampp\htdocs\odds_monitor\app\debug_betano_live.html"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    html = f.read()
# find tenis/mesa related
for m in re.finditer(r'.{0,80}(tenis|tênis|mesa|table.?tennis|ping).{0,80}', html, re.I):
    s = m.group(0).replace("\n"," ")[:200]
    print(s)
    print("---")
print("LEN", len(html))
# sport ids in initial_state
for m in re.finditer(r'"name"\s*:\s*"[^"]*(?:Mesa|Table|Tênis|Tenis)[^"]*"', html, re.I):
    print("NAME:", m.group(0))
for m in re.finditer(r'/live/[^"\']+', html):
    u = m.group(0)
    if any(x in u.lower() for x in ("mesa","table","tenis","tennis")):
        print("URL:", u[:120])
