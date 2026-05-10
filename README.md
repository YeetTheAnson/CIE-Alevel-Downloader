# CIE A-Level Past Paper Downloader

## 1. Overview

This is a command-line interface (CLI) tool designed to efficiently download Cambridge International A-Level past papers from `pastpapers.papacambridge.com`.

The script uses a high-speed, parallel brute-force approach to acquire files. It has two modes of operation:

**Standard two-phase mode (default):**
1. **Parallel Probing** — Generates a comprehensive list of all potential file URLs based on your input, then uses many parallel workers to rapidly check which files actually exist on the server, without downloading them.
2. **Parallel Downloading** — Once the list of confirmed files is ready, a separate pool of workers downloads them all simultaneously.

**Simultaneous mode (`--simul`):**
Probing and downloading happen at the same time. As soon as a probe confirms a valid PDF exists, it is immediately queued for download — no waiting for all probing to finish first. This is the **recommended mode** for large jobs as it significantly reduces total wall-clock time.

## 2. Features

- **Targeted Downloads**: Specify syllabus code, year range, specific paper numbers, and seasons.
- **Component Selection**: Download question papers (`qp`), mark schemes (`ms`), and/or grade thresholds (`gt`).
- **Simultaneous Probe + Download**: Start fetching files the moment they're confirmed, instead of waiting for the full probe to complete.
- **High-Speed Parallel Operations**: Concurrent workers for both probing and downloading, tunable to your network.
- **Flexible File Organisation**: Four directory structure options to suit your study workflow.
- **Live Dual Progress Bars**: Separate progress bars for probing and downloading run side-by-side in simultaneous mode.
- **Skips Existing Files**: Automatically avoids re-downloading files already on disk.
- **No Lookup File Needed**: Unlike older versions, no `syllabus.csv` is required — just provide the 4-digit code directly.

## 3. Prerequisites

- **Python 3.6+**
- **Required libraries**: Install with pip:
    ```bash
    pip install requests tqdm
    ```

## 4. Setup

No additional setup files are needed. Just place `cie_downloader.py` anywhere and run it from your terminal.

```
my_paper_downloader/
└── cie_downloader.py
```

Downloaded files will be saved into a `CIE_OUT` folder in your current working directory.

## 5. Usage

```bash
python cie_downloader.py -s <SYLLABUS_CODE> --start_year <YEAR> [OPTIONS]
```

### All Arguments

| Flag | Argument | Required? | Default | Description |
|---|---|---|---|---|
| `-s`, `--syllabus` | `<code>` | **Yes** | — | The 4-digit syllabus code (e.g., `9709`). |
| `--start_year` | `<year>` | **Yes** | — | First year of the download range (inclusive). |
| `--end_year` | `<year>` | No | same as `start_year` | Last year of the download range (inclusive). |
| `-p`, `--papers` | `"p1,p2,..."` | No | `1–9` | Comma-separated paper numbers to check (e.g., `"1,2,3"`). |
| `--seasons` | `"s,w,m"` | No | `s,w,m` | Which exam sessions to include. `s`=May-June, `w`=Oct-Nov, `m`=March (Feb/Mar). |
| `--ms` | | No | off | Include mark schemes. |
| `--gt` | | No | off | Include grade thresholds. |
| `-fs`, `--file_structure` | `<choice>` | No | `year_month_paper` | Output directory structure. See Section 6. |
| `-j`, `--jobs` | `<num>` | No | `4` | Parallel download workers. **Recommended: `8`**. |
| `-pj`, `--probe-jobs` | `<num>` | No | `8` | Parallel probe workers. **Recommended: `16`**. |
| `--simul` | | No | off | Simultaneous mode: download files as they are found, instead of waiting for all probing to finish. **Recommended for large jobs.** |

### Recommended Settings

For the best balance of speed and avoiding rate limiting:

```bash
-j 8 -pj 16 --simul
```

- `-pj 16` lets the prober cast a wide net quickly without hammering the server too hard.
- `-j 8` keeps downloads moving fast without triggering throttling.
- `--simul` means you start getting files immediately rather than waiting for the probe phase to fully complete.

Going significantly higher than these values (e.g., 32+ probe jobs) risks the server rate-limiting or temporarily blocking your requests.

## 6. The `--file_structure` Argument

Controls the folder hierarchy inside `CIE_OUT`. All examples below use **Physics (9702), May-June 2023** as the illustration.

---

#### `year_month_paper` (Default)

Groups by year, then session, then splits into Paper subfolders. Best for studying one year at a time.

```
CIE_OUT/
└── 9702/
    └── 2023/
        └── May-June/
            ├── 9702_s23_gt.pdf
            ├── Paper 1/
            │   ├── 9702_s23_qp_11.pdf
            │   └── 9702_s23_ms_11.pdf
            └── Paper 2/
                ├── 9702_s23_qp_21.pdf
                └── 9702_s23_ms_21.pdf
```

