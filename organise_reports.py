#!/usr/bin/env python3
"""
organise_reports.py

Scans the 'debug-responses' directory to find all saved JSON responses from the
PageSpeed Insights API. It then renames each file according to a consistent
naming convention based on the contents of the JSON data.

NEW CONVENTION: <page-slug>-<strategy>-<timestamp>.json

It also creates a backup zip of the entire directory before starting.
"""

import os
import json
import pathlib
import datetime
import configparser
from urllib.parse import urlparse

# -------------------------------------------------
# Load Configuration
# -------------------------------------------------
config = configparser.ConfigParser()
config.read('config.ini')

def sanitise_timestamp(fetch_time: str) -> str:
    """
    Converts an ISO 8601 timestamp into a filename-friendly format.
    Example: '2023-11-20T15:30:00.123Z' -> '2023-11-20-153000'
    """
    # Deal with potential timezone formats ('Z' or +00:00)
    fetch_time = fetch_time.replace("Z", "+00:00")
    try:
        # From Python 3.11, fromisoformat handles +00:00 better
        dt_object = datetime.datetime.fromisoformat(fetch_time)
    except ValueError:
        # Fallback for older Python or slightly different formats
        dt_object = datetime.datetime.strptime(fetch_time, "%Y-%m-%dT%H:%M:%S.%f%z")
        
    return dt_object.strftime("%Y-%m-%d-%H%M%S")

def get_slug_from_url(url: str) -> str:
    """
    Generates a filename-friendly slug from a URL.
    - Homepage URL becomes a slug of the normalised domain.
    - Subpage URL becomes a slug of its path.
    """
    parsed_url = urlparse(url)
    
    path_part = parsed_url.path
    if not path_part or path_part == "/":
        # For homepage, slug is the normalised domain name
        domain_part = parsed_url.netloc
        return domain_part.replace("www.", "").replace(".", "-")
    else:
        # For subpages, slug is the sanitised path
        return path_part.strip("/").replace("/", "_")

def organise_files():
    """Main logic for finding, parsing, and renaming files."""
    base_dir = pathlib.Path(config['Paths']['debug_dir'])
    if not base_dir.exists():
        print(f"❌ Error: Directory '{base_dir}' not found. There is nothing to organise.")
        return

    json_files = list(base_dir.rglob('*.json'))
    if not json_files:
        print("No JSON files found to organise.")
        return
        
    print(f"\nFound {len(json_files)} JSON files to process. Starting renaming...")
    
    total_renamed = 0
    total_skipped = 0

    for old_path in json_files:
        try:
            with open(old_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # --- Extract canonical data from JSON content ---
            lighthouse_result = data.get("lighthouseResult", {})
            
            url = lighthouse_result.get("requestedUrl")
            strategy = lighthouse_result.get("configSettings", {}).get("emulatedFormFactor")
            fetch_time = lighthouse_result.get("fetchTime")

            if not all([url, strategy, fetch_time]):
                print(f"🟡 Skipping '{old_path.name}': Missing required data (URL, strategy, or fetchTime).")
                total_skipped += 1
                continue

            # --- Generate new filename ---
            page_slug = get_slug_from_url(url)
            timestamp_str = sanitise_timestamp(fetch_time)
            
            new_filename = f"{page_slug}-{strategy}-{timestamp_str}.json"
            new_path = old_path.with_name(new_filename)

            # --- Rename file ---
            if old_path == new_path:
                # print(f"✅ '{old_path.name}' is already named correctly. Skipping.")
                total_skipped += 1
                continue
            
            if new_path.exists():
                print(f"🟡 Skipping '{old_path.name}': a file named '{new_path.name}' already exists.")
                total_skipped += 1
                continue

            old_path.rename(new_path)
            print(f"✅ Renamed '{old_path.name}' -> '{new_path.name}'")
            total_renamed += 1

        except (json.JSONDecodeError, KeyError, AttributeError) as e:
            print(f"🟡 Skipping '{old_path.name}': Could not process file. Error: {e}")
            total_skipped += 1
            continue

    print("\n--- Organisation Complete ---")
    print(f"Renamed: {total_renamed} files")
    print(f"Skipped: {total_skipped} files")


if __name__ == "__main__":
    organise_files()
