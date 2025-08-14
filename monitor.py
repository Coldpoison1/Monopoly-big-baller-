import os, json, datetime as dt, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = "https://casinoscores.com/monopoly-big-baller/"
THRESH_HOURS = 5.0
STATE = Path(".state.json")
WEBHOOK = os.getenv("WEBHOOK_URL", "")

def load_state():
    try:
        return json.loads(STATE.read_text())
    except:
        return {}

def save_state(s):
    STATE.write_text(json.dumps(s))

def notify(msg):
    if not WEBHOOK:
        print("[Alert]", msg)
        return
    import requests
    try:
        requests.post(WEBHOOK, json={"content": msg}, timeout=15)
    except Exception as e:
        print("Notify failed:", e, file=sys.stderr)

def get_hours_since_last_5roll():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(URL, wait_until="networkidle", timeout=60000)
        # accept cookies if needed
        for label in ["Accept", "Agree", "Allow", "OK"]:
            try:
                page.get_by_text(label, exact=False).first.click(timeout=800)
                break
            except:
                pass
        # find all result blocks with their timestamp
        rows = page.locator("div:has-text('Aug')")  # date rows
        n = rows.count()
        for i in range(n):
            text_block = rows.nth(i).inner_text()
            if " 5 " in text_block or text_block.startswith("5 ") or text_block.endswith(" 5"):
                # Found a row with a 5 roll
                parts = text_block.split("\n")
                # first line should be like '14 Aug 2025' and next like '15:28'
                date_str = None
                time_str = None
                for part in parts:
                    if "Aug" in part or "Sep" in part or "Oct" in part:
                        date_str = part.strip()
                    if ":" in part and part.count(":") == 1:
                        time_str = part.strip()
                if date_str and time_str:
                    ts = dt.datetime.strptime(f"{date_str} {time_str}", "%d %b %Y %H:%M")
                    ts = ts.replace(tzinfo=dt.timezone.utc)
                    diff_hours = (dt.datetime.now(dt.timezone.utc) - ts).total_seconds() / 3600
                    browser.close()
                    return diff_hours
        browser.close()
    return None

def main():
    state = load_state()
    age = get_hours_since_last_5roll()
    if age is None:
        print("Could not determine hours since last 5 roll.")
        return
    print(f"Hours since last 5 roll: {age:.2f}")
    drought_id = int(age)  # change if needed
    if age >= THRESH_HOURS and state.get("last") != drought_id:
        notify(f"Monopoly Big Baller: {age:.2f} hours since last 5 roll. {URL}")
        state["last"] = drought_id
        save_state(state)

if __name__ == "__main__":
    main()
