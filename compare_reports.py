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
from typing import List, Dict
from urllib.parse import urlparse
from datetime import datetime, timedelta

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

def group_timestamps(timestamp_strs, tolerance_seconds=120):
    """
    Groups timestamp strings that are within a certain tolerance of each other.
    
    Returns: A list of tuples, where each tuple contains:
             (representative_datetime, list_of_original_timestamp_strings_in_group)
    """
    if not timestamp_strs:
        return []

    parsed_dts = []
    for ts in timestamp_strs:
        try:
            # Timestamps are expected in YYYY-MM-DD-HHMMSS format from the organiser script
            dt = datetime.strptime(ts, "%Y-%m-%d-%H%M%S")
            parsed_dts.append(dt)
        except ValueError:
            print(f"🟡 Warning: Could not parse timestamp from '{ts}'. Skipping this report in grouping.")
            continue
            
    dts = sorted(parsed_dts)

    if not dts:
        return []

    groups = []
    current_group = [dts[0]]

    # Iterate through the sorted datetimes to form groups
    for i in range(1, len(dts)):
        if (dts[i] - current_group[0]) <= timedelta(seconds=tolerance_seconds):
            current_group.append(dts[i])
        else:
            groups.append(current_group)
            current_group = [dts[i]]
    groups.append(current_group) # Add the last group

    # Format the output with the representative (earliest) timestamp and original strings
    result = []
    for group in groups:
        representative_ts = group[0]
        original_strings = [dt.strftime("%Y-%m-%d-%H%M%S") for dt in group]
        result.append((representative_ts, original_strings))
        
    return result

def get_page_slug_from_path(json_path: pathlib.Path) -> str:
    """Extracts the page slug from a JSON file path for consistent filtering."""
    file_stem = json_path.stem
    if "-desktop-" in file_stem:
        return file_stem.split("-desktop-", 1)[0]
    elif "-mobile-" in file_stem:
        return file_stem.split("-mobile-", 1)[0]
    else:
        # Fallback for older or unexpected formats
        try:
            return file_stem.rsplit('-', 2)[0]
        except IndexError:
            return file_stem

