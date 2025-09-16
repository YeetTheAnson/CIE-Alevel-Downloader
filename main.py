import argparse
import os
import sys
import csv
import concurrent.futures
from urllib.parse import urljoin
import requests
from tqdm import tqdm

BASE_URL = "https://pastpapers.co/cie/A-Level"
OUTPUT_DIR = "CIE_OUT"
SYLLABUS_FILE = "syllabus.csv"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://pastpapers.co/',
}

def load_syllabus_map(filename):
    if not os.path.exists(filename):
        print(f"Error: The syllabus lookup file '{filename}' was not found.")
        print("Please create it in the same directory as the script.")
        sys.exit(1)
    
    syllabus_map = {}
    with open(filename, mode='r', encoding='utf-8') as infile:
        reader = csv.reader(infile)
        next(reader)
        for code, path in reader:
            syllabus_map[code.strip()] = path.strip()
    return syllabus_map

def probe_worker(url, save_path, headers):
    if os.path.exists(save_path):
        return None
    
    try:
        response = requests.head(url, headers=headers, timeout=10, allow_redirects=True)
        if response.status_code == 200:
            return (url, save_path)
    except requests.exceptions.RequestException:
        pass
    
    return None

def download_worker(url, save_path, headers):
    try:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        
        response = requests.get(url, stream=True, headers=headers, timeout=60)
        response.raise_for_status()
        
        with open(save_path, 'wb') as f:
            for data in response.iter_content(chunk_size=8192):
                f.write(data)
        return True
    except requests.exceptions.RequestException:
        return False
    except Exception:
        return False

def main():
    parser = argparse.ArgumentParser(
        description="Download Cambridge A-Level past papers from pastpapers.co using a brute-force method.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    parser.add_argument('-s', '--syllabus', type=str, required=True, help='The 4-digit syllabus code (e.g., 9231).')
    parser.add_argument('--start_year', type=int, required=True, help='The starting year for the download range (inclusive).')
    parser.add_argument('--end_year', type=int, help='The ending year for the download range (inclusive). Defaults to start_year.')
    parser.add_argument('-p', '--papers', type=str, help='Comma-separated list of paper numbers to check (e.g., "1,3"). Defaults to 1-9.')
    parser.add_argument('--ms', action='store_true', help='Include mark schemes in the download.')
    parser.add_argument('--gt', action='store_true', help='Include grade thresholds in the download.')
    parser.add_argument(
        '-fs', '--file_structure', type=str, choices=['month_year_paper', 'year_month_paper', 'month_year', 'year_month'], default='year_month_paper',
        help="Choose the output directory structure (default: year_month_paper)"
    )
    parser.add_argument(
        '-j', '--jobs', type=int, default=4,
        help='Number of parallel downloads to run at once (default: 4).'
    )
    parser.add_argument(
        '-pj', '--probe-jobs', type=int, default=8,
        help='Number of parallel probes to run at once. Increase with caution. (default: 8).'
    )

    args = parser.parse_args()
    
    syllabus_map = load_syllabus_map(SYLLABUS_FILE)
    if args.syllabus not in syllabus_map:
        print(f"Error: Syllabus code '{args.syllabus}' not found in '{SYLLABUS_FILE}'.")
        sys.exit(1)
        
    link_path = syllabus_map[args.syllabus]
    syllabus_name_code = link_path.strip('/')
    
    end_year = args.end_year if args.end_year else args.start_year
    years = range(args.start_year, end_year + 1)
    paper_numbers_to_check = args.papers.split(',') if args.papers else [str(i) for i in range(1, 10)]
    seasons = [('s', 'May-June'), ('w', 'Oct-Nov'), ('m', 'March')]
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    print(f"Starting download for {syllabus_name_code} from {args.start_year}-{end_year}")

    probe_list = []
    for year in years:
        for season_char, season_folder in seasons:
            year_short = str(year)[-2:]
            
            if args.file_structure in ['month_year_paper', 'month_year']: base_path_parts = [OUTPUT_DIR, syllabus_name_code, season_folder, str(year)]
            else: base_path_parts = [OUTPUT_DIR, syllabus_name_code, str(year), season_folder]

            if args.gt:
                filename = f"{args.syllabus}_{season_char}{year_short}_gt.pdf"
                url = f"{BASE_URL}{link_path}/{year}-{season_folder}/{filename}"
                save_path = os.path.join(*base_path_parts, filename)
                probe_list.append((url, save_path))

            for paper in paper_numbers_to_check:
                path_parts = list(base_path_parts)
                if 'paper' in args.file_structure: path_parts.append(f"Paper {paper}")
                for variant_num in range(1, 10):
                    qp_filename = f"{args.syllabus}_{season_char}{year_short}_qp_{paper}{variant_num}.pdf"
                    qp_url = f"{BASE_URL}{link_path}/{year}-{season_folder}/{qp_filename}"
                    qp_save_path = os.path.join(*path_parts, qp_filename)
                    probe_list.append((qp_url, qp_save_path))
                    
                    if args.ms:
                        ms_filename = f"{args.syllabus}_{season_char}{year_short}_ms_{paper}{variant_num}.pdf"
                        ms_url = f"{BASE_URL}{link_path}/{year}-{season_folder}/{ms_filename}"
                        ms_save_path = os.path.join(*path_parts, ms_filename)
                        probe_list.append((ms_url, ms_save_path))

    print(f"\nPhase 1: Probing {len(probe_list):,} potential files with {args.probe_jobs} parallel workers...")
    download_queue = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.probe_jobs) as executor:
        future_to_probe = {executor.submit(probe_worker, url, path, HEADERS): (url, path) for url, path in probe_list}
        
        with tqdm(total=len(probe_list), unit="probe", desc="Probing") as pbar:
            for future in concurrent.futures.as_completed(future_to_probe):
                result = future.result()
                if result:
                    download_queue.append(result)
                pbar.update(1)

    print(f"\nProbing complete. Found {len(download_queue)} new files to download.")
    
    files_downloaded = 0
    if not download_queue:
        print("Everything is up to date.")
    else:
        print(f"\nPhase 2: Downloading files with {args.jobs} parallel workers...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as executor:
            future_to_url = {executor.submit(download_worker, url, path, HEADERS): url for url, path in download_queue}
            
            with tqdm(total=len(download_queue), unit="file", desc="Downloading") as pbar:
                for future in concurrent.futures.as_completed(future_to_url):
                    try:
                        if future.result():
                            files_downloaded += 1
                        else:
                            pbar.write(f'Warning: Failed to download {os.path.basename(future_to_url[future])}')
                    except Exception as exc:
                        pbar.write(f'Error: Exception for {os.path.basename(future_to_url[future])}: {exc}')
                    finally:
                        pbar.update(1)

    print("\n------------------------------------")
    print("Download process completed.")
    print(f"Successfully downloaded {files_downloaded} new files.")
    print(f"All files are saved in: {os.path.abspath(OUTPUT_DIR)}")
    print("------------------------------------")

if __name__ == '__main__':
    main()
