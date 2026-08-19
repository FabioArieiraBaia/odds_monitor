from bs4 import BeautifulSoup

try:
    with open(r'C:\Users\fabio\AppData\Local\Programs\odds_monitor\resources\app\app\1xbet_dump.txt', 'r', encoding='utf-8') as f:
        html = f.read()

    print("Title of the page:", BeautifulSoup(html, 'html.parser').title.string if BeautifulSoup(html, 'html.parser').title else "No title")
    print("Length of HTML:", len(html))
    print("Does it contain 'geo-permission'? ", "geo-permission" in html)
    print("Does it contain 'cookies'? ", "cookies" in html)
    print("Classes found:")
    soup = BeautifulSoup(html, 'html.parser')
    classes = [cls for tag in soup.find_all(class_=True) for cls in tag['class']]
    import collections
    for c, count in collections.Counter(classes).most_common(10):
        print(c, count)
except Exception as e:
    print("Error:", e)
