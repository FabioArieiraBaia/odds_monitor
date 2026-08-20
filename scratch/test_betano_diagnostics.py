"""
Diagnostic script to test and inspect data received from Betano BR.
Tests direct API endpoints and browser responses (Read-only).
"""
import sys
import os
import asyncio
import aiohttp
import json

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

BETANO_URLS = [
    "https://www.betano.bet.br/api/live/",
    "https://www.betano.bet.br/api/sport/table-tennis/live/",
    "https://www.betano.bet.br/api/live/matches",
    "https://www.betano.bet.br/api/events/live",
    "https://www.betano.bet.br/live/"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.betano.bet.br/live/",
    "Origin": "https://www.betano.bet.br"
}


async def test_betano_api():
    print("=" * 65)
    print("🔍 DIAGNÓSTICO DE DADOS - BETANO BR")
    print("=" * 65)

    timeout = aiohttp.ClientTimeout(total=8, connect=4)
    async with aiohttp.ClientSession(timeout=timeout, headers=HEADERS) as session:
        for url in BETANO_URLS:
            try:
                print(f"\n📡 Testando: {url}")
                async with session.get(url) as response:
                    status = response.status
                    content_type = response.headers.get("Content-Type", "")
                    print(f"   Status HTTP: {status} | Content-Type: {content_type}")
                    
                    text = await response.text()
                    print(f"   Tamanho da resposta: {len(text)} bytes")

                    if "application/json" in content_type:
                        try:
                            data = json.loads(text)
                            print(f"   ✅ JSON válido recebido! Chaves raiz: {list(data.keys()) if isinstance(data, dict) else 'Lista com ' + str(len(data)) + ' itens'}")
                            
                            # Inspect structure
                            if isinstance(data, dict):
                                data_obj = data.get("data", {})
                                if isinstance(data_obj, dict):
                                    print(f"      Chaves em 'data': {list(data_obj.keys())}")
                        except Exception as parse_err:
                            print(f"   ⚠️ Erro ao parsear JSON: {parse_err}")
                    else:
                        preview = text[:200].replace("\n", " ")
                        print(f"   Preview: {preview}...")
            except Exception as e:
                print(f"   ❌ Erro de conexão: {e}")

    print("\n" + "=" * 65)


if __name__ == "__main__":
    asyncio.run(test_betano_api())
