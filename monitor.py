import os, re, json, datetime as dt, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = "https://casinoscores.com/monopoly-big-baller/"
THRESH_HOURS = 5.0
STATE = Path(".state.json")
WEBHOOK = os.getenv("WEBHOOK_URL", "")

def load_state():
    try: return json.loads(STATE.read_text())
    except: return {}
def save_state(s): STATE.write_text(json.dumps(s))

def notify(msg):
    if not WEBHOOK:
        print("[Alert]", msg); return
    import requests
    try: requests.post(WEBHOOK, json={"content": msg}, timeout=15)
    except Exception as e: print("Notify failed:", e, file=sys.stderr)

# --- Parsing helpers --------------------------------------------------------

# Ex: "14 Aug 2025 15:28" (we build this from separate date + time)
DATE_TIME_FMT = "%d %b %Y %H:%M"

# match things like "14 Aug 2025" followed (nearby) by "15:28"
DATE_TIME_NEARBY = re.compile(
    r"(?P<date>\b\d{1,2}\s+[A-Za-z]{3}\s+\d{4}\b)[^\n]{0,80}?(?P<time>\b\d{1,2}:\d{2}\b)",
    flags=re.S
)

# standalone number 5 (not 15, 50, etc.)
HAS_FIVE = re.compile(r"(?<!\d)5(?!\d)")

def extract_latest_5roll_time(page_text: str):
    """
    Find blocks that look like:
      14 Aug 2025
      15:28
      <then a bunch of numbers in circles, including possibly '5'>
    We:
      1) locate each date+time pair,
      2) look ahead ~400 chars for a standalone '5',
      3) if found, parse that date+time as a game that had a 5 roll.
    Return the most recent such datetime (UTC).
    """
    latest = None
    for m in DATE_TIME_NEARBY.finditer(page_text):
        date_str = m.group("date")
        time_str = m.group("time")

        # Look in the text right after the match for the numbers of that round
        window = page_text[m.end(): m.end() + 400]

        if HAS_FIVE.search(window):
            # Build "14 Aug 2025 15:28"
            dt_str = f"{date_str} {time_str}"
            try:
                ts = dt.datetime.strptime(dt_str, DATE_TIME_FMT).replace(tzinfo=dt.timezone.utc)
                if latest is None or ts > latest:
                    latest = ts
            except Exception:
                # Ignore lines that happen to include extra words; our regex already narrows it
                continue
    return latest

def get_hours_since_last_5roll():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(URL, wait_until="networkidle", timeout=60000)
        # try to clear cookie banners
        for label in ["Accept", "Agree", "Allow", "OK", "I understand"]:
            try:
                page.get_by_text(label, exact=False).first.click(timeout=800)
                break
            except:
                pass
        text = page.inner_text("body")
        browser.close()

    last_5 = extract_latest_5roll_time(text)
    if not last_5:
        return None
    return (dt.datetime.now(dt.timezone.utc) - last_5).total_seconds() / 3600.0

# --- Main -------------------------------------------------------------------

def main():
    state = load_state()
    age = get_hours_since_last_5roll()
    if age is None:
        print("Could not determine hours since last 5 roll (selector/regex tweak may be needed).")
        return

    print(f"Hours since last 5 roll: {age:.2f}")

    # Build an ID for this drought so we only alert once per stretch
    approx_last = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=age)).replace(second=0, microsecond=0)
    drought_id = approx_last.isoformat(timespec="minutes")

    if age >= THRESH_HOURS and state.get("last") != drought_id:
        notify(f"Monopoly Big Baller: {age:.2f} hours since last 5 roll. {URL}")
        state["last"] = drought_id
        save_state(state)

if __name__ == "__main__":
    main()
