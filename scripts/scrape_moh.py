#!/usr/bin/env python3
"""
Medal of Honor Recipients Scraper
Outputs: moh_recipients.json

Strategy:
  1. PRIMARY   — Download CORGIS CSV (3,475 records w/ full citations through ~2007)
  2. SUPPLEMENT — Try CMOHS.org for any newer recipients

Run locally:  python scripts/scrape_moh.py
GitHub Actions: .github/workflows/update-moh.yml (runs monthly)
"""

import requests
from bs4 import BeautifulSoup
import csv
import json
import io
import re
import os
import time
from datetime import date

# ─── Config ──────────────────────────────────────────────────────────────────

OUTPUT_FILE = "moh_recipients.json"
RATE_LIMIT  = 1.2
SAVE_EVERY  = 25

CORGIS_URL = (
    "https://raw.githubusercontent.com/corgis-edu/corgis/master"
    "/website/datasets/csv/medal_of_honor/medal_of_honor.csv"
)
CMOHS_BASE = "https://www.cmohs.org"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# ─── State Abbreviation Map ───────────────────────────────────────────────────

STATE_MAP = {
    # Old-style postal abbreviations with periods
    "Ala.":"Alabama","Ariz.":"Arizona","Ark.":"Arkansas",
    "Cal.":"California","Calif.":"California","Colo.":"Colorado","Conn.":"Connecticut",
    "Del.":"Delaware","Fla.":"Florida","Ga.":"Georgia",
    "Ill.":"Illinois","Ind.":"Indiana",
    "Kans.":"Kansas","Kan.":"Kansas","Ky.":"Kentucky","La.":"Louisiana",
    "Md.":"Maryland","Mass.":"Massachusetts","Mich.":"Michigan",
    "Minn.":"Minnesota","Miss.":"Mississippi","Mo.":"Missouri","Mont.":"Montana",
    "Nebr.":"Nebraska","Neb.":"Nebraska","Nev.":"Nevada","N.H.":"New Hampshire",
    "N.J.":"New Jersey","N.Mex.":"New Mexico","N.M.":"New Mexico",
    "N.Y.":"New York","N.C.":"North Carolina","N.Dak.":"North Dakota","N.D.":"North Dakota",
    "Okla.":"Oklahoma","Oreg.":"Oregon","Ore.":"Oregon","Pa.":"Pennsylvania",
    "R.I.":"Rhode Island","S.C.":"South Carolina","S.Dak.":"South Dakota","S.D.":"South Dakota",
    "Tenn.":"Tennessee","Tex.":"Texas","Vt.":"Vermont",
    "Va.":"Virginia","Wash.":"Washington","W.Va.":"West Virginia",
    "Wis.":"Wisconsin","Wyo.":"Wyoming",
    # Modern two-letter codes (no periods)
    "AL":"Alabama","AK":"Alaska","AZ":"Arizona","AR":"Arkansas","CA":"California",
    "CO":"Colorado","CT":"Connecticut","DE":"Delaware","FL":"Florida","GA":"Georgia",
    "HI":"Hawaii","ID":"Idaho","IL":"Illinois","IN":"Indiana","IA":"Iowa",
    "KS":"Kansas","KY":"Kentucky","LA":"Louisiana","ME":"Maine","MD":"Maryland",
    "MA":"Massachusetts","MI":"Michigan","MN":"Minnesota","MS":"Mississippi",
    "MO":"Missouri","MT":"Montana","NE":"Nebraska","NV":"Nevada","NH":"New Hampshire",
    "NJ":"New Jersey","NM":"New Mexico","NY":"New York","NC":"North Carolina",
    "ND":"North Dakota","OH":"Ohio","OK":"Oklahoma","OR":"Oregon","PA":"Pennsylvania",
    "RI":"Rhode Island","SC":"South Carolina","SD":"South Dakota","TN":"Tennessee",
    "TX":"Texas","UT":"Utah","VT":"Vermont","VA":"Virginia","WA":"Washington",
    "WV":"West Virginia","WI":"Wisconsin","WY":"Wyoming",
    # Full state names (for CMOHS format)
    "Alaska":"Alaska","Hawaii":"Hawaii","Idaho":"Idaho","Iowa":"Iowa",
    "Maine":"Maine","Ohio":"Ohio","Utah":"Utah",
}

