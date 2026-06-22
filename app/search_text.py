import re

with open('debug_bet365.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Find occurrences of href="...EV..." or onclick="...EV..."
matches = re.finditer(r'(href|onclick|data-id|data-fixtureid|data-eventid)=["\'][^"\']*?EV[^"\']*?["\']', content)
print("Regex matches for EV links in debug_bet365_real.html:")
count = 0
for m in matches:
    count += 1
    start = max(0, m.start() - 150)
    end = min(len(content), m.end() + 150)
    print(f"\nMatch {count}:")
    print(content[start:end])
    if count >= 10:
        break
if count == 0:
    # Let's search for just "/#/IP/" or "/IP/"
    print("\nNo EV matches. Searching for '/#/IP/' or 'IP/'...")
    matches_ip = re.finditer(r'/#/IP/[a-zA-Z0-9_]*', content)
    for m in matches_ip:
        count += 1
        start = max(0, m.start() - 100)
        end = min(len(content), m.end() + 100)
        print(content[start:end])
        if count >= 10:
            break


