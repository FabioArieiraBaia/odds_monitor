import os
import shutil
import subprocess
import time

import undetected_chromedriver as uc


def main():
    port = 9333
    ud = os.path.join(os.environ["LOCALAPPDATA"], "OddsDivergenceMonitor", "uc_test4")
    shutil.rmtree(ud, ignore_errors=True)
    os.makedirs(ud, exist_ok=True)

    opts = uc.ChromeOptions()
    opts.add_argument(f"--user-data-dir={ud}")
    opts.add_argument(f"--remote-debugging-port={port}")
    opts.add_argument("--no-first-run")
    opts.add_argument("--lang=pt-BR")

    print("launching uc...")
    d = uc.Chrome(options=opts, headless=False, use_subprocess=True)
    time.sleep(4)
    dbg = (d.capabilities.get("goog:chromeOptions") or {}).get("debuggerAddress")
    print("debugger", dbg)
    print(subprocess.getoutput(f"netstat -ano | findstr :{port} | findstr LISTENING")[:300])

    d.get("https://www.betano.bet.br/live/")
    time.sleep(7)
    print("title", d.title)
    body = d.find_element("tag name", "body").text
    print("body", body[:600])
    blocked = "restricted" in body.lower() or "compliance" in body.lower()
    print("BLOCKED", blocked)
    d.quit()
    print("done")


if __name__ == "__main__":
    main()
