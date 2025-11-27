#!/usr/bin/env python3
"""
compare_reports.py

Scans the 'debug-responses' directory to find all saved JSON responses from the
PageSpeed Insights API, then generates a single HTML report to show performance
trends over time for each site.
"""

import os
import json
import pathlib
import argparse
import datetime
from typing import List, Dict

# This function is copied from pagespeed_to_csv.py to make this script standalone.
def extract_metrics(data: dict) -> Dict[str, object]:
    """
    Pull the fields we care about from the raw API response.
    Returns a flat dictionary ready for processing.
    """
    # Helper to safely get nested values
    def _get(path: List[str], default=None):
        cur = data
        for p in path:
            cur = cur.get(p, {})
        return cur if cur != {} else default

    # Overall category scores (0-1 range, convert to 0-100)
    perf_score = int(_get(["lighthouseResult", "categories", "performance", "score"], 0) * 100)
    acc_score  = int(_get(["lighthouseResult", "categories", "accessibility", "score"], 0) * 100)
    bp_score   = int(_get(["lighthouseResult", "categories", "best-practices", "score"], 0) * 100)
    seo_score  = int(_get(["lighthouseResult", "categories", "seo", "score"], 0) * 100)
    
    # Core Web Vitals and other performance metrics
    fcp  = int(_get(["lighthouseResult", "audits", "first-contentful-paint", "numericValue"], 0))
    lcp  = int(_get(["lighthouseResult", "audits", "largest-contentful-paint", "numericValue"], 0))
    tti  = int(_get(["lighthouseResult", "audits", "interactive", "numericValue"], 0))
    tbt  = int(_get(["lighthouseResult", "audits", "total-blocking-time", "numericValue"], 0))
    cls  = float(_get(["lighthouseResult", "audits", "cumulative-layout-shift", "numericValue"], 0))
    
    return {
        "PerfScore": perf_score,
        "AccessibilityScore": acc_score,
        "BestPracticesScore": bp_score,
        "SEOScore": seo_score,
        "FCP_ms": fcp,
        "LCP_ms": lcp,
        "TTI_ms": tti,
        "TBT_ms": tbt,
        "CLS": round(cls, 4),
    }

def main():
    """Finds JSON data, processes it, and generates an HTML report."""
    
    parser = argparse.ArgumentParser(description="Generate a PageSpeed Insights comparison report from saved JSON data.")
    parser.add_argument(
        "-s", "--site",
        type=str,
        help="Generate a report for only a specific site (e.g., 'example-com')."
    )
    args = parser.parse_args()

    print("🔎 Starting report generation...")
    
    base_dir = pathlib.Path("debug-responses")
    if args.site:
        base_dir = base_dir / args.site

    if not base_dir.exists():
        print(f"❌ Error: Directory '{base_dir}' not found. Check the site name or run the main script first.")
        return

    all_reports = []
    json_files = list(base_dir.rglob('*.json'))

    if not json_files:
        print(f"🟡 Warning: No JSON files found in '{base_dir}'. Nothing to compare.")
        return

    print(f"📄 Found {len(json_files)} JSON files to process.")

    for path in json_files:
        try:
            # Extract metadata from path: .../<site-name>/<page-slug>-<strategy>-<timestamp>.json
            site_name = path.parts[-2]
            file_stem = path.stem
            
            # The timestamp can contain hyphens, so we can't just split by '-'.
            # We split from the right, knowing the strategy is the second to last part.
            parts = file_stem.rsplit('-', 2)
            page_slug = parts[0]
            strategy = parts[1]
            timestamp = parts[2]

            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            metrics = extract_metrics(data)
            
            report_data = {
                "site": site_name,
                "page": page_slug,
                "strategy": strategy,
                "timestamp": timestamp,
                **metrics
            }
            all_reports.append(report_data)

        except (IndexError, ValueError, json.JSONDecodeError) as e:
            print(f"🟡 Warning: Could not parse file '{path}'. Malformed name or content? Error: {e}")
            continue
    
    # --- Group reports ---
    grouped_reports = {}
    for report in all_reports:
        key = (report["site"], report["page"], report["strategy"])
        if key not in grouped_reports:
            grouped_reports[key] = []
        grouped_reports[key].append(report)

    # Sort the reports in each group by timestamp
    for key in grouped_reports:
        grouped_reports[key].sort(key=lambda r: r["timestamp"])
    
    # --- Generate and write HTML report ---
    print("🎨 Generating HTML report...")
    html_content = generate_html_report(grouped_reports)
    
    # --- Prepare output directory and filename ---
    reports_dir = pathlib.Path("reports")
    reports_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H%M")
    
    if args.site:
        report_filename = reports_dir / f"comparison-report-{args.site}-{timestamp}.html"
    else:
        report_filename = reports_dir / f"comparison-report-{timestamp}.html"
    
    with open(report_filename, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"\n✅ Finished. Report saved to '{report_filename}'.")


