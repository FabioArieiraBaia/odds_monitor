import asyncio
import subprocess
import os
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
            page = await context.new_page()
            await page.set_viewport_size({"width": 1920, "height": 1080})
            await Stealth().apply_stealth_async(page)
            
            print("Navegando para a rota com hash #/B18...")
            await page.goto("https://www.bet365.bet.br/#/B18", wait_until="commit", timeout=60000)
            await asyncio.sleep(8)
            
            # Localizar elemento centralizado (loader)
            elements_info = await page.evaluate("""
                () => {
                    const results = [];
                    const allEls = document.querySelectorAll('*');
                    allEls.forEach(el => {
                        const rect = el.getBoundingClientRect();
                        // Procurar elementos próximos ao centro (960, 540) com tamanho razoável (por exemplo, 20px a 100px)
                        const isCenter = Math.abs(rect.left + rect.width/2 - 960) < 50 && 
                                         Math.abs(rect.top + rect.height/2 - 540) < 50;
                        if (isCenter && rect.width > 0 && rect.width < 300) {
                            results.push({
                                tagName: el.tagName,
                                className: el.className,
                                id: el.id,
                                rect: { x: rect.x, y: rect.y, w: rect.width, h: rect.height },
                                outerHTML: el.outerHTML.slice(0, 150)
                            });
                        }
                    });
                    return results;
                }
            """)
            
            print("\nElementos centralizados encontrados:")
            for idx, el in enumerate(elements_info):
                print(f"[{idx}] Tag: {el['tagName']}, Class: {el['className']}, ID: {el['id']}")
                print(f"    Rect: {el['rect']}")
                print(f"    HTML: {el['outerHTML']}")
                
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