---

#### `month_year_paper`

Groups by session first, then year, then Paper subfolders. Best for comparing the same session across multiple years.

```
CIE_OUT/
└── 9702/
    └── May-June/
        └── 2023/
            ├── 9702_s23_gt.pdf
            ├── Paper 1/
            │   └── 9702_s23_qp_11.pdf
            └── Paper 2/
                └── 9702_s23_qp_21.pdf
```

---

#### `year_month`

Year → session, no Paper subfolders. All files for a session sit together in one flat directory.

```
CIE_OUT/
└── 9702/
    └── 2023/
        └── May-June/
            ├── 9702_s23_gt.pdf
            ├── 9702_s23_qp_11.pdf
            ├── 9702_s23_ms_11.pdf
            └── 9702_s23_qp_21.pdf
```

---

#### `month_year`

Session → year, no Paper subfolders. The flattest option — everything in one place per session/year combination.

```
CIE_OUT/
└── 9702/
    └── May-June/
        └── 2023/
            ├── 9702_s23_gt.pdf
            ├── 9702_s23_qp_11.pdf
            ├── 9702_s23_ms_11.pdf
            └── 9702_s23_qp_21.pdf
```

## 7. Examples

#### Basic single-year download
Download all available question papers for Further Mathematics (9231) for 2023 only.
```bash
python cie_downloader.py -s 9231 --start_year 2023
```

---

#### Recommended: full subject download with mark schemes
Download Physics (9702) from 2017 to 2025, with mark schemes, organised by session-first, using recommended speeds and simultaneous mode.
```bash
python cie_downloader.py -s 9702 --start_year 2017 --end_year 2025 --ms -fs month_year_paper -j 8 -pj 16 --simul
```

---

#### Comprehensive download with grade thresholds
Download Computer Science (9618), papers 1–4, with mark schemes and grade thresholds, across four years at full speed.
```bash
python cie_downloader.py -s 9618 --start_year 2020 --end_year 2023 -p "1,2,3,4" --ms --gt -j 8 -pj 16 --simul
```

---

#### May-June only, specific papers
Download only the May-June sitting of Mathematics (9709), papers 1 and 3, for the last three years.
```bash
python cie_downloader.py -s 9709 --start_year 2022 --end_year 2025 --seasons s -p "1,3" --ms -j 8 -pj 16 --simul
```

---

#### Conservative download (avoid rate limiting)
If the server starts returning errors or empty responses, dial back the workers.
```bash
python cie_downloader.py -s 9231 --start_year 2019 --end_year 2025 --ms -j 4 -pj 8
```

## 8. Output

### Standard mode

```
Syllabus: 9702  |  Years: 2017–2025  |  Seasons: s, w, m

Phase 1: Probing 3,888 potential files with 16 parallel workers...
Probing: 100%|██████████| 3888/3888 [00:22<00:00, 174.20probe/s]

Probing complete. Found 87 new files to download.

Phase 2: Downloading files with 8 parallel workers...
Downloading: 100%|██████████| 87/87 [00:11<00:00,  7.63file/s]
```

### Simultaneous mode (`--simul`)

Both bars run live at the same time — downloads begin before probing finishes:

```
Syllabus: 9702  |  Years: 2017–2025  |  Seasons: s, w, m

Simultaneous mode: probing 3,888 files with 16 probe workers
and downloading confirmed files immediately with 8 download workers...

Probing    :  67%|██████▋   | 2601/3888 [00:13<00:07, 188.4probe/s]
Downloading:  41%|████      |   36/87   [00:09<00:13,  3.9 file/s]
```

### Final summary

```
------------------------------------
Download process completed.
Found 87 new file(s) during probing.
Successfully downloaded 87 new files.
All files are saved in: /home/user/papers/CIE_OUT
------------------------------------
```

## 9. Troubleshooting

**No files are being downloaded:**
- The year range or paper numbers you specified may not exist for that syllabus. Try broadening the range.
- Run without `--seasons` to include all three sessions instead of just one.
- Check your internet connection.
- The website may be temporarily down or rate-limiting you — try reducing `-pj` and `-j`.

**Downloads are slow or stalling:**
- You may be getting rate-limited. Lower your worker counts: try `-j 4 -pj 8`.
- Remove `--simul` and let the two phases run separately to see if probing alone completes cleanly.

**`ImportError: No module named 'requests'` or `'tqdm'`:**
- Run `pip install requests tqdm` and try again.

**Files download as 0 bytes or appear corrupt:**
- The script validates every file is a real PDF (checks for the `%PDF` magic bytes) before saving it. Corrupt files are automatically deleted. If this keeps happening, the server may be returning error pages — reduce worker counts and retry.
