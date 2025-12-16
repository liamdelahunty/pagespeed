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

    all_json_files = sorted(site_debug_dir.glob(f"{page_slug}-*-*.json"), reverse=True) # newest first

    if last_n_runs is not None:
        # Filter to get the last N unique runs based on timestamp
        unique_timestamps = sorted(list(set([f.stem.split('-')[-1] for f in all_json_files])), reverse=True)
        timestamps_for_n_runs = unique_timestamps[:last_n_runs]
        
        filtered_json_files = []
        for ts in timestamps_for_n_runs:
            for f in all_json_files:
                if f.stem.endswith(ts) and f not in filtered_json_files:
                    filtered_json_files.append(f)
        all_json_files = sorted(filtered_json_files) # sort by date for plotting

    for json_file in all_json_files:
        try:
            parts = json_file.stem.split('-')
            file_page_slug = '-'.join(parts[:-2])
            file_strategy = parts[-2]
            file_timestamp_str = parts[-1]
            
            # Basic validation of filename parts
            if not (file_page_slug == page_slug and file_strategy in STRATEGIES):
                continue
            
            file_datetime = datetime.datetime.strptime(file_timestamp_str, "%Y%m%d%H%M")
            file_date = file_datetime.date()

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
        help="Path to a file containing a list of URLs (one per line). Overrides -u."
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
    report_name_base = ""

    if args.url_file:
        urls_to_process = load_urls(args.url_file)
        report_name_base = Path(args.url_file).stem
        print(f"🔎 Using URL file: {args.url_file}")
    elif args.url:
        url_to_test = args.url
        if not url_to_test.startswith(('http://', 'https://')):
            url_to_test = 'https://' + url_to_test
        urls_to_process.append(url_to_test)
        parsed_url = urlparse(url_to_test)
        report_name_base = parsed_url.netloc.replace("www.", "").replace(".", "-")
        print(f"🔎 Testing single URL: {url_to_test}")
    else:
        print("[ERROR] No URLs provided. Use -u or -f.", file=sys.stderr)
        sys.exit(1)

    if not urls_to_process:
        print("[ERROR] No URLs found for testing. Exiting.", file=sys.stderr)
        sys.exit(1)

    # Determine date range
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
            end_date = last_day_last_month # Set end_date to the last day of last month
        elif args.period == 'all-time':
            start_date = datetime.date(2000, 1, 1) # Effectively all time
    
    print(f"🗓️ Generating report for period: {args.period or f'last {args.last_runs} runs'}")
    if start_date and end_date:
        print(f"    From {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

    all_data_frames = []
    for url in urls_to_process:
        df = get_historical_data(url, start_date=start_date, end_date=end_date, last_n_runs=args.last_runs)
        if not df.empty:
            all_data_frames.append(df)
        else:
            print(f"[WARN] No data found for {url} within the specified period.", file=sys.stderr)

    if not all_data_frames:
        print("[ERROR] No historical data available for any of the provided URLs within the specified period. Exiting.", file=sys.stderr)
        sys.exit(1)

    # Prepare data for rendering
    report_data = []
    for df in all_data_frames:
        url = df["URL"].iloc[0]
        # Generate plots for key metrics
        plots = {
            "PerformanceScore": create_metric_plot(df, "PerformanceScore", f"Performance Score over Time for {url}"),
            "LCP_ms": create_metric_plot(df, "LCP_ms", f"Largest Contentful Paint (ms) over Time for {url}"),
            "CLS": create_metric_plot(df, "CLS", f"Cumulative Layout Shift over Time for {url}"),
            "FCP_ms": create_metric_plot(df, "FCP_ms", f"First Contentful Paint (ms) over Time for {url}"),
            "TBT_ms": create_metric_plot(df, "TBT_ms", f"Total Blocking Time (ms) over Time for {url}"),
            "TTI_ms": create_metric_plot(df, "TTI_ms", f"Time To Interactive (ms) over Time for {url}"),
            "SpeedIndex_ms": create_metric_plot(df, "SpeedIndex_ms", f"Speed Index (ms) over Time for {url}"),
            "SRT_ms": create_metric_plot(df, "SRT_ms", f"Server Response Time (ms) over Time for {url}"),
            "AccessibilityScore": create_metric_plot(df, "AccessibilityScore", f"Accessibility Score over Time for {url}"),
            "BestPracticesScore": create_metric_plot(df, "BestPracticesScore", f"Best Practices Score over Time for {url}"),
            "SEOScore": create_metric_plot(df, "SEOScore", f"SEO Score over Time for {url}"),
        }
        report_data.append({"url": url, "plots": plots})

    # Set up Jinja2 environment
    template_loader = FileSystemLoader(searchpath="./") # Look for templates in current dir
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
        h1, h2 { color: #0056b3; border-bottom: 2px solid #e0e0e0; padding-bottom: 10px; margin-top: 30px; }
        h1 { font-size: 2.2em; text-align: center; }
        h2 { font-size: 1.8em; }
        .url-section { margin-bottom: 40px; padding: 20px; background-color: #f9f9f9; border-left: 5px solid #007bff; border-radius: 4px; }
        .plot-container { margin-bottom: 20px; }
        p { line-height: 1.6; }
        .footer { text-align: center; margin-top: 50px; font-size: 0.8em; color: #777; }
        .date-range { text-align: center; margin-bottom: 30px; font-style: italic; color: #555; }
    </style>
</head>
<body>
    <div class="container">
        <h1>PageSpeed History Report</h1>
        <p class="date-range">Report Generated: {{ generation_date }}</p>
        <p class="date-range">Period: {{ period_display }} {% if start_date and end_date %}({{ start_date }} to {{ end_date }}){% endif %}</p>

        {% for entry in report_data %}
            <div class="url-section">
                <h2>History for: <a href="{{ entry.url }}" target="_blank">{{ entry.url }}</a></h2>
                {% for plot_title, plot_html in entry.plots.items() %}
                    <div class="plot-container">
                        <h3>{{ plot_title.replace('_', ' ').replace('ms', '(ms)') }}</h3>
                        {{ plot_html | safe }}
                    </div>
                {% endfor %}
            </div>
        {% endfor %}

        <div class="footer">
            <p>Generated by generate_html_report.py</p>
        </div>
    </div>
</body>
</html>
""")

    # Render the template
    html_output = template.render(
        report_title=report_name_base,
        generation_date=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        period_display=args.period or f"Last {args.last_runs} runs",
        start_date=start_date.strftime('%Y-%m-%d') if start_date else 'N/A',
        end_date=end_date.strftime('%Y-%m-%d') if end_date else 'N/A',
        report_data=report_data
    )

    # Save the report
    timestamp_suffix = datetime.datetime.now().strftime("%Y-%m-%d-%H%M")
    output_filename = REPORTS_DIR / f"history-report-{report_name_base}-{timestamp_suffix}.html"
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(html_output)
    
    print(f"\n✅ HTML report generated: {output_filename}")


if __name__ == "__main__":
    main()
