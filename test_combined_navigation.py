import asyncio
import subprocess
import os
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

# Use python executable's directory or workspace for relative files
ARTIFACT_DIR = r"C:\Users\fabio\.gemini\antigravity\brain\504d872b-b0f5-42d5-bde2-624ce9496fab"
os.makedirs(ARTIFACT_DIR, exist_ok=True)

SPORT_NAMES = {
    "B18": "Basquete",
    "B13": "Tênis",
    "B1": "Futebol"
}

async def navigate_to_sport_combined(page, sport_code):
    sport_name = SPORT_NAMES.get(sport_code)
    print(f"\n--- Navegando para {sport_name} ({sport_code}) ---")
    
    # 1. Tentar clicar no menu lateral usando o elemento folha
    clicked = await page.evaluate(f"""
        () => {{
            const leaf = Array.from(document.querySelectorAll('*'))
                .find(el => {{
                    const t = el.textContent ? el.textContent.trim() : '';
                    return (el.tagName === 'SPAN' || el.tagName === 'DIV') && 
                           t === '{sport_name}' && 
                           el.children.length === 0 &&
                           el.getBoundingClientRect().width > 0;
                }});
            if (leaf) {{
                leaf.click();
                return true;
            }}
            return false;
        }}
    """)
    
    if clicked:
        print(f"Clique no menu lateral para '{sport_name}' efetuado com sucesso.")
        await asyncio.sleep(5)
    else:
        print(f"Item '{sport_name}' não encontrado no menu lateral. Usando page.goto + reload...")
        url = f"https://www.bet365.bet.br/#/{sport_code}"
        await page.goto(url, wait_until="commit", timeout=60000)
        await asyncio.sleep(2)
        await page.reload(wait_until="commit", timeout=60000)
        await asyncio.sleep(5)
        
    url_now = page.url
    fixtures_count = await page.locator(".ovm-Fixture, .ipe-EventViewDetail").count()
    print(f"URL atual: {url_now} | Fixtures na tela: {fixtures_count}")
    
    # Screenshot
    screenshot_path = os.path.join(ARTIFACT_DIR, f"combined_{sport_name.lower()}.png")
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
        return True, fixtures_count, fixture_names
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
        
    user_data_dir = os.path.join(os.getcwd(), "chrome_data")
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
            page = context.pages[0] if context.pages else await context.new_page()
            await page.set_viewport_size({"width": 1920, "height": 1080})
            await Stealth().apply_stealth_async(page)
            
            print("Navegando para a home (Desktop)...")
            await page.goto("https://www.bet365.bet.br/", wait_until="commit", timeout=60000)
            await asyncio.sleep(5)
            
            # Aceitar cookies
            cookie_btn = page.locator("text=Aceitar todos")
            if await cookie_btn.count() > 0:
                print("Aceitando cookies...")
                await cookie_btn.click()
                await asyncio.sleep(3)
                
            # Testar Basquete
            success_b, count_b, list_b = await navigate_to_sport_combined(page, "B18")
            
            # Testar Tênis
            success_t, count_t, list_t = await navigate_to_sport_combined(page, "B13")
            
            # Testar Futebol
            success_f, count_f, list_f = await navigate_to_sport_combined(page, "B1")
            
            print("\n================ COMBINED SUMMARY ================")
            print(f"Basquete (B18): Sucesso={success_b}, Fixtures={count_b}")
            print(f"Tênis (B13): Sucesso={success_t}, Fixtures={count_t}")
            print(f"Futebol (B1): Sucesso={success_f}, Fixtures={count_f}")
            print("==================================================")
            
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
