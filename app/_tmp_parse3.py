import re
path = r"C:\xampp\htdocs\odds_monitor\app\debug_betano_live.html"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    html = f.read()
# find section-wrapper near Tênis de Mesa
idx = html.find("Tênis de Mesa")
chunk = html[max(0,idx-800):idx+200]
print(chunk)
print("====")
# all section-wrapper data-qa
for m in re.finditer(r'id="section-wrapper-([^"]+)"[^>]*data-qa="([^"]+)"', html):
    print("wrapper", m.group(1), m.group(2))
for m in re.finditer(r'data-qa="(TABL|FOOT|TENN|BASK)"', html):
    print("qa", m.group(0), "pos", m.start())
