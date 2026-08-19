import asyncio
import subprocess
import os
import sys
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

# Use python executable's directory or workspace for relative files
ARTIFACT_DIR = r"C:\Users\fabio\.gemini\antigravity\brain\504d872b-b0f5-42d5-bde2-624ce9496fab"
os.makedirs(ARTIFACT_DIR, exist_ok=True)

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
            
            # Test direct navigation to B18 (Basketball) in a clean page
            page = await context.new_page()
            await Stealth().apply_stealth_async(page)
            
            url = "https://www.bet365.bet.br/#/B18"
            print(f"Navegando DIRETAMENTE para {url}...")
            await page.goto(url, wait_until="commit", timeout=60000)
            
            print("Aguardando 10 segundos...")
            await asyncio.sleep(10)
            
            # Aceitar cookies se aparecer
            cookie_btn = page.locator("text=Aceitar todos")
            if await cookie_btn.count() > 0:
                print("Aceitando cookies...")
                await cookie_btn.click()
                await asyncio.sleep(5)
            
            body_text = await page.inner_text("body")
            print(f"URL final: {page.url}")
            
            loader_exists = await page.locator(".ovm-Loader, .gl-Loader").count() > 0
            fixtures_count = await page.locator(".ovm-Fixture, .ipe-EventViewDetail").count()
            
            print(f"Loader ativo? {loader_exists}")
            print(f"Total de fixtures: {fixtures_count}")
            
            # Screenshot
            screenshot_path = os.path.join(ARTIFACT_DIR, "test_direct_basketball.png")
            await page.screenshot(path=screenshot_path)
            print(f"Screenshot salvo em {screenshot_path}")
            
            # Print title and snippet
            title = await page.title()
            print(f"Título da página: {title}")
            print(f"Snippet do body: {' '.join(body_text.split())[:300]}")
            
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
