import asyncio
import subprocess
import os
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

# Use python executable's directory or workspace for relative files
ARTIFACT_DIR = r"C:\Users\fabio\.gemini\antigravity\brain\504d872b-b0f5-42d5-bde2-624ce9496fab"
os.makedirs(ARTIFACT_DIR, exist_ok=True)

async def click_and_capture(page, sport_name, file_prefix):
    print(f"\n--- Tentando navegar para {sport_name} pelo menu ---")
    try:
        # Procurar o elemento do esporte no menu superior
        # Pode estar num contêiner com classes de cabeçalho ou menu
        sport_locator = page.locator(f"text={sport_name}")
        if await sport_locator.count() > 0:
            print(f"Elemento '{sport_name}' encontrado. Clicando...")
            await sport_locator.first.click()
            await asyncio.sleep(5)
            print(f"URL após clique em {sport_name}: {page.url}")
            
            # Tirar screenshot
            screenshot_path = os.path.join(ARTIFACT_DIR, f"menu_{file_prefix}.png")
            await page.screenshot(path=screenshot_path)
            print(f"Screenshot salvo em {screenshot_path}")
            
            # Verificar se carregou fixtures
            fixtures_count = await page.locator(".ovm-Fixture, .ipe-EventViewDetail").count()
            print(f"Total de fixtures na tela: {fixtures_count}")
            
            # Tentar extrair alguns nomes de jogos
            if fixtures_count > 0:
                fixture_names = await page.evaluate("""
                    () => {
                        return Array.from(document.querySelectorAll('.ovm-FixtureName_Name, [class*="ParticipantName"], [class*="TeamName"]'))
                            .map(e => e.textContent.trim())
                            .filter(t => t.length > 0 && !/^\\d+$/.test(t))
                            .slice(0, 6);
                    }
                """)
                print(f"Jogos extraídos para {sport_name}: {fixture_names}")
        else:
            print(f"Elemento '{sport_name}' NÃO encontrado no menu.")
    except Exception as e:
        print(f"Erro ao navegar para {sport_name}: {e}")

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
        
    user_data_dir = os.path.join(os.getcwd(), "app", "chrome_data_test")
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
            print("Conectando Playwright...")
            browser = await pw.chromium.connect_over_cdp("http://localhost:9222")
            context = browser.contexts[0]
            page = await context.new_page()
            await Stealth().apply_stealth_async(page)
            
            print("Navegando para a home...")
            await page.goto("https://www.bet365.bet.br/", wait_until="commit", timeout=60000)
            await asyncio.sleep(5)
            
            # Aceitar cookies
            cookie_btn = page.locator("text=Aceitar todos")
            if await cookie_btn.count() > 0:
                print("Aceitando cookies...")
                await cookie_btn.click()
                await asyncio.sleep(3)
                
            # Clicar em Basquete no menu
            await click_and_capture(page, "Basquete", "basketball")
            
            # Clicar em Tênis no menu
            await click_and_capture(page, "Tênis", "tennis")
            
            await page.close()
            
        except Exception as e:
            print(f"Erro: {e}")
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
