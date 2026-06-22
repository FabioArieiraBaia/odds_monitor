from bs4 import BeautifulSoup
import re

with open('debug_bet365.html', 'r', encoding='utf-8') as f:
    html = f.read()

soup = BeautifulSoup(html, 'html.parser')

print("=== ALL LINKS ===")
links = soup.find_all('a')
print(f"Total 'a' tags: {len(links)}")
for idx, l in enumerate(links[:30]):
    print(f"  a[{idx}]: href={l.get('href')}, class={l.get('class')}, text={l.text.strip()[:30]}")

print("\n=== ELEMENTS WITH CLASS CONTAINING 'Fixture' ===")
fixture_els = soup.find_all(class_=re.compile('Fixture', re.I))
print(f"Total Fixture elements: {len(fixture_els)}")
for idx, el in enumerate(fixture_els[:10]):
    print(f"  el[{idx}]: tag={el.name}, class={el.get('class')}, text={el.text.strip()[:50]}")

print("\n=== ELEMENTS WITH CLASS CONTAINING 'Participant' ===")
part_els = soup.find_all(class_=re.compile('Participant', re.I))
print(f"Total Participant elements: {len(part_els)}")
for idx, el in enumerate(part_els[:10]):
    print(f"  el[{idx}]: tag={el.name}, class={el.get('class')}, text={el.text.strip()[:50]}")
