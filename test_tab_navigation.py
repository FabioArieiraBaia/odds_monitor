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
            
            print("Navegando para a home...")
            await page.goto("https://www.bet365.bet.br/", wait_until="commit", timeout=60000)
            await asyncio.sleep(5)
            
            # Aceitar cookies
            cookie_btn = page.locator("text=Aceitar todos")
            if await cookie_btn.count() > 0:
                print("Aceitando cookies...")
                await cookie_btn.click()
                await asyncio.sleep(3)
                
            # Listar todos os botões na tab bar
            tab_buttons = await page.evaluate("""
                () => {
                    const buttons = Array.from(document.querySelectorAll('div[class*="TabBar"], [class*="tbm-c"] a, [class*="tbm-c"] div'));
                    return buttons.map((b, idx) => ({
                        index: idx,
                        text: b.textContent.trim(),
                        tagName: b.tagName,
                        classes: b.className
                    })).filter(b => b.text.length > 0);
                }
            """)
            
            print("Botões encontrados na TabBar:")
            for b in tab_buttons:
                print(f"Index {b['index']}: '{b['text']}' ({b['tagName']} class='{b['classes']}')")
                
            # Tentar clicar no botão que diz "Ao-Vivo" especificando a classe ou tag
            print("Clicando no botão 'Ao-Vivo' da TabBar...")
            # Encontrar o index do botão Ao-Vivo
            ao_vivo_btn = page.locator("a:has-text('Ao-Vivo'), div:has-text('Ao-Vivo')").first
            if await ao_vivo_btn.count() > 0:
                await ao_vivo_btn.click()
                print("Botão clicado.")
            else:
                print("Botão Ao-Vivo não encontrado.")
                
            await asyncio.sleep(8)
            print(f"URL final: {page.url}")
            
            # Tirar screenshot
            screenshot_path = os.path.join(ARTIFACT_DIR, "tab_ao_vivo.png")
            await page.screenshot(path=screenshot_path)
            print(f"Screenshot salvo em {screenshot_path}")
            
            # Verificar o conteúdo da página Ao-Vivo
            body_text = await page.inner_text("body")
            print(f"Snippet do body: {' '.join(body_text.split())[:300]}")
            
            fixtures_count = await page.locator(".ovm-Fixture, .ipe-EventViewDetail").count()
            print(f"Total de fixtures na tela: {fixtures_count}")
            
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
