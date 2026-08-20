import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app")))

import urllib.request
import json
import time

def validate_live_feed():
    url = "http://127.0.0.1:8005/api/matches"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Validator/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"Erro ao conectar com API do servidor: {e}")
        return

    matches = data if isinstance(data, list) else data.get("matches", [])
    print(f"=== AUDITORIA E VALIDAÇÃO DE DADOS EM TEMPO REAL ===")
    print(f"Timestamp: {time.strftime('%H:%M:%S')}")
    print(f"Total de partidas ativas no cache: {len(matches)}\n")

    for i, m in enumerate(matches, 1):
        name = m.get("name")
        sources = m.get("sources", {})
        
        b365 = sources.get("bet365")
        betano = sources.get("betano")
        xbet = sources.get("1xbet") or sources.get("betburger")
        
        print(f"[{i}] PARTIDA: {name}")
        print(f"    - Bet365:   Sets={b365.get('set_score') if b365 else 'N/D'} | Game={b365.get('game_score') if b365 else 'N/D'} | Pts={b365.get('point_score') if b365 else 'N/D'}")
        print(f"    - Betano:   Sets={betano.get('set_score') if betano else 'N/D'} | Game={betano.get('game_score') if betano else 'N/D'} | Pts={betano.get('point_score') if betano else 'N/D'}")
        print(f"    - 1xBet:    Sets={xbet.get('set_score') if xbet else 'N/D'} | Game={xbet.get('game_score') if xbet else 'N/D'} | Pts={xbet.get('point_score') if xbet else 'N/D'}")
        
        # Check links
        b365_link = m.get("bet365_link", "")
        print(f"    - Link Bet365: {b365_link[:60] if b365_link else 'N/D'}...")
        print("-" * 65)

if __name__ == "__main__":
    validate_live_feed()
