#!/usr/bin/env python3
"""
generate_summary_report.py
Generates a consolidated HTML summary report showing the performance 
score progress for a list of URLs over a given period.

Can also generate a 'latest score' report with the --group-report flag.
"""
import os
import sys
import json
import datetime
import pathlib
import argparse
import pandas as pd
import plotly.graph_objects as go
from jinja2 import Environment, FileSystemLoader
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse
from pathlib import Path

# --- Constants ---
REPORTS_DIR = pathlib.Path("reports")
DEBUG_RESPONSES_DIR = pathlib.Path("debug-responses")
URL_LISTS_DIR = pathlib.Path("url-lists")

# Strategies we expect to find data for
STRATEGIES = ("desktop", "mobile")

# Ensure necessary directories exist
REPORTS_DIR.mkdir(exist_ok=True)

# --- Helper Functions ---

def load_urls(path: str) -> List[str]:
    """Read URLs from a file, one per line, stripping whitespace."""
    file_path = Path(path)
    if not file_path.exists():
        file_path = URL_LISTS_DIR / path
        if not file_path.exists():
            print(f"[ERROR] URL file '{path}' not found in the root or in '{URL_LISTS_DIR}'.", file=sys.stderr)
            sys.exit(1)
    with open(file_path, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f.readlines() if line.strip()]
    if not urls:
        print(f"[ERROR] No URLs found in the file: {file_path}", file=sys.stderr)
        sys.exit(1)
    return urls

def load_grouped_urls(path: str) -> Optional[List[Dict[str, str]]]:
    """Read grouped URLs from a JSON file."""
    file_path = Path(path)
    if not file_path.exists():
        return None
    
    with open(file_path, "r", encoding="utf-8") as f:
        try:
            grouped_data = json.load(f)
            if not isinstance(grouped_data, list):
                print(f"[ERROR] Expected a JSON array in '{file_path}'.", file=sys.stderr)
                return None
            for item in grouped_data:
                if not all(k in item for k in ["Company", "Type", "URL"]):
                    print(f"[ERROR] Each item in '{file_path}' must have 'Company', 'Type', and 'URL' keys.", file=sys.stderr)
                    return None
            return grouped_data
        except json.JSONDecodeError as e:
            print(f"[ERROR] Invalid JSON in file '{file_path}': {e}", file=sys.stderr)
            return None

def get_timestamp_from_stem(stem: str) -> str:
    """Robustly extracts the timestamp from a filename stem."""
    if '-desktop-' in stem:
        return stem.split('-desktop-')[1]
    if '-mobile-' in stem:
        return stem.split('-mobile-')[1]
    return ""

def get_latest_pagespeed_data(url: str, strategy: str) -> Optional[Dict[str, Any]]:
    """Retrieves the latest PageSpeed Insights data for a given URL and strategy."""
    parsed_url = urlparse(url)
    site_dir_name = parsed_url.netloc.replace("www.", "").replace(".", "-")
    page_slug = parsed_url.path.strip("/").replace("/", "_") or "_root_"
    
    site_debug_dir = DEBUG_RESPONSES_DIR / site_dir_name
    if not site_debug_dir.exists():
        return None

    search_pattern = f"{page_slug}-{strategy}-*.json"
    
    json_files = list(site_debug_dir.glob(search_pattern))
    if page_slug == "_root_":
        domain_pattern = f"{site_dir_name}-{strategy}-*.json"
        json_files.extend(list(site_debug_dir.glob(domain_pattern)))
    
    if not json_files:
        return None

    # Sort files by timestamp in their stem, descending, to get the latest
    json_files.sort(key=lambda p: get_timestamp_from_stem(p.stem), reverse=True)
    
    for json_file in json_files:
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                score = data.get("lighthouseResult", {}).get("categories", {}).get("performance", {}).get("score")
                
                if score is not None:
                    perf_score = int(score * 100)
                    stem = json_file.stem
                    file_timestamp_str = get_timestamp_from_stem(stem)
                    
                    try:
                        file_datetime = datetime.datetime.strptime(file_timestamp_str, "%Y-%m-%d-%H%M%S")
                    except ValueError:
                        file_datetime = datetime.datetime.strptime(file_timestamp_str, "%Y-%m-%d-%H%M")
                    
                    return {
                        "score": perf_score,
                        "timestamp_str": file_datetime.strftime("%Y-%m-%d %H:%M:%S"),
                        "timestamp_dt": file_datetime
                    }
        except Exception as e:
            print(f"[WARN] Could not process file {json_file}: {e}", file=sys.stderr)
            continue
            
    return None

