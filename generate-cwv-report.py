#!/usr/bin/env python3
"""
generate-cwv-report.py

Generates an HTML report summarizing Core Web Vitals (CWV) metrics
from PageSpeed Insights JSON files corresponding to a given URL or list of URLs.
"""

import argparse
import json
import pathlib
import datetime
import sys
from urllib.parse import urlparse
from pathlib import Path
import configparser
from typing import List, Optional
import pandas as pd

# --- Constants ---
config = configparser.ConfigParser()
config.read('config.ini')

REPORTS_DIR = pathlib.Path(config['Paths']['reports_dir'])
DEBUG_RESPONSES_DIR = pathlib.Path(config['Paths']['debug_dir'])
URL_LISTS_DIR = pathlib.Path(config['Paths']['url_lists_dir'])

# --- Constants for CWV Thresholds ---
LCP_THRESHOLDS = {"good": 2500, "ni": 4000}  # Largest Contentful Paint (ms)
FID_THRESHOLDS = {"good": 100, "ni": 300}   # First Input Delay (ms) - using Max Potential FID
CLS_THRESHOLDS = {"good": 0.1, "ni": 0.25}  # Cumulative Layout Shift (unitless)

def get_metric_rating(value, thresholds):
    """Categorizes a metric value as 'Good', 'Needs Improvement', or 'Poor'."""
    if value is None or pd.isna(value):
        return "N/A"
    if value <= thresholds["good"]:
        return "Good"
    if value <= thresholds["ni"]:
        return "Needs Improvement"
    return "Poor"

def get_rating_color(rating):
    """Returns a color code based on the metric rating."""
    if rating == "Good":
        return "#6ECC00"
    if rating == "Needs Improvement":
        return "#E5AC00"
    if rating == "Poor":
        return "#E54545"
    return "#808080"

def load_urls(path: str) -> List[str]:
    """Read URLs from a file, one per line, stripping whitespace."""
    file_path = Path(path)
    if not file_path.is_absolute():
        file_path = URL_LISTS_DIR / path
    
    if not file_path.exists():
        print(f"[ERROR] URL file '{path}' not found.", file=sys.stderr)
        sys.exit(1)
        
    with open(file_path, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f.readlines() if line.strip()]
        
    if not urls:
        print(f"[ERROR] No URLs found in the file: {file_path}", file=sys.stderr)
        sys.exit(1)
        
    return urls

def get_timestamp_from_stem(stem: str) -> str:
    """Robustly extracts the timestamp from a filename stem."""
    if '-desktop-' in stem:
        return stem.split('-desktop-')[1]
    if '-mobile-' in stem:
        return stem.split('-mobile-')[1]
    return ""

def find_report_files(url: str, start_date: Optional[datetime.date] = None, end_date: Optional[datetime.date] = None, last_n_runs: Optional[int] = None) -> List[pathlib.Path]:
    """Finds relevant JSON report files for a given URL and time range."""
    parsed_url = urlparse(url)
    site_dir_name = parsed_url.netloc.replace("www.", "").replace(".", "-")
    page_slug = parsed_url.path.strip("/").replace("/", "_") or "_root_"
    
    site_debug_dir = DEBUG_RESPONSES_DIR / site_dir_name
    if not site_debug_dir.exists():
        return []

    search_pattern = f"{page_slug}-*-*.json"
    all_json_files = list(site_debug_dir.glob(search_pattern))
    if page_slug == "_root_":
         domain_slug_files = list(site_debug_dir.glob(f"{site_dir_name}-*-*.json"))
         all_json_files.extend(domain_slug_files)

    all_json_files = sorted(list(set(all_json_files)), key=lambda p: p.name, reverse=True)

    if last_n_runs:
        unique_timestamps = sorted(list(set(get_timestamp_from_stem(f.stem) for f in all_json_files if get_timestamp_from_stem(f.stem))), reverse=True)
        timestamps_to_keep = unique_timestamps[:last_n_runs]
        
        files_to_return = [f for f in all_json_files if get_timestamp_from_stem(f.stem) in timestamps_to_keep]
        return sorted(files_to_return, key=lambda p: p.name)

    files_to_return = []
    for f in all_json_files:
        timestamp_str = get_timestamp_from_stem(f.stem)
        try:
            file_datetime = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d-%H%M%S")
        except ValueError:
            try:
                file_datetime = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d-%H%M")
            except ValueError:
                continue
        
        file_date = file_datetime.date()
        if (not start_date or file_date >= start_date) and (not end_date or file_date <= end_date):
            files_to_return.append(f)
            
    return sorted(files_to_return, key=lambda p: p.name)

