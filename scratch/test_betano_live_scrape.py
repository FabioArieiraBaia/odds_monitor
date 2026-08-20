"""
Read-only script to test live Betano scraping and inspect actual received data.
"""
import sys
import os
import asyncio
import logging

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("test_betano")

# Add app directory to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from sources.betano_scraper import BetanoScraper


async def inspect_betano_live():
    print("=" * 65)
    print("🔍 INSPECIONANDO DADOS RECEBIDOS DA BETANO AO VIVO")
    print("=" * 65)

    scraper = BetanoScraper(headless=False)
    print("🚀 Iniciando navegador Chrome para Betano...")
    try:
        await scraper.start()
        print("⏳ Aguardando carregamento da página ao vivo e filtro de Tênis de Mesa...")
        await asyncio.sleep(8)

        print("\n📥 Extraindo eventos ao vivo da Betano...")
        events = await scraper.fetch_live_events()
        print(f"\n📊 Total de partidas de Tênis de Mesa recebidas da Betano: {len(events)}")

        if events:
            print("\n📋 Lista detalhada dos eventos recebidos:")
            for i, ev in enumerate(events, 1):
                print(f"\n--- [Jogo {i}] ---")
                print(f"   🏓 Partida : {ev.match_name}")
                print(f"   🆔 Match ID : {ev.match_id}")
                print(f"   🏆 Esporte  : {ev.sport}")
                print(f"   📊 Sets     : {ev.set_score}")
                print(f"   🎯 Game     : {ev.game_score}")
                print(f"   🔢 Pts      : {ev.point_score}")
                print(f"   🔗 Link     : {ev.deep_link}")
                if ev.extra_data:
                    print(f"   ℹ️ Extra    : {ev.extra_data}")
        else:
            print("⚠️ Nenhum evento foi extraído na primeira tentativa. Testando segunda extração...")
            await asyncio.sleep(4)
            events = await scraper.fetch_live_events()
            print(f"📊 Segunda tentativa: {len(events)} eventos")
            for i, ev in enumerate(events, 1):
                print(f"   [{i}] {ev.match_name} | Sets: {ev.set_score} | Game: {ev.game_score} | Link: {ev.deep_link}")

    except Exception as e:
        print(f"❌ Erro durante teste da Betano: {e}")
    finally:
        print("\n🛑 Encerrando navegador de teste...")
        await scraper.stop()

    print("\n" + "=" * 65)
    print("TESTE DE INSPEÇÃO DA BETANO CONCLUÍDO.")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(inspect_betano_live())