def get_historical_data(url: str, start_date: datetime.date = None, end_date: datetime.date = None, last_n_runs: int = None) -> pd.DataFrame:
    """Retrieves historical PageSpeed Insights data for a given URL."""
    parsed_url = urlparse(url)
    site_dir_name = parsed_url.netloc.replace("www.", "").replace(".", "-")
    page_slug = parsed_url.path.strip("/").replace("/", "_") or "_root_"
    
    site_debug_dir = DEBUG_RESPONSES_DIR / site_dir_name
    if not site_debug_dir.exists():
        return pd.DataFrame()

    all_json_files = list(site_debug_dir.glob(f"{page_slug}-*-*.json"))
    if page_slug == "_root_":
        domain_slug_files = list(site_debug_dir.glob(f"{site_dir_name}-*-*.json"))
        all_json_files.extend(domain_slug_files)
    
    all_json_files = sorted(list(set(all_json_files)), key=lambda p: p.name, reverse=True)

    if last_n_runs is not None:
        unique_timestamps = sorted(list(set([get_timestamp_from_stem(f.stem) for f in all_json_files if get_timestamp_from_stem(f.stem)])), reverse=True)
        timestamps_for_n_runs = unique_timestamps[:last_n_runs]
        
        filtered_json_files = []
        for ts in timestamps_for_n_runs:
            for f in all_json_files:
                if get_timestamp_from_stem(f.stem) == ts and f not in filtered_json_files:
                    filtered_json_files.append(f)
        all_json_files = sorted(filtered_json_files, key=lambda p: p.name)
    
    data_records = []
    for json_file in all_json_files:
        try:
            stem = json_file.stem
            file_strategy = 'desktop' if '-desktop-' in stem else 'mobile'
            file_page_slug, file_timestamp_str = stem.split(f'-{file_strategy}-')

            is_valid_slug = (file_page_slug == page_slug) or (page_slug == "_root_" and file_page_slug == site_dir_name)
            if not is_valid_slug:
                continue

            try:
                file_datetime = datetime.datetime.strptime(file_timestamp_str, "%Y-%m-%d-%H%M%S")
            except ValueError:
                file_datetime = datetime.datetime.strptime(file_timestamp_str, "%Y-%m-%d-%H%M")
            
            file_date = file_datetime.date()

            if last_n_runs is None:
                if start_date and file_date < start_date: continue
                if end_date and file_date > end_date: continue
            
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                perf_score = int(data.get("lighthouseResult", {}).get("categories", {}).get("performance", {}).get("score", 0) * 100)
                record = {"Date": file_datetime, "URL": url, "Strategy": file_strategy, "PerformanceScore": perf_score}
                data_records.append(record)
        except Exception as e:
            print(f"[WARN] Could not process file {json_file}: {e}", file=sys.stderr)
            continue
    
    if not data_records: return pd.DataFrame()
    return pd.DataFrame(data_records).sort_values(by="Date").reset_index(drop=True)

def create_summary_plot(all_dfs: List[pd.DataFrame], strategy: str) -> str:
    """Generates a consolidated Plotly line chart for a given strategy."""
    fig = go.Figure()
    
    for df in all_dfs:
        strategy_df = df[df['Strategy'] == strategy]
        if not strategy_df.empty:
            url_label = strategy_df['URL'].iloc[0].replace('https://', '').replace('http://', '')
            fig.add_trace(go.Scatter(
                x=strategy_df["Date"],
                y=strategy_df["PerformanceScore"],
                mode='lines+markers',
                name=url_label
            ))

    fig.update_layout(
        title_text=f"Performance Score Trends ({strategy.capitalize()})",
        xaxis_title="Date",
        yaxis_title="Performance Score",
        hovermode="x unified",
        template="plotly_white",
        height=500,
        legend_title_text='URLs'
    )
    
    return fig.to_html(full_html=False, include_plotlyjs='cdn')

