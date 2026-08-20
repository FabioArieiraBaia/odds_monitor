"""
Validation script to test BetBurger authentication and live feed scraping.
"""
import sys
import os
import asyncio
import logging
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("test_betburger")

# Add app directory to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

load_dotenv()

from sources.betburger_source import BetBurgerScraper


async def test_betburger_login_and_scrape():
    print("=" * 65)
    print("🍔 VALIDANDO AUTENTICAÇÃO E DADOS DA BETBURGER")
    print("=" * 65)

    email = os.getenv("BETBURGER_EMAIL", "")
    password = os.getenv("BETBURGER_PASSWORD", "")
    
    print(f"📧 E-mail configurado: {email}")
    print(f"🔑 Senha configurada : {'*' * len(password)}")
    assert email and password, "Credenciais não encontradas no .env"

    scraper = BetBurgerScraper(email=email, password=password, headless=False)
    print("\n🚀 1. Iniciando navegador Chrome para BetBurger (porta 9223)...")
    try:
        await scraper.start()
        print("✅ Navegador BetBurger iniciado e conectado via CDP!")

        print("\n🔐 2. Efetuando login no BetBurger...")
        login_success = await scraper._login()
        print(f"   Resultado do login: {'✅ SUCESSO' if login_success else '⚠️ Não foi necessário ou pendente'}")

        print("\n⏳ Aguardando 6 segundos para carregamento dos feeds ao vivo...")
        await asyncio.sleep(6)

        print("\n📥 3. Extraindo eventos ao vivo do BetBurger...")
        events = await scraper.fetch_live_events()
        print(f"✅ Total de eventos recebidos do BetBurger: {len(events)}")

        if events:
            print("\n📋 Primeiras partidas extraídas do BetBurger:")
            for i, ev in enumerate(events[:6], 1):
                print(f"   [{i}] 🏓 {ev.match_name}")
                print(f"       Sets: {ev.set_score} | Game: {ev.game_score} | Pts: {ev.point_score}")
                print(f"       Link: {ev.deep_link}")
                if ev.extra_data:
                    print(f"       Extra: {ev.extra_data}")
        else:
            print("⚠️ Nenhum evento foi retornado na primeira extração. Verificando URL atual...")
            current_url = scraper.page.url if scraper.page else "N/A"
            print(f"   URL atual: {current_url}")

    except Exception as e:
        print(f"❌ Erro durante o teste do BetBurger: {e}")
        logger.exception(e)
    finally:
        print("\n🛑 Encerrando navegador de teste do BetBurger...")
        await scraper.stop()

    print("\n" + "=" * 65)
    print("VALIDAÇÃO DA BETBURGER CONCLUÍDA.")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(test_betburger_login_and_scrape())