# ─── Conflict Classification ──────────────────────────────────────────────────

CONFLICT_RANGES = [
    (1861, 1865, "U.S. Civil War"),
    (1866, 1897, "Indian Campaigns"),
    (1898, 1898, "Spanish-American War"),
    (1899, 1913, "Philippine Insurrection"),
    (1900, 1901, "China Relief Expedition"),
    (1914, 1916, "Mexican Campaign"),
    (1915, 1920, "Haitian Campaign"),
    (1917, 1918, "World War I"),
    (1941, 1945, "World War II"),
    (1950, 1953, "Korean War"),
    (1964, 1975, "Vietnam War"),
    (2001, 2030, "War on Terrorism"),
]

def classify_conflict(action_year_str, issued_str=None):
    """
    Classify conflict from action year. Falls back to issued year for
    records where the action date is unknown (-1).
    """
    def year_from(s):
        try:
            y = int(str(s).split("-")[0])
            return y if y > 0 else None
        except (ValueError, TypeError, IndexError):
            return None

    year = year_from(action_year_str)

    # Fallback: derive year from issued date if action year unknown
    if year is None and issued_str:
        m = re.search(r"(\d{4})", issued_str)
        if m:
            issued_year = int(m.group(1))
            # Issued dates are usually 0–40 years after the action
            # Use the issued year to narrow down the most likely conflict
            # (not exact but better than "Unknown")
            for start, end, name in CONFLICT_RANGES:
                if start <= issued_year <= end + 40:
                    year = start  # anchor to conflict start for classification
                    break

    if year is None:
        return "Unknown"

    for start, end, name in CONFLICT_RANGES:
        if start <= year <= end:
            return name

    return "Unknown"


# ─── CORGIS PRIMARY SOURCE ───────────────────────────────────────────────────

def load_corgis():
    print("  Downloading CORGIS dataset...")
    try:
        r = requests.get(CORGIS_URL, headers=HEADERS, timeout=30)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"  ERROR: {e}")
        return {}

    reader = csv.DictReader(io.StringIO(r.text))
    recipients = {}
    seen_slugs = {}   # handle duplicate names

    for raw in reader:
        name_raw = raw.get("name", "").strip()
        if not name_raw:
            continue

        name = _invert_name(name_raw)
        base_slug = _slugify(name)

        # Deduplicate slugs
        if base_slug in seen_slugs:
            seen_slugs[base_slug] += 1
            slug = f"{base_slug}-{seen_slugs[base_slug]}"
        else:
            seen_slugs[base_slug] = 1
            slug = base_slug

        born = _clean(raw.get("birth.location name"))
        entered = _clean(raw.get("military record.entered service at"))
        action_year = raw.get("awarded.date.year", "")
        issued = raw.get("awarded.issued", "")

        recipient = {
            "id": slug,
            "name": name,
            "rank": _clean(raw.get("military record.rank")),
            "branch": _clean(raw.get("military record.organization")),
            "conflict": classify_conflict(action_year, issued),
            "unit": _clean(
                _join(raw.get("military record.company"),
                      raw.get("military record.division"))
            ),
            "action_date": _clean_date(raw.get("awarded.date.full")),
            "action_place": _clean(raw.get("awarded.location.name")),
            "citation": _clean(raw.get("awarded.citation")),
            "posthumous": raw.get("death", "").strip().lower() == "true",
            "born": born,
            "accredited_to": _clean(raw.get("awarded.accredited to")),
            "home_state": _parse_state(born or entered or ""),
            "source": "corgis",
            "url": _modernize_cmohs_url(raw.get("metadata.link", "")),
        }
        recipients[slug] = recipient

    print(f"  CORGIS: loaded {len(recipients)} records")
    return recipients


def _invert_name(raw):
    if "," in raw:
        parts = raw.split(",", 1)
        return f"{parts[1].strip()} {parts[0].strip()}"
    return raw.strip()


