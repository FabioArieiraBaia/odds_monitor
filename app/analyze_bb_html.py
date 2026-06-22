import re
from bs4 import BeautifulSoup
import json

def analyze():
    with open('debug_betburger.html', 'r', encoding='utf-8') as f:
        html = f.read()
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Let's find rows
    rows = soup.select('.surebet, .arb, [class*="surebet"], .bet-row, [class*="event-row"]')
    if not rows:
        rows = soup.select('table tbody tr, .main-content .row, [class*="event"]')
        
    print(f"Found {len(rows)} potential rows")
    
    for i, row in enumerate(rows[:5]):
        print(f"\n--- Row {i+1} ---")
        text = row.get_text(separator=' ', strip=True)
        print(f"Raw text: {text[:200]}")
        
        # Look for score-like patterns
        scores = re.findall(r'\d+:\d+', text)
        print(f"Scores found: {scores}")
        
        # Print HTML structure of the row
        print(f"HTML snippet: {str(row)[:300]}")

if __name__ == '__main__':
    analyze()
