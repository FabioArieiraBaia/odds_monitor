import asyncio
import subprocess
import os
import sys
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

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
            page = context.pages[0] if context.pages else await context.new_page()
            await Stealth().apply_stealth_async(page)
            
            print("Acessando home da Bet365...")
            await page.goto("https://www.bet365.bet.br/", wait_until="networkidle", timeout=60000)
            
            # Aceitar cookies se aparecer
            cookie_btn = page.locator("text=Aceitar todos")
            if await cookie_btn.count() > 0:
                print("Aceitando cookies...")
                await cookie_btn.click()
                await asyncio.sleep(3)
            
            # Buscar links interessantes
            print("\n--- Analisando Links na Página ---")
            links_info = await page.evaluate("""
                () => {
                    const results = [];
                    // Todos os links
                    document.querySelectorAll('a').forEach(a => {
                        const href = a.getAttribute('href');
                        const text = a.textContent.trim();
                        if (href && (href.includes('#') || href.includes('IP') || text.length > 2)) {
                            results.push({ text, href });
                        }
                    });
                    return results;
                }
            """)
            
            for item in links_info:
                print(f"Texto: '{item['text']}' -> Href: '{item['href']}'")
                
            # Salvar o HTML para inspeção profunda se necessário
            html = await page.content()
            with open("debug_bet365_home.html", "w", encoding="utf-8") as f:
                f.write(html)
            print("\nHTML da home salvo em debug_bet365_home.html")
            
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
