import os
import sys
import json
import datetime
import pathlib
import argparse
import pandas as pd
import plotly.graph_objects as go
from jinja2 import Environment, FileSystemLoader
from typing import List, Dict
from urllib.parse import urlparse
from pathlib import Path

# --- Constants ---
REPORTS_DIR = pathlib.Path("reports")
DEBUG_RESPONSES_DIR = pathlib.Path("debug-responses")

# Ensure output directories exist
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
DEBUG_RESPONSES_DIR.mkdir(parents=True, exist_ok=True)

# Strategies we expect to find data for
STRATEGIES = ("desktop", "mobile")

# --- Helper Functions ---
def load_urls(path: str) -> List[str]:
    """Read URLs from a file, one per line, stripping whitespace."""
    file_path = Path(path)
    if not file_path.exists():
        # If the file is not found, check inside the 'url-lists' directory
        file_path = Path("url-lists") / path
        if not file_path.exists():
            print(f"[ERROR] URL file '{path}' not found in the root or in the 'url-lists' directory.", file=sys.stderr)
            sys.exit(1)

    with open(file_path, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f.readlines() if line.strip()]
    if not urls:
        print(f"[ERROR] No URLs found in the file: {file_path}", file=sys.stderr)
        sys.exit(1)
    return urls

def extract_metrics_from_json(data: dict) -> Dict[str, object]:
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
    perf_score = int(_get(["lighthouseResult", "categories", "performance", "score"], 0) * 100)
    acc_score  = int(_get(["lighthouseResult", "categories", "accessibility", "score"], 0) * 100)
    bp_score   = int(_get(["lighthouseResult", "categories", "best-practices", "score"], 0) * 100)
    seo_score  = int(_get(["lighthouseResult", "categories", "seo", "score"], 0) * 100)
    
    # Performance metrics (numericValue is in ms for timing metrics,
    # unitless for CLS)
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


def get_timestamp_from_stem(stem: str) -> str:
    """Robustly extracts the timestamp from a filename stem."""
    if '-desktop-' in stem:
        return stem.split('-desktop-')[1]
    if '-mobile-' in stem:
        return stem.split('-mobile-')[1]
    return ""

def get_historical_data(url: str, start_date: datetime.date = None, end_date: datetime.date = None, last_n_runs: int = None) -> pd.DataFrame:
    """
    Retrieves historical PageSpeed Insights data for a given URL and strategy,
    filtered by date range or last N runs.
    """
    parsed_url = urlparse(url)
    site_dir_name = parsed_url.netloc.replace("www.", "").replace(".", "-")
    page_slug = parsed_url.path.strip("/").replace("/", "_") or "_root_"

    data_records = []
    
    # Path to the specific site's debug responses
    site_debug_dir = DEBUG_RESPONSES_DIR / site_dir_name

    if not site_debug_dir.exists():
        print(f"[WARN] No debug data found for {url} in {site_debug_dir}", file=sys.stderr)
        return pd.DataFrame()

    all_json_files = list(site_debug_dir.glob(f"{page_slug}-*-*.json"))

    if page_slug == "_root_":
        # Also look for files named with the domain slug as a fallback
        domain_slug_files = list(site_debug_dir.glob(f"{site_dir_name}-*-*.json"))
        all_json_files.extend(domain_slug_files)
    
    # Remove duplicates and sort newest first
    all_json_files = sorted(list(set(all_json_files)), key=lambda p: p.name, reverse=True)

    if last_n_runs is not None:
        # Filter to get the last N unique runs based on timestamp
        unique_timestamps = sorted(list(set([get_timestamp_from_stem(f.stem) for f in all_json_files if get_timestamp_from_stem(f.stem)])), reverse=True)
        timestamps_for_n_runs = unique_timestamps[:last_n_runs]
        
        filtered_json_files = []
        for ts in timestamps_for_n_runs:
            for f in all_json_files:
                if get_timestamp_from_stem(f.stem) == ts and f not in filtered_json_files:
                    filtered_json_files.append(f)
        all_json_files = sorted(filtered_json_files, key=lambda p: p.name) # sort by date for plotting

    for json_file in all_json_files:
        try:
            # Robustly parse filename
            stem = json_file.stem
            file_strategy = None
            if '-desktop-' in stem:
                file_strategy = 'desktop'
                parts = stem.split('-desktop-')
            elif '-mobile-' in stem:
                file_strategy = 'mobile'
                parts = stem.split('-mobile-')
            else:
                continue

            file_page_slug = parts[0]
            file_timestamp_str = parts[1]

            # Basic validation of filename parts
            is_valid_slug = (file_page_slug == page_slug)
            if page_slug == "_root_":
                is_valid_slug = is_valid_slug or (file_page_slug == site_dir_name)

            if not (is_valid_slug and file_strategy in STRATEGIES):
                continue
            
            try:
                # First, try to parse with seconds
                file_datetime = datetime.datetime.strptime(file_timestamp_str, "%Y-%m-%d-%H%M%S")
            except ValueError:
                # If that fails, try to parse without seconds
                file_datetime = datetime.datetime.strptime(file_timestamp_str, "%Y-%m-%d-%H%M")
            
            file_date = file_datetime.date()

            # If using --period, filter by date. This check is skipped for --last-runs.
            if last_n_runs is None:
                if start_date and file_date < start_date:
                    continue
                if end_date and file_date > end_date:
                    continue
            
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                metrics = extract_metrics_from_json(data)
                record = {
                    "Date": file_datetime,
                    "URL": url,
                    "Strategy": file_strategy,
                    **metrics
                }
                data_records.append(record)

        except Exception as e:
            print(f"[WARN] Could not process file {json_file}: {e}", file=sys.stderr)
            continue
    
    if not data_records:
        return pd.DataFrame()

    df = pd.DataFrame(data_records)
    df = df.sort_values(by="Date").reset_index(drop=True)
    return df

