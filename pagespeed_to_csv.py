#!/usr/bin/env python3
"""
pagespeed_to_csv.py
Collect PageSpeed Insights / Lighthouse data for a list of URLs
and dump the results into a CSV file.

Features
--------
* Handles both desktop and mobile strategies.
* Extracts overall category scores (Performance, Accessibility, Best Practices, SEO, PWA).
* Extracts the most common performance metrics:
    - First Contentful Paint (FCP)
    - Speed Index
    - Largest Contentful Paint (LCP)
    - Time to Interactive (TTI)
    - Total Blocking Time (TBT)
    - Cumulative Layout Shift (CLS)
    - Server Response Time (SRT)
* Simple CSV output.
* Saves a file named pagespeed-report-YYYY‑MM‑DD‑HHMM.csv
* Dumps the raw JSON responses to debug-responses/
* Both saved with ISO date string for archiving.
* Basic error handling + progress bar.
* All results are deterministic (no cache, no cookies, fixed throttling), 
  making the CSV comparable across users and locations.

How to run
----------
#1 Install Python 3.8+ & upgrade pip
py -m pip install --upgrade pip

#2  Install required packages
py -m pip install requests tqdm python-dotenv

#3 Create a Google Cloud API key with the PageSpeed Insights API enabled.

#4 Save it in a .env file (same folder as the script):
echo "PSI_API_KEY=YOUR_KEY" > .env

#5  Add URLs to urls.txt (one per line)
echo "https://www.croneri.co.uk" > urls.txt

#6 Run the collector
python pagespeed_to_csv.py or run the code in Python IDLE or VS Code.

Configuration notes
-------------------
Setting:        API endpoint    
Default:        https://www.googleapis.com/pagespeedonline/v5/runPagespeed  
How to change:  Edit API_ENDPOINT constant in the script.

Setting:        Strategies
Default:        ("desktop", "mobile")   
How to change:  Modify STRATEGIES tuple.

Setting:        Categories  
Default:        All five (performance, accessibility, best‑practices, seo, pwa) 
How to change:  Adjust the category list in call_pagespeed.

Setting:        Timeout 
Default:        90 seconds  
How to change:  Change timeout= in requests.get.

Common issues & fixes
---------------------
Symptom:        NameError: PSI_API_KEY
Likely cause:   .env missing or variable misspelled
Fix:            Ensure .env exists and contains PSI_API_KEY=….

Symptom:        400 Bad Request	
Likely cause:   API key restricted (referrer/IP)	
Fix:            In Google Cloud Console → Credentials → Edit → set Application restrictions to None (or add your IP).

Symptom:        ModuleNotFoundError: requests	
Likely cause:   Dependencies not installed	
Fix:            Run py -m pip install requests tqdm python-dotenv.

Author: Liam Victor Delahunty – October 2025
"""
import os
import sys
import csv
import json
import time
import datetime
import pathlib
import requests
from tqdm import tqdm
from dotenv import load_dotenv
from typing import List, Dict
from pathlib import Path

# -------------------------------------------------
# Ensure the output directory exists
# -------------------------------------------------
REPORTS_DIR = pathlib.Path("reports")
REPORTS_DIR.mkdir(parents=True, exist_ok=True)   # creates ./reports if missing

# -------------------------------------------------
# Load environment variables
# -------------------------------------------------
load_dotenv()
API_KEY = os.getenv("PSI_API_KEY")
if not API_KEY:
    raise RuntimeError("PSI_API_KEY not found – check your .env file.")

API_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
TIMESTAMP = datetime.datetime.now().strftime("%Y-%m-%d-%H%M")
OUTPUT_CSV = REPORTS_DIR / f"pagespeed-report-{TIMESTAMP}.csv"
URLS_FILE = "urls.txt"

# Strategies we want to query – keep both unless you deliberately want only one.
STRATEGIES = ("desktop", "mobile")


# ----------------------------------------------------------------------
# HELPERS --------------------------------------------------------------
# ----------------------------------------------------------------------
def load_urls(path: str) -> List[str]:
    """Read URLs from a file, one per line, stripping whitespace."""
    if not Path(path).exists():
        print(f"[ERROR] URL file '{path}' not found.", file=sys.stderr)
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f.readlines() if line.strip()]
    if not urls:
        print("[ERROR] No URLs found in the file.", file=sys.stderr)
        sys.exit(1)
    return urls

def call_pagespeed(url: str, strategy: str) -> dict:
    """
    Perform a single PageSpeed Insights request.
    Returns the parsed JSON response (or raises on failure).
    """
    params = {
        "url": url,
        "strategy": strategy,
        "key": API_KEY,
        "category": [
            "performance",
            "accessibility",
            "best-practices",
            "seo",
            "pwa",
        ],
    }
    try:
        r = requests.get(API_ENDPOINT, params=params, timeout=90)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as exc:
        raise RuntimeError(f"Request failed for {url} ({strategy}): {exc}") from exc

def dump_response(data: dict, url: str, strategy: str):
    """Write the raw JSON to a readable file for debugging."""
    out_dir = pathlib.Path("debug-responses")
    out_dir.mkdir(exist_ok=True)

    # Build a safe filename:
    safe_url = url.replace("https://", "").replace("/", "-")
    filename = out_dir / f"{safe_url}-{strategy}-{TIMESTAMP}.json"

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)

    print(f"🔍 Dumped raw response to {filename}")

