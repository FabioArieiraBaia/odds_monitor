import os
import time
import re
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By


def main():
    ud = os.path.join(os.environ["LOCALAPPDATA"], "OddsDivergenceMonitor", "chrome_data_betano_stealth")
    opts = uc.ChromeOptions()
    opts.add_argument(f"--user-data-dir={ud}")
    opts.add_argument("--lang=pt-BR")
    d = uc.Chrome(options=opts, headless=False, use_subprocess=True)
    d.get("https://www.betano.bet.br/live/")
    time.sleep(6)
    # click tenis de mesa
    for el in d.find_elements(By.XPATH, "//*[contains(., 'Tênis de Mesa') or contains(., 'Tenis de Mesa')]"):
        t = (el.text or "").strip()
        if t and len(t) < 40 and "mesa" in t.lower():
            try:
                el.click()
                time.sleep(3)
                print("clicked", t)
                break
            except Exception:
                pass
    anchors = d.find_elements(By.CSS_SELECTOR, "a[href]")
    hrefs = []
    for a in anchors:
        h = a.get_attribute("href") or ""
        if "live" in h or re.search(r"/\d{5,}", h):
            hrefs.append((h, (a.text or "")[:40].replace("\n", " ")))
    print("total a", len(anchors), "live-ish", len(hrefs))
    for h, t in hrefs[:40]:
        print(h, "|", t)
    print("title", d.title)
    print("url", d.current_url)
    d.quit()


if __name__ == "__main__":
    main()
