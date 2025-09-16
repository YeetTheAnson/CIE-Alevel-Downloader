# CIE A-Level Past Paper Downloader

## 1. Overview

This is a command-line interface (CLI) tool designed to efficiently download Cambridge International A-Level past papers from the website `pastpapers.co`.

Instead of blindly checking for every possible paper, variant, and file type, this script uses a "smart probe" brute-force method. It first checks for the existence of a base paper (e.g., Paper 1, Variant 1). If that paper exists for a given session, it then proceeds to download it and search for other variants and associated mark schemes for that specific paper, significantly reducing unnecessary network requests and speeding up the download process.

## 2. Features

-   **Targeted Downloads**: Specify syllabus code, year range, and specific paper numbers.
-   **Component Selection**: Choose to download question papers (`qp`), mark schemes (`ms`), and grade thresholds (`gt`).
-   **Smart Probing**: Minimizes failed requests by only checking for variants and mark schemes if a base paper is found.
-   **Flexible File Organization**: Customize the output directory structure to suit your preferences.
-   **Progress Tracking**: A clear progress bar shows the status of the download checks.
-   **Skips Existing Files**: Automatically avoids re-downloading files that are already present.

## 3. Prerequisites

-   **Python 3.6+**: The script is written in Python 3.
-   **Required Libraries**: You will need `requests` and `tqdm`. You can install them using pip:
    ```bash
    pip install requests tqdm
    ```

## 4. Setup and File Structure (Crucial!)

Before running the script, you must set up your files in a specific way. The script requires a helper file named **`syllabus.csv`** to be in the **same directory** as the Python script itself.

Your project folder must look like this:

```
my_paper_downloader/
├── main.py          # The Python script
└── syllabus.csv           # The mandatory syllabus lookup file
```

### The `syllabus.csv` File

This file acts as a map, telling the script which URL path corresponds to a given syllabus code. You must create this file yourself.

**Format:**
The CSV file must contain two columns with a header row: `code,path`.
-   `code`: The 4-digit syllabus code (e.g., `9709`).
-   `path`: The text that appears in the URL for that syllabus on `pastpapers.co`.

**How to find the `path` value:**
1.  Go to the A-Level section: `https://pastpapers.co/cie/A-Level/`
2.  Find and click on your desired subject (e.g., "Mathematics (9709)").
3.  Look at the URL in your browser's address bar. It will be something like `https://pastpapers.co/cie/A-Level/Mathematics-9709/`.
4.  The part after `/A-Level/` and before the final `/` is the `path`. In this case, it is `Mathematics-9709`.

**Example `syllabus.csv` content:**

```csv
code,path
9709,Mathematics-9709
9702,Physics-9702
9701,Chemistry-9701
9231,Further-Mathematics-9231
9618,Computer-Science-9618
```

> **Important**: The script will fail if `syllabus.csv` is not found or if the syllabus code you provide is not listed within this file.

## 5. Usage

Run the script from your terminal within the directory where `main.py` and `syllabus.csv` are located.

The basic command structure is:
```bash
python main.py -s <SYLLABUS_CODE> --start_year <YEAR> [OPTIONS]
```

### Command-Line Arguments

| Flag                  | Argument            | Required? | Description                                                                                                                              |
| --------------------- | ------------------- | --------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `-s`, `--syllabus`      | `<code>`            | **Yes**   | The 4-digit syllabus code (e.g., `9709`). This code **must** exist in your `syllabus.csv` file.                                          |
| `--start_year`        | `<year>`            | **Yes**   | The first year in the download range (inclusive). Example: `2022`.                                                                       |
| `--end_year`          | `<year>`            | No        | The last year in the download range (inclusive). If omitted, it defaults to the `start_year` (i.e., only one year is downloaded).          |
| `-p`, `--papers`        | `"p1,p2,..."`       | No        | A comma-separated string of paper numbers to download (e.g., `"1,3"`). If omitted, the script will check for papers 1 through 9.           |
| `--ms`                |                     | No        | A flag to include mark schemes (`ms`) in the download. If omitted, only question papers are downloaded.                                |
| `--gt`                |                     | No        | A flag to include grade thresholds (`gt`) in the download.                                                                               |
| `-fs`, `--file_structure` | `<choice>`          | No        | Defines the output directory structure. See the detailed section below. Default is `year_month_paper`.                                 |


## 6. The `--file_structure` Argument In-Depth

The `-fs` or `--file_structure` argument is a powerful feature that lets you control the exact folder hierarchy for your downloaded files. All files are saved within a main `CIE_OUT` directory, but the internal structure can be tailored to your study habits.

Below are detailed explanations of the four available choices, using a concrete example: downloading **Mathematics (9709)** papers from the **May-June 2023** session.

---
#### 1. `year_month_paper` (Default)

This structure prioritizes the **year**, then the exam session, and finally groups files into specific 'Paper' folders. This is excellent for focusing on a single year's worth of material at a time.

**Logic:** Year -> Session -> Paper -> Files

**Example Command:**
```bash
python main.py -s 9709 --start_year 2023 --ms --gt -fs year_month_paper
```

