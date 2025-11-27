#!/usr/bin/env python3
"""
pagespeed_to_csv.py
Collect PageSpeed Insights / Lighthouse data for a list of URLs
and dump the results into a CSV file.

Change Log
----------
2025-10-24 - v1.2
    • Dropped the “PWA” category because the PageSpeed Insights API no longer returns it.  
    All references to the PWA column have been removed from:
        - the CSV header (`write_csv_header`)
        - the metric extraction (`extract_metrics`)
        - the row-building logic in `main()`.
    • Updated documentation throughout the file to reflect the new set of categories:
      Performance, Accessibility, Best-Practices, SEO.

Features
--------
* Handles both desktop and mobile strategies.
* Extracts overall category scores (Performance, Accessibility, Best Practices, SEO).
* Extracts the most common performance metrics:
    - First Contentful Paint (FCP)
    - Speed Index
    - Largest Contentful Paint (LCP)
    - Time to Interactive (TTI)
    - Total Blocking Time (TBT)
    - Cumulative Layout Shift (CLS)
    - Server Response Time (SRT)
* Simple CSV output.
* Saves a file named pagespeed-report-YYYY-MM-DD-HHMM.csv
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
Default:        All four (performance, accessibility, best-practices, seo) 
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

Author: Liam Victor Delahunty - October 2025
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
import argparse
from typing import List, Dict
from urllib.parse import urlparse
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
    raise RuntimeError("PSI_API_KEY not found - check your .env file.")

API_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


# Strategies we want to query - keep both unless you deliberately want only one.
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
            "seo"
        ],
    }
    try:
        r = requests.get(API_ENDPOINT, params=params, timeout=90)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as exc:
        raise RuntimeError(f"Request failed for {url} ({strategy}): {exc}") from exc

def dump_response(data: dict, url: str, strategy: str, timestamp: str):
    """Write the raw JSON to a readable file for debugging/storage."""
    parsed_url = urlparse(url)
    
    # Create a safe directory name from the URL's domain
    site_dir_name = parsed_url.netloc.replace("www.", "").replace(".", "-")

    # Create a safe "slug" from the URL path to identify the page
    path = parsed_url.path
    if not path or path == "/":
        page_slug = "_root_"
    else:
        # Sanitize the path: remove slashes, replace with underscores
        page_slug = path.strip("/").replace("/", "_")

    # Create the nested directory structure, e.g., /debug-responses/example-com/
    out_dir = pathlib.Path("debug-responses") / site_dir_name
    out_dir.mkdir(parents=True, exist_ok=True)

    # New filename includes the page slug for clear identification
    filename = out_dir / f"{page_slug}-{strategy}-{timestamp}.json"

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)

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

    # Category scores (0-1 range, convert to 0-100)
    cats = data.get("lighthouseResult", {}).get("categories", {})
    perf_score = int(_get(["lighthouseResult", "categories", "performance", "score"], 0) * 100)
    acc_score  = int(_get(["lighthouseResult", "categories", "accessibility", "score"], 0) * 100)
    bp_score   = int(_get(["lighthouseResult", "categories", "best-practices", "score"], 0) * 100)
    seo_score  = int(_get(["lighthouseResult", "categories", "seo", "score"], 0) * 100)
    
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
    parser = argparse.ArgumentParser(
        description="Collect PageSpeed Insights data for one or more URLs and save the results to a CSV file.",
        epilog=(
            "Examples:\n"
            "  # Test a single URL\n"
            "  python pagespeed_to_csv.py -u https://www.example.com\n\n"
            "  # Test all URLs from a file named 'custom_urls.txt'\n"
            "  python pagespeed_to_csv.py -f custom_urls.txt\n\n"
            "  # Show this help message\n"
            "  python pagespeed_to_csv.py --help"
        ),
        formatter_class=argparse.RawTextHelpFormatter  # Keeps epilog formatting
    )
    parser.add_argument(
        "-f", "--url-file",
        type=str,
        default="urls.txt", # Default value now handled by argparse directly
        help="Path to a file containing a list of URLs (one per line). Defaults to 'urls.txt'."
    )
    parser.add_argument(
        "-u", "--url",
        type=str,
        help="A single URL to test. If provided, --url-file will be ignored."
    )
    args = parser.parse_args()

    if not API_KEY:
        print("[ERROR] Please set the PSI_API_KEY environment variable.", file=sys.stderr)
        sys.exit(1)

    urls: List[str] = []
    report_name_base = ""

    if args.url:
        urls.append(args.url)
        parsed_url = urlparse(args.url)
        # Generate a safe filename from the URL's domain
        report_name_base = parsed_url.netloc.replace("www.", "").replace(".", "-")
        print(f"🔎 Testing single URL: {args.url}")
    else:
        urls = load_urls(args.url_file)
        report_name_base = Path(args.url_file).stem
        print(f"🔎 Using URL file: {args.url_file}")

    if not urls:
        print("[ERROR] No URLs provided for testing. Exiting.", file=sys.stderr)
        sys.exit(1)

    # Generate timestamp and output filename
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H%M")
    output_csv = REPORTS_DIR / f"pagespeed-report-{report_name_base}-{timestamp}.csv"

    total_requests = len(urls) * len(STRATEGIES)

    print(f"🔎 Running PageSpeed Insights for {len(urls)} URLs ({total_requests} requests total)")
    write_csv_header(output_csv)

    # Progress bar over the Cartesian product of URLs × strategies
    for url in tqdm(urls, desc="URLs", unit="url"):
        for strat in STRATEGIES:
            try:
                data = call_pagespeed(url, strat)
                dump_response(data, url, strat, timestamp)
                metrics = extract_metrics(data)

                # Build the CSV row - order must match the header defined above
                csv_row = [
                    time.strftime("%Y-%m-%d %H:%M"),   # Date
                    url,
                    "Desktop" if strat == "desktop" else "Mobile",
                    strat,
                    metrics["PerformanceScore"],
                    metrics["AccessibilityScore"],
                    metrics["BestPracticesScore"],
                    metrics["SEOScore"],
                    metrics["FCP_ms"],
                    metrics["SpeedIndex_ms"],
                    metrics["LCP_ms"],
                    metrics["TTI_ms"],
                    metrics["TBT_ms"],
                    metrics["CLS"],
                    metrics["SRT_ms"],
                    "",                         # Notes - you can fill manually later
                ]

                append_row(output_csv, csv_row)

            except Exception as e:
                tqdm.write(f"[WARN] {url} ({strat}) → {e}")
                # Write a row with empty scores so you can see which combos failed
                empty_row = [
                    time.strftime("%Y-%m-%d %H:%M"),
                    url,
                    "Desktop" if strat == "desktop" else "Mobile",
                    strat,
                    "", "", "", "",  # 4 score columns
                    "", "", "", "", "", "", "", # 7 metric columns
                    f"ERROR: {e}"        # put the error message in the Notes column
                ]
                append_row(output_csv, empty_row)

    print(f"\n✅ Finished. Results saved to '{output_csv}'.")
    print("Happy analysing!")

if __name__ == "__main__":
    main()
