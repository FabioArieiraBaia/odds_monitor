import re
from bs4 import BeautifulSoup

def analyze():
    with open('debug_bet365.html', 'r', encoding='utf-8') as f:
        html = f.read()
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Try to find teams or scores
    elements = soup.find_all(class_=re.compile(r'(participant|team|score|fixture|event|name)', re.I))
    
    classes_found = set()
    for el in elements:
        if el.has_attr('class'):
            classes_found.add(" ".join(el['class']))
            
    print("Possíveis classes para as partidas:")
    for c in list(classes_found)[:40]:
        print(f"- {c}")
        
    print(f"\nTotal de elementos encontrados: {len(elements)}")

if __name__ == '__main__':
    analyze()
