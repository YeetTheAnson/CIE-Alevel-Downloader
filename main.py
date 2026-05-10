import argparse
import os
import sys
import concurrent.futures
import queue
import threading
import requests
from tqdm import tqdm

DOWNLOAD_BASE = "https://pastpapers.papacambridge.com/download_file.php?files=https://pastpapers.papacambridge.com/directories/CAIE/CAIE-pastpapers/upload"
OUTPUT_DIR = "CIE_OUT"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://pastpapers.papacambridge.com/',
}


def probe_worker(url, save_path, headers):
    """
    Checks if a file exists and is a valid PDF by peeking at the first 4 bytes.
    """
    if os.path.exists(save_path):
        return None

    try:
        with requests.get(url, headers=headers, stream=True, timeout=10, allow_redirects=True) as response:

            if response.status_code != 200:
                return None

            content_type = response.headers.get('Content-Type', '').lower()
            if 'text/html' in content_type:
                return None

            try:
                first_chunk = next(response.iter_content(chunk_size=4))
                if first_chunk.startswith(b'%PDF'):
                    return (url, save_path)
            except StopIteration:
                pass

    except requests.exceptions.RequestException:
        pass
    except Exception:
        pass

    return None


def download_worker(url, save_path, headers):
    try:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        with requests.get(url, stream=True, headers=headers, timeout=60) as response:
            response.raise_for_status()

            content_type = response.headers.get('Content-Type', '').lower()
            if 'text/html' in content_type:
                return False

            with open(save_path, 'wb') as f:
                iterator = response.iter_content(chunk_size=4)
                try:
                    first_chunk = next(iterator)
                    if not first_chunk.startswith(b'%PDF'):
                        return False
                    f.write(first_chunk)
                except StopIteration:
                    return False

                for data in response.iter_content(chunk_size=8192):
                    f.write(data)

        return True
    except requests.exceptions.RequestException:
        return False
    except Exception:
        if os.path.exists(save_path):
            try:
                os.remove(save_path)
            except:
                pass
        return False


# Sentinel object used to signal the download thread that probing is complete
_PROBE_DONE = object()


def run_simultaneous(probe_list, probe_jobs, download_jobs):
    """
    Simultaneously probe and download: as soon as a probe confirms a valid PDF,
    it's immediately queued for download without waiting for all probes to finish.
    Returns the number of files successfully downloaded.
    """
    dl_queue = queue.Queue()

    probe_counter = {"done": 0, "found": 0}
    counter_lock = threading.Lock()

    probe_pbar = tqdm(total=len(probe_list), unit="probe", desc="Probing    ", position=0)
    dl_pbar    = tqdm(total=0,               unit="file",  desc="Downloading", position=1)

    files_downloaded = 0
    dl_lock = threading.Lock()

    def download_consumer():
        nonlocal files_downloaded
        with concurrent.futures.ThreadPoolExecutor(max_workers=download_jobs) as dl_executor:
            pending_futures = {}

            while True:
                try:
                    item = dl_queue.get(timeout=0.2)
                except queue.Empty:
                    done_keys = [f for f in list(pending_futures) if f.done()]
                    for f in done_keys:
                        url = pending_futures.pop(f)
                        try:
                            if f.result():
                                with dl_lock:
                                    files_downloaded += 1
                        except Exception as exc:
                            dl_pbar.write(f'Error: {os.path.basename(url)}: {exc}')
                        finally:
                            dl_pbar.update(1)
                    continue

                if item is _PROBE_DONE:
                    for f, url in concurrent.futures.as_completed(
                            {fut: u for fut, u in pending_futures.items()}
                    ) if pending_futures else []:
                        try:
                            if f.result():
                                with dl_lock:
                                    files_downloaded += 1
                        except Exception as exc:
                            dl_pbar.write(f'Error: {os.path.basename(url)}: {exc}')
                        finally:
                            dl_pbar.update(1)
                    break

                url, save_path = item
                fut = dl_executor.submit(download_worker, url, save_path, HEADERS)
                pending_futures[fut] = url

                done_keys = [f for f in list(pending_futures) if f.done()]
                for f in done_keys:
                    u = pending_futures.pop(f)
                    try:
                        if f.result():
                            with dl_lock:
                                files_downloaded += 1
                    except Exception as exc:
                        dl_pbar.write(f'Error: {os.path.basename(u)}: {exc}')
                    finally:
                        dl_pbar.update(1)

    dl_thread = threading.Thread(target=download_consumer, daemon=True)
    dl_thread.start()

    with concurrent.futures.ThreadPoolExecutor(max_workers=probe_jobs) as probe_executor:
        future_to_probe = {
            probe_executor.submit(probe_worker, url, path, HEADERS): (url, path)
            for url, path in probe_list
        }

        for future in concurrent.futures.as_completed(future_to_probe):
            result = future.result()
            if result:
                with counter_lock:
                    probe_counter["found"] += 1
                dl_pbar.total = (dl_pbar.total or 0) + 1
                dl_pbar.refresh()
                dl_queue.put(result)
            probe_pbar.update(1)

    dl_queue.put(_PROBE_DONE)
    dl_thread.join()

    probe_pbar.close()
    dl_pbar.close()

    return files_downloaded, probe_counter["found"]