# --- Main Logic ---
def main():
    parser = argparse.ArgumentParser(
        description="Generate HTML summary reports of PageSpeed performance scores.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "-f", "--url-file",
        type=str,
        required=True,
        help="Path to a file containing a list of URLs."
    )
    parser.add_argument(
        "--group-report",
        action="store_true",
        help="Generate a single HTML report of the latest scores, optionally grouped by a companion JSON file."
    )
    # Argument group for the historical summary report
    period_group = parser.add_mutually_exclusive_group()
    period_group.add_argument(
        "--period",
        type=str,
        choices=['7d', '28d', 'this-month', 'last-month', 'all-time'],
        help="Define the reporting period for the historical summary."
    )
    period_group.add_argument(
        "--last-runs",
        type=int,
        metavar='N',
        help="Report on the last N unique runs for each URL for the historical summary."
    )
    args = parser.parse_args()

    # --- Group Report Mode ---
    if args.group_report:
        run_group_report(args)
    # --- Default Historical Summary Mode ---
    else:
        # Validate that period or last-runs is provided if not in group-report mode
        if not args.period and not args.last_runs:
            parser.error("--period or --last-runs is required when --group-report is not specified.")
        run_historical_summary(args)

def run_group_report(args: argparse.Namespace):
    """Generates a report of the latest scores for a list of URLs."""
    urls_to_process = load_urls(args.url_file)
    print(f"🔎 Processing {len(urls_to_process)} URLs from file: {args.url_file} for latest score report.")

    url_file_path = Path(args.url_file)
    if not url_file_path.exists():
        url_file_path = URL_LISTS_DIR / args.url_file
    
    ordering_json_path = url_file_path.parent / f"{url_file_path.stem}-ordering.json"
    grouped_data = load_grouped_urls(str(ordering_json_path))

    template_loader = FileSystemLoader(searchpath="./")
    env = Environment(loader=template_loader)

    def score_style(score):
        try:
            score = int(score)
            color = ""
            if score >= 90:
                color = "#7CFC00"  # Green
            elif score >= 50:
                color = "#FFBF00"  # Amber
            else:
                color = "#FF4D4D"  # Red
            return f'style="background-color: {color}; text-align: center;"'
        except (ValueError, TypeError):
            return 'style="text-align: center;"'

    env.filters['score_style'] = score_style

    def score_color_class(score):
        try:
            score = int(score)
            if score >= 90: return "score-green"
            if score >= 50: return "score-amber"
            return "score-red"
        except (ValueError, TypeError):
            return ""
    env.filters['score_color_class'] = score_color_class

    all_timestamps = []
    
    # --- Logic for Grouped/Ordered Report ---
    if grouped_data:
        print(f"📖 Found ordering file: {ordering_json_path}. Generating grouped report.")
        
        report_data = []
        # Iterate through the ordering file to maintain the desired order
        for group_item in grouped_data:
            url = group_item['URL']
            
            # Only process URLs that are also in the primary url-file
            if url not in urls_to_process:
                continue

            desktop_data = get_latest_pagespeed_data(url, "desktop")
            mobile_data = get_latest_pagespeed_data(url, "mobile")
            
            if desktop_data: all_timestamps.append(desktop_data['timestamp_dt'])
            if mobile_data: all_timestamps.append(mobile_data['timestamp_dt'])

            report_data.append({
                "company": group_item['Company'],
                "type": group_item['Type'],
                "url": url,
                "desktop_score": desktop_data['score'] if desktop_data else "N/A",
                "mobile_score": mobile_data['score'] if mobile_data else "N/A"
            })
        
        template_str = GROUPED_REPORT_TEMPLATE
        render_context = {
            "report_data": report_data
        }

    # --- Logic for Simple (Ungrouped) Report ---
    else:
        print(f"📖 Ordering file not found. Generating simple report.")
        results = []
        for url in urls_to_process:
            desktop_data = get_latest_pagespeed_data(url, "desktop")
            mobile_data = get_latest_pagespeed_data(url, "mobile")
            
            if desktop_data: all_timestamps.append(desktop_data['timestamp_dt'])
            if mobile_data: all_timestamps.append(mobile_data['timestamp_dt'])
            
            results.append({
                "url": url,
                "desktop_score": desktop_data['score'] if desktop_data else "N/A",
                "mobile_score": mobile_data['score'] if mobile_data else "N/A"
            })
            
        template_str = SIMPLE_REPORT_TEMPLATE
        render_context = {
            "results": results
        }

    # --- Filename and Subtitle Generation ---
    report_name_base = url_file_path.stem
    min_date_str, max_date_str = "", ""
    if all_timestamps:
        min_date = min(all_timestamps)
        max_date = max(all_timestamps)
        filename_suffix = f"{min_date.strftime('%Y%m%d')}-{max_date.strftime('%Y%m%d')}"
        min_date_str = min_date.strftime('%Y-%m-%d')
        max_date_str = max_date.strftime('%Y-%m-%d')
    else:
        now = datetime.datetime.now()
        filename_suffix = now.strftime("%Y%m%d")
        min_date_str = max_date_str = now.strftime('%Y-%m-%d')

    render_context.update({
        "generation_date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "start_date": min_date_str,
        "end_date": max_date_str
    })
        
    output_filename = REPORTS_DIR / f"latest-scores-{report_name_base}-{filename_suffix}.html"
    
    # --- Render and Write ---
    html_output = env.from_string(template_str).render(**render_context)
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(html_output)
    print(f"\n✅ Latest score report generated: {output_filename}")


