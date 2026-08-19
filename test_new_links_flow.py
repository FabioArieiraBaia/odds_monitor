import asyncio
import subprocess
import os
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

# Use python executable's directory or workspace for relative files
ARTIFACT_DIR = r"C:\Users\fabio\.gemini\antigravity\brain\504d872b-b0f5-42d5-bde2-624ce9496fab"
os.makedirs(ARTIFACT_DIR, exist_ok=True)

async def test_sport_flow(page, sport_name, code, file_prefix):
    print(f"\n--- Testando fluxo para {sport_name} ({code}) ---")
    url = f"https://www.bet365.bet.br/#/{code}"
    try:
        # Navega para a URL com hash
        print(f"Navegando para {url}...")
        await page.goto(url, wait_until="commit", timeout=60000)
        await asyncio.sleep(3)
        
        # Recarrega a página para forçar o carregamento limpo com o hash setado
        print("Recarregando a página para forçar o roteamento do hash...")
        await page.reload(wait_until="commit", timeout=60000)
        
        # Aguarda o carregamento dos eventos
        print("Aguardando 10 segundos para renderizar eventos...")
        await asyncio.sleep(10)
        
        body_text = await page.inner_text("body")
        print(f"URL atual: {page.url}")
        
        fixtures_count = await page.locator(".ovm-Fixture, .ipe-EventViewDetail").count()
        print(f"Total de fixtures encontrados: {fixtures_count}")
        
        # Screenshot
        screenshot_path = os.path.join(ARTIFACT_DIR, f"flow_{file_prefix}.png")
        await page.screenshot(path=screenshot_path)
        print(f"Screenshot salvo em {screenshot_path}")
        
        # Verificar texto
        text_found = sport_name.lower() in body_text.lower()
        print(f"Texto '{sport_name}' no body? {text_found}")
        
        # Extrair dados
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
            
            # Tentar rodar o extrator do robô para ver se encontra eventos estruturados
            events_data = await page.evaluate("""
                () => {
                    const results = [];
                    const fixtures = Array.from(document.querySelectorAll('.ovm-Fixture, .ipe-EventViewDetail'));
                    for (const f of fixtures) {
                        const nameEls = Array.from(f.querySelectorAll('.ovm-FixtureName_Name, [class*="ParticipantName"], [class*="TeamName"]'))
                            .map(e => e.textContent.trim())
                            .filter(t => t.length > 0 && !/^\\d+$/.test(t));
                        if (nameEls.length >= 2) {
                            results.push(nameEls.slice(0, 2).join(' vs '));
                        }
                    }
                    return results;
                }
            """)
            print(f"Nomes de eventos estruturados extraídos: {events_data[:5]}")
            
        return fixtures_count > 0
    except Exception as e:
        print(f"Erro no fluxo de {sport_name}: {e}")
        return False

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
            
            print("Passo 1: Acessar a home para aceitar os cookies...")
            await page.goto("https://www.bet365.bet.br/", wait_until="commit", timeout=60000)
            await asyncio.sleep(5)
            
            cookie_btn = page.locator("text=Aceitar todos")
            if await cookie_btn.count() > 0:
                print("Aceitando cookies...")
                await cookie_btn.click()
                await asyncio.sleep(3)
            
            # Passo 2: Testar Basquete (#/B18)
            await test_sport_flow(page, "Basquete", "B18", "basketball")
            
            # Passo 3: Testar Tênis (#/B13)
            await test_sport_flow(page, "Tênis", "B13", "tennis")
            
            # Passo 4: Testar Futebol (#/B1)
            await test_sport_flow(page, "Futebol", "B1", "soccer")
            
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
