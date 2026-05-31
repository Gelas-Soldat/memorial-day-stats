#!/usr/bin/env python3
"""
Fix conflict classifications in moh_recipients.json.

Run once from your repo root:
    python scripts/fix_conflicts.py

Then commit the updated moh_recipients.json.
"""

import json
import re
from datetime import date

INPUT_FILE = "moh_recipients.json"

# ── Keyword → conflict mapping ────────────────────────────────────────────────
# Checked against action_place, unit, and citation text (in that order).
# First match wins.
KEYWORD_MAP = [
    ("War on Terrorism", [
        "afghanistan", "iraq", "fallujah", "ramadi", "kandahar", "helmand",
        "kunar", "korengal", "tikrit", "mosul", "baghdad", "sadr city",
        "bagram", "wanat", "nuristan", "paktika", "khost", "anbar",
        "operation iraqi", "operation enduring", "operation freedom"
    ]),
    ("Vietnam War", [
        "vietnam", "saigon", "mekong", "hue", "quang tri", "quang nam",
        "da nang", "kontum", "pleiku", "nha trang", "bien hoa", "phu bai",
        "khe sanh", "dak to", "ia drang", "long binh", "binh dinh",
        "republic of vietnam", "south vietnam", "north vietnam"
    ]),
    ("Korean War", [
        "korea", "chosin", "inchon", "pusan", "pork chop", "heartbreak ridge",
        "38th parallel", "yalu", "wonsan", "hungnam", "pyongyang",
        "republic of korea", "chonghyon", "uijongbu", "munsan"
    ]),
    ("World War II", [
        "normandy", "iwo jima", "okinawa", "guadalcanal", "leyte", "bataan",
        "midway", "anzio", "sicily", "palau", "saipan", "guam", "philippines",
        "peleliu", "tarawa", "bougainville", "new guinea", "luzon",
        "ardennes", "rhine", "pacific theater", "european theater",
        "hacksaw ridge", "urasoe-mura", "tan son nhut"
    ]),
    ("World War I", [
        "argonne", "belleau", "chateau thierry", "saint mihiel", "verdun",
        "somme", "ypres", "meuse", "marne", "alsace", "france",
        "western front", "cantigny", "blanc mont"
    ]),
    ("U.S. Civil War", [
        "gettysburg", "antietam", "bull run", "fredericksburg",
        "chancellorsville", "vicksburg", "shiloh", "wilderness",
        "appomattox", "fort wagner", "cold harbor", "spotsylvania",
        "petersburg", "richmond", "shenandoah", "atlanta", "savannah"
    ]),
    ("Indian Campaigns", [
        "apache", "sioux", "comanche", "cheyenne", "nez perce",
        "modoc", "geronimo", "indian territory", "frontier",
        "little bighorn", "wounded knee", "big hole"
    ]),
    ("Philippine Insurrection", [
        "philippine", "manila", "luzon", "mindanao", "cebu",
        "visayan", "samar", "leyte", "iloilo", "cavite",
        "bulacan", "laguna", "batangas"
    ]),
    ("Spanish-American War", [
        "cuba", "san juan hill", "el caney", "havana",
        "puerto rico", "manila bay", "santiago", "guantanamo"
    ]),
    ("Mexican Campaign", [
        "vera cruz", "veracruz", "mexico", "chihuahua",
        "pancho villa", "pershing expedition"
    ]),
]

# ── CMOHS conflict name normalization ─────────────────────────────────────────
# Maps raw CMOHS "Conflict/Era" strings to our standard names.
CMOHS_MAP = {
    "War on Terrorism (Afghanistan)":       "War on Terrorism",
    "War on Terrorism (Iraq)":              "War on Terrorism",
    "Venezuela (Operation Absolute Resolve)": "War on Terrorism",
    "Somalia (Operation Restore Hope)":     "War on Terrorism",
    "Korean War":                           "Korean War",
    "Vietnam War":                          "Vietnam War",
    "World War II":                         "World War II",
    "World War I":                          "World War I",
    "U.S. Civil War":                       "U.S. Civil War",
    "Philippine Insurrection":              "Philippine Insurrection",
    "Spanish-American War":                 "Spanish-American War",
    "Indian Campaigns":                     "Indian Campaigns",
    "China Relief Expedition (Boxer Rebellion)": "Indian Campaigns",
    "Action Against Outlaws, Philippines 1911": "Philippine Insurrection",
    "Haitian Campaign 1915":                "Peacetime / Other",
    "Haitian Campaign 1919 - 1920":         "Peacetime / Other",
    "Dominican Campaign":                   "Peacetime / Other",
    "Samoa Campaign":                       "Peacetime / Other",
    "Second Nicaraguan Campaign":           "Peacetime / Other",
    "Korean Campaign 1871":                 "Peacetime / Other",
    "Mexican Campaign (Vera Cruz)":         "Mexican Campaign",
    "Interim 1865 - 1870":                  "Peacetime / Other",
    "Interim 1871 - 1899":                  "Peacetime / Other",
    "Interim 1899 - 1910":                  "Peacetime / Other",
    "Interim 1915 - 1916":                  "Peacetime / Other",
    "Interim 1920 - 1940":                  "Peacetime / Other",
}

NEEDS_FIX = {"Peacetime / Other", "Unknown", None, ""}


def classify_from_text(text):
    """Scan text for war-related keywords and return a conflict name."""
    if not text:
        return None
    t = text.lower()
    for conflict, keywords in KEYWORD_MAP:
        if any(kw in t for kw in keywords):
            return conflict
    return None


def fix_record(r):
    """Fix a single recipient record in place. Returns True if changed."""
    old = r.get("conflict", "")

    # ── CMOHS records: normalize the raw conflict string ──────────────────────
    if r.get("source") == "cmohs" and old:
        normalized = CMOHS_MAP.get(old)
        if normalized and normalized != old:
            r["conflict"] = normalized
            return True
        # If not in the map, it's probably already a clean name — leave it.
        return False

    # ── CORGIS records: try to reclassify unknown/peacetime entries ───────────
    if old not in NEEDS_FIX:
        return False  # already properly classified

    # Try action_place first (most precise), then unit, then citation
    for field in ("action_place", "unit", "citation"):
        result = classify_from_text(r.get(field, ""))
        if result:
            r["conflict"] = result
            return True

    return False  # couldn't determine — leave as-is


def main():
    with open(INPUT_FILE, encoding="utf-8") as f:
        data = json.load(f)

    recipients = data["recipients"]

    before_counts = {}
    after_counts  = {}
    fixed = 0

    for r in recipients:
        old = r.get("conflict") or "Unknown"
        before_counts[old] = before_counts.get(old, 0) + 1

        if fix_record(r):
            fixed += 1

        new = r.get("conflict") or "Unknown"
        after_counts[new] = after_counts.get(new, 0) + 1

    data["meta"]["last_updated"] = date.today().isoformat()

    with open(INPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Fixed {fixed} records\n")

    print("Before:")
    for k, v in sorted(before_counts.items(), key=lambda x: -x[1]):
        print(f"  {v:5d}  {k}")

    print("\nAfter:")
    for k, v in sorted(after_counts.items(), key=lambda x: -x[1]):
        print(f"  {v:5d}  {k}")

    print(f"\nTotal records: {len(recipients)}")


if __name__ == "__main__":
    main()