def run_historical_summary(args: argparse.Namespace):
    """Generates a historical summary report with trend graphs."""
    urls_to_process = load_urls(args.url_file)
    print(f"🔎 Processing {len(urls_to_process)} URLs from file: {args.url_file} for historical summary.")

    start_date, end_date = None, datetime.date.today()
    if args.period:
        if args.period == '7d': start_date = end_date - datetime.timedelta(days=7)
        elif args.period == '28d': start_date = end_date - datetime.timedelta(days=28)
        elif args.period == 'this-month': start_date = end_date.replace(day=1)
        elif args.period == 'last-month':
            first_day_this_month = end_date.replace(day=1)
            last_day_last_month = first_day_this_month - datetime.timedelta(days=1)
            start_date, end_date = last_day_last_month.replace(day=1), last_day_last_month
        elif args.period == 'all-time': start_date = datetime.date(2000, 1, 1)

    print(f"🗓️ Reporting for period: {args.period or f'last {args.last_runs} runs'}")
    if start_date and end_date and args.period != 'all-time':
        print(f"    (From {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')})")

    summary_data = []
    all_dfs = []

    for url in urls_to_process:
        df = get_historical_data(url, start_date=start_date, end_date=end_date, last_n_runs=args.last_runs)
        if df.empty:
            print(f"\n[WARN] No data found for {url} within the specified period.")
            continue
        
        all_dfs.append(df)

        for strategy in STRATEGIES:
            strategy_df = df[df['Strategy'] == strategy]
            if len(strategy_df) > 1:
                first_run = strategy_df.iloc[0]
                last_run = strategy_df.iloc[-1]
                
                start_score = first_run['PerformanceScore']
                end_score = last_run['PerformanceScore']
                change = end_score - start_score
                
                summary_data.append({
                    "url": url,
                    "strategy": strategy.capitalize(),
                    "start_date": first_run['Date'].strftime('%Y-%m-%d'),
                    "start_score": start_score,
                    "end_date": last_run['Date'].strftime('%Y-%m-%d'),
                    "end_score": end_score,
                    "change": f"+{change}" if change > 0 else str(change)
                })

    if not all_dfs:
        print("[ERROR] No data available to generate a summary report. Exiting.", file=sys.stderr)
        sys.exit(1)

    desktop_plot_html = create_summary_plot(all_dfs, 'desktop')
    mobile_plot_html = create_summary_plot(all_dfs, 'mobile')

    template_loader = FileSystemLoader(searchpath="./")
    env = Environment(loader=template_loader)
    
    full_report_df = pd.concat(all_dfs)
    min_date_obj = full_report_df['Date'].min()
    max_date_obj = full_report_df['Date'].max()
    
    report_name_base = Path(args.url_file).stem
    filename_suffix = f"{min_date_obj.strftime('%Y%m%d')}-{max_date_obj.strftime('%Y%m%d')}"
    output_filename = REPORTS_DIR / f"summary-report-{report_name_base}-{filename_suffix}.html"

    html_output = env.from_string(HISTORICAL_SUMMARY_TEMPLATE).render(
        summary_data=summary_data,
        period_display=args.period or f"Last {args.last_runs} runs",
        desktop_plot=desktop_plot_html,
        mobile_plot=mobile_plot_html,
        generation_date=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        start_date=min_date_obj.strftime('%Y-%m-%d'),
        end_date=max_date_obj.strftime('%Y-%m-%d')
    )

    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(html_output)
    
    print(f"\n✅ Consolidated summary report generated: {output_filename}")