def get_change_color(change: float, metric: str) -> str:
    """Determines the color for a metric change. Green for good, red for bad."""
    if change == 0:
        return "gray"
    
    # For time-based metrics (ms), lower is better.
    if "ms" in metric:
        return "green" if change < 0 else "red"
    # For scores, higher is better. CLS is a score where lower is better.
    elif "CLS" in metric:
        return "green" if change < 0 else "red"
    else: # All other scores
        return "green" if change > 0 else "red"

def format_change(change: float, metric: str) -> str:
    """Formats the change value with a sign and appropriate units."""
    sign = "+" if change > 0 else ""
    if "ms" in metric:
        return f"{sign}{int(change)}"
    if "Score" in metric:
        return f"{sign}{int(change)}"
    # CLS
    return f"{sign}{change:.4f}"


def generate_html_report(grouped_data: dict) -> str:
    """Takes grouped data and returns a full HTML report as a string."""
    
    # --- HTML and CSS Boilerplate ---
    html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PageSpeed Insights Comparison Report</title>
    <style>
        body { font-family: sans-serif; margin: 2rem; background-color: #f9f9f9; color: #333; }
        h1, h2 { color: #111; border-bottom: 2px solid #eee; padding-bottom: 0.5rem; }
        h1 { font-size: 2rem; }
        h2 { font-size: 1.5rem; margin-top: 3rem; }
        table { border-collapse: collapse; width: 100%; margin-top: 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.06); background: white; }
        th, td { border: 1px solid #ddd; padding: 0.75rem; text-align: left; }
        th { background-color: #f2f2f2; font-weight: bold; }
        tr:nth-child(even) { background-color: #f9f9f9; }
        .site-name { font-weight: bold; text-transform: capitalize; }
        .page-name { font-family: monospace; background-color: #eee; padding: 2px 5px; border-radius: 3px; }
        .strategy { font-style: italic; }
        .change { font-weight: bold; }
        .green { color: #28a745; }
        .red { color: #dc3545; }
        .gray { color: #6c757d; }
    </style>
</head>
<body>
    <h1>PageSpeed Insights Comparison Report</h1>
    """

    # --- Summary Table ---
    html += "<h2>Summary of Changes (First vs. Last)</h2>"
    html += """
    <table>
        <thead>
            <tr>
                <th>Site</th>
                <th>Page</th>
                <th>Strategy</th>
                <th>Metric</th>
                <th>Oldest Value</th>
                <th>Newest Value</th>
                <th>Change</th>
            </tr>
        </thead>
        <tbody>
    """
    sorted_keys = sorted(grouped_data.keys())

    for site, page, strategy in sorted_keys:
        reports = grouped_data[(site, page, strategy)]
        if len(reports) < 2:
            continue
        
        first = reports[0]
        last = reports[-1]
        
        metrics_to_compare = ["PerfScore", "LCP_ms", "TBT_ms", "CLS"]
        
        for i, metric in enumerate(metrics_to_compare):
            old_val = first[metric]
            new_val = last[metric]
            change = new_val - old_val
            color = get_change_color(change, metric)

            html += f"<tr>"
            if i == 0:
                html += f'<td rowspan="{len(metrics_to_compare)}" class="site-name">{site}</td>'
                html += f'<td rowspan="{len(metrics_to_compare)}" class="page-name">{page}</td>'
                html += f'<td rowspan="{len(metrics_to_compare)}" class="strategy">{strategy}</td>'
            
            html += f"<td>{metric}</td>"
            html += f"<td>{old_val}</td>"
            html += f"<td>{new_val}</td>"
            html += f'<td class="change {color}">{format_change(change, metric)}</td>'
            html += "</tr>"
    
    html += "</tbody></table>"


    # --- Detailed Trend Tables ---
    for site, page, strategy in sorted_keys:
        reports = grouped_data[(site, page, strategy)]
        html += f'<h2>Trend for <span class="site-name">{site}</span> (<span class="page-name">{page}</span> page, <span class="strategy">{strategy}</span>)</h2>'
        html += """
        <table>
            <thead>
                <tr>
                    <th>Timestamp</th>
                    <th>Perf</th>
                    <th>Access</th>
                    <th>BP</th>
                    <th>SEO</th>
                    <th>LCP (ms)</th>
                    <th>TBT (ms)</th>
                    <th>CLS</th>
                </tr>
            </thead>
            <tbody>
        """
        for report in reversed(reports): # Show newest first
            html += f"""
            <tr>
                <td>{report['timestamp']}</td>
                <td>{report['PerfScore']}</td>
                <td>{report['AccessibilityScore']}</td>
                <td>{report['BestPracticesScore']}</td>
                <td>{report['SEOScore']}</td>
                <td>{report['LCP_ms']}</td>
                <td>{report['TBT_ms']}</td>
                <td>{report['CLS']:.4f}</td>
            </tr>
            """
        html += "</tbody></table>"

    html += "</body></html>"
    return html




if __name__ == "__main__":
    main()
