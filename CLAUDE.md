# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

Two-part tool for scraping and parsing Facebook Marketplace ads:

1. **Chrome extension** (`extension/`) — a Manifest V3 extension. Clicking the toolbar button (or pressing `Ctrl+Shift+Y`) grabs the current tab's URL, title, HTML, and first 20 000 chars of `innerText`, then POSTs them as JSON to `http://127.0.0.1:9999`.

2. **Local server + parser** (Python) — `server/capture_server.py` receives POSTs from the extension and writes timestamped `<ms>_capture.json` files into the active project folder. `parsers/parse_marketplace.py` (and `parsers/parse_amazon.py`) read those files and extract structured fields from the plain-text `text` field. `parsers/parse_router.py` dispatches to the right parser by URL.

## Repo layout

```
server/          entry-point scripts (capture_server, hub, process_captures)
parsers/         parser modules (marketplace, amazon, router)
extension/       Chrome extension (Manifest V3)
projects/        gitignored — project folders created at runtime
```

Runtime state files (`active_project.json`, `app_settings.json`) are gitignored; copy `app_settings.template.json` → `app_settings.json` on a fresh clone if needed.

## Running the pieces

No dependencies to install — all Python files use the standard library only.

**Recommended:** double-click `launch_hub.bat` — opens the Control Hub, where you can start/stop the server, see live captures, switch projects, and view the ad database all in one window.

Or start the capture server headlessly:
```
python server/capture_server.py
```

Or double-click `start_server.bat`.

Parse a captured file directly:
```
python parsers/parse_marketplace.py projects/<name>/<timestamp>_capture.json
```

## Capture file format

Each `.json` file has five top-level keys: `capturedAt`, `url`, `title`, `html`, `text`.  
The parsers work exclusively from `text` (the page's `innerText`), not `html`.

## Parser logic notes

`parsers/parse_marketplace.py` relies on the predictable line order Facebook Marketplace uses in `innerText`: title → price → listed/location → Condition → Brand → free-text description → "Location is approximate" → Seller details → seller name → rating count → joined year. Any structural change to Facebook's page layout will break the line-index heuristics in `parse_marketplace_ad()`.

## Loading the extension

In Chrome: go to `chrome://extensions`, enable Developer mode, click **Load unpacked**, and select the `extension/` folder. The server must be running before you click the button.
