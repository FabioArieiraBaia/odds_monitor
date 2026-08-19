import asyncio
import subprocess
import os
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
            
            page.on("console", lambda msg: print(f"[Console {msg.type.upper()}] {msg.text}"))
            
            # Navegar para a home primeiro
            print("Carregando home...")
            await page.goto("https://www.bet365.bet.br/", wait_until="commit", timeout=60000)
            await asyncio.sleep(5)
            
            # Aceitar cookies
            cookie_btn = page.locator("text=Aceitar todos")
            if await cookie_btn.count() > 0:
                await cookie_btn.click()
                await asyncio.sleep(2)
                
            # Clicar em Ao-Vivo no topo
            print("Clicando em Ao-Vivo...")
            await page.evaluate("""
                () => {
                    const btn = Array.from(document.querySelectorAll('*'))
                        .find(el => {
                            const t = el.textContent ? el.textContent.trim() : '';
                            return (t === 'Ao-Vivo' || t === 'Ao Vivo') && el.getBoundingClientRect().y < 120;
                        });
                    if (btn) btn.click();
                }
            """)
            
            # Aguardar 30 segundos
            print("Aguardando 30 segundos para ver se o loader some...")
            for i in range(1, 7):
                await asyncio.sleep(5)
                loader_exists = await page.locator(".ovm-Loader, .gl-Loader").count() > 0
                fixtures_count = await page.locator(".ovm-Fixture, .ipe-EventViewDetail").count()
                print(f"[{i*5}s] Loader ativo? {loader_exists} | Fixtures na tela: {fixtures_count}")
                
            # Screenshot final
            screenshot_path = os.path.join(ARTIFACT_DIR, "long_wait_aovivo.png")
            await page.screenshot(path=screenshot_path)
            print(f"Screenshot salvo em {screenshot_path}")
            
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
