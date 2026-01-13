#!/usr/bin/env python3
"""
generate-cwv-report.py

Generates an HTML report summarizing Core Web Vitals (CWV) metrics
from a directory of PageSpeed Insights JSON files.
"""

import argparse
import json
import pathlib
from datetime import datetime

# --- Constants for CWV Thresholds ---
LCP_THRESHOLDS = {"good": 2500, "ni": 4000}  # Largest Contentful Paint (ms)
FID_THRESHOLDS = {"good": 100, "ni": 300}   # First Input Delay (ms) - using Max Potential FID
CLS_THRESHOLDS = {"good": 0.1, "ni": 0.25}  # Cumulative Layout Shift (unitless)

def get_metric_rating(value, thresholds):
    """Categorizes a metric value as 'Good', 'Needs Improvement', or 'Poor'."""
    if value is None:
        return "N/A"
    if value <= thresholds["good"]:
        return "Good"
    if value <= thresholds["ni"]:
        return "Needs Improvement"
    return "Poor"

def get_rating_color(rating):
    """Returns a color code based on the metric rating."""
    if rating == "Good":
        return "#6ECC00"  # Green
    if rating == "Needs Improvement":
        return "#E5AC00"  # Amber
    if rating == "Poor":
        return "#E54545"  # Red
    return "#808080" # Grey for N/A

def process_json_file(file_path):
    """Processes a single PageSpeed JSON file to extract CWV data."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"Skipping malformed or missing file: {file_path} ({e})")
        return None

    audits = data.get("lighthouseResult", {}).get("audits", {})

    lcp_val = audits.get("largest-contentful-paint", {}).get("numericValue")
    fid_val = audits.get("max-potential-fid", {}).get("numericValue") # Using MPFID as proxy
    cls_val = audits.get("cumulative-layout-shift", {}).get("numericValue")
    
    url = data.get("id", "N/A")
    strategy = data.get("lighthouseResult", {}).get("configSettings", {}).get("emulatedFormFactor", "N/A")

    return {
        "url": url,
        "strategy": strategy.capitalize(),
        "lcp": lcp_val,
        "lcp_rating": get_metric_rating(lcp_val, LCP_THRESHOLDS),
        "fid": fid_val,
        "fid_rating": get_metric_rating(fid_val, FID_THRESHOLDS),
        "cls": cls_val,
        "cls_rating": get_metric_rating(cls_val, CLS_THRESHOLDS),
    }

def create_html_report(report_data, aggregated_data, report_name):
    """Generates the HTML report string."""
    
    # Chart.js data
    chart_data = json.dumps({
        "labels": ["Largest Contentful Paint (LCP)", "First Input Delay (FID)", "Cumulative Layout Shift (CLS)"],
        "datasets": [
            {"label": "Good", "data": [aggregated_data["lcp"]["Good"], aggregated_data["fid"]["Good"], aggregated_data["cls"]["Good"]], "backgroundColor": get_rating_color("Good")},
            {"label": "Needs Improvement", "data": [aggregated_data["lcp"]["Needs Improvement"], aggregated_data["fid"]["Needs Improvement"], aggregated_data["cls"]["Needs Improvement"]], "backgroundColor": get_rating_color("Needs Improvement")},
            {"label": "Poor", "data": [aggregated_data["lcp"]["Poor"], aggregated_data["fid"]["Poor"], aggregated_data["cls"]["Poor"]], "backgroundColor": get_rating_color("Poor")},
        ]
    })

    # Table rows
    table_rows = ""
    for item in report_data:
        table_rows += f"""
        <tr>
            <td><a href="{item['url']}" target="_blank">{item['url']}</a></td>
            <td>{item['strategy']}</td>
            <td style="background-color: {get_rating_color(item['lcp_rating'])}">{f"{item['lcp']:.0f} ms" if item['lcp'] is not None else 'N/A'}</td>
            <td style="background-color: {get_rating_color(item['fid_rating'])}">{f"{item['fid']:.0f} ms" if item['fid'] is not None else 'N/A'}</td>
            <td style="background-color: {get_rating_color(item['cls_rating'])}">{f"{item['cls']:.3f}" if item['cls'] is not None else 'N/A'}</td>
        </tr>
        """

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Core Web Vitals Report: {report_name}</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body {{ background-color: #f8f9fa; }}
            .container {{ padding-top: 2rem; padding-bottom: 2rem; }}
            .chart-container {{ max-width: 800px; margin: 2rem auto; }}
            .table-responsive {{ max-height: 600px; }}
            td, th {{ text-align: center; vertical-align: middle; }}
            td a {{ display: block; max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="text-center mb-4">
                <h1 class="display-5">Core Web Vitals Report</h1>
                <p class="lead">Report for: <strong>{report_name}</strong> | Generated on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
            </div>
            
            <div class="chart-container">
                <canvas id="cwvChart"></canvas>
            </div>

            <div class="card mt-5">
                <div class="card-header">
                    <h2 class="h5 mb-0">Detailed Report</h2>
                </div>
                <div class="table-responsive">
                    <table class="table table-striped table-hover mb-0">
                        <thead class="table-light">
                            <tr>
                                <th>URL</th>
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
        description="Generate an HTML report for Core Web Vitals (CWV) from PageSpeed JSON data.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--input-dir",
        type=pathlib.Path,
        default="debug-responses",
        help="Directory containing the PageSpeed JSON reports. Defaults to 'debug-responses'."
    )
    parser.add_argument(
        "--output-dir",
        type=pathlib.Path,
        default="reports",
        help="Directory where the HTML report will be saved. Defaults to 'reports'."
    )
    parser.add_argument(
        "--report-name",
        type=str,
        default="all",
        help="A custom name for the report, used in the output filename. Defaults to 'all'."
    )
    args = parser.parse_args()

    print(f"Generating CWV report from JSON files in: {args.input_dir}")

    report_data = []
    json_files = sorted(list(args.input_dir.rglob("*.json")))
    if not json_files:
        print("No JSON files found in the input directory. Exiting.")
        return

    for file_path in json_files:
        data = process_json_file(file_path)
        if data:
            report_data.append(data)

    if not report_data:
        print("No valid PageSpeed data found. Exiting.")
        return

    # Aggregate data for the chart
    aggregated_data = {
        "lcp": {"Good": 0, "Needs Improvement": 0, "Poor": 0},
        "fid": {"Good": 0, "Needs Improvement": 0, "Poor": 0},
        "cls": {"Good": 0, "Needs Improvement": 0, "Poor": 0},
    }
    for item in report_data:
        if item["lcp_rating"] != "N/A": aggregated_data["lcp"][item["lcp_rating"]] += 1
        if item["fid_rating"] != "N/A": aggregated_data["fid"][item["fid_rating"]] += 1
        if item["cls_rating"] != "N/A": aggregated_data["cls"][item["cls_rating"]] += 1

    # Generate and save the report
    report_content = create_html_report(report_data, aggregated_data, args.report_name)
    
    args.output_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d")
    report_filename = args.output_dir / f"cwv-report-{args.report_name}-{timestamp}.html"
    
    with open(report_filename, "w", encoding="utf-8") as f:
        f.write(report_content)

    print(f"✅ Successfully generated CWV report: {report_filename}")

if __name__ == "__main__":
    main()
