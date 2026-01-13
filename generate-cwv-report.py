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
import plotly.graph_objects as go

# --- Constants ---
config = configparser.ConfigParser()
config.read('config.ini')

REPORTS_DIR = pathlib.Path(config['Paths']['reports_dir'])
DEBUG_RESPONSES_DIR = pathlib.Path(config['Paths']['debug_dir'])
URL_LISTS_DIR = pathlib.Path(config['Paths']['url_lists_dir'])

# --- Constants for CWV Thresholds ---
LCP_THRESHOLDS = {"good": 2500, "ni": 4000}
FID_THRESHOLDS = {"good": 100, "ni": 300}
CLS_THRESHOLDS = {"good": 0.1, "ni": 0.25}

def get_metric_rating(value, thresholds):
    if value is None or pd.isna(value):
        return "N/A"
    if value <= thresholds["good"]:
        return "Good"
    if value <= thresholds["ni"]:
        return "Needs Improvement"
    return "Poor"

def get_rating_color(rating):
    if rating == "Good": return "#6ECC00"
    if rating == "Needs Improvement": return "#E5AC00"
    if rating == "Poor": return "#E54545"
    return "#ffffff"

def load_urls(path: str) -> List[str]:
    file_path = Path(path)
    if not file_path.is_absolute():
        file_path = URL_LISTS_DIR / path
    if not file_path.exists():
        print(f"[ERROR] URL file '{path}' not found.", file=sys.stderr)
        sys.exit(1)
    with open(file_path, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f.readlines() if line.strip()]
    if not urls:
        print(f"[ERROR] No URLs found in file: {file_path}", file=sys.stderr)
        sys.exit(1)
    return urls

def get_timestamp_from_stem(stem: str) -> str:
    if '-desktop-' in stem: return stem.split('-desktop-')[1]
    if '-mobile-' in stem: return stem.split('-mobile-')[1]
    return ""

def find_report_files(url: str, start_date: Optional[datetime.date] = None, end_date: Optional[datetime.date] = None, last_n_runs: Optional[int] = None) -> List[pathlib.Path]:
    parsed_url = urlparse(url)
    site_dir_name = parsed_url.netloc.replace("www.", "").replace(".", "-")
    page_slug = parsed_url.path.strip("/").replace("/", "_") or "_root_"
    site_debug_dir = DEBUG_RESPONSES_DIR / site_dir_name
    if not site_debug_dir.exists(): return []

    search_pattern = f"{page_slug}-*-*.json"
    all_json_files = list(site_debug_dir.glob(search_pattern))
    if page_slug == "_root_":
        all_json_files.extend(list(site_debug_dir.glob(f"{site_dir_name}-*-*.json")))
    
    all_json_files = sorted(list(set(all_json_files)), key=lambda p: p.name, reverse=True)

    if last_n_runs:
        unique_timestamps = sorted(list(set(get_timestamp_from_stem(f.stem) for f in all_json_files if get_timestamp_from_stem(f.stem))), reverse=True)
        files_to_return = [f for f in all_json_files if get_timestamp_from_stem(f.stem) in unique_timestamps[:last_n_runs]]
        return sorted(files_to_return, key=lambda p: p.name)

    files_to_return = []
    for f in all_json_files:
        timestamp_str = get_timestamp_from_stem(f.stem)
        try:
            file_datetime = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d-%H%M%S")
        except ValueError:
            try:
                file_datetime = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d-%H%M")
            except ValueError: continue
        
        file_date = file_datetime.date()
        if (not start_date or file_date >= start_date) and (not end_date or file_date <= end_date):
            files_to_return.append(f)
            
    return sorted(files_to_return, key=lambda p: p.name)

def process_json_file(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f: data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"Skipping malformed file: {file_path} ({e})")
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

def create_cwv_plot(df: pd.DataFrame, metric_col: str, title: str) -> str:
    if df.empty or metric_col not in df.columns: return "<p>No data for this plot.</p>"
    fig = go.Figure()
    for strategy in df["strategy"].unique():
        strategy_df = df[df["strategy"] == strategy]
        fig.add_trace(go.Scatter(x=strategy_df["timestamp"], y=strategy_df[metric_col], mode='lines+markers', name=f'{strategy} {metric_col.upper()}'))
    fig.update_layout(title_text=title, xaxis_title="Date", yaxis_title=metric_col.upper(), hovermode="x unified", template="plotly_white", height=400, margin=dict(l=50, r=50, b=50, t=50))
    return fig.to_html(full_html=False, include_plotlyjs='cdn')

