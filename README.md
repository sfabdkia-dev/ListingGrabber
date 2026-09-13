# Listing Grabber

A Chrome extension + local Python server that captures and parses product listings from online marketplaces. Navigate to any supported listing, press a key, and the structured data lands in a local database — no scraping scripts, no browser automation.

Currently supports **Facebook Marketplace** and **Amazon**.

---

## Quick Setup & Installation

**Requirements:** Chrome, Python 3.x (standard library only), Windows

1. Clone the repo:
   ```
   git clone https://github.com/Saeed9310/listing-grabber.git
   cd listing-grabber
   ```

2. Copy the settings template:
   ```
   copy app_settings.template.json app_settings.json
   ```

3. Load the extension in Chrome:
   - Go to `chrome://extensions`
   - Enable **Developer mode** (top-right toggle)
   - Click **Load unpacked** and select the `extension/` folder

4. Launch the Control Hub (recommended):
   ```
   double-click launch_hub.bat
   ```
   Or start the capture server headlessly:
   ```
   python server/capture_server.py
   ```

---

## How It Works

```
Browser tab
    │
    │  Ctrl+Shift+U  (or toolbar button)
    ▼
Chrome Extension  ──── POST JSON ────►  Capture Server (port 9999)
                                               │
                                               │  writes  <timestamp>_capture.json
                                               ▼
                                        Active Project Folder
                                               │
                                               │  parse_router.py  (detects website from URL)
                                               ▼
                                 ┌──────────────────────────────┐
                                 │  Pase the data using parsers │   (e.g., parse_amazon.py)
                                 └──────────────────────────────┘
                                               │
                                               ▼
                                        ads_database.jsonl (extracted database)
```

The extension grabs the tab's URL, title, and page text (`innerText`), then POSTs them to the local server. The router inspects the URL and dispatches to the correct parser. The result is appended to the project's JSONL database and shown in the Control Hub.

---

## Supported Sites

| Site                 |    Status    |
|----------------------|--------------|
| Facebook Marketplace | Supported    |
| Amazon               | Supported    |
| Others               | send request |

---

## Repo Structure

```
extension/               Chrome extension (Manifest V3)
  background.js          Service worker — intercepts keyboard shortcut, POSTs to server
  popup.html             Popup UI shown when clicking the toolbar button
  manifest.json          Extension manifest

server/
  capture_server.py      HTTP server on port 9999 — receives POSTs, writes capture files
  hub.py                 Control Hub GUI (tkinter) — start/stop server, view DB, manage projects
  process_captures.py    Batch-process all captures in a folder into the database

parsers/
  parse_router.py        Detects site from URL and dispatches to the right parser
  parse_marketplace.py   Facebook Marketplace parser
  parse_amazon.py        Amazon parser

My projects/             Runtime folder (gitignored) — one subfolder per project
app_settings.template.json  Copy to app_settings.json on a fresh clone
launch_hub.bat           Double-click to open the Control Hub
start_server.bat         Double-click to start the server headlessly
```

---

## Usage

1. **Start the server** — click **▶ Start Server** in the Control Hub (or run `start_server.bat`).
2. **Open or create a project** — use **File → New Project** or the project dropdown in the toolbar.
3. **Navigate to a listing** in Chrome (Facebook Marketplace or Amazon product page).
4. **Grab the listing**:
   - `Ctrl+Shift+U` — grab immediately, no popup
   - `Ctrl+Shift+Y` — open the extension popup first
5. The capture appears in the **Capture Log** and is auto-parsed into the database table.
6. **Edit, delete, or export** records from the Hub toolbar. Double-click a URL cell to open it in the browser.

---

## Extracted Fields

### Facebook Marketplace

| Field               | Description                                  |
|---------------------|----------------------------------------------|
| `title`             | Listing title                                |
| `price`             | Current asking price                         |
| `original_price`    | Pre-discount price (if reduced)              |
| `listed`            | "Listed N days ago in …" string              |
| `location`          | City/region extracted from the listed line   |
| `condition`         | e.g. "Used - Good"                           |
| `brand`             | Brand field (if present)                     |
| `description`       | Free-text description body                   |
| `seller_name`       | Seller display name                          |
| `seller_rating_count` | Number of ratings                          |
| `seller_joined`     | Year the seller joined Facebook              |
| `url`               | Listing URL                                  |
| `captured_at`       | Capture timestamp (ms since epoch)           |

### Amazon

| Field               | Description                                   |
|---------------------|-----------------------------------------------|
| `title`             | Product title (page title with suffix stripped)|
| `price`             | Buy-box price                                 |
| `original_price`    | "Was" price                                   |
| `discount_percent`  | Savings percentage                            |
| `deal_type`         | e.g. "Limited-time deal", "Lightning Deal"    |
| `amazon_choice`     | `true` if Amazon's Choice badge is present    |
| `bought_recently`   | "N+ bought in past month"                     |
| `rating`            | Star rating (e.g. "4.5")                      |
| `review_count`      | Number of reviews                             |
| `availability`      | "In Stock" / "Out of Stock" / etc.            |
| `ships_from`        | Fulfilment source                             |
| `sold_by`           | Seller name                                   |
| `brand`             | From the product spec table                   |
| `selected_variant`  | Colour, size, style, etc. (if shown)          |
| `asin`              | Amazon Standard Identification Number         |
| `manufacturer`      | From product details section                  |
| `best_sellers_rank` | Category rank string                          |
| `specs`             | Full key-value spec table as a JSON object    |
| `description`       | Bullet points from "About this item"          |
| `url`               | Product URL                                   |
| `captured_at`       | Capture timestamp (ms since epoch)            |

---

## Running Parsers Directly

Auto-dispatch (detects site from URL):
```
python parsers/parse_router.py "My projects/<name>/<timestamp>_capture.json"
```

Parse a specific site:
```
python parsers/parse_marketplace.py "My projects/<name>/<timestamp>_capture.json"
python parsers/parse_amazon.py      "My projects/<name>/<timestamp>_capture.json"
```

Output is printed as formatted JSON.

---

## Project Management

The Control Hub keeps all captures and parsed records organised into **projects** — each project is a folder under `My projects/`. Switch projects from the dropdown in the toolbar or via **File → Open Project**. Each project has its own `ads_database.jsonl` file. Records can be exported to CSV at any time.

---

## Adding Support for a New Site

1. Create `parsers/parse_<site>.py` with a function `parse_<site>_product(json_path) -> dict`.
2. Register it in `parsers/parse_router.py` — add a URL pattern check and call your function.

The capture format (`capturedAt`, `url`, `title`, `html`, `text`) is the same for every site.

---

## Known Limitations

- Parsers read from `innerText` and rely on Facebook/Amazon's current page layout. A site redesign may break field extraction.
- The `.bat` launchers are Windows-only. On Mac/Linux, run the Python scripts directly.
- Amazon price extraction targets the buy-box and may miss prices on pages with atypical layouts (e.g. multi-seller offers, age-restricted items).

---

## License

MIT License

Copyright (c) [2026] [Saeed AM.]

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