def process_json_file(file_path):
    """Processes a single PageSpeed JSON file to extract CWV data."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"Skipping malformed or missing file: {file_path} ({e})")
        return None

    audits = data.get("lighthouseResult", {}).get("audits", {})
    timestamp_str = get_timestamp_from_stem(file_path.stem)
    try:
        timestamp = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d-%H%M%S")
    except ValueError:
        timestamp = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d-%H%M")

    return {
        "timestamp": timestamp,
        "url": data.get("id", "N/A"),
        "strategy": data.get("lighthouseResult", {}).get("configSettings", {}).get("emulatedFormFactor", "N/A").capitalize(),
        "lcp": audits.get("largest-contentful-paint", {}).get("numericValue"),
        "fid": audits.get("max-potential-fid", {}).get("numericValue"),
        "cls": audits.get("cumulative-layout-shift", {}).get("numericValue"),
    }

def create_html_report(df, aggregated_data, report_name_base, date_range_str):
    """Generates the HTML report string."""
    
    chart_data = json.dumps({
        "labels": ["Largest Contentful Paint (LCP)", "First Input Delay (FID)", "Cumulative Layout Shift (CLS)"],
        "datasets": [
            {"label": "Good", "data": [aggregated_data["lcp"]["Good"], aggregated_data["fid"]["Good"], aggregated_data["cls"]["Good"]], "backgroundColor": get_rating_color("Good")},
            {"label": "Needs Improvement", "data": [aggregated_data["lcp"]["Needs Improvement"], aggregated_data["fid"]["Needs Improvement"], aggregated_data["cls"]["Needs Improvement"]], "backgroundColor": get_rating_color("Needs Improvement")},
            {"label": "Poor", "data": [aggregated_data["lcp"]["Poor"], aggregated_data["fid"]["Poor"], aggregated_data["cls"]["Poor"]], "backgroundColor": get_rating_color("Poor")},
        ]
    })

    table_rows = ""
    for index, row in df.iterrows():
        lcp_rating = get_metric_rating(row['lcp'], LCP_THRESHOLDS)
        fid_rating = get_metric_rating(row['fid'], FID_THRESHOLDS)
        cls_rating = get_metric_rating(row['cls'], CLS_THRESHOLDS)
        table_rows += f"""
        <tr>
            <td>{row['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}</td>
            <td>{row['strategy']}</td>
            <td style="background-color: {get_rating_color(lcp_rating)}">{f"{row['lcp']:.0f} ms" if pd.notna(row['lcp']) else 'N/A'}</td>
            <td style="background-color: {get_rating_color(fid_rating)}">{f"{row['fid']:.0f} ms" if pd.notna(row['fid']) else 'N/A'}</td>
            <td style="background-color: {get_rating_color(cls_rating)}">{f"{row['cls']:.3f}" if pd.notna(row['cls']) else 'N/A'}</td>
        </tr>
        """

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>CWV History Report: {report_name_base}</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body {{ background-color: #f8f9fa; }}
            .container {{ padding-top: 2rem; padding-bottom: 2rem; }}
            .chart-container {{ max-width: 800px; margin: 2rem auto; }}
            td, th {{ text-align: center; vertical-align: middle; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="text-center mb-4">
                <h1 class="display-5">Core Web Vitals History Report</h1>
                <p class="lead">URL: <strong>{report_name_base}</strong> | {date_range_str}</p>
            </div>
            
            <div class="chart-container">
                <canvas id="cwvChart"></canvas>
            </div>

            <div class="card mt-5">
                <div class="card-header">
                    <h2 class="h5 mb-0">Detailed History</h2>
                </div>
                <div class="table-responsive">
                    <table class="table table-striped table-hover mb-0">
                        <thead class="table-light">
                            <tr>
                                <th>Timestamp</th>
                                <th>Strategy</th>
                                <th>LCP</th>
                                <th>FID (MPFID)</th>
                                <th>CLS</th>
                            </tr>
                        </thead>
                        <tbody>
                            {table_rows}
                        </tbody>
                    </table>
                </div>
            </div>
            <div class="footer text-center mt-4 text-muted">
                <p>Generated by generate-cwv-report.py | Learn more: <a href="https://developers.google.com/speed/docs/insights/v5/about" target="_blank">PageSpeed Insights Documentation</a> | <a href="https://googlechrome.github.io/lighthouse/viewer/" target="_blank">Lighthouse Report Viewer</a> | <a href="https://github.com/liamdelahunty/pagespeed" target="_blank">GitHub Repository</a></p>
            </div>
        </div>
        <script>
            const ctx = document.getElementById('cwvChart').getContext('2d');
            new Chart(ctx, {{
                type: 'bar',
                data: {chart_data},
                options: {{
                    responsive: true,
                    plugins: {{
                        title: {{ display: true, text: 'Core Web Vitals Distribution' }},
                    }},
                    scales: {{
                        x: {{ stacked: true }},
                        y: {{ stacked: true, beginAtZero: true }}
                    }}
                }}
            }});
        </script>
    </body>
    </html>
    """

def main():
    """Main function to generate the CWV report."""
    parser = argparse.ArgumentParser(
        description="Generate a Core Web Vitals HTML report from existing PageSpeed JSON data.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-f", "--url-file", type=str, help="Path to a file containing a list of URLs.")
    group.add_argument("-u", "--url", type=str, help="A single URL to generate a report for.")
    
    period_group = parser.add_mutually_exclusive_group()
    period_group.add_argument("--period", type=str, choices=['7d', '28d', 'this-month', 'last-month', 'all-time'], help="Define the reporting period.")
    period_group.add_argument("--last-runs", type=int, metavar='N', help="Report on the last N unique runs for each URL.")
    
    args = parser.parse_args()

    urls_to_process = [args.url] if args.url else load_urls(args.url_file)

    start_date, end_date = None, datetime.date.today()
    if args.period:
        if args.period == '7d': start_date = end_date - datetime.timedelta(days=7)
        elif args.period == '28d': start_date = end_date - datetime.timedelta(days=28)
        elif args.period == 'this-month': start_date = end_date.replace(day=1)
        elif args.period == 'last-month':
            first_day_this_month = end_date.replace(day=1)
            end_date = first_day_this_month - datetime.timedelta(days=1)
            start_date = end_date.replace(day=1)
        elif args.period == 'all-time': start_date = None

    print(f"🔎 Processing {len(urls_to_process)} URL(s) for CWV reports...")
    
    for url in urls_to_process:
        files_to_process = find_report_files(url, start_date, end_date, args.last_runs)
        
        if not files_to_process:
            print(f"  - No data found for {url}. Skipping.")
            continue

        report_data = [process_json_file(f) for f in files_to_process if f]
        report_data = [d for d in report_data if d is not None]

        if not report_data:
            print(f"  - Could not extract valid data for {url}. Skipping.")
            continue
            
        df = pd.DataFrame(report_data)

        # Aggregate data for the bar chart
        aggregated_data = {
            "lcp": {"Good": 0, "Needs Improvement": 0, "Poor": 0},
            "fid": {"Good": 0, "Needs Improvement": 0, "Poor": 0},
            "cls": {"Good": 0, "Needs Improvement": 0, "Poor": 0},
        }
        df['lcp_rating'] = df['lcp'].apply(lambda x: get_metric_rating(x, LCP_THRESHOLDS))
        df['fid_rating'] = df['fid'].apply(lambda x: get_metric_rating(x, FID_THRESHOLDS))
        df['cls_rating'] = df['cls'].apply(lambda x: get_metric_rating(x, CLS_THRESHOLDS))

        lcp_counts = df['lcp_rating'].value_counts().to_dict()
        fid_counts = df['fid_rating'].value_counts().to_dict()
        cls_counts = df['cls_rating'].value_counts().to_dict()

        for rating in ["Good", "Needs Improvement", "Poor"]:
            aggregated_data["lcp"][rating] = lcp_counts.get(rating, 0)
            aggregated_data["fid"][rating] = fid_counts.get(rating, 0)
            aggregated_data["cls"][rating] = cls_counts.get(rating, 0)

        # Determine date range for filename and title
        min_date_obj = df['timestamp'].min()
        max_date_obj = df['timestamp'].max()
        min_date_str = min_date_obj.strftime('%Y%m%d')
        max_date_str = max_date_obj.strftime('%Y%m%d')
        filename_suffix = f"{min_date_str}-{max_date_str}"
        
        date_range_display = f"Data from {min_date_obj.strftime('%Y-%m-%d')} to {max_date_obj.strftime('%Y-%m-%d')}"
        if min_date_str == max_date_str:
            date_range_display = f"Data from {min_date_obj.strftime('%Y-%m-%d')}"

        report_name_base = urlparse(url).netloc.replace("www.", "").replace(".", "-")
        
        # Generate and save the report
        report_content = create_html_report(df.sort_values(by="timestamp"), aggregated_data, report_name_base, date_range_display)
        
        REPORTS_DIR.mkdir(exist_ok=True)
        report_filename = REPORTS_DIR / f"cwv-history-report-{report_name_base}-{filename_suffix}.html"
        
        with open(report_filename, "w", encoding="utf-8") as f:
            f.write(report_content)

        print(f"  ✅ Successfully generated CWV report for {url}: {report_filename}")

if __name__ == "__main__":
    main()
