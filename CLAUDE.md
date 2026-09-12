# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

Two-part tool for scraping and parsing Facebook Marketplace ads:

1. **Chrome extension** (`ad-grabber plugin/`) — a Manifest V3 extension. Clicking the toolbar button (or pressing `Ctrl+Shift+Y`) grabs the current tab's URL, title, HTML, and first 20 000 chars of `innerText`, then POSTs them as JSON to `http://127.0.0.1:9999`.

2. **Local server + parser** (Python) — `Capture_server.py` receives POSTs from the extension and writes timestamped `<ms>_capture.json` files into `captures/`. `parse_ad.py` reads those files and extracts structured ad fields (title, price, location, condition, brand, description, seller info) from the plain-text `text` field.

## Running the pieces

No dependencies to install — both Python files use the standard library only.

Start the capture server (keep it running while browsing):
```
python Capture_server.py
```

Parse a captured file:
```
python parse_ad.py captures/<timestamp>_capture.json
```

## Capture file format

Each `.json` file has five top-level keys: `capturedAt`, `url`, `title`, `html`, `text`.  
`parse_ad.py` works exclusively from `text` (the page's `innerText`), not `html`.

## Parser logic notes

`parse_ad.py` relies on the predictable line order Facebook Marketplace uses in `innerText`: title → price → listed/location → Condition → Brand → free-text description → "Location is approximate" → Seller details → seller name → rating count → joined year. Any structural change to Facebook's page layout will break the line-index heuristics in `parse_marketplace_ad()`.

## Loading the extension

In Chrome: go to `chrome://extensions`, enable Developer mode, click **Load unpacked**, and select the `ad-grabber plugin/` folder. The server must be running before you click the button.