def create_html_report(table_data, table_headers, aggregated_data, url, date_range_str, plots, period_str):
    chart_data = json.dumps({
        "labels": ["LCP", "FID", "CLS"],
        "datasets": [
            {"label": "Good", "data": [aggregated_data["lcp"]["Good"], aggregated_data["fid"]["Good"], aggregated_data["cls"]["Good"]], "backgroundColor": get_rating_color("Good")},
            {"label": "Needs Improvement", "data": [aggregated_data["lcp"]["Needs Improvement"], aggregated_data["fid"]["Needs Improvement"], aggregated_data["cls"]["Needs Improvement"]], "backgroundColor": get_rating_color("Needs Improvement")},
            {"label": "Poor", "data": [aggregated_data["lcp"]["Poor"], aggregated_data["fid"]["Poor"], aggregated_data["cls"]["Poor"]], "backgroundColor": get_rating_color("Poor")},
        ]
    })
    table_rows = ""
    for row in table_data:
        table_rows += "<tr>"
        for header in table_headers:
            value = row.get(header, "N/A")
            rating = "N/A"
            if "LCP" in header and pd.notna(value): rating = get_metric_rating(value, LCP_THRESHOLDS)
            elif "FID" in header and pd.notna(value): rating = get_metric_rating(value, FID_THRESHOLDS)
            elif "CLS" in header and pd.notna(value): rating = get_metric_rating(value, CLS_THRESHOLDS)
            
            display_value = value
            if isinstance(value, float):
                display_value = f"{value:.3f}" if "CLS" in header else f"{value:.0f} ms"
            elif isinstance(value, datetime.datetime):
                 display_value = value.strftime('%Y-%m-%d %H:%M:%S')

            table_rows += f'<td style="background-color: {get_rating_color(rating)}">{display_value}</td>'
        table_rows += "</tr>"
    header_html = "".join(f"<th>{h}</th>" for h in table_headers)

    plots_html = ""
    for plot_title, plot_html in plots.items():
        plots_html += f'<div class="plot-container mt-4"><h3>{plot_title}</h3>{plot_html}</div>'

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>CWV History: {url}</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body {{ background-color: #f8f9fa; }} .container {{ padding: 2rem; }}
            .chart-container {{ max-width: 800px; margin: 2rem auto; }}
            td, th {{ text-align: center; vertical-align: middle; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="text-center mb-4"><h1>CWV History Report</h1><p class="lead"><strong><a href="{url}" target="_blank">{url}</a></strong> | {period_str}: {date_range_str}</p></div>
            <div class="chart-container"><canvas id="cwvChart"></canvas></div>
            {plots_html}
            <div class="card mt-5"><div class="card-header"><h2 class="h5 mb-0">Detailed History</h2></div>
            <div class="table-responsive"><table class="table table-striped table-hover mb-0"><thead class="table-light"><tr>{header_html}</tr></thead><tbody>{table_rows}</tbody></table></div></div>
            <div class="footer text-center mt-4 text-muted"><p>Generated by generate-cwv-report.py | <a href="https://developers.google.com/speed/docs/insights/v5/about" target="_blank">Docs</a> | <a href="https://googlechrome.github.io/lighthouse/viewer/" target="_blank">Viewer</a> | <a href="https://github.com/liamdelahunty/pagespeed" target="_blank">Repo</a></p></div>
        </div>
        <script>
            new Chart(document.getElementById('cwvChart'), {{
                type: 'bar', data: {chart_data},
                options: {{ responsive: true, plugins: {{ title: {{ display: true, text: 'CWV Distribution' }} }}, scales: {{ x: {{ stacked: true }}, y: {{ stacked: true }} }} }}
            }});
        </script>
    </body>
    </html>
    """

def main():
    parser = argparse.ArgumentParser(description="Generate CWV reports from existing JSON data.", formatter_class=argparse.RawTextHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-f", "--url-file", help="File with URLs.")
    group.add_argument("-u", "--url", help="Single URL.")
    period_group = parser.add_mutually_exclusive_group()
    period_group.add_argument("--period", choices=['7d', '28d', 'this-month', 'last-month', 'all-time'], default='28d', help="Reporting period.")
    period_group.add_argument("--last-runs", type=int, metavar='N', help="Last N runs.")
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
        files = find_report_files(url, start_date, end_date, args.last_runs)
        if not files:
            print(f"  - No data for {url}. Skipping.")
            continue
        
        report_data = [d for d in [process_json_file(f) for f in files] if d]
        if not report_data:
            print(f"  - No valid data for {url}. Skipping.")
            continue
        
        df = pd.DataFrame(report_data).sort_values('timestamp').reset_index(drop=True)
        
        table_headers = ["Timestamp"]
        metrics_to_display = ['lcp', 'fid', 'cls']
        for metric in metrics_to_display:
            for strategy in ["Mobile", "Desktop"]:
                table_headers.append(f"{metric.upper()} {strategy}")
        
        table_data_rows, processed_indices = [], set()
        for i in range(len(df)):
            if i in processed_indices: continue
            processed_indices.add(i)
            row1 = df.iloc[i]
            row_data = {h: "N/A" for h in table_headers}
            row_data['Timestamp'] = row1['timestamp']
            
            for metric in metrics_to_display:
                col_name = f"{metric.upper()} {row1['strategy']}"
                if metric in row1 and pd.notna(row1[metric]): row_data[col_name] = row1[metric]
            
            for j in range(i + 1, len(df)):
                if j in processed_indices: continue
                row2 = df.iloc[j]
                if (row2['strategy'] != row1['strategy'] and (row2['timestamp'] - row1['timestamp']) <= pd.Timedelta(minutes=15)):
                    processed_indices.add(j)
                    for metric in metrics_to_display:
                        col_name = f"{metric.upper()} {row2['strategy']}"
                        if metric in row2 and pd.notna(row2[metric]): row_data[col_name] = row2[metric]
                    break
            table_data_rows.append(row_data)

        aggregated = {m: {"Good": 0, "Needs Improvement": 0, "Poor": 0} for m in ['lcp', 'fid', 'cls']}
        for metric in aggregated:
            df[f'{metric}_rating'] = df[metric].apply(lambda x: get_metric_rating(x, globals()[f'{metric.upper()}_THRESHOLDS']))
            counts = df[f'{metric}_rating'].value_counts()
            for rating, count in counts.items():
                if rating in aggregated[metric]:
                    aggregated[metric][rating] = count

        min_date, max_date = df['timestamp'].min(), df['timestamp'].max()
        date_suffix = f"{min_date.strftime('%Y%m%d')}-{max_date.strftime('%Y%m%d')}"
        date_display = f"{min_date.strftime('%Y-%m-%d')} to {max_date.strftime('%Y-%m-%d')}"
        if min_date.date() == max_date.date(): date_display = f"on {min_date.strftime('%Y-%m-%d')}"
        
        name_base = urlparse(url).netloc.replace("www.", "").replace(".", "-")
        
        period_display_str = ""
        if args.last_runs:
            period_display_str = f"Last {args.last_runs} runs"
        elif args.period:
            period_map = {
                '7d': 'Last 7 days',
                '28d': 'Last 28 days',
                'this-month': 'This month',
                'last-month': 'Last month',
                'all-time': 'All time'
            }
            period_display_str = period_map.get(args.period)

        plots = {
            "LCP Trend": create_cwv_plot(df, "lcp", "LCP Trend"),
            "FID Trend": create_cwv_plot(df, "fid", "FID Trend"),
            "CLS Trend": create_cwv_plot(df, "cls", "CLS Trend"),
        }
        
        report_content = create_html_report(table_data_rows, table_headers, aggregated, url, date_display, plots, period_display_str)
        report_filename = REPORTS_DIR / f"cwv-history-{name_base}-{date_suffix}.html"
        with open(report_filename, "w", encoding="utf-8") as f: f.write(report_content)
        print(f"  ✅ Report for {url}: {report_filename}")

if __name__ == "__main__":
    main()
