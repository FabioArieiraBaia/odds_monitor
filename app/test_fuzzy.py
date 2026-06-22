import difflib

def match_score(name1, name2):
    n1 = name1.lower()
    n2 = name2.lower()
    
    ratio = difflib.SequenceMatcher(None, n1, n2).ratio()
    
    t1 = set([t for t in n1.replace('/', ' ').replace('-', ' ').replace(',', ' ').split() if len(t) >= 3])
    t2 = set([t for t in n2.replace('/', ' ').replace('-', ' ').replace(',', ' ').split() if len(t) >= 3])
    
    # Partial token matching (if one token is a substring of another)
    match_count = 0
    for token1 in t1:
        for token2 in t2:
            if token1 in token2 or token2 in token1:
                match_count += 1
                break
                
    t1_len = len(t1) if len(t1) > 0 else 1
    t2_len = len(t2) if len(t2) > 0 else 1
    token_ratio = match_count / min(t1_len, t2_len)
    
    return ratio, token_ratio

pairs = [
    ("H Roh vs M Bouzige", "Roh, Hoyoung - Bouzi"),
    ("J Delaney vs M Purcell", "Delaney, Jesse - Purcell, Max"),
    ("T Sach vs M Imamura", "Tai Sach - Masamichi Imamura"),
    ("Y Kitahara vs T Naklo", "Kitahara, Y - Naklo, Thasaporn"),
    ("N Kawaguchi/A Shimizu vs J Jeng/Y Tzeng", "N.Kawaguchi/A.Shimizu - J.Jeng/Y.Tzeng"),
    ("M Kawamura/Y Ohwaki vs R Kosaka/M Uemura", "Kawamura M. / Ohwaki Y. - Kosaka R. / Uemura M."),
    ("C Shek vs E Desvignes", "Shek, C - Desvignes, E")
]

for p1, p2 in pairs:
    r, tr = match_score(p1, p2)
    print(f"[{r:.2f} | {tr:.2f}] {p1}  <==>  {p2}")