def build_probe_list(syllabus, years, seasons, paper_numbers, include_ms, include_gt, file_structure):
    """
    Build the list of (url, save_path) pairs to probe.

    URL structure (same for ALL years — the download endpoint only needs the
    bare filename, so there are no year-based naming exceptions here):

        <DOWNLOAD_BASE>/<syllabus>_<season_char><year_short>_<type>_<paper><variant>.pdf

    Season folder names used for the local directory tree:
        s -> May-June
        w -> Oct-Nov
        m -> March
    """
    probe_list = []

    season_folder = {
        's': 'May-June',
        'w': 'Oct-Nov',
        'm': 'March',
    }

    for year in years:
        year_short = str(year)[-2:]

        for season_char in seasons:
            folder = season_folder[season_char]

            if file_structure in ('month_year_paper', 'month_year'):
                base_path_parts = [OUTPUT_DIR, syllabus, folder, str(year)]
            else:
                base_path_parts = [OUTPUT_DIR, syllabus, str(year), folder]

            # Grade threshold (one per session, no variant)
            if include_gt:
                filename = f"{syllabus}_{season_char}{year_short}_gt.pdf"
                url = f"{DOWNLOAD_BASE}/{filename}"
                save_path = os.path.join(*base_path_parts, filename)
                probe_list.append((url, save_path))

            for paper in paper_numbers:
                path_parts = list(base_path_parts)
                if 'paper' in file_structure:
                    path_parts.append(f"Paper {paper}")

                for variant_num in range(1, 10):
                    # Question paper
                    qp_filename = f"{syllabus}_{season_char}{year_short}_qp_{paper}{variant_num}.pdf"
                    qp_url = f"{DOWNLOAD_BASE}/{qp_filename}"
                    qp_save_path = os.path.join(*path_parts, qp_filename)
                    probe_list.append((qp_url, qp_save_path))

                    # Mark scheme
                    if include_ms:
                        ms_filename = f"{syllabus}_{season_char}{year_short}_ms_{paper}{variant_num}.pdf"
                        ms_url = f"{DOWNLOAD_BASE}/{ms_filename}"
                        ms_save_path = os.path.join(*path_parts, ms_filename)
                        probe_list.append((ms_url, ms_save_path))

    return probe_list


