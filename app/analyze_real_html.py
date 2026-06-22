import re
from bs4 import BeautifulSoup
import json

def analyze():
    with open('debug_bet365_real.html', 'r', encoding='utf-8') as f:
        html = f.read()
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # We want to find common strings for tennis matches. 
    # Usually we can find the name of players or some score formats.
    # Let's just grab all div classes and count them to see the most common ones 
    # that might represent rows or participants.
    
    class_counts = {}
    divs = soup.find_all('div')
    for d in divs:
        if d.has_attr('class'):
            c_str = " ".join(d['class'])
            class_counts[c_str] = class_counts.get(c_str, 0) + 1
            
    sorted_classes = sorted(class_counts.items(), key=lambda x: x[1], reverse=True)
    print("Classes mais frequentes (Top 20):")
    for c, count in sorted_classes[:20]:
        print(f"{count}x: {c}")
        
    print("\nProcurando por palavras chave 'Fixture', 'Participant', 'Event', 'Team':")
    for c, count in sorted_classes:
        c_lower = c.lower()
        if 'fixture' in c_lower or 'participant' in c_lower or 'event' in c_lower or 'team' in c_lower:
            print(f"{count}x: {c}")

if __name__ == '__main__':
    analyze()
