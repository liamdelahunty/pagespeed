# PageSpeed Insights CSV Collector
A tiny Python utility that reads a list of URLs, calls the Google PageSpeed Insights v5 API (desktop + mobile), extracts the five Lighthouse category scores plus the core performance metrics, and writes a timestamped CSV file you can open in Excel, LibreOffice, or pandas.

## ✨ What it does
Loads URLs from urls.txt (one per line).
Queries the API for Performance, Accessibility, Best‑Practices, SEO, PWA.
Retrieves FCP, Speed Index, LCP, TTI, TBT, CLS, SRT.
Saves a file named pagespeed-report-YYYY‑MM‑DD‑HHMM.csv.
Dumps the raw JSON responses to debug-responses/ for troubleshooting.
All results are deterministic (no cache, no cookies, fixed throttling), making the CSV comparable across users and locations.

## 📦 Prerequisites
Python 3.8+ (official installer from https://python.org).

Upgrade pip (optional but recommended):

py -m pip install --upgrade pip

Install required packages (run in the project folder):

py -m pip install requests tqdm python-dotenv
Create a Google Cloud API key with the PageSpeed Insights API enabled.
Store it in a .env file (same folder as the script):

PSI_API_KEY=YOUR_GOOGLE_API_KEY
Prepare the URL list – a plain‑text file named urls.txt:

https://example.com
https://another-site.org/page

### 🚀 How to run
From the folder that contains pagespeed_to_csv.py
python pagespeed_to_csv.py

The script will:
Print a progress bar (tqdm).
Create pagespeed-report-2025-10-15-1432.csv (timestamp varies).
Save raw API responses under debug-responses/ (optional, for debugging).

## 📋 Configuration Notes  

| Setting | Default | How to change |
|---------|---------|---------------|
| **API endpoint** | `https://www.googleapis.com/pagespeedonline/v5/runPagespeed` | Edit the `API_ENDPOINT` constant near the top of `pagespeed_to_csv.py`. |
| **Strategies** | `("desktop", "mobile")` | Modify the `STRATEGIES` tuple (`STRATEGIES = ("desktop",)` for only desktop, etc.). |
| **Categories** | All five – `performance, accessibility, best‑practices, seo, pwa` | Change the `category` list inside `call_pagespeed` if you need a subset. |
| **Timeout** | `90` seconds | Adjust the `timeout=` argument in `requests.get(...)`. |
| **Output folder** | CSV written to the repository root (or `reports/` if you applied the folder change) | Update `OUTPUT_CSV` (or `REPORTS_DIR`) constants. |
| **Debug JSON dump folder** | `debug-responses/` (or `reports/debug-responses/` after folder change) | Change the `out_dir` path inside `dump_response`. |
| **Timestamp format** | `YYYY‑MM‑DD‑HHMM` (e.g., `2025-10-15-1432`) | Edit the `strftime` pattern in `TIMESTAMP = datetime.datetime.now().strftime("%Y-%m-%d-%H%M")`. |

---

## 🐞 Common Issues & Fixes  

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| `NameError: PSI_API_KEY` | `.env` file missing, mis‑named, or variable not set. | Create a `.env` file in the project root with `PSI_API_KEY=YOUR_GOOGLE_API_KEY`. Ensure the file is saved and the variable name is spelled exactly. |
| `400 Bad Request` from the API | API key restricted (referrer/IP) or malformed request parameters. | In Google Cloud Console → **APIs & Services → Credentials** → edit the key → set **Application restrictions** to **None** (or add your public IP). Also verify the `category` list is a Python list, not a comma‑separated string. |
| `ModuleNotFoundError: requests` (or `tqdm`, `python‑dotenv`) | Dependencies not installed. | Run `py -m pip install --upgrade pip` then `py -m pip install requests tqdm python-dotenv`. |
| Scores are all `0` (Performance, Accessibility, etc.) | Wrong `category` format or API response missing those fields. | Use the list version for `category` (see the **Categories** row above). |
| Script runs very slowly or times out | Network throttling on your side or the target site is extremely slow. | Increase the `timeout` value in `call_pagespeed` (e.g., `timeout=180`). |
| CSV file not created or empty | `urls.txt` missing or contains no valid URLs. | Ensure `urls.txt` exists in the repo root and has at least one non‑blank line with a full URL (`https://example.com`). |
| Raw JSON files not appearing | `debug-responses/` folder not created or path incorrect. | Verify the `out_dir` path in `dump_response`. If you moved the CSV folder to `reports/`, also update the debug folder to `REPORTS_DIR / "debug-responses"` (see the folder‑change snippet). |
| Different users get different results | Users are running the script locally with their own Chrome version or caching. | Use the **PageSpeed Insights API** (or a Docker‑wrapped Lighthouse with a pinned Chrome version) for deterministic, location‑independent results. |
| “Permission denied” when installing packages on Windows | Running the command without admin rights. | Add the `--user` flag: `py -m pip install --user requests tqdm python-dotenv`, or run the terminal as Administrator. |
