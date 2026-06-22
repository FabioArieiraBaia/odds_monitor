import re
from bs4 import BeautifulSoup

def test():
    with open('debug_betburger.html', 'r', encoding='utf-8') as f:
        html = f.read()
    
    soup = BeautifulSoup(html, 'html.parser')
    rows = soup.select('.surebet, .arb, [class*="arb-item"]')
    
    raw_data = []
    for row in rows:
        text = row.get_text(separator='\\n', strip=True) # closest to innerText
        if len(text) >= 10:
            raw_data.append({'text': text})
            
    print(f"raw_data has {len(raw_data)} items")
    
    events = []
    for item in raw_data:
        text = item.get('text', '')
        sport = "unknown"
        for s in ["Tennis", "Soccer", "Basketball", "Volleyball", "Table Tennis", "Badminton", "Ice Hockey", "Baseball"]:
            if s in text:
                sport = s.lower().replace(" ", "")
                break
                
        match_name = ""
        lines = re.split(r'\\n|\\s{2,}', text)
        print(f"\\nTrying to parse text: {text[:100]}...")
        for line in lines:
            line = line.strip()
            if " - " in line and len(line) > 5 and not "for Team" in line and not "AH" in line:
                parts = line.split(" - ")
                if len(parts) >= 2:
                    match_name = f"{parts[0].strip()} - {parts[1].strip()}"
                    print(f"  -> Found match name: {match_name}")
                    break
                    
        if not match_name:
            m = re.search(r'([A-Za-z\\.\\s]+)\\s+-\\s+([A-Za-z\\.\\s]+)', text)
            if m:
                match_name = f"{m.group(1).strip()} - {m.group(2).strip()}"
                print(f"  -> Fallback found match name: {match_name}")
            else:
                print("  -> FAILED to find match name")
                continue
                
        scores = re.findall(r'\\d+:\\d+', text)
        events.append(match_name)
        
    print(f"Extracted {len(events)} events: {events}")

if __name__ == '__main__':
    test()
