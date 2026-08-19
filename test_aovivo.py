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
                
            # Clicar em "Ao-Vivo" no menu inferior
            # Vamos procurar um elemento que contenha "Ao-Vivo" ou "Ao Vivo" ou "ao-vivo"
            print("Tentando clicar no botão Ao-Vivo...")
            
            # Vamos tentar vários seletores possíveis para o botão Ao-Vivo
            selectors = [
                "text=Ao-Vivo",
                "text=Ao Vivo",
                ".tab-bar-item:has-text('Ao-Vivo')",
                ".tab-bar-item:has-text('Ao Vivo')",
                "a[href*='IP']",
                "[class*='TabBar'] >> text=Ao-Vivo",
                "[class*='TabBar'] >> text=Ao Vivo"
            ]
            
            clicked = False
            for sel in selectors:
                loc = page.locator(sel)
                if await loc.count() > 0:
                    print(f"Selector encontrado: {sel}. Clicando...")
                    await loc.first.click()
                    clicked = True
                    break
            
            if not clicked:
                print("Não foi possível encontrar o botão Ao-Vivo usando seletores de texto.")
                # Vamos tentar clicar no elemento usando suas coordenadas ou um seletor genérico
                # Por exemplo, clicar na parte inferior do meio da tela
                viewport = page.viewport_size
                if viewport:
                    x = viewport['width'] / 2
                    y = viewport['height'] - 30
                    print(f"Clicando na coordenada genérica (inferior central): x={x}, y={y}")
                    await page.mouse.click(x, y)
                    clicked = True
            
            await asyncio.sleep(8)
            
            print(f"URL final: {page.url}")
            
            loader_exists = await page.locator(".ovm-Loader, .gl-Loader").count() > 0
            fixtures_count = await page.locator(".ovm-Fixture, .ipe-EventViewDetail").count()
            
            print(f"Loader ativo? {loader_exists}")
            print(f"Total de fixtures na tela Ao-Vivo: {fixtures_count}")
            
            # Screenshot
            screenshot_path = os.path.join(ARTIFACT_DIR, "test_ao_vivo_page.png")
            await page.screenshot(path=screenshot_path)
            print(f"Screenshot salvo em {screenshot_path}")
            
            if fixtures_count > 0:
                fixture_names = await page.evaluate("""
                    () => {
                        return Array.from(document.querySelectorAll('.ovm-FixtureName_Name, [class*="ParticipantName"], [class*="TeamName"]'))
                            .map(e => e.textContent.trim())
                            .filter(t => t.length > 0 && !/^\\d+$/.test(t))
                            .slice(0, 6);
                    }
                """)
                print(f"Jogos Ao-Vivo extraídos: {fixture_names}")
                
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
