# PageSpeed Insights CSV Collector
A Python utility that:
* reads a list of URLs, 
* calls the Google PageSpeed Insights v5 API (desktop + mobile), 
* extracts the five Lighthouse category scores plus the core performance metrics, 
* writes a timestamped CSV file,
* and the JSON response.

## ✨ What it does
* Loads URLs from a file in the `url-lists/` directory (one per line).
* Queries the API for Performance, Accessibility, Best‑Practices, SEO.
* Retrieves FCP, Speed Index, LCP, TTI, TBT, CLS, SRT.
* Saves a file named `pagespeed-report-<source>-YYYY-MM-DD-HHMM.csv`, where `<source>` is derived from the input (e.g., the website domain or the input filename).
* Dumps the raw JSON responses to debug-responses/ for troubleshooting.
* All results are deterministic (no cache, no cookies, fixed throttling), making the CSV comparable across users and locations.
* Automatically retries failed requests once at the end of the run.
* Allows you to provide a URL without a scheme (e.g. `www.example.com`) to the `-u` flag.

## Scripts and Their Outputs

This project contains several Python scripts that form a data collection and reporting pipeline. Here is a summary of each script, its purpose, an example command, and the assets it produces.

| Script | Purpose | Example Command | Generated Assets |
| --- | --- | --- | --- |
| **`pagespeed_to_csv.py`** | The core data collection script. It calls the PageSpeed Insights API and saves the raw data. | `python pagespeed_to_csv.py --url-file urls.txt` | <ul><li>`reports/pagespeed-report-urls-YYYY-MM-DD-HHMM.csv`</li><li>`debug-responses/.../...-YYYY-MM-DD-HHMMSS.json` (multiple files)</li></ul> |
| **`organise_reports.py`** | A maintenance script that renames the raw JSON files in `debug-responses/` to a consistent format. | `python organise_reports.py` | Renamed JSON files in place. |
| **`generate_summary_report.py`** | Generates a single HTML report summarizing data for multiple URLs. Has two modes: historical trend and latest scores. | `python generate_summary_report.py -f urls.txt --period 7d` | `reports/summary-report-urls-YYYYMMDD-YYYYMMDD.html` |
| **`generate_html_report.py`** | Generates a detailed, individual HTML report for each URL, focusing on historical trends with graphs. | `python generate_html_report.py -f urls.txt --period 7d` | `reports/history-report-<site-name>-YYYYMMDD-YYYYMMDD.html` (one per URL) |
| **`generate-cwv-report.py`** | Generates a summary HTML report for Core Web Vitals (LCP, FID, CLS) with a chart and detailed breakdown. | `python generate-cwv-report.py -f urls.txt --period 7d` | `reports/cwv-report-urls-YYYYMMDD-YYYYMMDD.html` |
| **`compare_reports.py`** | Generates a single HTML report comparing the first and last runs for multiple sites, showing the change over time. | `python compare_reports.py --from-file urls.txt --with-graphs` | `reports/comparison-report-from-urls-YYYY-MM-DD-HHMM.html` |
| **`send_email_report.py`** | Sends an email summary based on the latest generated CSV report. | `python send_email_report.py` | An email sent to the configured recipient. (No file produced). |
| **`retention.py`** | A maintenance script that prunes old report files from the `debug-responses/` and `reports/` directories based on a configurable retention policy. | `python retention.py debug-responses --dry-run`<br>`python retention.py debug-responses --archive bak/debug-responses-achive-yyyy-mm-dd.zip` | <ul><li>`retention.log`</li><li>Optionally, a zip archive of pruned files.</li></ul> |

