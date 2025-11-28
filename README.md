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

## 📦 Prerequisites
Python 3.8+ (official installer from https://python.org).

Upgrade pip (optional but recommended):

```py -m pip install --upgrade pip```

Install required packages (run in the project folder):

```py -m pip install requests tqdm python-dotenv```

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

## 📊 Comparing Reports
This project also includes a `compare_reports.py` script that generates an HTML report to show performance trends over time.

### How to run
```sh
python compare_reports.py
```
This will generate a `comparison-report-all-sites-<timestamp>.html` file in the `reports/` directory.

You can also specify a single site to report on:
```sh
python compare_reports.py -s example-com
```
This will generate a `comparison-report-example-com-<timestamp>.html` file.

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