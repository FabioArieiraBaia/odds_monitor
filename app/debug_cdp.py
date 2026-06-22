import asyncio
import subprocess
import os
import time
from playwright.async_api import async_playwright

async def main():
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    user_data_dir = os.path.join(os.getcwd(), "chrome_data")
    port = 9222
    
    print("Iniciando Google Chrome real...")
    process = subprocess.Popen([
        chrome_path,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
    ])
    
    # Aguarda o Chrome iniciar
    time.sleep(3)
    
    async with async_playwright() as p:
        try:
            print("Conectando o Playwright ao Chrome via CDP...")
            browser = await p.chromium.connect_over_cdp(f"http://localhost:{port}")
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else await context.new_page()
            
            print("Acessando Bet365...")
            await page.goto("https://www.bet365.bet.br/#/IP/B13", timeout=60000)
            await asyncio.sleep(10)
            
            await page.screenshot(path="bet365_cdp.png", full_page=True)
            print("Screenshot salvo: bet365_cdp.png")
            
        except Exception as e:
            print(f"Erro: {e}")
        finally:
            print("Fechando navegador...")
            process.terminate()

if __name__ == "__main__":
    asyncio.run(main())