def main():
    """Finds JSON data, processes it, and generates an HTML report."""
    
    parser = argparse.ArgumentParser(description="Generate a PageSpeed Insights comparison report from saved JSON data.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "-u", "--url",
        type=str,
        help="Generate a report for a specific page URL. This will infer the host and page."
    )
    group.add_argument(
        "-H", "--host",
        type=str,
        help="Generate a report for all pages on a specific host. Accepts a domain or the site's directory name."
    )
    group.add_argument(
        "-f", "--from-file",
        dest="url_file",
        type=str,
        help="Generate a report for all URLs listed in a given file."
    )
    parser.add_argument(
        "--strategy",
        type=str,
        choices=['desktop', 'mobile'],
        help="Filter results for a specific strategy."
    )
    parser.add_argument(
        "-d", "--deep-dive",
        action="store_true",
        help="Include all performance metrics (LCP, TBT, CLS, etc.) in the report. By default, only the Performance Score is shown."
    )
    args = parser.parse_args()

    print("🔎 Starting report generation...")
    
    base_dir = pathlib.Path("debug-responses")
    report_output_name_parts = []
    all_reports = []
    json_files = []
    
    # --- Collect JSON files based on input ---
    if args.url_file:
        url_list_path = pathlib.Path(args.url_file)
        # If the filename is provided without a directory path, assume it's in the 'url-lists' directory.
        if url_list_path.parent == pathlib.Path('.'):
            url_list_path = pathlib.Path("url-lists") / url_list_path

        if not url_list_path.is_file():
            print(f"❌ Error: URL file not found at '{url_list_path}'")
            return

        report_output_name_parts.append(f"from-{url_list_path.stem}")
        print(f"📄 Reading URLs from '{url_list_path}'...")
        
        with open(url_list_path, "r", encoding="utf-8") as f:
            urls = [line.strip() for line in f if line.strip()]

        for url in urls:
            url_input = url if "://" in url else f"https://{url}"
            parsed_url = urlparse(url_input)
            
            host_part = parsed_url.netloc
            normalized_host_dir = host_part.replace("www.", "").replace(".", "-")
            
            potential_site_dir = base_dir / normalized_host_dir
            if not potential_site_dir.is_dir():
                print(f"🟡 Warning: Could not find site directory for host '{host_part}' (tried '{normalized_host_dir}'). Skipping URL: {url}")
                continue

            path_part = parsed_url.path
            if not path_part or path_part == "/":
                requested_page_slug = normalized_host_dir
            else:
                requested_page_slug = path_part.strip("/").replace("/", "_")

            all_json_in_site_dir = list(potential_site_dir.rglob('*.json'))
            files_for_this_url = [p for p in all_json_in_site_dir if get_page_slug_from_path(p) == requested_page_slug]
            
            if not files_for_this_url:
                print(f"🟡 Warning: No JSON files found for page '{requested_page_slug}' in '{potential_site_dir}'. URL: {url}")
            
            json_files.extend(files_for_this_url)
        
        if args.strategy:
            json_files = [p for p in json_files if f"-{args.strategy}-" in p.name]
            report_output_name_parts.append(args.strategy)

    else:
        # --- Legacy logic for --url, --host, or all sites ---
        search_dir = base_dir
        requested_page_slug = None

        if args.url:
            url_input = args.url if "://" in args.url else f"https://{args.url}"
            parsed_url = urlparse(url_input)
            
            host_part = parsed_url.netloc
            normalized_host_dir = host_part.replace("www.", "").replace(".", "-")
            
            potential_site_dir = base_dir / normalized_host_dir
            if potential_site_dir.is_dir():
                search_dir = potential_site_dir
                report_output_name_parts.append(normalized_host_dir)
                print(f"✅ Normalized URL's host to site directory: '{normalized_host_dir}'")

                path_part = parsed_url.path
                if not path_part or path_part == "/":
                    requested_page_slug = normalized_host_dir
                else:
                    requested_page_slug = path_part.strip("/").replace("/", "_")
                
                report_output_name_parts.append(requested_page_slug)
                print(f"✅ Targeting specific page with slug: '{requested_page_slug}'")
            else:
                print(f"❌ Error: Could not find a site directory for host '{host_part}' (tried '{normalized_host_dir}').")
                return

        elif args.host:
            host_input = args.host
            normalized_host_dir = host_input.replace("www.", "").replace(".", "-")
            
            potential_site_dir = base_dir / normalized_host_dir
            if potential_site_dir.is_dir():
                search_dir = potential_site_dir
                report_output_name_parts.append(normalized_host_dir)
                print(f"✅ Found site directory for host: '{normalized_host_dir}'")
            else:
                print(f"❌ Error: Could not find a site directory matching host '{host_input}' (tried '{normalized_host_dir}').")
                return
        else:
            report_output_name_parts.append("all-sites")

        if not search_dir.exists():
            print(f"❌ Error: Directory '{search_dir}' not found. Ensure site data exists.")
            return

        all_json_paths = list(search_dir.rglob('*.json'))
        json_files = all_json_paths

        if requested_page_slug:
            json_files = [p for p in json_files if get_page_slug_from_path(p) == requested_page_slug]

        if args.strategy:
            json_files = [p for p in json_files if f"-{args.strategy}-" in p.name]
            report_output_name_parts.append(args.strategy)

    # --- Common processing logic ---
    if not json_files:
        print(f"🟡 Warning: No JSON files found matching the criteria. Nothing to compare.")
        return

    print(f"📄 Found {len(json_files)} JSON files to process.")

    for path in json_files:
        try:
            # Extract metadata from path: .../<site-name>/<page-slug>-<strategy>-<timestamp>.json
            site_name = path.parts[-2] # This is the actual site_name from the dir
            file_stem = path.stem
            
            page_slug = ""
            strategy = ""
            timestamp = ""

            if "-desktop-" in file_stem:
                parts = file_stem.split("-desktop-", 1)
                page_slug = parts[0]
                strategy = "desktop"
                timestamp = parts[1]
            elif "-mobile-" in file_stem:
                parts = file_stem.split("-mobile-", 1)
                page_slug = parts[0]
                strategy = "mobile"
                timestamp = parts[1]
            else:
                # Fallback for unexpected formats, or if strategy not clearly separated
                # This should ideally not be hit with the new naming convention
                parts = file_stem.rsplit('-', 2)
                page_slug = parts[0]
                strategy = parts[1]
                timestamp = parts[2]
                print(f"🟡 Warning: Fallback parsing used for '{path}'. Unexpected filename format.")

            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            metrics = extract_metrics(data)

            # Get proper display names from the JSON content
            requested_url = data.get("lighthouseResult", {}).get("requestedUrl", "")
            display_host = site_name # Fallback
            display_page = page_slug # Fallback
            if requested_url:
                parsed_url = urlparse(requested_url)
                display_host = parsed_url.netloc
                display_page = parsed_url.path if parsed_url.path else "/"

            report_data = {
                "site": site_name,
                "page": page_slug,
                "strategy": strategy,
                "timestamp": timestamp,
                "display_host": display_host,
                "display_page": display_page,
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
    html_content = generate_html_report(grouped_reports, args.deep_dive)
    
    # --- Prepare output directory and filename ---
    reports_dir = pathlib.Path("reports")
    reports_dir.mkdir(exist_ok=True)
    
    current_datetime = datetime.now().strftime("%Y-%m-%d-%H%M")
    
    # Construct output filename based on what was requested
    report_filename_base = "-".join(report_output_name_parts)
    report_filename = reports_dir / f"comparison-report-{report_filename_base}-{current_datetime}.html"
    
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


def generate_html_report(grouped_data: dict, deep_dive: bool = False) -> str:
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
        .site-name { font-weight: bold; }
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
    <p>Generated from <a href="https://github.com/liamdelahunty/pagespeed" target="_blank">liamdelahunty/pagespeed</a></p>
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
        
        # Use the proper display names, with fallback to the slugs
        display_host = first.get("display_host", site)
        display_page = first.get("display_page", page)

        if deep_dive:
            metrics_to_compare = ["PerfScore", "LCP_ms", "TBT_ms", "CLS"]
        else:
            metrics_to_compare = ["PerfScore"]
        
        for i, metric in enumerate(metrics_to_compare):
            old_val = first[metric]
            new_val = last[metric]
            change = new_val - old_val
            color = get_change_color(change, metric)

            html += f"<tr>"
            if i == 0:
                html += f'<td rowspan="{len(metrics_to_compare)}" class="site-name">{display_host}</td>'
                html += f'<td rowspan="{len(metrics_to_compare)}" class="page-name">{display_page}</td>'
                html += f'<td rowspan="{len(metrics_to_compare)}" class="strategy">{strategy}</td>'
            
            html += f"<td>{metric}</td>"
            html += f"<td>{old_val}</td>"
            html += f"<td>{new_val}</td>"
            html += f'<td class="change {color}">{format_change(change, metric)}</td>'
            html += "</tr>"
    
    html += "</tbody></table>"


    # --- Detailed Trend Tables (Horizontal with Smart Headers) ---
    html += "<h2>Detailed Trend Analysis</h2>"

    # Regroup data by URL (site, page) to combine mobile and desktop
    url_groups = {}
    for (site, page, strategy), reports in grouped_data.items():
        url_key = (site, page)
        if url_key not in url_groups:
            url_groups[url_key] = {
                "display_host": reports[0].get("display_host", site),
                "display_page": reports[0].get("display_page", page),
            }
        url_groups[url_key][strategy] = reports
    
    if deep_dive:
        metrics_to_show = ["PerfScore", "AccessibilityScore", "BestPracticesScore", "SEOScore", "LCP_ms", "TBT_ms", "CLS"]
    else:
        metrics_to_show = ["PerfScore"]

    for url_key, strategies_data in url_groups.items():
        display_host = strategies_data["display_host"]
        display_page = strategies_data["display_page"]
        html += f'<h3><span class="site-name">{display_host}</span> (<span class="page-name">{display_page}</span>)</h3>'
        
        all_timestamps_str = set()
        if 'mobile' in strategies_data:
            all_timestamps_str.update(r['timestamp'] for r in strategies_data['mobile'])
        if 'desktop' in strategies_data:
            all_timestamps_str.update(r['timestamp'] for r in strategies_data['desktop'])
        
        if not all_timestamps_str:
            continue
            
        grouped_timestamps = group_timestamps(list(all_timestamps_str))
        grouped_timestamps.sort(key=lambda x: x[0], reverse=True) # Sort groups by newest first

        # Start table and build multi-level header
        html += '<table><thead>'
        # Date Row (Top)
        html += '<tr><th rowspan="2">Metric</th><th rowspan="2">Strategy</th>'
        
        # Group representative timestamps by date to calculate colspans
        date_groups = {}
        for rep_ts, _ in grouped_timestamps:
            date_str = rep_ts.strftime("%Y-%m-%d")
            if date_str not in date_groups:
                date_groups[date_str] = 0
            date_groups[date_str] += 1
        
        for date_str, span in date_groups.items():
            html += f'<th colspan="{span}">{date_str}</th>'
        html += '</tr>'
        
        # Time Row (Bottom)
        html += '<tr>'
        for rep_ts, _ in grouped_timestamps:
            html += f'<th>{rep_ts.strftime("%H:%M")}</th>'
        html += '</tr></thead>'

        # Table Body
        html += '<tbody>'
        mobile_reports = {r['timestamp']: r for r in strategies_data.get('mobile', [])}
        desktop_reports = {r['timestamp']: r for r in strategies_data.get('desktop', [])}

        for metric in metrics_to_show:
            for strategy in ['mobile', 'desktop']:
                reports_map = mobile_reports if strategy == 'mobile' else desktop_reports
                if not reports_map:
                    continue

                html += f"<tr><td>{metric}</td><td>{strategy}</td>"
                
                for _, original_ts_strs in grouped_timestamps:
                    found_value = None
                    for ts in original_ts_strs:
                        value = reports_map.get(ts, {}).get(metric)
                        if value is not None:
                            found_value = value
                            break # Found the first available value in the group
                    
                    display_value = found_value if found_value is not None else "N/A"
                    html += f"<td>{display_value}</td>"
                
                html += "</tr>"
        
        html += "</tbody></table>"

    html += "</body></html>"
    return html




if __name__ == "__main__":
    main()