def main():
    parser = argparse.ArgumentParser(
        description="Download Cambridge A-Level past papers from pastpapers.papacambridge.com.",
        formatter_class=argparse.RawTextHelpFormatter
    )

    parser.add_argument('-s', '--syllabus', type=str, required=True,
                        help='The 4-digit syllabus code (e.g., 9231).')
    parser.add_argument('--start_year', type=int, required=True,
                        help='The starting year for the download range (inclusive).')
    parser.add_argument('--end_year', type=int,
                        help='The ending year for the download range (inclusive). Defaults to start_year.')
    parser.add_argument('-p', '--papers', type=str,
                        help='Comma-separated list of paper numbers to check (e.g., "1,3"). Defaults to 1-9.')
    parser.add_argument('--seasons', type=str, default='s,w,m',
                        help='Comma-separated season codes to include: s=May-June, w=Oct-Nov, m=March (default: s,w,m).')
    parser.add_argument('--ms', action='store_true',
                        help='Include mark schemes in the download.')
    parser.add_argument('--gt', action='store_true',
                        help='Include grade thresholds in the download.')
    parser.add_argument(
        '-fs', '--file_structure', type=str,
        choices=['month_year_paper', 'year_month_paper', 'month_year', 'year_month'],
        default='year_month_paper',
        help="Choose the output directory structure (default: year_month_paper)"
    )
    parser.add_argument('-j', '--jobs', type=int, default=4,
                        help='Number of parallel downloads to run at once (default: 4).')
    parser.add_argument('-pj', '--probe-jobs', type=int, default=8,
                        help='Number of parallel probes to run at once (default: 8).')
    parser.add_argument(
        '--simul', action='store_true',
        help=(
            'Simultaneous mode: start downloading files immediately as probes succeed,\n'
            'rather than waiting for all probing to finish first.\n'
            'Reduces total wall-clock time when there are many valid files to fetch.'
        )
    )

    args = parser.parse_args()

    end_year = args.end_year if args.end_year else args.start_year
    years = range(args.start_year, end_year + 1)
    paper_numbers = args.papers.split(',') if args.papers else [str(i) for i in range(1, 10)]
    seasons = [s.strip() for s in args.seasons.split(',')]

    invalid_seasons = [s for s in seasons if s not in ('s', 'w', 'm')]
    if invalid_seasons:
        print(f"Error: Invalid season code(s): {', '.join(invalid_seasons)}. Use s, w, or m.")
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    probe_list = build_probe_list(
        syllabus=args.syllabus,
        years=years,
        seasons=seasons,
        paper_numbers=paper_numbers,
        include_ms=args.ms,
        include_gt=args.gt,
        file_structure=args.file_structure,
    )

    print(f"Syllabus: {args.syllabus}  |  Years: {args.start_year}–{end_year}  |  Seasons: {', '.join(seasons)}")

    if args.simul:
        print(f"\nSimultaneous mode: probing {len(probe_list):,} files with {args.probe_jobs} probe workers")
        print(f"and downloading confirmed files immediately with {args.jobs} download workers...\n")
        files_downloaded, files_found = run_simultaneous(probe_list, args.probe_jobs, args.jobs)
        found_msg = f"Found {files_found} new file(s) during probing."
    else:
        print(f"\nPhase 1: Probing {len(probe_list):,} potential files with {args.probe_jobs} parallel workers...")

        download_queue = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.probe_jobs) as executor:
            future_to_probe = {
                executor.submit(probe_worker, url, path, HEADERS): (url, path)
                for url, path in probe_list
            }

            with tqdm(total=len(probe_list), unit="probe", desc="Probing") as pbar:
                for future in concurrent.futures.as_completed(future_to_probe):
                    result = future.result()
                    if result:
                        download_queue.append(result)
                    pbar.update(1)

        print(f"\nProbing complete. Found {len(download_queue)} new files to download.")
        found_msg = f"Found {len(download_queue)} new file(s) to download."

        files_downloaded = 0
        if not download_queue:
            print("Everything is up to date.")
        else:
            print(f"\nPhase 2: Downloading files with {args.jobs} parallel workers...")
            with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as executor:
                future_to_url = {
                    executor.submit(download_worker, url, path, HEADERS): url
                    for url, path in download_queue
                }

                with tqdm(total=len(download_queue), unit="file", desc="Downloading") as pbar:
                    for future in concurrent.futures.as_completed(future_to_url):
                        try:
                            if future.result():
                                files_downloaded += 1
                        except Exception as exc:
                            pbar.write(f'Error: Exception for {os.path.basename(future_to_url[future])}: {exc}')
                        finally:
                            pbar.update(1)

    print("\n------------------------------------")
    print("Download process completed.")
    print(found_msg)
    print(f"Successfully downloaded {files_downloaded} new files.")
    print(f"All files are saved in: {os.path.abspath(OUTPUT_DIR)}")
    print("------------------------------------")


if __name__ == '__main__':
    main()
