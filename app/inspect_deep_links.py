import os
print("Importing bs4...")
from bs4 import BeautifulSoup
print("Imported bs4 successfully!")

def inspect_links():
    print("Beginning inspect_links function...")
    html_path = r"c:\xampp\htdocs\odds_monitor\app\debug_bet365_real.html"
    if not os.path.exists(html_path):
        print(f"File not found: {html_path}")
        return

    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()

    soup = BeautifulSoup(html, 'html.parser')
    
    # Let's find all divs matching the main selectors used in the code
    selectors = [
        '.ovm-Fixture',
        '.ipe-EventViewDetail',
        '[class*="Fixture"][class*="ovm"]',
        '[class*="rcl-ParticipantFixture"]',
        '.gl-Market_General'
    ]
    
    fixtures = []
    for sel in selectors:
        if sel.startswith('.'):
            fixtures = soup.select(sel)
        elif sel.startswith('['):
            # Parse simple attr selectors
            attr = sel.strip('[]').split('*=')
            if len(attr) == 2:
                name, val = attr[0], attr[1].replace('"', '')
                fixtures = soup.find_all(attrs={name: lambda x: x and val in x})
            else:
                fixtures = soup.select(sel)
        else:
            fixtures = soup.select(sel)
            
        print(f"Selector {sel} matched {len(fixtures)} elements")
        if fixtures:
            print(f"Found {len(fixtures)} fixtures using selector: {sel}")
            break

    print(f"Total fixtures to inspect: {len(fixtures)}")


    # Inspect the first 15 fixtures in detail
    for idx, fixture in enumerate(fixtures[:15]):
        print(f"\n--- Fixture {idx+1} ---")
        
        # 1. Names
        names = []
        name_elements = fixture.select('.ovm-FixtureName_Name, [class*="ParticipantName"], [class*="TeamName"], [class*="FixtureDetailsTwoWay_TeamName"]')
        # Filter leaf nodes
        leaf_names = [el.text.strip() for el in name_elements if not el.find(class_=True)]
        names = [n for n in leaf_names if n and not n.isdigit()]
        match_name = " vs ".join(names[:2])
        print(f"Match Name: {match_name}")
        
        # 2. Extract links and attributes using existing strategy
        link_el = fixture.select_one('a[href*="EV"]')
        href = link_el['href'] if link_el else None
        print(f"href selector: {href}")
        
        data_id = fixture.get('data-id')
        data_fixtureid = fixture.get('data-fixtureid')
        data_eventid = fixture.get('data-eventid')
        print(f"Direct attributes: data-id={data_id}, data-fixtureid={data_fixtureid}, data-eventid={data_eventid}")
        
        # Check closest ancestor attributes (simulate closest)
        ancestor_fixtureid = None
        curr = fixture
        while curr:
            if curr.has_attr('data-fixtureid'):
                ancestor_fixtureid = curr['data-fixtureid']
                break
            curr = curr.parent
        print(f"Closest data-fixtureid: {ancestor_fixtureid}")
        
        # Let's find all 'a' elements inside to see if there is a more reliable way
        all_a = fixture.find_all('a')
        print(f"Number of 'a' tags inside: {len(all_a)}")
        for a_idx, a in enumerate(all_a[:5]): # Show up to 5
            print(f"  a[{a_idx}]: href={a.get('href')}, class={a.get('class')}, text={a.text.strip() or '[Empty]'}")

if __name__ == '__main__':
    inspect_links()
