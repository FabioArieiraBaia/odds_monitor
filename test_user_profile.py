import asyncio
import subprocess
import os
import sys
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

# Use python executable's directory or workspace for relative files
ARTIFACT_DIR = r"C:\Users\fabio\.gemini\antigravity\brain\504d872b-b0f5-42d5-bde2-624ce9496fab"
os.makedirs(ARTIFACT_DIR, exist_ok=True)

async def test_sport_with_profile(page, sport_name, code):
    print(f"\n--- Testando {sport_name} ({code}) com perfil real ---")
    url = f"https://www.bet365.bet.br/#/{code}"
    try:
        print(f"Navegando para {url}...")
        await page.goto(url, wait_until="commit", timeout=60000)
        await asyncio.sleep(2)
        
        print("Recarregando para garantir o roteamento da SPA...")
        await page.reload(wait_until="commit", timeout=60000)
        await asyncio.sleep(5)
        
        # Tirar screenshot
        screenshot_path = os.path.join(ARTIFACT_DIR, f"profile_{sport_name.lower()}.png")
        await page.screenshot(path=screenshot_path)
        print(f"Screenshot salvo em {screenshot_path}")
        
        fixtures_count = await page.locator(".ovm-Fixture, .ipe-EventViewDetail").count()
        print(f"Fixtures encontrados: {fixtures_count}")
        
        if fixtures_count > 0:
            fixture_names = await page.evaluate("""
                () => {
                    return Array.from(document.querySelectorAll('.ovm-FixtureName_Name, [class*="ParticipantName"], [class*="TeamName"]'))
                        .map(e => e.textContent.trim())
                        .filter(t => t.length > 0 && !/^\\d+$/.test(t))
                        .slice(0, 6);
                }
            """)
            print(f"Jogos extraídos: {fixture_names}")
            return True, fixtures_count, fixture_names
        else:
            # Print body text to debug if still stuck or other page
            body_text = await page.inner_text("body")
            print(f"Snippet do Body: {' '.join(body_text.split())[:200]}")
            return False, 0, []
            
    except Exception as e:
        print(f"Erro ao testar {sport_name}: {e}")
        return False, 0, []

async def main():
    print("Limpando processos na porta 9222...")
    try:
        subprocess.run(
            'for /f "tokens=5" %a in (\'netstat -ano ^| findstr :9222\') do taskkill /PID %a /T /F',
            shell=True, capture_output=True, timeout=5
        )
    except:
        pass

    possible_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    ]
    chrome_path = next((p for p in possible_paths if os.path.exists(p)), None)
    if not chrome_path:
        print("Chrome não encontrado")
        return
        
    # Usar a pasta REAL de perfil do robô
    user_data_dir = os.path.join(os.getcwd(), "chrome_data")
    print(f"Usando diretório de perfil real: {user_data_dir}")
    
    chrome_process = subprocess.Popen([
        chrome_path,
        f"--remote-debugging-port=9222",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
    ])
    
    await asyncio.sleep(5)
    
    async with async_playwright() as pw:
        try:
            print("Conectando Playwright ao Chrome real...")
            browser = await pw.chromium.connect_over_cdp("http://localhost:9222")
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else await context.new_page()
            await Stealth().apply_stealth_async(page)
            
            # Testar Basquete
            success_b, count_b, list_b = await test_sport_with_profile(page, "Basquete", "B18")
            
            # Testar Tênis
            success_t, count_t, list_t = await test_sport_with_profile(page, "Tênis", "B13")
            
            # Testar Futebol
            success_s, count_s, list_s = await test_sport_with_profile(page, "Futebol", "B1")
            
            print("\n================ PROFILE TEST SUMMARY ================")
            print(f"Basquete (B18): Sucesso={success_b}, Fixtures={count_b}, Amostra={list_b[:2]}")
            print(f"Tênis (B13): Sucesso={success_t}, Fixtures={count_t}, Amostra={list_t[:2]}")
            print(f"Futebol (B1): Sucesso={success_s}, Fixtures={count_s}, Amostra={list_s[:2]}")
            print("======================================================")
            
            await page.close()
            
        except Exception as e:
            print(f"Erro Geral: {e}")
        finally:
            try:
                await browser.close()
            except:
                pass
            try:
                chrome_process.terminate()
            except:
                pass

if __name__ == "__main__":
    asyncio.run(main())
