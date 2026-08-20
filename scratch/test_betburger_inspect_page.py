"""
Diagnostic script to inspect the BetBurger sign_in page HTML and form fields.
"""
import sys
import os
import asyncio

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Add app directory to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from sources.betburger_source import BetBurgerScraper


async def inspect_sign_in_page():
    scraper = BetBurgerScraper(email="fabioarieira2@gmail.com", password="t3r3z422F@", headless=False)
    try:
        await scraper.start()
        await scraper.page.goto("https://www.betburger.com/users/sign_in", timeout=30000)
        await asyncio.sleep(4)

        # Inspect inputs and buttons on page
        info = await scraper.page.evaluate("""() => {
            const inputs = Array.from(document.querySelectorAll('input')).map(i => ({
                id: i.id,
                name: i.name,
                type: i.type,
                placeholder: i.placeholder,
                isVisible: i.offsetParent !== null
            }));
            const buttons = Array.from(document.querySelectorAll('button, a.btn, input[type="submit"]')).map(b => ({
                tag: b.tagName,
                text: b.innerText.trim(),
                id: b.id,
                name: b.name,
                type: b.type
            }));
            const title = document.title;
            const bodyPreview = document.body ? document.body.innerText.slice(0, 300) : '';
            return { title, inputs, buttons, bodyPreview };
        }""")

        print("=== BETBURGER SIGN IN PAGE INFO ===")
        print("Title:", info.get("title"))
        print("\nInputs found:")
        for inp in info.get("inputs", []):
            print(" ", inp)
        print("\nButtons found:")
        for btn in info.get("buttons", []):
            print(" ", btn)
        print("\nBody preview:\n", info.get("bodyPreview"))
        print("===================================")

    finally:
        await scraper.stop()


if __name__ == "__main__":
    asyncio.run(inspect_sign_in_page())
