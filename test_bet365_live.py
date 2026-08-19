import asyncio
import subprocess
import os
import time
import re
import sys
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

# Use python executable's directory or workspace for relative files
ARTIFACT_DIR = r"C:\Users\fabio\.gemini\antigravity\brain\504d872b-b0f5-42d5-bde2-624ce9496fab"
os.makedirs(ARTIFACT_DIR, exist_ok=True)

async def test_url_with_cookies(page, name, url, expected_text):
    print(f"\n--- Testando link [{name}]: {url} ---")
    try:
        # Navigate to the page
        print(f"Navegando para {url}...")
        await page.goto(url, wait_until="commit", timeout=30000)
        
        # Wait a bit for page to load
        await asyncio.sleep(5)
        
        # Click "Aceitar todos" if cookie banner is visible
        cookie_btn = page.locator("text=Aceitar todos")
        if await cookie_btn.count() > 0:
            print("Banner de cookies detectado. Clicando em 'Aceitar todos'...")
            try:
                await cookie_btn.click()
                await asyncio.sleep(2)
                print("Banner clicado.")
            except Exception as e:
                print(f"Erro ao clicar no banner: {e}")
                
        # Wait for React SPA routing
        await asyncio.sleep(5)
        
        # Check if we need to force location hash
        hash_code = url.split("#")[-1]
        print(f"Forçando window.location.hash = '{hash_code}'...")
        await page.evaluate(f"window.location.hash = '{hash_code}';")
        await asyncio.sleep(8)
        
        body_text = await page.inner_text("body")
        url_now = page.url
        print(f"URL atual após navegação e hash forçado: {url_now}")
        
        loader_exists = await page.locator(".ovm-Loader, .gl-Loader").count() > 0
        fixtures_count = await page.locator(".ovm-Fixture, .ipe-EventViewDetail").count()
        
        print(f"Loader na tela? {'SIM' if loader_exists else 'NÃO'}")
        print(f"Total de fixtures (.ovm-Fixture / .ipe-EventViewDetail) encontrados: {fixtures_count}")
        
        # Save screenshot
        screenshot_path = os.path.join(ARTIFACT_DIR, f"test_cookies_{name}.png")
        await page.screenshot(path=screenshot_path, full_page=False)
        print(f"Screenshot salvo em: {screenshot_path}")
        
        text_found = expected_text.lower() in body_text.lower()
        print(f"Texto esperado '{expected_text}' encontrado no body? {'SIM' if text_found else 'NÃO'}")
        
        clean_text = " ".join(body_text.split())[:300]
        print(f"Snippet do Body: {clean_text}")
        
        # Extract matches
        if fixtures_count > 0:
            fixture_names = await page.evaluate("""
                () => {
                    const names = Array.from(document.querySelectorAll('.ovm-FixtureName_Name, [class*="ParticipantName"], [class*="TeamName"]'))
                        .map(e => e.textContent.trim())
                        .filter(t => t.length > 0 && !/^\\d+$/.test(t));
                    return names.slice(0, 6);
                }
            """)
            print(f"Nomes de equipes/jogadores extraídos: {fixture_names}")
            
            events_info = await page.evaluate("""
                () => {
                    const links = Array.from(document.querySelectorAll('a[href*="EV"], [data-fixtureid], [data-eventid]'))
                        .map(e => {
                            return {
                                href: e.getAttribute('href'),
                                fid: e.getAttribute('data-fixtureid'),
                                eid: e.getAttribute('data-eventid')
                            };
                        });
                    return links.slice(0, 3);
                }
            """)
            print(f"Exemplos de links/IDs de eventos encontrados: {events_info}")
            
        return {
            "success": fixtures_count > 0 or text_found,
            "url_now": url_now,
            "fixtures_count": fixtures_count,
            "screenshot": f"test_cookies_{name}.png",
            "body_snippet": clean_text
        }
    except Exception as e:
        print(f"Erro ao testar link {name}: {e}")
        return {"success": False, "error": str(e)}

async def main():
    print("Limpando processos na porta 9222...")
    try:
        subprocess.run(
            'for /f "tokens=5" %a in (\'netstat -ano ^| findstr :9222\') do taskkill /PID %a /T /F',
            shell=True, capture_output=True, timeout=5
        )
    except Exception as e:
        print(f"Erro na limpeza de porta: {e}")

    possible_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    ]
    chrome_path = next((p for p in possible_paths if os.path.exists(p)), None)
    if not chrome_path:
        print("ERRO: Google Chrome ou Microsoft Edge não encontrado!")
        sys.exit(1)
        
    user_data_dir = os.path.join(os.getcwd(), "app", "chrome_data_test")
    port = 9222
    
    chrome_process = subprocess.Popen([
        chrome_path,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
    ])
    
    await asyncio.sleep(5)
    
    async with async_playwright() as pw:
        try:
            print(f"Conectando o Playwright ao Chrome via CDP na porta {port}...")
            browser = await pw.chromium.connect_over_cdp(f"http://localhost:{port}", timeout=30000)
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            page = context.pages[0] if context.pages else await context.new_page()
            await Stealth().apply_stealth_async(page)
            
            # Navigar para a home primeiro para limpar cookie banner
            print("Acessando home da Bet365 para aceitar cookies...")
            await page.goto("https://www.bet365.bet.br/", wait_until="commit", timeout=30000)
            await asyncio.sleep(5)
            cookie_btn = page.locator("text=Aceitar todos")
            if await cookie_btn.count() > 0:
                print("Aceitando cookies na home...")
                await cookie_btn.click()
                await asyncio.sleep(3)
            
            # Teste 1: Basquete novo (#/B18)
            res_basketball_new = await test_url_with_cookies(
                page, 
                "basketball_new", 
                "https://www.bet365.bet.br/#/B18", 
                "Basquete"
            )
            
            # Teste 2: Tênis de Mesa novo (#/B92)
            res_tabletennis_new = await test_url_with_cookies(
                page, 
                "tabletennis_new", 
                "https://www.bet365.bet.br/#/B92", 
                "Mesa"
            )
            
            # Teste 3: Tênis novo (#/B13)
            res_tennis_new = await test_url_with_cookies(
                page, 
                "tennis_new", 
                "https://www.bet365.bet.br/#/B13", 
                "Tênis"
            )
            
            print("\n================ TEST SUMMARY ================")
            print(f"Basquete Novo (#/B18): Sucesso={res_basketball_new.get('success')}, Fixtures={res_basketball_new.get('fixtures_count', 0)}")
            print(f"Tênis de Mesa Novo (#/B92): Sucesso={res_tabletennis_new.get('success')}, Fixtures={res_tabletennis_new.get('fixtures_count', 0)}")
            print(f"Tênis Novo (#/B13): Sucesso={res_tennis_new.get('success')}, Fixtures={res_tennis_new.get('fixtures_count', 0)}")
            print("==============================================")
            
        except Exception as err:
            print(f"Erro durante a execução do teste: {err}")
        finally:
            print("Fechando conexões...")
            try:
                await browser.close()
            except:
                pass
            
            try:
                chrome_process.terminate()
                chrome_process.wait(timeout=5)
            except:
                try:
                    chrome_process.kill()
                except:
                    pass
                
            try:
                subprocess.run(
                    'for /f "tokens=5" %a in (\'netstat -ano ^| findstr :9222\') do taskkill /PID %a /T /F',
                    shell=True, capture_output=True, timeout=5
                )
            except:
                pass

if __name__ == "__main__":
    asyncio.run(main())
