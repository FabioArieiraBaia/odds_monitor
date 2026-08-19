import asyncio
import subprocess
import os
import sys
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

# Use python executable's directory or workspace for relative files
ARTIFACT_DIR = r"C:\Users\fabio\.gemini\antigravity\brain\504d872b-b0f5-42d5-bde2-624ce9496fab"
os.makedirs(ARTIFACT_DIR, exist_ok=True)

async def run_stage1_accept_cookies(chrome_path, user_data_dir):
    print("\n=== ESTÁGIO 1: Aceitando e salvando cookies no disco ===")
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
            
            print("Carregando homepage para aceitar cookies...")
            await page.goto("https://www.bet365.bet.br/", wait_until="commit", timeout=60000)
            await asyncio.sleep(5)
            
            cookie_btn = page.locator("text=Aceitar todos")
            if await cookie_btn.count() > 0:
                print("Botão de cookies encontrado! Clicando...")
                await cookie_btn.click()
                await asyncio.sleep(3)
                print("Cookies aceitos com sucesso.")
            else:
                print("Cookies já aceitos ou banner não visível.")
                
            await page.close()
            await browser.close()
        except Exception as e:
            print(f"Erro no Estágio 1: {e}")
        finally:
            print("Fechando Chrome do Estágio 1...")
            chrome_process.terminate()
            chrome_process.wait(timeout=5)
            
            # Limpeza final de processos
            try:
                subprocess.run(
                    'for /f "tokens=5" %a in (\'netstat -ano ^| findstr :9222\') do taskkill /PID %a /T /F',
                    shell=True, capture_output=True, timeout=5
                )
            except:
                pass

async def run_stage2_direct_hash(chrome_path, user_data_dir):
    print("\n=== ESTÁGIO 2: Carregando rota com hash diretamente ===")
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
            
            # Navegar DIRETAMENTE para a rota de basquete com hash
            url = "https://www.bet365.bet.br/#/B18"
            print(f"Navegando DIRETAMENTE para {url} (deve usar cookies persistidos)...")
            await page.goto(url, wait_until="commit", timeout=60000)
            
            print("Aguardando 10 segundos para ver se renderiza sem travar no loader...")
            await asyncio.sleep(10)
            
            url_now = page.url
            print(f"URL final: {url_now}")
            
            # Tirar screenshot
            screenshot_path = os.path.join(ARTIFACT_DIR, "saved_cookies_basketball.png")
            await page.screenshot(path=screenshot_path)
            print(f"Screenshot salvo em {screenshot_path}")
            
            fixtures_count = await page.locator(".ovm-Fixture, .ipe-EventViewDetail").count()
            print(f"Total de fixtures na tela: {fixtures_count}")
            
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
            await browser.close()
        except Exception as e:
            print(f"Erro no Estágio 2: {e}")
        finally:
            print("Fechando Chrome do Estágio 2...")
            chrome_process.terminate()
            chrome_process.wait(timeout=5)
            try:
                subprocess.run(
                    'for /f "tokens=5" %a in (\'netstat -ano ^| findstr :9222\') do taskkill /PID %a /T /F',
                    shell=True, capture_output=True, timeout=5
                )
            except:
                pass

async def main():
    possible_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    ]
    chrome_path = next((p for p in possible_paths if os.path.exists(p)), None)
    if not chrome_path:
        print("Chrome não encontrado")
        return
        
    user_data_dir = os.path.join(os.getcwd(), "app", "chrome_data_test")
    
    # Executar estágio 1
    await run_stage1_accept_cookies(chrome_path, user_data_dir)
    
    # Executar estágio 2
    await run_stage2_direct_hash(chrome_path, user_data_dir)

if __name__ == "__main__":
    asyncio.run(main())