def _slugify(name):
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug.strip())
    return slug


def _join(*parts):
    return ", ".join(p.strip() for p in parts if p and p.strip())


def _clean_date(val):
    """Clean dates, returning None for -1--1--1 sentinel values."""
    if not val:
        return None
    cleaned = _clean(val)
    if cleaned and re.match(r"^-1", cleaned):
        return None
    return cleaned


def _modernize_cmohs_url(old_url):
    m = re.search(r"/recipient-detail/\d+/([^.]+)\.php", old_url)
    if m:
        return f"https://www.cmohs.org/recipients/{m.group(1)}"
    return old_url or None


def _parse_state(location):
    if not location:
        return None
    # Try each abbreviation
    for abbr, full_name in STATE_MAP.items():
        # Match abbr at end of string, after comma/space, with optional trailing period
        pattern = rf"(?:^|[,\s])({re.escape(abbr)})\.?(?:\s*$|[,\s])"
        if re.search(pattern, location):
            return full_name
    return None


# ─── CMOHS SUPPLEMENT ────────────────────────────────────────────────────────

def get_recent_cmohs_slugs(existing_ids):
    slugs = []

    # Sitemap first
    try:
        r = _get(f"{CMOHS_BASE}/sitemap.xml", timeout=20)
        if r:
            soup = BeautifulSoup(r.text, "lxml-xml")
            pattern = re.compile(
                r"^https://www\.cmohs\.org/recipients/([a-z0-9][a-z0-9-]+)$"
            )
            for loc in soup.find_all("loc"):
                m = pattern.match(loc.text.strip())
                if m:
                    slug = m.group(1)
                    if slug not in ("overview", "connect") and slug not in existing_ids:
                        slugs.append(slug)
            if slugs:
                print(f"  CMOHS sitemap: {len(slugs)} new slugs")
                return slugs
    except Exception as e:
        print(f"  Sitemap: {e}")

    # Paginated HTML listing fallback
    page = 1
    link_pattern = re.compile(r"/recipients/([a-z0-9][a-z0-9-]+)$")
    consecutive_empty = 0

    while page <= 200:
        r = _get(f"{CMOHS_BASE}/recipients?p={page}", timeout=15)
        if not r:
            break
        soup = BeautifulSoup(r.text, "html.parser")
        links = soup.find_all("a", href=link_pattern)

        if not links:
            consecutive_empty += 1
            if consecutive_empty >= 2:
                break
        else:
            consecutive_empty = 0
            for a in links:
                m = link_pattern.search(a["href"])
                if m:
                    slug = m.group(1)
                    if slug not in ("overview","connect") and slug not in existing_ids and slug not in slugs:
                        slugs.append(slug)
        page += 1
        time.sleep(RATE_LIMIT)

    if slugs:
        print(f"  CMOHS HTML: {len(slugs)} new slugs")
    return slugs


def parse_cmohs_recipient(slug):
    url = f"{CMOHS_BASE}/recipients/{slug}"
    r = _get(url, timeout=15)
    if not r:
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text(separator="\n", strip=True)

    name = _extract_name(soup)
    if not name:
        return None

    rank         = _field(text, "Rank",                      ["Conflict"])
    conflict     = _field(text, "Conflict/Era",               ["Unit"])
    unit         = _field(text, "Unit/Command",               ["Military Service Branch"])
    branch       = _field(text, "Military Service Branch",    ["Medal of Honor Action Date"])
    action_date  = _field(text, "Medal of Honor Action Date", ["Medal of Honor Action Place"])
    action_place = _field(text, "Medal of Honor Action Place",["Additional"])
    accredited   = _field(text, "Accredited to",              ["Awarded Posthumously"])
    posthumous   = _field(text, "Awarded Posthumously",       ["Presentation Date"])
    born         = _field(text, "Born",                       ["Location of Medal"])

    return {
        "id": slug,
        "name": _clean(name),
        "rank": _clean(rank),
        "branch": _clean(branch),
        "conflict": _clean(conflict),
        "unit": _clean(unit),
        "action_date": _clean(action_date),
        "action_place": _clean(action_place),
        "citation": _clean(_extract_citation(soup)),
        "posthumous": _parse_bool(posthumous),
        "born": _clean(born),
        "accredited_to": _clean(accredited),
        "home_state": _parse_state(born or accredited or ""),
        "source": "cmohs",
        "url": url,
    }


