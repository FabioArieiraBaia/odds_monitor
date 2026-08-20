"""
Live validation test: tests real feed fetching from 1xBet, StateCache pairing,
DivergenceDetector temporal tracking and UI serialization without starting Chrome.
"""
import sys
import os
import asyncio
from datetime import datetime

# Configure stdout encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Add app directory to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from core.normalizer import NormalizedEvent
from core.state_cache import StateCache
from core.divergence_detector import DivergenceDetector
from sources.onexbet_scraper import OneXBetScraper
from main import build_active_matches_payload


async def run_live_test():
    print("=" * 60)
    print("INICIANDO TESTE COM DADOS REAIS AO VIVO")
    print("=" * 60)

    # 1. Test 1xBet real live API
    scraper = OneXBetScraper()
    print("[1/4] Conectando a API ao vivo da 1xBet...")
    events = await scraper.fetch_live_events()
    print(f"[OK] Total de eventos reais recebidos da 1xBet: {len(events)}")
    assert len(events) > 0, "Deveria receber pelo menos 1 evento ao vivo da 1xBet"

    for ev in events[:5]:
        print(f"   [TT] {ev.match_name} | Sets: {ev.set_score} | Game: {ev.game_score} | Link: {ev.deep_link}")

    # 2. Test StateCache ingestion
    print("\n[2/4] Testando StateCache e pareamento canonico...")
    cache = StateCache(match_threshold=0.70)
    for ev in events:
        cache.update(ev)

    active_ids = cache.get_all_active_match_ids()
    print(f"[OK] Partidas indexadas no cache: {len(active_ids)}")

    # 3. Simulate Bet365 event slightly delayed for the first real match
    ref_event = events[0]
    # Parse 1xbet score to make a slightly delayed Bet365 score
    s1, s2 = [int(x) for x in ref_event.set_score.split(":")] if ":" in ref_event.set_score else (0, 0)
    g1, g2 = [int(x) for x in ref_event.game_score.split(":")] if ":" in ref_event.game_score else (0, 0)

    # Create delayed score for bet365 (e.g. 1 point behind)
    b365_g1 = max(0, g1 - 1)
    b365_ev = NormalizedEvent(
        match_id=ref_event.match_id,
        match_name=ref_event.match_name,
        sport=ref_event.sport,
        source="bet365",
        set_score=f"{s1}:{s2}",
        game_score=f"{b365_g1}:{g2}",
        point_score="0",
        timestamp=datetime.now(),
        deep_link="https://www.bet365.bet.br/#/IP/EV123456C1"
    )
    cache.update(b365_ev)
    print(f"[OK] Inserido par Bet365 simulado atrasado: B365={b365_ev.game_score} vs 1xBet={ref_event.game_score}")

    # 4. Test Divergence Detector with 0s threshold
    print("\n[3/4] Testando Detector de Divergencia Temporal...")
    detector = DivergenceDetector(state_cache=cache, freeze_threshold_seconds=0.0)
    alerts = detector.check_divergences()
    print(f"[OK] Alertas gerados pelo detector: {len(alerts)}")
    if alerts:
        a = alerts[0]
        print(f"   [ALERTA] {a['match_name']}")
        print(f"      Bet365: {a['bet365_score']} | 1xBet: {a['xbet_score']}")
        print(f"      Prioridade: {a['priority']} | Confianca: {a['confidence']}%")
        print(f"      Casas a frente: {a['leading_houses']}")

    # 5. Test UI Payload serialization
    print("\n[4/4] Testando serializacao do payload para WebSocket...")
    import main
    main.state_cache = cache
    ui_matches = build_active_matches_payload()
    print(f"[OK] Partidas ativas serializadas para UI: {len(ui_matches)}")
    if ui_matches:
        print(f"   Primeiro card UI: {ui_matches[0]['name']} | Fontes: {list(ui_matches[0]['sources'].keys())}")

    await scraper.stop()
    print("\n" + "=" * 60)
    print("TODOS OS TESTES COM DADOS REAIS FORAM CONCLUIDOS COM SUCESSO!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_live_test())
