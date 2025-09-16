import argparse
import os
import sys
import csv
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

def download_if_exists(url, save_path):
    try:
        head_response = requests.head(url, headers=HEADERS, timeout=5, allow_redirects=True)
        if head_response.status_code == 200:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            
            response = requests.get(url, stream=True, headers=HEADERS, timeout=30)
            response.raise_for_status()
            
            with open(save_path, 'wb') as f:
                for data in response.iter_content(chunk_size=1024):
                    f.write(data)
            return True
        return False
    except requests.exceptions.RequestException:
        return False

def main():
    parser = argparse.ArgumentParser(
        description="Download Cambridge A-Level past papers from pastpapers.co using a brute-force method.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    parser.add_argument(
        '-s', '--syllabus', 
        type=str, 
        required=True,
        help='The 4-digit syllabus code (e.g., 9231). Must exist in syllabus.csv.'
    )
    parser.add_argument(
        '--start_year', 
        type=int, 
        required=True,
        help='The starting year for the download range (inclusive).'
    )
    parser.add_argument(
        '--end_year', 
        type=int, 
        help='The ending year for the download range (inclusive). Defaults to start_year if not provided.'
    )
    parser.add_argument(
        '-p', '--papers', 
        type=str, 
        help='Comma-separated list of paper numbers to check (e.g., "1,3"). If omitted, checks 1 through 6.'
    )
    parser.add_argument(
        '--ms', 
        action='store_true', 
        help='Include mark schemes in the download.'
    )
    parser.add_argument(
        '--gt', 
        action='store_true', 
        help='Include grade thresholds in the download.'
    )
    parser.add_argument(
        '-fs', '--file_structure', 
        type=str, 
        choices=['month_year_paper', 'year_month_paper', 'month_year', 'year_month'],
        default='year_month_paper',
        help="""Choose the output directory structure:
  - month_year_paper: (e.g., May-June/2024/Paper 1/...)
  - year_month_paper: (e.g., 2024/May-June/Paper 1/...)
  - month_year:       (e.g., May-June/2024/...)
  - year_month:       (e.g., 2024/May-June/...)
(default: year_month_paper)"""
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
    variants_to_check = range(1, 10)
    
    seasons = [
        ('s', 'May-June'),
        ('w', 'Oct-Nov'),
        ('m', 'March')
    ]
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    files_downloaded = 0
    
    print(f"Starting optimized brute-force download for {syllabus_name_code} from {args.start_year}-{end_year}")
    
    tasks = []
    for year in years:
        for season_char, season_folder in seasons:
            tasks.append(('gt', year, season_char, season_folder, '', ''))
            for paper in paper_numbers_to_check:
                tasks.append(('probe', year, season_char, season_folder, paper, ''))

    with tqdm(total=len(tasks), unit="checks", desc="Initializing...") as pbar:
        for task_type, year, season_char, season_folder, paper, variant in tasks:
            year_short = str(year)[-2:]

            if task_type == 'gt':
                pbar.set_description(f"Checking GT for {year} {season_folder}")
                if args.gt:
                    filename_gt = f"{args.syllabus}_{season_char}{year_short}_gt.pdf"
                    url_gt = f"{BASE_URL}{link_path}/{year}-{season_folder}/{filename_gt}"
                    
                    if args.file_structure in ['month_year_paper', 'month_year']:
                        path_parts = [OUTPUT_DIR, syllabus_name_code, season_folder, str(year)]
                    else:
                        path_parts = [OUTPUT_DIR, syllabus_name_code, str(year), season_folder]
                    
                    save_path_gt = os.path.join(*path_parts, filename_gt)
                    
                    if not os.path.exists(save_path_gt):
                        if download_if_exists(url_gt, save_path_gt):
                            files_downloaded += 1
                pbar.update(1)
                continue

            if task_type == 'probe':
                pbar.set_description(f"Probing Paper {paper} for {year} {season_folder}")
                probe_filename = f"{args.syllabus}_{season_char}{year_short}_qp_{paper}1.pdf"
                probe_url = f"{BASE_URL}{link_path}/{year}-{season_folder}/{probe_filename}"
                
                probe_exists = requests.head(probe_url, headers=HEADERS, timeout=5, allow_redirects=True).status_code == 200

                if probe_exists:
                    paper_num_folder = f"Paper {paper}"
                    if 'paper' in args.file_structure:
                        if args.file_structure == 'month_year_paper': path_parts = [OUTPUT_DIR, syllabus_name_code, season_folder, str(year), paper_num_folder]
                        else: path_parts = [OUTPUT_DIR, syllabus_name_code, str(year), season_folder, paper_num_folder]
                    else:
                        if args.file_structure == 'month_year': path_parts = [OUTPUT_DIR, syllabus_name_code, season_folder, str(year)]
                        else: path_parts = [OUTPUT_DIR, syllabus_name_code, str(year), season_folder]

                    save_path = os.path.join(*path_parts, probe_filename)
                    if not os.path.exists(save_path):
                        if download_if_exists(probe_url, save_path):
                            files_downloaded += 1
                            pbar.set_description(f"Downloaded {probe_filename}")

                    for variant_num in range(2, 10):
                        filename_qp = f"{args.syllabus}_{season_char}{year_short}_qp_{paper}{variant_num}.pdf"
                        url_qp = f"{BASE_URL}{link_path}/{year}-{season_folder}/{filename_qp}"
                        save_path_qp = os.path.join(*path_parts, filename_qp)
                        if not os.path.exists(save_path_qp):
                            if download_if_exists(url_qp, save_path_qp):
                                files_downloaded += 1
                                pbar.set_description(f"Downloaded {filename_qp}")

                    if args.ms:
                        for variant_num in range(1, 10):
                            filename_ms = f"{args.syllabus}_{season_char}{year_short}_ms_{paper}{variant_num}.pdf"
                            url_ms = f"{BASE_URL}{link_path}/{year}-{season_folder}/{filename_ms}"
                            save_path_ms = os.path.join(*path_parts, filename_ms)
                            if not os.path.exists(save_path_ms):
                                if download_if_exists(url_ms, save_path_ms):
                                    files_downloaded += 1
                                    pbar.set_description(f"Downloaded {filename_ms}")
                
                pbar.update(1)

    print("\n------------------------------------")
    print("Brute-force process completed.")
    print(f"Successfully downloaded {files_downloaded} new files.")
    print(f"All files are saved in: {os.path.abspath(OUTPUT_DIR)}")
    print("------------------------------------")

if __name__ == '__main__':
    main()