# --- HTML Templates ---

SIMPLE_REPORT_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PageSpeed Insights Scores</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet" integrity="sha384-T3c6CoIi6uLrA9TneNEoa7RxnatzjcDSCmG1MXxSR1GAsXEV/Dwwykc2MPK8M2HN" crossorigin="anonymous">
    <style>
        body {
            background-color: #f8f9fa;
        }
        .score {
            text-align: center;
        }
        .card-header {
            background-color: #0d6efd;
            color: white;
        }
        .container {
            padding-top: 2rem;
            padding-bottom: 2rem;
        }
        .table {
            table-layout: fixed;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="text-center mb-4">
            <h1 class="display-4">PageSpeed Insights Scores</h1>
            <p class="lead">Generated on {{ generation_date }}. {% if start_date == end_date %}Data from {{ start_date }}.{% else %}Data from {{ start_date }} to {{ end_date }}.{% endif %}</p>
        </div>

        <div class="card">
            <div class="table-responsive">
                <table class="table table-striped table-hover mb-0">
                    <thead class="table-light">
                        <tr>
                            <th scope="col">URL</th>
                            <th scope="col" class="score" style="width: 20%;">Desktop Score</th>
                            <th scope="col" class="score" style="width: 20%;">Mobile Score</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for item in results %}
                        <tr>
                            <td><a href="{{ item.url }}" target="_blank">{{ item.url }}</a></td>
                            <td {{ item.desktop_score | score_style }}>{{ item.desktop_score }}</td>
                            <td {{ item.mobile_score | score_style }}>{{ item.mobile_score }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>

        <div class="footer text-center mt-4 text-muted">
            <p>Generated by generate_summary_report.py | Learn more: <a href="https://developers.google.com/speed/docs/insights/v5/about" target="_blank">PageSpeed Insights Documentation</a> | <a href="https://googlechrome.github.io/lighthouse/viewer/" target="_blank">Lighthouse Report Viewer</a> | <a href="https://github.com/liamdelahunty/pagespeed" target="_blank">GitHub Repository</a></p>
        </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js" integrity="sha384-C6RzsynM9kWDrMNeT87bh95OGNyZPhcTNXj1NW7RuBCsyN/o0jlpcV8Qyq46cDfL" crossorigin="anonymous"></script>
</body>
</html>
"""

GROUPED_REPORT_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PageSpeed Insights Scores</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet" integrity="sha384-T3c6CoIi6uLrA9TneNEoa7RxnatzjcDSCmG1MXxSR1GAsXEV/Dwwykc2MPK8M2HN" crossorigin="anonymous">
    <style>
        body {
            background-color: #f8f9fa;
        }
        .score {
            text-align: center;
        }
        .card-header {
            background-color: #0d6efd;
            color: white;
        }
        .container {
            padding-top: 2rem;
            padding-bottom: 2rem;
        }
        .table {
            table-layout: fixed;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="text-center mb-4">
            <h1 class="display-4">PageSpeed Insights Scores</h1>
            <p class="lead">Generated on {{ generation_date }}. {% if start_date == end_date %}Data from {{ start_date }}.{% else %}Data from {{ start_date }} to {{ end_date }}.{% endif %}</p>
        </div>

        {% for item in report_data | groupby('company') %}
        <div class="card mb-4">
            <div class="card-header">
                <h2 class="h5 mb-0">{{ item.grouper }}</h2>
            </div>
            <div class="table-responsive">
                <table class="table table-striped table-hover mb-0">
                    <thead class="table-light">
                        <tr>
                            <th scope="col" style="width: 15%;">Type</th>
                            <th scope="col">URL</th>
                            <th scope="col" class="score" style="width: 15%;">Desktop Score</th>
                            <th scope="col" class="score" style="width: 15%;">Mobile Score</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for row in item.list %}
                        <tr>
                            <td>{{ row.type }}</td>
                            <td><a href="{{ row.url }}" target="_blank">{{ row.url }}</a></td>
                            <td {{ row.desktop_score | score_style }}>{{ row.desktop_score }}</td>
                            <td {{ row.mobile_score | score_style }}>{{ row.mobile_score }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
        {% endfor %}

        <div class="footer text-center mt-4 text-muted">
             <p>Generated by generate_summary_report.py | Learn more: <a href="https://developers.google.com/speed/docs/insights/v5/about" target="_blank">PageSpeed Insights Documentation</a> | <a href="https://googlechrome.github.io/lighthouse/viewer/" target="_blank">Lighthouse Report Viewer</a> | <a href="https://github.com/liamdelahunty/pagespeed" target="_blank">GitHub Repository</a></p>
        </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js" integrity="sha384-C6RzsynM9kWDrMNeT87bh95OGNyZPhcTNXj1NW7RuBCsyN/o0jlpcV8Qyq46cDfL" crossorigin="anonymous"></script>
</body>
</html>
"""

HISTORICAL_SUMMARY_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Performance Score Summary Report</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 20px; background-color: #f4f7f6; color: #333; }
        .container { max-width: 1200px; margin: auto; background: #fff; padding: 30px; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); }
        h1, h2 { color: #0056b3; text-align: center; border-bottom: 2px solid #e0e0e0; padding-bottom: 10px; margin-bottom: 20px; }
        .summary-table { width: 100%; border-collapse: collapse; margin: 40px 0; }
        .summary-table th, .summary-table td { border: 1px solid #ddd; padding: 12px; text-align: left; }
        .summary-table th { background-color: #0056b3; color: white; }
        .summary-table tr:nth-child(even) { background-color: #f2f2f2; }
        .change-positive { color: #28a745; font-weight: bold; }
        .change-negative { color: #dc3545; font-weight: bold; }
        .footer { text-align: center; margin-top: 40px; font-size: 0.8em; color: #777; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Performance Score Summary</h1>
        <p style="text-align:center;">Report Generated: {{ generation_date }} | Period: <strong>{{ period_display }}</strong> ({{ start_date }} to {{ end_date }})</p>
        
        <h2>Performance Trends</h2>
        <div>{{ desktop_plot | safe }}</div>
        <div>{{ mobile_plot | safe }}</div>

        <h2>Score Change Summary</h2>
        <table class="summary-table">
            <thead>
                <tr>
                    <th>URL</th>
                    <th>Strategy</th>
                    <th>Start Date</th>
                    <th>Start Score</th>
                    <th>End Date</th>
                    <th>End Score</th>
                    <th>Change</th>
                </tr>
            </thead>
            <tbody>
                {% for item in summary_data %}
                <tr>
                    <td><a href="{{ item.url }}" target="_blank">{{ item.url }}</a></td>
                    <td>{{ item.strategy }}</td>
                    <td>{{ item.start_date }}</td>
                    <td>{{ item.start_score }}</td>
                    <td>{{ item.end_date }}</td>
                    <td>{{ item.end_score }}</td>
                    <td class="{% if item.change.startswith('+') %}change-positive{% elif item.change != '0' %}change-negative{% endif %}">{{ item.change }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        <div class="footer">
            <p>Generated by generate_summary_report.py | Learn more: <a href="https://developers.google.com/speed/docs/insights/v5/about" target="_blank">PageSpeed Insights Documentation</a> | <a href="https://googlechrome.github.io/lighthouse/viewer/" target="_blank">Lighthouse Report Viewer</a> | <a href="https://github.com/liamdelahunty/pagespeed" target="_blank">GitHub Repository</a></p>
        </div>
    </div>
</body>
</html>
"""

if __name__ == "__main__":
    main()