def create_metric_plot(df: pd.DataFrame, metric_col: str, title: str) -> str:
    """Generates a Plotly line chart for a given metric and returns it as an HTML string."""
    if df.empty:
        return "<p>No data available for this plot.</p>"

    fig = go.Figure()
    
    # Iterate over unique strategies (desktop/mobile)
    for strategy in df["Strategy"].unique():
        strategy_df = df[df["Strategy"] == strategy]
        fig.add_trace(go.Scatter(
            x=strategy_df["Date"],
            y=strategy_df[metric_col],
            mode='lines+markers',
            name=f'{strategy.capitalize()} {metric_col}'
        ))

    fig.update_layout(
        title_text=title,
        xaxis_title="Date",
        yaxis_title=metric_col,
        hovermode="x unified",
        template="plotly_white",
        height=400,
        margin=dict(l=50, r=50, b=50, t=50) # Reduce margins
    )
    
    return fig.to_html(full_html=False, include_plotlyjs='cdn')


# --- Main Logic ---
def main():
    parser = argparse.ArgumentParser(
        description="Generate HTML reports of PageSpeed Insights historical data.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "-f", "--url-file",
        type=str,
        help="Path to a file containing a list of URLs (one per line). Generates individual reports for each URL."
    )
    parser.add_argument(
        "-u", "--url",
        type=str,
        help="A single URL to test. Ignored if -f is provided."
    )
    period_group = parser.add_mutually_exclusive_group(required=True)
    period_group.add_argument(
        "--period",
        type=str,
        choices=['7d', '28d', 'this-month', 'last-month', 'all-time'],
        help="Define the reporting period (e.g., '7d' for last 7 days)."
    )
    period_group.add_argument(
        "--last-runs",
        type=int,
        metavar='N',
        help="Report on the last N unique runs for each URL."
    )
    args = parser.parse_args()

    urls_to_process: List[str] = []
    
    if args.url_file:
        urls_to_process = load_urls(args.url_file)
        print(f"🔎 Processing {len(urls_to_process)} URLs from file: {args.url_file}")
    elif args.url:
        url_to_test = args.url
        if not url_to_test.startswith(('http://', 'https://')):
            url_to_test = 'https://' + url_to_test
        urls_to_process.append(url_to_test)
        print(f"🔎 Processing single URL: {url_to_test}")
    else:
        print("[ERROR] No URLs provided. Use -u or -f.", file=sys.stderr)
        sys.exit(1)

    # Determine date range for filtering
    start_date, end_date = None, datetime.date.today()
    if args.period:
        if args.period == '7d':
            start_date = end_date - datetime.timedelta(days=7)
        elif args.period == '28d':
            start_date = end_date - datetime.timedelta(days=28)
        elif args.period == 'this-month':
            start_date = end_date.replace(day=1)
        elif args.period == 'last-month':
            first_day_this_month = end_date.replace(day=1)
            last_day_last_month = first_day_this_month - datetime.timedelta(days=1)
            start_date = last_day_last_month.replace(day=1)
            end_date = last_day_last_month
        elif args.period == 'all-time':
            start_date = datetime.date(2000, 1, 1)
    
    print(f"🗓️ Reporting for period: {args.period or f'last {args.last_runs} runs'}")
    if start_date and end_date and args.period != 'all-time':
        print(f"    (From {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')})")

    # Set up Jinja2 environment once
    template_loader = FileSystemLoader(searchpath="./")
    env = Environment(loader=template_loader)
    template = env.from_string("""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PageSpeed History Report - {{ report_title }}</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 20px; background-color: #f4f7f6; color: #333; }
        .container { max-width: 1200px; margin: auto; background: #fff; padding: 30px; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); }
        h1, h2, h3 { color: #0056b3; }
        h1 { font-size: 2.2em; text-align: center; border-bottom: 2px solid #e0e0e0; padding-bottom: 10px; margin-bottom: 20px; }
        h2 { font-size: 1.8em; border-bottom: 1px solid #e0e0e0; padding-bottom: 8px; margin-top: 40px;}
        h3 { font-size: 1.4em; }
        .url-section { margin-bottom: 40px; padding: 20px; background-color: #f9f9f9; border-left: 5px solid #007bff; border-radius: 4px; }
        .plot-container, .table-container { margin-bottom: 30px; }
        p { line-height: 1.6; }
        .footer { text-align: center; margin-top: 50px; font-size: 0.8em; color: #777; }
        .date-range { text-align: center; margin-bottom: 30px; font-style: italic; color: #555; }
        .data-table { width: 100%; border-collapse: collapse; margin-top: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
        .data-table th, .data-table td { border: 1px solid #ddd; padding: 12px; text-align: center; }
        .data-table th { background-color: #0056b3; color: white; font-weight: bold; }
        .data-table tr:nth-child(even) { background-color: #f2f2f2; }
        .data-table tr:hover { background-color: #e2e2e2; }
    </style>
</head>
<body>
    <div class="container">
        <h1>PageSpeed History Report</h1>
        <p class="date-range">Report Generated: {{ generation_date }} | Period: {{ period_display }} {% if start_date and end_date %}({{ start_date }} to {{ end_date }}){% endif %}</p>
        {% for entry in report_data %}
            <div class="url-section">
                <h2>History for: <a href="{{ entry.url }}" target="_blank">{{ entry.url }}</a></h2>
                <div class="table-container">
                    <h3>Data Summary</h3>
                    {{ entry.table | safe }}
                </div>
                {% for plot_title, plot_html in entry.plots.items() %}
                    <div class="plot-container">
                        <h3>{{ plot_title.replace('_', ' ').replace('ms', '(ms)') }}</h3>
                        {{ plot_html | safe }}
                    </div>
                {% endfor %}
            </div>
        {% endfor %}
        <div class="footer">
            <p>Generated by generate_html_report.py | Learn more: <a href="https://developers.google.com/speed/docs/insights/v5/about" target="_blank">PageSpeed Insights Documentation</a> | <a href="https://googlechrome.github.io/lighthouse/viewer/" target="_blank">Lighthouse Report Viewer</a> | <a href="https://github.com/liamdelahunty/pagespeed" target="_blank">GitHub Repository</a></p>
        </div>
    </div>
</body>
</html>
""")

    # Process each URL and generate a separate report
    for url in urls_to_process:
        df = get_historical_data(url, start_date=start_date, end_date=end_date, last_n_runs=args.last_runs)
        
        if df.empty:
            print(f"\n[WARN] No data found for {url} within the specified period. Skipping report generation.")
            continue

        # --- Prepare data for a single URL report ---
        report_data = []
        
        # Prepare data table
        table_df = df.copy()
        table_df['Date'] = pd.to_datetime(table_df['Date']).dt.strftime('%Y-%m-%d %H:%M')
        pivot_df = table_df.pivot(index='Date', columns='Strategy', values=['PerformanceScore', 'LCP_ms', 'CLS', 'FCP_ms', 'TBT_ms'])
        
        new_columns = []
        for col_name in pivot_df.columns:
            metric_raw, strategy = col_name[0], col_name[1]
            metric_formatted = metric_raw.replace("Score", " Score").replace("_ms", " (ms)").replace("_", " ")
            new_columns.append(f"{metric_formatted.strip()} {strategy.capitalize()}")
        pivot_df.columns = new_columns
        pivot_df = pivot_df.reset_index()
        data_table_html = pivot_df.to_html(classes='data-table', border=0, index=False, justify='center')

        # Generate plots
        plots = {
            "PerformanceScore": create_metric_plot(df, "PerformanceScore", f"Performance Score over Time"),
            "LCP_ms": create_metric_plot(df, "LCP_ms", f"Largest Contentful Paint (ms) over Time"),
            "CLS": create_metric_plot(df, "CLS", f"Cumulative Layout Shift over Time"),
            # Add other plots as needed
        }
        report_data.append({"url": url, "plots": plots, "table": data_table_html})

        # --- Render and Save Report ---
        report_name_base = urlparse(url).netloc.replace("www.", "").replace(".", "-")
        
        # Determine the date range for display in the report
        report_start_date = df['Date'].min()
        report_end_date = df['Date'].max()

        html_output = template.render(
            report_title=url,
            generation_date=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            period_display=args.period or f"Last {args.last_runs} runs",
            start_date=report_start_date.strftime('%Y-%m-%d'),
            end_date=report_end_date.strftime('%Y-%m-%d'),
            report_data=report_data
        )

        # --- Filename Generation ---
        filename_suffix = f"{report_start_date.strftime('%Y%m%d')}-{report_end_date.strftime('%Y%m%d')}"
        output_filename = REPORTS_DIR / f"history-report-{report_name_base}-{filename_suffix}.html"
        
        with open(output_filename, "w", encoding="utf-8") as f:
            f.write(html_output)
        
        print(f"\n✅ HTML report generated for {url}: {output_filename}")

if __name__ == "__main__":
    main()
