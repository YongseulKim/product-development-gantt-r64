"""Find desktop Chrome/Chromium and matching ChromeDriver across PCs."""
import os
import shutil
from pathlib import Path

def browser_environment(project_root):
    env = dict(os.environ)
    termux = Path('/data/data/com.termux/files/usr')
    if termux.is_dir():
        # Avoid Codex's older bundled libc++ on Termux only.
        env['LD_LIBRARY_PATH'] = str(termux / 'lib')
    browser = env.get('CHROME_BINARY')
    driver = env.get('CHROMEDRIVER_BINARY')
    if not browser:
        candidates = [termux / 'lib/chromium/chrome']
        for name in ('chromium', 'chromium-browser', 'google-chrome', 'chrome'):
            found = shutil.which(name)
            if found:
                candidates.append(Path(found))
        for key in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA'):
            if env.get(key):
                candidates.append(Path(env[key]) / 'Google/Chrome/Application/chrome.exe')
        candidates.append(Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'))
        browser = next((str(p) for p in candidates if p.is_file()), None)
    if not driver:
        driver = shutil.which('chromedriver')
    if not browser or not Path(browser).is_file():
        raise RuntimeError('Install Chrome/Chromium or set CHROME_BINARY to its full path.')
    if not driver or not Path(driver).is_file():
        raise RuntimeError('Install matching ChromeDriver on PATH or set CHROMEDRIVER_BINARY.')
    return browser, driver, env