**Resulting File Tree:**
```
CIE_OUT/
└── Mathematics-9709/
    └── 2023/
        └── May-June/
            ├── 9709_s23_gt.pdf  (Grade Threshold lives here)
            ├── Paper 1/
            │   ├── 9709_s23_qp_11.pdf
            │   ├── 9709_s23_qp_12.pdf
            │   └── 9709_s23_ms_12.pdf
            └── Paper 3/
                ├── 9709_s23_qp_31.pdf
                └── 9709_s23_ms_31.pdf
```

---
#### 2. `month_year_paper`

This structure prioritizes the exam **session** (e.g., 'May-June') first, then the year. It's useful for comparing the same paper from the same session across different years.

**Logic:** Session -> Year -> Paper -> Files

**Example Command:**
```bash
python main.py -s 9709 --start_year 2023 --ms --gt -fs month_year_paper
```

**Resulting File Tree:**
```
CIE_OUT/
└── Mathematics-9709/
    └── May-June/
        └── 2023/
            ├── 9709_s23_gt.pdf
            ├── Paper 1/
            │   ├── 9709_s23_qp_11.pdf
            │   ├── 9709_s23_qp_12.pdf
            │   └── 9709_s23_ms_12.pdf
            └── Paper 3/
                ├── 9709_s23_qp_31.pdf
                └── 9709_s23_ms_31.pdf
```

---
#### 3. `year_month`

Similar to the default, this sorts by year then session, but it **omits the separate 'Paper' folders**. All files for a session are placed directly together, resulting in a flatter structure.

**Logic:** Year -> Session -> Files

**Example Command:**
```bash
python main.py -s 9709 --start_year 2023 --ms --gt -fs year_month
```

**Resulting File Tree:**
```
CIE_OUT/
└── Mathematics-9709/
    └── 2023/
        └── May-June/
            ├── 9709_s23_gt.pdf
            ├── 9709_s23_qp_11.pdf
            ├── 9709_s23_qp_12.pdf
            ├── 9709_s23_ms_12.pdf
            ├── 9709_s23_qp_31.pdf
            └── 9709_s23_ms_31.pdf
```
---
#### 4. `month_year`

This sorts by session then year, and also **omits the separate 'Paper' folders**. It's the flattest structure, useful for browsing all files from a session and year in one place.

**Logic:** Session -> Year -> Files

**Example Command:**
```bash
python main.py -s 9709 --start_year 2023 --ms --gt -fs month_year
```

**Resulting File Tree:**
```
CIE_OUT/
└── Mathematics-9709/
    └── May-June/
        └── 2023/
            ├── 9709_s23_gt.pdf
            ├── 9709_s23_qp_11.pdf
            ├── 9709_s23_qp_12.pdf
            ├── 9709_s23_ms_12.pdf
            ├── 9709_s23_qp_31.pdf
            └── 9709_s23_ms_31.pdf
```

## 7. Examples

#### **Example 1: Basic Download**
Download all available papers for Further Mathematics (9231) for the year 2023.
```bash
python main.py -s 9231 --start_year 2023
```

#### **Example 2: Comprehensive Download over a Range**
Download Computer Science (9618) papers 1, 2, 3, and 4, including their mark schemes and grade thresholds, for the years 2020 through 2023.
```bash
python main.py -s 9618 --start_year 2020 --end_year 2023 -p "1,2,3,4" --ms --gt
```

#### **Example 3: Custom File Structure**
Download Physics (9702) papers for 2022, but organize the folders by session first, then by year.
```bash
python main.py -s 9702 --start_year 2022 -fs month_year_paper
```
This will create a directory structure like: `CIE_OUT/Physics-9702/May-June/2022/Paper 2/...`

## 8. Output

When you run the script, you will see a progress bar that updates as it checks each combination of year, session, and paper. The description on the progress bar will tell you what it's currently doing.

```
Initializing...: 100%|██████████| 36/36 [00:00<00:00, 123.45checks/s]
Downloaded 9709_s23_ms_31.pdf: 100%|██████████| 36/36 [00:15<00:00, 2.33checks/s]
```

Once completed, a summary message will be displayed:

```
------------------------------------
Brute-force process completed.
Successfully downloaded 42 new files.
All files are saved in: /path/to/my_paper_downloader/CIE_OUT
------------------------------------
```

## 9. Troubleshooting

-   **Error: "Syllabus code 'xxxx' not found in 'syllabus.csv'"**:
    -   Ensure `syllabus.csv` is in the same directory as `main.py`.
    -   Open `syllabus.csv` and verify that the code you are using is listed in the first column.
    -   Check for typos or extra spaces in the CSV file.

-   **No files are being downloaded**:
    -   The years or papers you specified may not be available on the website. Try a wider year range.
    -   Check your internet connection.
    -   The website `pastpapers.co` might be down or have changed its URL structure.

-   **`ImportError: No module named 'requests'` or `'tqdm'`**:
    -   You have not installed the required libraries. Run `pip install requests tqdm`.