def _extract_name(soup):
    for tag in ["h1","h2","h3"]:
        el = soup.find(tag)
        if el:
            name = el.get_text(strip=True)
            if name and len(name.split()) >= 2 and "Medal of Honor" not in name:
                return name
    return None


def _field(text, label, stops=None):
    escaped = re.escape(label)
    stop_str = "|".join(re.escape(s) for s in (stops or []))
    pattern = (
        rf"{escaped}\s*:?\s*([\s\S]+?)(?={stop_str}|\Z)"
        if stop_str else
        rf"{escaped}\s*:?\s*([\s\S]+?)(?=\n{{2,}}|\Z)"
    )
    m = re.search(pattern, text, re.IGNORECASE)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else None


def _extract_citation(soup):
    paras = [p.get_text(strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 150]
    return max(paras, key=len) if paras else None


def _parse_bool(raw):
    return raw.strip().lower() in ("yes","true","1") if raw else None


# ─── Utilities ────────────────────────────────────────────────────────────────

def _clean(val):
    if val is None:
        return None
    cleaned = re.sub(r"\s+", " ", str(val)).strip()
    return cleaned or None


def _get(url, timeout=15):
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", 10))
                print(f"    Rate limited — waiting {wait}s")
                time.sleep(wait)
                continue
            if r.ok:
                return r
            if r.status_code in (403, 404, 410):
                return None
            time.sleep(3 * (attempt + 1))
        except requests.RequestException as e:
            print(f"    Request error ({attempt+1}/3): {e}")
            time.sleep(3 * (attempt + 1))
    return None


# ─── Persistence ─────────────────────────────────────────────────────────────

def load_existing():
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE) as f:
            data = json.load(f)
        return {r["id"]: r for r in data.get("recipients", [])}
    return {}


def save(recipients_dict):
    output = {
        "meta": {
            "last_updated": date.today().isoformat(),
            "source": "CORGIS Dataset + Congressional Medal of Honor Society",
            "source_url": "https://www.cmohs.org/recipients",
            "total": len(recipients_dict),
        },
        "recipients": sorted(recipients_dict.values(), key=lambda r: r.get("name", "")),
    }
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"  Saved {len(recipients_dict)} records → {OUTPUT_FILE}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=== MoH Recipients Scraper ===\n")

    existing = load_existing()
    print(f"Existing records: {len(existing)}")

    # Step 1: CORGIS base
    print("\nStep 1: Loading CORGIS base dataset...")
    corgis = load_corgis()
    recipients = dict(existing)
    corgis_new = sum(1 for slug in corgis if slug not in recipients)
    recipients.update({slug: rec for slug, rec in corgis.items() if slug not in recipients})
    print(f"  New from CORGIS: {corgis_new} | Total: {len(recipients)}")

    # Step 2: CMOHS supplement
    print("\nStep 2: Checking CMOHS for recent recipients...")
    new_slugs = get_recent_cmohs_slugs(set(recipients.keys()))

    if not new_slugs:
        print("  No new slugs from CMOHS (may be blocked or already up to date)")
    else:
        print(f"  Scraping {len(new_slugs)} pages...")
        cmohs_new = 0
        for i, slug in enumerate(new_slugs, 1):
            print(f"  [{i}/{len(new_slugs)}] {slug}")
            rec = parse_cmohs_recipient(slug)
            if rec:
                recipients[slug] = rec
                cmohs_new += 1
            time.sleep(RATE_LIMIT)
            if cmohs_new > 0 and cmohs_new % SAVE_EVERY == 0:
                save(recipients)
        print(f"  New from CMOHS: {cmohs_new}")

    print("\nFinal save...")
    save(recipients)
    print(f"\nTotal records: {len(recipients)}")


if __name__ == "__main__":
    main()