def extract_metrics(data: dict) -> Dict[str, object]:
    """
    Pull the fields we care about from the raw API response.
    Returns a flat dictionary ready for CSV writing.
    """
    # Helper to safely get nested values
    def _get(path: List[str], default=None):
        cur = data
        for p in path:
            cur = cur.get(p, {})
        return cur if cur != {} else default

    # Category scores (0‑1 range, convert to 0‑100)
    cats = data.get("lighthouseResult", {}).get("categories", {})
    perf_score = int(_get(["lighthouseResult", "categories", "performance", "score"], 0) * 100)
    acc_score  = int(_get(["lighthouseResult", "categories", "accessibility", "score"], 0) * 100)
    bp_score   = int(_get(["lighthouseResult", "categories", "best-practices", "score"], 0) * 100)
    seo_score  = int(_get(["lighthouseResult", "categories", "seo", "score"], 0) * 100)
    pwa_score  = int(_get(["lighthouseResult", "categories", "pwa", "score"], 0) * 100)

    # Performance metrics (numericValue is in ms for timing metrics,
    # unitless for CLS)
    audits = data.get("lighthouseResult", {}).get("audits", {})
    fcp  = int(_get(["lighthouseResult", "audits", "first-contentful-paint", "numericValue"], 0))
    si   = int(_get(["lighthouseResult", "audits", "speed-index", "numericValue"], 0))
    lcp  = int(_get(["lighthouseResult", "audits", "largest-contentful-paint", "numericValue"], 0))
    tti  = int(_get(["lighthouseResult", "audits", "interactive", "numericValue"], 0))
    tbt  = int(_get(["lighthouseResult", "audits", "total-blocking-time", "numericValue"], 0))
    cls  = float(_get(["lighthouseResult", "audits", "cumulative-layout-shift", "numericValue"], 0))
    srt  = int(_get(["lighthouseResult", "audits", "server-response-time", "numericValue"], 0))

    return {
        "PerformanceScore": perf_score,
        "AccessibilityScore": acc_score,
        "BestPracticesScore": bp_score,
        "SEOScore": seo_score,
        "PWAScore": pwa_score,
        "FCP_ms": fcp,
        "SpeedIndex_ms": si,
        "LCP_ms": lcp,
        "TTI_ms": tti,
        "TBT_ms": tbt,
        "CLS": round(cls, 4),
        "SRT_ms": srt,
    }


def write_csv_header(csv_path: str):
    header = [
        "Date",
        "URL",
        "Device",
        "Strategy",
        "PerfScore",
        "AccessibilityScore",
        "BestPracticesScore",
        "SEOScore",
        "PWAScore",
        "FCP_ms",
        "SpeedIndex_ms",
        "LCP_ms",
        "TTI_ms",
        "TBT_ms",
        "CLS",
        "SRT_ms",
        "Notes",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)


def append_row(csv_path: str, row: List[object]):
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(row)


# ----------------------------------------------------------------------
# MAIN LOGIC -----------------------------------------------------------
# ----------------------------------------------------------------------
def main():
    if not API_KEY:
        print("[ERROR] Please set the PSI_API_KEY environment variable.", file=sys.stderr)
        sys.exit(1)

    urls = load_urls(URLS_FILE)
    total_requests = len(urls) * len(STRATEGIES)

    print(f"🔎 Running PageSpeed Insights for {len(urls)} URLs ({total_requests} requests total)")
    write_csv_header(OUTPUT_CSV)

    # Progress bar over the Cartesian product of URLs × strategies
    for url in tqdm(urls, desc="URLs", unit="url"):
        for strat in STRATEGIES:
            try:
                data = call_pagespeed(url, strat)
                dump_response(data, url, strat)   
                metrics = extract_metrics(data)

                # Build the CSV row – order must match the header defined above
                csv_row = [
                    time.strftime("%Y-%m-%d"),   # Date
                    url,
                    "Desktop" if strat == "desktop" else "Mobile",
                    strat,
                    metrics["PerformanceScore"],
                    metrics["AccessibilityScore"],
                    metrics["BestPracticesScore"],
                    metrics["SEOScore"],
                    metrics["PWAScore"],
                    metrics["FCP_ms"],
                    metrics["SpeedIndex_ms"],
                    metrics["LCP_ms"],
                    metrics["TTI_ms"],
                    metrics["TBT_ms"],
                    metrics["CLS"],
                    metrics["SRT_ms"],
                    "",                         # Notes – you can fill manually later
                ]

                append_row(OUTPUT_CSV, csv_row)

            except Exception as e:
                tqdm.write(f"[WARN] {url} ({strat}) → {e}")
                # Write a row with empty scores so you can see which combos failed
                empty_row = [
                    time.strftime("%Y-%m-%d"),
                    url,
                    "Desktop" if strat == "desktop" else "Mobile",
                    strat,
                    "", "", "", "", "",   # five score columns left blank
                    "", "", "", "", "", "", "", "",  # performance metric columns blank
                    f"ERROR: {e}"        # put the error message in the Notes column
                ]
                append_row(OUTPUT_CSV, empty_row)

    print(f"\n✅ Finished. Results saved to '{OUTPUT_CSV}'.")
    print("Happy analysing!")

if __name__ == "__main__":
    main()
