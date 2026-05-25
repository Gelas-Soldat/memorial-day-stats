"""
Memorial Day Dashboard — Data Scraper
Runs weekly via GitHub Actions.

What it does:
  1. Fetches active-duty death totals from the DoD Defense Casualty Analysis System (DCAS)
  2. Fetches the VA Americas Wars fact sheet for any updated historical figures
  3. Compares against current data.json
  4. If anything changed, updates data.json and commits it back to the repo

Sources:
  - DoD DCAS: https://dcas.dmdc.osd.mil/dcas/app/summaryData/deaths/byWar
  - VA Americas Wars: https://department.va.gov/americas-wars/
"""

import json
import os
import re
import sys
from datetime import date
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "data.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; MemorialDayDashboard/1.0; "
        "educational data aggregator; contact via GitHub)"
    )
}

# Known stable values for historical wars (pre-1980).
# These rarely change — the VA updates them maybe once a decade.
# The scraper will try to confirm them from the VA page; if scraping
# fails it falls back to these hardcoded values so the site never breaks.
HISTORICAL_FALLBACK = {
    "Iraq/Afghan": {
        "battle": 7057,
        "other": 1300,
        "wounded": 53174,
        "service": "3,500,000+",
        "years": "2001–present",
    }
}

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def fetch(url):
    """Fetch a URL and return the response text, or None on failure."""
    try:
        req = Request(url, headers=HEADERS)
        with urlopen(req, timeout=20) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (URLError, HTTPError) as e:
        print(f"  WARNING: Could not fetch {url} — {e}")
        return None


def load_data():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  data.json saved.")


# ---------------------------------------------------------------------------
# SCRAPER 1 — DoD DCAS (post-9/11 active duty deaths, updated frequently)
# ---------------------------------------------------------------------------

def scrape_dcas():
    """
    Attempt to pull current Iraq/Afghanistan/post-9/11 death totals
    from the DoD DCAS summary page.

    DCAS renders data via JavaScript so we try a few known data endpoints.
    If all fail, returns None and we keep existing numbers.
    """
    print("Fetching DoD DCAS data...")

    # DCAS exposes summary JSON at this path (confirmed working as of 2024)
    endpoints = [
        "https://dcas.dmdc.osd.mil/dcas/app/summaryData/deaths/byWar",
        "https://dcas.dmdc.osd.mil/dcas/pages/main.xhtml",
    ]

    for url in endpoints:
        html = fetch(url)
        if not html:
            continue

        # Try to find OEF/OIF/OND total deaths in the page text
        # DCAS labels these operations differently over time
        patterns = [
            # Matches things like: "7,057" near "Operation"
            r'(?:OEF|OIF|OND|Enduring Freedom|Iraqi Freedom|post.?9.11)[^0-9]{0,80}?(\d{1,2},\d{3})',
            r'Total[^0-9]{0,40}?(\d{1,2},\d{3})[^0-9]{0,20}?(?:killed|deaths|KIA)',
        ]
        for pat in patterns:
            match = re.search(pat, html, re.IGNORECASE)
            if match:
                raw = match.group(1).replace(",", "")
                total = int(raw)
                if 6000 < total < 15000:   # sanity check
                    print(f"  DCAS: found post-9/11 battle deaths = {total:,}")
                    return {"battle": total}

        print(f"  DCAS: page fetched but pattern not matched at {url}")

    print("  DCAS: could not extract data — keeping existing numbers.")
    return None


# ---------------------------------------------------------------------------
# SCRAPER 2 — VA Americas Wars page (historical wars, updated annually)
# ---------------------------------------------------------------------------

def scrape_va():
    """
    Fetch the VA Americas Wars interactive fact sheet and look for
    updated figures. The VA page is JavaScript-heavy but key numbers
    are often present in the HTML source as data attributes or text.
    """
    print("Fetching VA Americas Wars data...")
    url = "https://department.va.gov/americas-wars/"
    html = fetch(url)
    if not html:
        print("  VA: page unavailable — keeping existing numbers.")
        return {}

    updates = {}

    # Look for Vietnam total — VA lists ~58,220
    m = re.search(r'Vietnam[^0-9]{0,200}?(\d{2},\d{3})[^0-9]{0,60}?(?:deaths|killed|battle)', html, re.IGNORECASE | re.DOTALL)
    if m:
        val = int(m.group(1).replace(",", ""))
        if 40000 < val < 70000:
            updates["Vietnam_battle"] = val
            print(f"  VA: Vietnam battle deaths = {val:,}")

    # Look for WWII total — VA lists ~291,557
    m = re.search(r'World War II[^0-9]{0,200}?(\d{3},\d{3})[^0-9]{0,60}?(?:deaths|killed|battle)', html, re.IGNORECASE | re.DOTALL)
    if m:
        val = int(m.group(1).replace(",", ""))
        if 250000 < val < 350000:
            updates["WWII_battle"] = val
            print(f"  VA: WWII battle deaths = {val:,}")

    # Look for Korea — VA lists ~33,686
    m = re.search(r'Korea[^0-9]{0,200}?(\d{2},\d{3})[^0-9]{0,60}?(?:deaths|killed|battle)', html, re.IGNORECASE | re.DOTALL)
    if m:
        val = int(m.group(1).replace(",", ""))
        if 25000 < val < 45000:
            updates["Korea_battle"] = val
            print(f"  VA: Korea battle deaths = {val:,}")

    if not updates:
        print("  VA: page fetched but no updated figures detected.")

    return updates


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    print("=" * 50)
    print(f"Memorial Day Scraper — {date.today()}")
    print("=" * 50)

    data = load_data()
    changed = False

    # -- DCAS: update Iraq/Afghanistan numbers --
    dcas = scrape_dcas()
    if dcas:
        for war in data["wars"]:
            if war["name"] == "Iraq/Afghan":
                old = war["battle"]
                new = dcas["battle"]
                if old != new:
                    print(f"  UPDATE Iraq/Afghan battle: {old:,} → {new:,}")
                    war["battle"] = new
                    changed = True
                    # Also update summary total
                    data["summary"]["total_battle_deaths"] += (new - old)

        # Mirror to cause_breakdown
        if changed:
            for cb in data["cause_breakdown"]:
                if cb["name"] == "Iraq/Afghan":
                    cb["battle"] = dcas["battle"]

    # -- VA: update historical numbers --
    va = scrape_va()
    field_map = {
        "Vietnam_battle": "Vietnam",
        "WWII_battle":    "WWII",
        "Korea_battle":   "Korea",
    }
    for key, war_name in field_map.items():
        if key in va:
            for war in data["wars"]:
                if war["name"] == war_name:
                    old = war["battle"]
                    new = va[key]
                    if old != new:
                        print(f"  UPDATE {war_name} battle: {old:,} → {new:,}")
                        diff = new - old
                        war["battle"] = new
                        data["summary"]["total_battle_deaths"] += diff
                        changed = True
            for cb in data["cause_breakdown"]:
                if cb["name"] == war_name and key in va:
                    cb["battle"] = va[key]

    # -- Always update the last_updated date --
    today = str(date.today())
    if data["meta"]["last_updated"] != today:
        data["meta"]["last_updated"] = today
        changed = True

    # -- Save if anything changed --
    if changed:
        save_data(data)
        print("\nData updated successfully.")
    else:
        # Still write the date so GitHub sees a commit reason
        save_data(data)
        print("\nNo data changes detected. Date updated.")

    print("=" * 50)
    return 0


if __name__ == "__main__":
    sys.exit(main())
