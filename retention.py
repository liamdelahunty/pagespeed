# retention.py
import os
import re
import argparse
from datetime import datetime, date, timedelta
from collections import defaultdict
import logging

# --- Configuration ---
import configparser

config = configparser.ConfigParser()
config.read('config.ini')

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[
    logging.FileHandler(config['Retention']['log_file']),
    logging.StreamHandler()
])

# Regular expressions to parse filenames
# For debug-responses: <page-slug>-<strategy>-<YYYY-MM-DD-HHMMSS>.json
DEBUG_RESPONSES_RE = re.compile(r"^(?P<slug>.*?)-(?P<strategy>desktop|mobile)-(?P<timestamp>\d{4}-\d{2}-\d{2}-\d{6})\.json$")
# For reports: comparison-report-<site>-<YYYY-MM-DD-HHMM>.html
REPORTS_RE = re.compile(r"^comparison-report-(?P<slug>.*?)-(?P<timestamp>\d{4}-\d{2}-\d{2}-\d{4})\.html$")


# --- File Parsing ---

def parse_filename(filename):
    """
    Parses a filename to extract the slug, strategy, and timestamp.
    Returns a tuple (slug, strategy, datetime_obj).
    Returns (None, None, None) if the filename does not match a known pattern.
    """
    match = DEBUG_RESPONSES_RE.match(filename)
    if match:
        data = match.groupdict()
        try:
            timestamp = datetime.strptime(data['timestamp'], '%Y-%m-%d-%H%M%S')
            return data['slug'], data['strategy'], timestamp
        except ValueError:
            return None, None, None

    match = REPORTS_RE.match(filename)
    if match:
        data = match.groupdict()
        try:
            # Reports timestamp has no seconds
            timestamp = datetime.strptime(data['timestamp'], '%Y-%m-%d-%H%M')
            return data['slug'], 'report', timestamp # using 'report' as strategy
        except ValueError:
            return None, None, None
            
    return None, None, None

# --- Retention Logic ---

def get_files_to_prune(directory):
    """
    Applies the retention policy to a directory and returns a set of files to be pruned.
    """
    
    # 1. Group files by slug, strategy, and day
    daily_latest = defaultdict(list)
    all_files = []

    for root, _, files in os.walk(directory):
        for filename in files:
            full_path = os.path.join(root, filename)
            slug, strategy, timestamp = parse_filename(filename)

            if not all([slug, strategy, timestamp]):
                logging.debug(f"Skipping non-matching file: {filename}")
                continue

            all_files.append(full_path)
            key = (slug, strategy, timestamp.date())
            daily_latest[key].append((timestamp, full_path))

    # 2. Identify daily duplicates for deletion
    files_to_keep = set()
    for key, file_group in daily_latest.items():
        # Sort by timestamp to find the latest
        file_group.sort(key=lambda x: x[0], reverse=True)
        # Keep the latest one
        files_to_keep.add(file_group[0][1])

    files_to_consider_for_retention = sorted(list(files_to_keep), key=lambda x: os.path.getmtime(x))
    
    # 3. Apply retention policy (90 days, weekly, monthly)
    today = datetime.now()
    ninety_days_ago = today - timedelta(days=int(config['Retention']['ninety_days']))
    one_year_ago = today - timedelta(days=int(config['Retention']['one_year']))

    weekly_retention = defaultdict(lambda: (datetime.min, None))
    monthly_retention = defaultdict(lambda: (datetime.min, None))
    
    final_files_to_keep = set()

    for file_path in files_to_consider_for_retention:
        _, _, timestamp = parse_filename(os.path.basename(file_path))
        
        # Rule 1: Keep all reports for the last 90 days
        if timestamp > ninety_days_ago:
            final_files_to_keep.add(file_path)
            continue
        
        # Rule 2: For data older than 90 days, keep one per week
        if timestamp > one_year_ago:
            week_key = timestamp.strftime('%Y-%W')
            if timestamp > weekly_retention[week_key][0]:
                weekly_retention[week_key] = (timestamp, file_path)

        # Rule 3: For data older than 1 year, keep one per month
        else:
            month_key = timestamp.strftime('%Y-%m')
            if timestamp > monthly_retention[month_key][0]:
                monthly_retention[month_key] = (timestamp, file_path)

    # Add weekly and monthly retained files to the keep set
    for _, file_path in weekly_retention.values():
        if file_path: final_files_to_keep.add(file_path)
    for _, file_path in monthly_retention.values():
        if file_path: final_files_to_keep.add(file_path)

    # 4. Determine files to prune
    return set(all_files) - final_files_to_keep


# --- Main Execution ---

def main():
    parser = argparse.ArgumentParser(description="Prune old report files based on a retention policy.")
    parser.add_argument("directory", help="The directory to clean up (e.g., 'reports' or 'debug-responses').")
    parser.add_argument("--dry-run", action="store_true", help="Simulate the pruning process without deleting files.")
    parser.add_argument("--archive", help="Move pruned files to a zip archive instead of deleting. Provide a name for the archive (e.g., 'archive.zip').")

    args = parser.parse_args()

    if not os.path.isdir(args.directory):
        logging.error(f"Error: Directory '{args.directory}' not found.")
        return

    logging.info(f"Starting pruning process for '{args.directory}'...")
    if args.dry_run:
        logging.info("DRY RUN MODE: No files will be deleted or moved.")

    files_to_prune = get_files_to_prune(args.directory)

    if not files_to_prune:
        logging.info("No files to prune.")
        return

    logging.info(f"Found {len(files_to_prune)} files to prune.")

    if args.archive:
        import zipfile
        logging.info(f"Archiving files to '{args.archive}'...")
        with zipfile.ZipFile(args.archive, 'a', zipfile.ZIP_DEFLATED) as zf:
            for file_path in files_to_prune:
                if not args.dry_run:
                    try:
                        zf.write(file_path, os.path.basename(file_path))
                        os.remove(file_path)
                        logging.info(f"Archived and removed: {file_path}")
                    except FileNotFoundError:
                         logging.warning(f"File not found for archiving, it might have been already removed: {file_path}")
                    except Exception as e:
                        logging.error(f"Error archiving {file_path}: {e}")
    else:
        logging.info("Deleting files...")
        for file_path in files_to_prune:
            if not args.dry_run:
                try:
                    os.remove(file_path)
                    logging.info(f"Deleted: {file_path}")
                except FileNotFoundError:
                    logging.warning(f"File not found for deletion, it might have been already removed: {file_path}")
                except Exception as e:
                    logging.error(f"Error deleting {file_path}: {e}")
            else:
                logging.info(f"DRY RUN: Would delete {file_path}")

    logging.info("Pruning process complete.")

if __name__ == "__main__":
    main()