## 📦 Prerequisites
Python 3.8+ (official installer from https://python.org).

Upgrade pip (optional but recommended):

```py -m pip install --upgrade pip```

Install required packages (run in the project folder):

```py -m pip install requests tqdm python-dotenv pandas plotly Jinja2```

Create a Google Cloud API key with the [PageSpeed Insights API](https://developers.google.com/speed/docs/insights/v5/get-started) enabled.
Store it in a .env file (same folder as the script):

```PSI_API_KEY=YOUR_GOOGLE_API_KEY```

Prepare the URL list – a plain‑text file inside the `url-lists/` directory:
```
https://example.com
https://another-site.org/page
```

### 🚀 Usage
The script can be run in two ways: by providing a single URL directly, or by providing a file containing a list of URLs.

**1. Test a single URL**

Use the `-u` or `--url` flag to test a specific URL. You can provide the URL with or without the `https://` prefix. This is useful for quick, one-off tests.

```sh
# With a scheme
python pagespeed_to_csv.py --url https://www.example.com
# Without a scheme
python pagespeed_to_csv.py --url www.example.com
```

**2. Test multiple URLs from a file**

Use the `-f` or `--url-file` flag to point to a text file containing one URL per line. If you don't provide this flag, the script will automatically look for `url-lists/urls.txt`. If you provide a filename without a path, the script will look for it in the `url-lists/` directory.

```sh
# This will use the default url-lists/urls.txt
python pagespeed_to_csv.py

# This will use a custom file named my_urls.txt located in the url-lists/ directory
python pagespeed_to_csv.py --url-file my_urls.txt
```

If both `--url` and `--url-file` are provided, the single URL from `--url` takes precedence.

### The script will:
* Print the progress for each URL with a dedicated progress bar.
* Create a report named `pagespeed-report-<source>-<timestamp>.csv`, where `<source>` is the domain for a single URL test or the filename for a batch test.
* Save raw API responses under debug-responses/ (optional, for debugging).
This can easily be read with the Lighthouse Viewer in the [Lighthouse Chrome Extension](https://chromewebstore.google.com/detail/lighthouse/blipmdconlkpinefehnmjammfjpmpbjk) or directly using the [Lighthouse viewer page](https://googlechrome.github.io/lighthouse/viewer/).

### 💡 Typical Workflow

While each script can be used independently, a common workflow for gathering data and generating reports looks like this:

1.  **Gather Data:** Run `pagespeed_to_csv.py` to collect the latest PageSpeed Insights data for your desired URLs. This will populate the `debug-responses/` directory with raw JSON files.
    ```sh
    # Example: Collect data for URLs in group.txt
    python pagespeed_to_csv.py --url-file group.txt
    ```

2.  **Organise Filenames (Optional but Recommended):** Run `organise_reports.py` to ensure all raw JSON files have a consistent naming convention. This helps the reporting scripts correctly identify and parse the data.
    ```sh
    python organise_reports.py
    ```

3.  **Generate Reports:** Choose one of the reporting scripts to visualize the data.
    *   To see the latest scores for a group of sites, use `generate_summary_report.py` with the `--group-report` flag.
        ```sh
        # Example: Generate a report of the latest scores for group.txt
        python generate_summary_report.py --group-report --url-file group.txt
        ```
    *   To see historical trends for a list of URLs in a single report, use `generate_summary_report.py` with a time period.
        ```sh
        # Example: Show the trend over the last 28 days for group.txt
        python generate_summary_report.py -f group.txt --period 28d
        ```
    *   To get an in-depth, side-by-side comparison of all runs for a specific URL, use `compare_reports.py`.
        ```sh
        # Example: Compare all historical runs for a single URL
        python compare_reports.py --url https://www.example.com --with-graphs
        ```

## 📊 Comparing Reports
The `compare_reports.py` script scans the raw JSON data in `debug-responses/` and generates a single, self-contained HTML report to show performance trends over time.

### Usage
The script offers several flags to filter the data included in the report.

**1. Generate a full report (all sites)**
```sh
python compare_reports.py
```
This will generate a `comparison-report-all-sites-<timestamp>.html` file in the `reports/` directory.

**2. Filter for a specific host**
Use the `-H` or `--host` flag to report on all pages for a specific website.
```sh
python compare_reports.py --host www.croneri.co.uk
```

**3. Filter for a specific URL**
Use the `-u` or `--url` flag to report on a single page.
```sh
python compare_reports.py --url https://www.croneri.co.uk/products
```

**4. Filter from a URL List File**
Use the `-f` or `--from-file` flag to report on a specific list of URLs contained in a file. This is useful for creating a report for a subset of pages across different sites. If you provide a filename without a path, the script automatically looks for it in the `url-lists/` directory.
```sh
# This will use 'url-lists/my-report-list.txt'
python compare_reports.py --from-file my-report-list.txt
```

**5. Filter by Strategy**
Add the `--strategy` flag to any command to limit the report to either `mobile` or `desktop` data.
```sh
python compare_reports.py --host www.croneri.co.uk --strategy mobile
```

**6. Show More Metrics**
Add the `-d` or `--deep-dive` flag to include all core web vitals and other performance metrics in the tables. By default, only the main Performance Score is shown.
```sh
python compare_reports.py --url https://www.croneri.co.uk -d
```

**7. Include Trend Graphs**
Add the `--with-graphs` flag to any command to include interactive line charts in the report. These charts visualize the trend of selected metrics over time for each URL.
```sh
python compare_reports.py --url https://www.croneri.co.uk --with-graphs
```

### Output Report
The generated HTML report contains two main sections, plus an optional section for graphs:

*   **Summary of Changes:** A high-level overview comparing the very first and very last report found for a given page, showing the change in score.
*   **Detailed Trend Analysis:** A set of horizontal tables, one for each URL. These tables provide a detailed, time-based view of performance.
    *   **Smart Headers:** To save space, timestamps are grouped. The top header row shows the Date (and spans across multiple tests from the same day), while the second row shows the Time.
    *   **Grouped Columns:** Mobile and Desktop tests run within two minutes of each other are grouped into a single column, making it easy to compare results from the same test run.
*   **Trend Graphs (Optional):** If the `--with-graphs` flag is used, interactive line charts are generated for each URL and metric, showing performance trends over time for both mobile and desktop strategies.

## 📈 Generating History Reports
The `generate_html_report.py` script provides a dynamic way to visualize PageSpeed Insights data over time. It creates interactive HTML reports with data tables and trend graphs for specified URLs and time periods, allowing for a detailed historical analysis of performance metrics.

### Usage
This script requires you to specify either a single URL or a file containing multiple URLs, along with a time period or a number of recent runs.

**1. Report for a single URL**
Use the `-u` or `--url` flag to generate a detailed report for a specific URL.
```sh
# Report for a single URL over the last 28 days
python generate_html_report.py --url https://www.example.com --period 28d
```

**2. Individual Reports for URLs from a File**
Use the `-f` or `--url-file` flag to generate a separate, individual report for each URL listed in the file.
```sh
# Generate a separate report for each URL in 'my-list.txt' for the last calendar month
python generate_html_report.py --url-file my-list.txt --period last-month
```

### Time Period Flags
You must choose either `--period` or `--last-runs`:
*   `--period {7d, 28d, this-month, last-month, all-time}`: Defines a relative date range for the data.
*   `--last-runs N`: Reports on the `N` most recent data collection runs, regardless of date.

### Output Report
The script generates one or more self-contained HTML files in the `reports/` directory. The filename is deterministic based on the data it contains, following the pattern: `history-report-<source>-<start_date>-<end_date>.html`.
*   `<source>` is the domain name of the URL.
*   `<start_date>` and `<end_date>` are the dates of the oldest and newest records in the report (formatted as YYYYMMDD).

This ensures that if you re-run a report on the same data, the file is overwritten, but if new data is included, a new file is created.

Each report includes:
*   A **Data Summary** table showing key metrics for each run.
*   Interactive line charts for all key PageSpeed metrics (Performance Score, LCP, CLS, etc.).
*   A single-line header and footer with report metadata and helpful links.

**Note on Data Merging:** The summary table now merges desktop and mobile runs into a single row if their execution timestamps are within a 15-minute window of each other. This provides a more consolidated view of performance for concurrent test runs. As a result, you may see fewer rows in the table than the total number of individual report files, as each merged row can represent two runs (one mobile, one desktop).

## 📊 Generating Consolidated Summary Reports
The `generate_summary_report.py` script creates a high-level, consolidated summary of performance score trends for a list of URLs. It's designed to give a quick overview of how multiple sites are progressing over a specific period, **generating a single HTML report for a group of URLs.**

### Report Organisation with JSON (for `--group-report` flag)
When using the `--group-report` flag, the script can leverage an optional companion JSON file (named `<your-url-file-stem>-ordering.json`) to define the layout and grouping of URLs within the report. This allows for a structured presentation, such as grouping URLs by company or type.

**JSON Structure Example (`my-list-ordering.json`):**
```json
[
  {
    "Company": "Example Corp",
    "Type": "Homepage",
    "URL": "https://www.example.com/"
  },
  {
    "Company": "Example Corp",
    "Type": "Product Page",
    "URL": "https://www.example.com/products"
  },
  {
    "Company": "Another Company",
    "Type": "Homepage",
    "URL": "https://www.anothersite.org/"
  }
]
```
If this JSON file is found alongside your URL list file (e.g., `my-list.txt` and `my-list-ordering.json` in `url-lists/`), the report will be structured according to the "Company" groupings defined in the JSON. If no such JSON file is present, a simple ungrouped report will be generated.

### Usage
This script requires a URL file and a time period.
```sh
# Generate a summary for all URLs in 'group.txt' for the last 4 runs
python generate_summary_report.py -f group.txt --last-runs 4

# Generate a summary for URLs in 'clients.txt' over the last 28 days
python generate_summary_report.py -f clients.txt --period 28d
```

### Output Report
This script generates a **single** HTML file in the `reports/` directory, named using the pattern `summary-report-<source>-<start_date>-<end_date>.html`.
*   `<source>` is the name of the input URL file.
*   `<start_date>` and `<end_date>` are the dates of the oldest and newest records across all data in the report.

The report contains:
*   **Performance Trend Graphs:** Two consolidated line charts (one for Desktop, one for Mobile) showing the Performance Score trend for every URL, making it easy to compare sites against each other.
*   **Score Change Summary:** A table detailing the change in performance for each URL and strategy, comparing the first and last data points in the selected period.

## 📊 Generating Core Web Vitals (CWV) Reports
The `generate-cwv-report.py` script creates a summary HTML report focused on Core Web Vitals. It finds the relevant raw JSON data based on the URL and time period provided and generates a single, consolidated report.

### Usage
This script uses the same argument structure as other reporting scripts, requiring a URL source and an optional time frame.

```sh
# Generate a CWV report for all URLs in 'uk-ie.txt' for the last 7 days
python generate-cwv-report.py --url-file uk-ie.txt --period 7d

# Generate a report for a single URL covering the last 5 runs
python generate-cwv-report.py --url https://www.example.com --last-runs 5
```

### Output Report
The script produces a single HTML file named `cwv-report-<source>-<start_date>-<end_date>.html`.
*   `<source>` is derived from the input URL or filename.
*   `<start_date>` and `<end_date>` reflect the date range of the data in the report.

The report includes:
*   A bar chart visualizing the distribution of "Good," "Needs Improvement," and "Poor" scores for LCP, FID (using Max Potential FID), and CLS across all the data found.
*   A detailed table listing the specific metric values for each URL and strategy, with cells colour-coded based on performance.

## 🧹 Organising Raw Reports

The `organise_reports.py` script helps to standardise the filenames of the raw JSON responses stored in the `debug-responses/` directory. This is particularly useful if your JSON files were generated with older naming conventions or if you want to ensure consistent naming for easier analysis.

The script renames files to the following format: `<page-slug>-<strategy>-<timestamp>.json`. It extracts the page URL, strategy (mobile/desktop), and fetch timestamp directly from the JSON content to ensure accuracy.

### How to run

To run the organisation script, execute the following command:

```sh
python organise_reports.py
```

The script will automatically scan all JSON files in `debug-responses/` and rename them in place. It will report on any files that were renamed or skipped.

```
Found X JSON files to process. Starting renaming...
✅ Renamed 'old-filename-mobile-timestamp.json' -> 'example-com-mobile-2023-10-27-103000.json'
🟡 Skipping 'already-correctly-named.json': a file named 'already-correctly-named.json' already exists.
--- Organisation Complete ---
Renamed: Y files
Skipped: Z files
```

**Note:** It's recommended to back up your `debug-responses/` directory before running this script, although the script has been designed to avoid overwriting files.

## 🧹 Managing Data Retention
The `retention.py` script is a powerful tool for managing the long-term storage of your PageSpeed data. Over time, the `debug-responses/` and `reports/` directories can grow very large. This script allows you to selectively prune old files based on a sophisticated retention policy, helping to control disk space usage while preserving a valuable history of your data.

### Retention Policy
The script applies the following rules:
1.  **De-duplication:** It first ensures that for any given day, only the single latest report for each unique URL and strategy is kept.
2.  **Tiered Retention:** On the de-duplicated dataset, it then applies a tiered retention policy:
    *   **Keep all** reports from the last **90 days**.
    *   Keep the **most recent report from each week** for data older than 90 days but newer than one year.
    *   Keep the **most recent report from each month** for data older than one year.

All operations are logged to `retention.log`.

### How to Use the Script
It is **strongly recommended** to perform a "dry run" before deleting or archiving any files to ensure the script is selecting the correct files for removal.

**1. Perform a "Dry Run" (Recommended First Step)**
This will simulate the process and show you which files would be removed, without actually touching them.
*   For the `debug-responses` directory:
    ```sh
    python retention.py debug-responses --dry-run
    ```
*   For the `reports` directory:
    ```sh
    python retention.py reports --dry-run
    ```

**2. Delete Files**
Once you have reviewed the dry run and are happy with the list of files to be pruned, you can run the script without the `--dry-run` flag to permanently delete them.
*   For the `debug-responses` directory:
    ```sh
    python retention.py debug-responses
    ```

**3. Archive Files**
If you prefer to archive the old files instead of deleting them, use the `--archive` flag and provide a name for the zip file. The script will move the pruned files into the archive and then delete them from their original location.
*   To archive files from the `reports` directory:
    ```sh
    python retention.py reports --archive reports-archive.zip
    ```

## 🤖 Continuous Monitoring with GitHub Actions

This repository is configured to run PageSpeed Insights checks automatically using GitHub Actions. The workflow files located in the `.github/workflows/` directory define scheduled jobs (cron jobs) that execute the scripts for different regional websites.

The following workflow files are included:

*   `pagespeed-au.yml`: Runs daily checks for Australian sites.
*   `pagespeed-ca.yml`: Runs daily checks for Canadian sites.
*   `pagespeed-cil.yml`: Runs daily checks for Croner-i and legacy sites.
*   `pagespeed-nz.yml`: Runs daily checks for New Zealand sites.
*   `pagespeed-uk-ie.yml`: Runs daily checks for UK and Irish sites.
*   `pagespeed.yml`: A general-purpose workflow that can be manually triggered to run checks.

These workflows ensure that PageSpeed data is collected consistently over time, allowing for robust historical analysis. The collected data (raw JSON responses) is uploaded as a time-stamped artifact (e.g., `pagespeed-reports-2026-01-06-1230`) to the workflow run, which can be downloaded for local report generation.

## 📋 Configuration Notes  

| Setting | Default | How to change |
|---------|---------|---------------|
| **API endpoint** | `https://www.googleapis.com/pagespeedonline/v5/runPagespeed` | Edit the `API_ENDPOINT` constant near the top of `pagespeed_to_csv.py`. |
| **Strategies** | `("desktop", "mobile")` | Modify the `STRATEGIES` tuple (`STRATEGIES = ("desktop",)` for only desktop, etc.). |
| **Categories** | All four – `performance, accessibility, best‑practices, seo` | Change the `category` list inside `call_pagespeed` if you need a subset. |
| **Timeout** | `90` seconds | Adjust the `timeout=` argument in `requests.get(...)`. |
| **Output folder** | CSVs are written to the `reports/` directory. | The output directory is defined by the `REPORTS_DIR` constant in the script. The filename is generated dynamically. |
| **Debug JSON dump folder** | `debug-responses/` | Change the `out_dir` path inside `dump_response`. |

---

## 🐞 Common Issues & Fixes  

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| `NameError: PSI_API_KEY` | `.env` file missing, mis‑named, or variable not set. | Create a `.env` file in the project root with `PSI_API_KEY=YOUR_GOOGLE_API_KEY`. Ensure the file is saved and the variable name is spelled exactly. [Select "Get a Key" on this page.](https://developers.google.com/speed/docs/insights/v5/get-started) |
| `400 Bad Request` from the API | API key restricted (referrer/IP) or malformed request parameters. | In Google Cloud Console → **APIs & Services → Credentials** → edit the key → set **Application restrictions** to **None** (or add your public IP). Also verify the `category` list is a Python list, not a comma‑separated string. |
| `ModuleNotFoundError: requests` (or `tqdm`, `python‑dotenv`) | Dependencies not installed. | Run `py -m pip install --upgrade pip` then `py -m pip install requests tqdm python-dotenv`. |
| Scores are all `0` (Performance, Accessibility, etc.) | Wrong `category` format or API response missing those fields. | Use the list version for `category` (see the **Categories** row above). |
| Script runs very slowly or times out | Network throttling on your side or the target site is extremely slow. | Increase the `timeout` value in `call_pagespeed` (e.g., `timeout=180`). |
| CSV file not created or empty | URL file missing or contains no valid URLs. | Ensure a URL file exists in the `url-lists/` directory and has at least one non‑blank line with a full URL (`https://example.com`). |
| Raw JSON files not appearing | `debug-responses/` folder not created or path incorrect. | Verify the `out_dir` path in `dump_response`. If you moved the CSV folder to `reports/`, also update the debug folder to `REPORTS_DIR / "debug-responses"` (see the folder‑change snippet). |
| Different users get different results | Users are running the script locally with their own Chrome version or caching. | Use the **PageSpeed Insights API**  for deterministic, location‑independent results. |
| “Permission denied” when installing packages on Windows | Running the command without admin rights. | Add the `--user` flag: `py -m pip install --user requests tqdm python-dotenv`, or run the terminal as Administrator. |


Happy monitoring!