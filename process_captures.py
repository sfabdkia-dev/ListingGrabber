"""Process all unprocessed capture files and append extracted ads to ads_database.jsonl.

Usage:
  python process_captures.py                    # uses the active project from active_project.json
  python process_captures.py <project_folder>   # processes a specific project folder
"""

import json
import sys
from pathlib import Path

from parse_ad import parse_marketplace_ad

APP_DIR = Path(__file__).resolve().parent
CONFIG_FILE = APP_DIR / "active_project.json"


def get_project_paths(project_arg=None):
    if project_arg:
        p = Path(project_arg)
        return p, p / "ads_database.jsonl", p.name
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            return Path(cfg["captures_dir"]), Path(cfg["database_file"]), cfg.get("name", "Default")
        except Exception:
            pass
    default = APP_DIR / "projects" / "default"
    return default, default / "ads_database.jsonl", "Default"


def load_database(db_path):
    """Return (records, url_index) where url_index maps url -> list index."""
    records, url_index = [], {}
    if Path(db_path).exists():
        with open(db_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rec = json.loads(line)
                        url = rec.get("url")
                        if url and url in url_index:
                            records[url_index[url]] = rec  # keep latest
                        else:
                            if url:
                                url_index[url] = len(records)
                            records.append(rec)
                    except json.JSONDecodeError:
                        pass
    return records, url_index


def save_records(records, db_path):
    with open(Path(db_path), "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main():
    captures_dir, db_path, project_name = get_project_paths(
        sys.argv[1] if len(sys.argv) > 1 else None)

    print(f"Project : {project_name}")
    print(f"Captures: {captures_dir}")
    print(f"Database: {db_path}")

    if not captures_dir.exists():
        print(f"\nCaptures directory not found: {captures_dir}")
        sys.exit(1)

    capture_files = sorted(captures_dir.glob("*_capture.json"))
    if not capture_files:
        print("No capture files found.")
        return

    records, url_index = load_database(db_path)
    processed = {r["source_file"] for r in records if "source_file" in r}
    new_files = [f for f in capture_files if f.name not in processed]

    if not new_files:
        print(f"\nAll {len(capture_files)} capture file(s) already processed. Nothing to do.")
        return

    print(f"\nFound {len(new_files)} new file(s) (skipping {len(processed)} already done).")

    added, updated = 0, 0
    for path in new_files:
        try:
            ad = parse_marketplace_ad(str(path))
            ad["source_file"] = path.name
            url = ad.get("url")
            if url and url in url_index:
                records[url_index[url]] = ad
                updated += 1
                print(f"  ↻ {path.name}  →  updated '{ad.get('title', '(no title)')[:55]}'")
            else:
                if url:
                    url_index[url] = len(records)
                records.append(ad)
                added += 1
                print(f"  + {path.name}  →  {ad.get('title', '(no title)')[:60]}")
        except Exception as exc:
            print(f"  ! {path.name}  ERROR: {exc}")

    if added or updated:
        save_records(records, db_path)

    print(f"\nDone. {added} added, {updated} updated. Database total: {len(records)}.")


if __name__ == "__main__":
    main()
