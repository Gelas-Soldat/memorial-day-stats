# Memorial Day Dashboard — Setup Guide

A living memorial dashboard that automatically pulls updated U.S. military casualty data from the DoD and VA every week.

---

## What's in this repo

```
memorial-site/
├── index.html                     ← The dashboard (your website)
├── data.json                      ← All the war data (auto-updated weekly)
├── scripts/
│   └── scrape_data.py             ← The scraper that fetches new numbers
└── .github/
    └── workflows/
        └── update-data.yml        ← GitHub Actions scheduler
```

---

## Step 1 — Create a GitHub repository

1. Go to **github.com** and sign in
2. Click the **+** icon (top right) → **New repository**
3. Name it something like `memorial-day-dashboard`
4. Set it to **Public** (required for free GitHub Pages hosting)
5. Leave everything else as default
6. Click **Create repository**

---

## Step 2 — Upload the files

You have two options:

### Option A — Upload via the website (easiest)
1. On your new repo page, click **uploading an existing file**
2. Drag and drop all four files/folders:
   - `index.html`
   - `data.json`
   - `scripts/scrape_data.py`
   - `.github/workflows/update-data.yml`
3. Scroll down and click **Commit changes**

> **Note:** GitHub's web uploader handles files but not folder structure well.
> For the workflow file, you may need to create the folders manually:
> - Click **Create new file**
> - Type `.github/workflows/update-data.yml` as the filename (GitHub creates the folders automatically)
> - Paste the contents of `update-data.yml`
> - Repeat for `scripts/scrape_data.py`

### Option B — Use GitHub Desktop (recommended)
1. Download **GitHub Desktop** from desktop.github.com
2. Clone your new repo to your computer
3. Copy all the files into the cloned folder
4. In GitHub Desktop, click **Commit to main** → **Push origin**

---

## Step 3 — Enable GitHub Pages

This makes your dashboard a real website with a public URL.

1. In your repo, click **Settings** (top tab)
2. Scroll down to **Pages** in the left sidebar
3. Under **Source**, select **Deploy from a branch**
4. Set branch to **main**, folder to **/ (root)**
5. Click **Save**
6. Wait about 60 seconds, then refresh
7. You'll see a green banner with your site URL, something like:
   `https://yourusername.github.io/memorial-day-dashboard`

---

## Step 4 — Test the scraper manually

Before waiting a week, run the scraper now to confirm it works.

1. Go to your repo on GitHub
2. Click the **Actions** tab
3. Click **Update casualty data** in the left sidebar
4. Click **Run workflow** → **Run workflow** (green button)
5. Watch the run — it should complete in about 30 seconds
6. If it succeeded, click on the run to see what data changed
7. Check your repo — `data.json` should have a fresh `last_updated` date

If it shows a red ✗, click into the run to read the error. Most common issue is a permissions problem — see Troubleshooting below.

---

## Step 5 — Confirm the site loads live data

1. Visit your GitHub Pages URL
2. Scroll down past the hero — you should see a small line under the source credit saying **"Data last updated: YYYY-MM-DD"**
3. That date comes from `data.json` — if it shows today's date, everything is wired up correctly

---

## How it updates automatically

- Every **Monday at 8am UTC** the GitHub Action wakes up
- It runs `scripts/scrape_data.py`
- The scraper fetches the DoD DCAS and VA pages, looking for updated numbers
- If anything changed, it updates `data.json` and commits it back to your repo
- GitHub Pages automatically serves the new `data.json` within a minute
- Every visitor to your site now sees the latest numbers

You don't have to do anything — it runs itself.

---

## Troubleshooting

**Actions tab says "Workflow requires write permissions"**
- Go to Settings → Actions → General
- Scroll to **Workflow permissions**
- Select **Read and write permissions**
- Save

**The scraper runs but data doesn't change**
- This is normal — if the DoD/VA haven't updated their pages, nothing changes
- The scraper still writes the current date to `data.json`

**Site shows old data / "Data last updated" doesn't appear**
- Open the browser console (F12 → Console)
- Look for a `data.json` fetch error
- Make sure `data.json` is in the root of your repo (same folder as `index.html`)

**GitHub Pages shows a 404**
- Make sure the file is named exactly `index.html` (lowercase)
- Wait 2-3 minutes after enabling Pages before checking

---

## Updating data manually

If you want to correct a number or add a new conflict:

1. Open `data.json` in GitHub (click the file → pencil icon to edit)
2. Find the war you want to update and change the number
3. Scroll down and click **Commit changes**
4. The site updates within 60 seconds

---

## Sources

- **VA Americas Wars fact sheet:** https://department.va.gov/americas-wars/
- **DoD Defense Casualty Analysis System (DCAS):** https://dcas.dmdc.osd.mil
- **Congressional Research Service — American War Casualties:** https://crsreports.congress.gov
