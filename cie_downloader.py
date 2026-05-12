import argparse
import os
import sys
import json
import time
import queue
import threading
import concurrent.futures
import platform
import subprocess
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

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

# ─── GLOBAL STATE FOR WEB UI ───────────────────────────────────────────────────
job_state = {
    'running': False,
    'start_time': 0,
    'probe_done': 0,
    'probe_total': 0,
    'dl_done': 0,
    'dl_total': 0,
    'found': 0
}
sse_clients = []
cancel_event = threading.Event()

def broadcast(msg_dict):
    """Broadcast JSON messages to all connected Web UI clients (Server-Sent Events)"""
    for q in sse_clients:
        q.put(msg_dict)

def open_out_folder():
    """Opens the CIE_OUT directory in the native OS file explorer"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    try:
        path = os.path.abspath(OUTPUT_DIR)
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        print(f"Failed to open folder: {e}")

# ─── PROGRESS HANDLERS ────────────────────────────────────────────────────────
class CLIProgressHandler:
    def init_probe(self, total, kwargs_dict):
        self.probe_pbar = tqdm(total=total, unit="probe", desc="Probing    ", position=0)
        self.dl_pbar = tqdm(total=0, unit="file", desc="Downloading", position=1)
    def update_probe(self): self.probe_pbar.update(1)
    def found_dl(self):
        self.dl_pbar.total = (self.dl_pbar.total or 0) + 1
        self.dl_pbar.refresh()
    def update_dl(self): self.dl_pbar.update(1)
    def log(self, msg, level='info'):
        if level in ('error', 'warn'): self.dl_pbar.write(f"[{level.upper()}] {msg}")
    def done(self, cancelled, dl, found, out_dir):
        self.probe_pbar.close()
        self.dl_pbar.close()

class UIProgressHandler:
    def init_probe(self, total, kwargs_dict):
        job_state['start_time'] = time.time()
        job_state['probe_total'] = total
        job_state['probe_done'] = 0
        job_state['dl_total'] = 0
        job_state['dl_done'] = 0
        job_state['found'] = 0
        broadcast({'type': 'start', 'probe_total': total, **kwargs_dict})
    def update_probe(self):
        job_state['probe_done'] += 1
        broadcast({'type': 'probe', 'done': job_state['probe_done'], 'total': job_state['probe_total']})
    def found_dl(self):
        job_state['found'] += 1
        job_state['dl_total'] += 1
        # Pass both 'done' and 'total' so the frontend doesn't reset its progress to 0
        broadcast({'type': 'dl_found', 'done': job_state['dl_done'], 'total': job_state['dl_total'], 'found': job_state['found']})
    def update_dl(self):
        job_state['dl_done'] += 1
        broadcast({'type': 'dl_done', 'done': job_state['dl_done'], 'total': job_state['dl_total']})
    def log(self, msg, level='info'):
        broadcast({'type': 'log', 'msg': msg, 'level': level})
    def done(self, cancelled, dl, found, out_dir):
        job_state['running'] = False
        if cancelled:
            broadcast({'type': 'cancelled', 'msg': 'Job was aborted.', 'output_dir': out_dir})
        else:
            broadcast({'type': 'done', 'downloaded': dl, 'found': found, 'output_dir': out_dir})

# ─── CORE WORKERS ─────────────────────────────────────────────────────────────
def probe_worker(url, save_path, headers):
    if cancel_event.is_set(): return None
    if os.path.exists(save_path): return None

    try:
        with requests.get(url, headers=headers, stream=True, timeout=10, allow_redirects=True) as response:
            if response.status_code != 200: return None
            if 'text/html' in response.headers.get('Content-Type', '').lower(): return None
            try:
                first_chunk = next(response.iter_content(chunk_size=4))
                if first_chunk.startswith(b'%PDF'):
                    return (url, save_path)
            except StopIteration: pass
    except: pass
    return None

def download_worker(url, save_path, headers):
    if cancel_event.is_set(): return False
    try:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with requests.get(url, stream=True, headers=headers, timeout=60) as response:
            response.raise_for_status()
            if 'text/html' in response.headers.get('Content-Type', '').lower(): return False

            with open(save_path, 'wb') as f:
                iterator = response.iter_content(chunk_size=4)
                try:
                    first_chunk = next(iterator)
                    if not first_chunk.startswith(b'%PDF'): return False
                    f.write(first_chunk)
                except StopIteration: return False

                for data in response.iter_content(chunk_size=8192):
                    if cancel_event.is_set():
                        f.close()
                        os.remove(save_path)
                        return False
                    f.write(data)
        return True
    except:
        if os.path.exists(save_path):
            try: os.remove(save_path)
            except: pass
        return False

# ─── JOB EXECUTORS ────────────────────────────────────────────────────────────
def build_probe_list(syllabus, years, seasons, paper_numbers, include_ms, include_gt, file_structure):
    probe_list = []
    season_folder = {'s': 'May-June', 'w': 'Oct-Nov', 'm': 'March'}
    for year in years:
        year_short = str(year)[-2:]
        for season_char in seasons:
            folder = season_folder[season_char]
            if file_structure in ('month_year_paper', 'month_year'):
                base_path_parts = [OUTPUT_DIR, syllabus, folder, str(year)]
            else:
                base_path_parts = [OUTPUT_DIR, syllabus, str(year), folder]

            if include_gt:
                filename = f"{syllabus}_{season_char}{year_short}_gt.pdf"
                probe_list.append((f"{DOWNLOAD_BASE}/{filename}", os.path.join(*base_path_parts, filename)))

            for paper in paper_numbers:
                path_parts = list(base_path_parts)
                if 'paper' in file_structure:
                    path_parts.append(f"Paper {paper}")

                for variant_num in range(1, 10):
                    qp_filename = f"{syllabus}_{season_char}{year_short}_qp_{paper}{variant_num}.pdf"
                    probe_list.append((f"{DOWNLOAD_BASE}/{qp_filename}", os.path.join(*path_parts, qp_filename)))

                    if include_ms:
                        ms_filename = f"{syllabus}_{season_char}{year_short}_ms_{paper}{variant_num}.pdf"
                        probe_list.append((f"{DOWNLOAD_BASE}/{ms_filename}", os.path.join(*path_parts, ms_filename)))
    return probe_list

def run_job(cfg, handler):
    years = range(int(cfg['start_year']), int(cfg.get('end_year', cfg['start_year'])) + 1)
    probe_list = build_probe_list(
        syllabus=cfg['syllabus'], years=years, seasons=cfg['seasons'],
        paper_numbers=cfg['papers'], include_ms=cfg['ms'], include_gt=cfg['gt'],
        file_structure=cfg['file_structure']
    )
    
    handler.init_probe(len(probe_list), cfg)
    files_downloaded = 0
    files_found = 0

    if cfg['simul']:
        dl_queue = queue.Queue()
        dl_lock = threading.Lock()
        
        def download_consumer():
            nonlocal files_downloaded
            with concurrent.futures.ThreadPoolExecutor(max_workers=cfg['dl_jobs']) as dl_executor:
                pending = {}
                while True:
                    if cancel_event.is_set(): break
                    try:
                        item = dl_queue.get(timeout=0.2)
                        if item is None: break  # Done signal
                        url, save_path = item
                        fut = dl_executor.submit(download_worker, url, save_path, HEADERS)
                        pending[fut] = url
                    except queue.Empty: pass
                    
                    done_keys = [f for f in list(pending) if f.done()]
                    for f in done_keys:
                        u = pending.pop(f)
                        try:
                            if f.result():
                                with dl_lock: files_downloaded += 1
                        except Exception as exc: handler.log(f'Error: {os.path.basename(u)}: {exc}', 'error')
                        finally: handler.update_dl()

                # Clean up remaining
                for f in concurrent.futures.as_completed(pending):
                    if cancel_event.is_set(): break
                    try:
                        if f.result():
                            with dl_lock: files_downloaded += 1
                    except Exception as exc: handler.log(f'Error: {exc}', 'error')
                    finally: handler.update_dl()

        dl_thread = threading.Thread(target=download_consumer)
        dl_thread.start()

        with concurrent.futures.ThreadPoolExecutor(max_workers=cfg['probe_jobs']) as probe_executor:
            future_to_probe = {probe_executor.submit(probe_worker, url, path, HEADERS): (url, path) for url, path in probe_list}
            for future in concurrent.futures.as_completed(future_to_probe):
                if cancel_event.is_set(): break
                result = future.result()
                if result:
                    files_found += 1
                    handler.found_dl()
                    dl_queue.put(result)
                    handler.log(f"Found: {os.path.basename(result[1])}", 'found')
                handler.update_probe()

        dl_queue.put(None)
        dl_thread.join()

    else:
        # Sequential
        download_queue = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=cfg['probe_jobs']) as executor:
            future_to_probe = {executor.submit(probe_worker, url, path, HEADERS): (url, path) for url, path in probe_list}
            for future in concurrent.futures.as_completed(future_to_probe):
                if cancel_event.is_set(): break
                result = future.result()
                if result:
                    download_queue.append(result)
                    files_found += 1
                    handler.found_dl()
                    handler.log(f"Found: {os.path.basename(result[1])}", 'found')
                handler.update_probe()

        if not cancel_event.is_set():
            with concurrent.futures.ThreadPoolExecutor(max_workers=cfg['dl_jobs']) as executor:
                future_to_url = {executor.submit(download_worker, url, path, HEADERS): url for url, path in download_queue}
                for future in concurrent.futures.as_completed(future_to_url):
                    if cancel_event.is_set(): break
                    try:
                        if future.result(): files_downloaded += 1
                    except Exception as exc: handler.log(f'Error: {os.path.basename(future_to_url[future])}: {exc}', 'error')
                    finally: handler.update_dl()

    handler.done(cancel_event.is_set(), files_downloaded, files_found, os.path.abspath(OUTPUT_DIR))

# ─── WEB SERVER SETUP ─────────────────────────────────────────────────────────
class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class WebUIHandler(BaseHTTPRequestHandler):
    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            with open(os.path.join(os.path.dirname(__file__), 'index.html'), 'rb') as f:
                self.wfile.write(f.read())
        
        elif self.path == '/status':
            state_copy = dict(job_state)
            if state_copy.get('running') and 'start_time' in state_copy:
                state_copy['elapsed'] = time.time() - state_copy['start_time']
            else:
                state_copy['elapsed'] = 0
            self.send_json(state_copy)
            
        elif self.path == '/events':
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.end_headers()
            
            q = queue.Queue()
            sse_clients.append(q)
            try:
                while True:
                    try:
                        msg = q.get(timeout=10)
                        self.wfile.write(f"data: {json.dumps(msg)}\n\n".encode('utf-8'))
                        self.wfile.flush()
                    except queue.Empty:
                        self.wfile.write(b": heartbeat\n\n")
                        self.wfile.flush()
            except: pass
            finally:
                if q in sse_clients: sse_clients.remove(q)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == '/run':
            length = int(self.headers.get('Content-Length', 0))
            data = json.loads(self.rfile.read(length))
            
            if job_state['running']:
                self.send_json({'error': 'Job already running'}, 400)
                return
            
            job_state['running'] = True
            cancel_event.clear()
            threading.Thread(target=run_job, args=(data, UIProgressHandler()), daemon=True).start()
            self.send_json({'status': 'started'})

        elif self.path == '/cancel':
            cancel_event.set()
            self.send_json({'status': 'cancelling'})

        elif self.path == '/open_folder':
            open_out_folder()
            self.send_json({'status': 'ok'})
            
        else:
            self.send_error(404)

    def log_message(self, format, *args): pass  # Suppress default HTTP logs

# ─── MAIN ENTRY POINT ─────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Download Cambridge A-Level past papers from pastpapers.papacambridge.com.",
        formatter_class=argparse.RawTextHelpFormatter
    )

    parser.add_argument('--ui', action='store_true', help='Launch the graphical Web UI in browser.')
    parser.add_argument('-s', '--syllabus', type=str, help='The 4-digit syllabus code (e.g., 9231).')
    parser.add_argument('--start_year', type=int, help='The starting year for the download range.')
    parser.add_argument('--end_year', type=int, help='The ending year for the download range.')
    parser.add_argument('-p', '--papers', type=str, help='Comma-separated paper numbers to check (e.g., "1,3"). Defaults to 1-9.')
    parser.add_argument('--seasons', type=str, default='s,w,m', help='Comma-separated season codes: s, w, m (default: s,w,m).')
    parser.add_argument('--ms', action='store_true', help='Include mark schemes in the download.')
    parser.add_argument('--gt', action='store_true', help='Include grade thresholds in the download.')
    parser.add_argument('-fs', '--file_structure', type=str, choices=['month_year_paper', 'year_month_paper', 'month_year', 'year_month'], default='year_month_paper', help="Output directory structure")
    parser.add_argument('-j', '--jobs', type=int, default=4, help='Parallel downloads at once (default: 4).')
    parser.add_argument('-pj', '--probe-jobs', type=int, default=8, help='Parallel probes at once (default: 8).')
    parser.add_argument('--simul', action='store_true', help='Simultaneous mode: download immediately as probes succeed.')

    args = parser.parse_args()

    if args.ui:
        print("Starting Web UI mode...")
        server = ThreadedHTTPServer(('127.0.0.1', 5050), WebUIHandler)
        url = "http://127.0.0.1:5050/"
        print(f"Listening on {url}")
        
        # Give the server a moment to boot before opening browser
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
        
        try: server.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")
            server.server_close()
            sys.exit(0)

    else:
        if not args.syllabus or not args.start_year:
            parser.error("CLI mode requires at least --syllabus and --start_year. Run with --ui for graphical mode.")
            
        seasons = [s.strip() for s in args.seasons.split(',')]
        if any(s not in ('s', 'w', 'm') for s in seasons):
            print("Error: Invalid season code(s). Use s, w, or m.")
            sys.exit(1)

        cfg = {
            'syllabus': args.syllabus,
            'start_year': args.start_year,
            'end_year': args.end_year if args.end_year else args.start_year,
            'seasons': seasons,
            'papers': args.papers.split(',') if args.papers else [str(i) for i in range(1, 10)],
            'ms': args.ms,
            'gt': args.gt,
            'file_structure': args.file_structure,
            'simul': args.simul,
            'probe_jobs': args.probe_jobs,
            'dl_jobs': args.jobs
        }

        print(f"Syllabus: {cfg['syllabus']}  |  Years: {cfg['start_year']}–{cfg['end_year']}  |  Seasons: {', '.join(cfg['seasons'])}")
        run_job(cfg, CLIProgressHandler())
        print("\n------------------------------------")
        print("Download process completed.")
        print(f"All files are saved in: {os.path.abspath(OUTPUT_DIR)}")
        print("------------------------------------")

if __name__ == '__main__':
    main()
