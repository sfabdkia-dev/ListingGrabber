# Capture_server.py
# Receives POSTs from the Chrome extension and saves captures to the active project.
# Also serves GET endpoints so the extension popup can read / switch the active project.

import json
import time
import datetime
import pathlib
from http.server import BaseHTTPRequestHandler, HTTPServer

APP_DIR = pathlib.Path(__file__).resolve().parent
PROJECTS_DIR = APP_DIR / "projects"
CONFIG_FILE = APP_DIR / "active_project.json"
SETTINGS_FILE = APP_DIR / "app_settings.json"


def _read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_active_project():
    cfg = _read_json(CONFIG_FILE)
    if cfg.get("captures_dir"):
        return cfg
    default_dir = PROJECTS_DIR / "default"
    return {
        "name": "Default",
        "path": str(default_dir),
        "captures_dir": str(default_dir),
        "database_file": str(default_dir / "ads_database.jsonl"),
    }


def get_captures_dir():
    d = pathlib.Path(get_active_project()["captures_dir"])
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_recent_projects():
    return _read_json(SETTINGS_FILE).get("recent_projects", [])


def _add_to_recent(name, path_str, max_recent=8):
    """Add a project to app_settings.json recent list."""
    settings = _read_json(SETTINGS_FILE)
    recent = [r for r in settings.get("recent_projects", []) if r["path"] != path_str]
    recent.insert(0, {"name": name, "path": path_str})
    settings["recent_projects"] = recent[:max_recent]
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")


def set_active_project(project_path):
    """Switch the active project to the given folder path."""
    p = pathlib.Path(project_path)
    if not p.exists():
        return None, "Folder not found"

    meta_file = p / "project.json"
    if meta_file.exists():
        name = _read_json(meta_file).get("name", p.name)
    else:
        name = p.name

    cfg = {
        "name": name,
        "path": str(p),
        "captures_dir": str(p),
        "database_file": str(p / "ads_database.jsonl"),
    }
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    _add_to_recent(name, str(p))
    return cfg, None


def create_project(name, parent=None):
    """Create a new project folder, set it active, return (cfg, err)."""
    if not name:
        return None, "Name is required"
    base = pathlib.Path(parent) if parent else PROJECTS_DIR
    folder = base / name
    folder.mkdir(parents=True, exist_ok=True)
    meta = {"name": name, "created": datetime.datetime.now().isoformat()}
    (folder / "project.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return set_active_project(str(folder))


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path == "/projects":
            self._send_json(200, {"recent_projects": get_recent_projects()})
        else:
            self._send_json(200, get_active_project())

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw)
        except Exception:
            self._send_json(400, {"ok": False, "error": "invalid JSON"})
            return

        if self.path == "/set-project":
            cfg, err = set_active_project(data.get("path", ""))
            if err:
                self._send_json(404, {"ok": False, "error": err})
            else:
                print(f"Active project → {cfg['name']}")
                self._send_json(200, {**cfg, "ok": True})
            return

        if self.path == "/new-project":
            cfg, err = create_project(
                data.get("name", "").strip(),
                data.get("parent") or None,
            )
            if err:
                self._send_json(400, {"ok": False, "error": err})
            else:
                print(f"Created project '{cfg['name']}' at {cfg['path']}")
                self._send_json(200, {**cfg, "ok": True})
            return

        # Default: save a capture
        out = get_captures_dir()
        ts = int(time.time() * 1000)
        path = out / f"{ts}_capture.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        project_name = get_active_project().get("name", "Default")
        print(f"[{project_name}] saved {path.name}  ({data.get('url', '?')[:80]})")
        self._send_json(200, {"ok": True})

    def log_message(self, *a, **k):
        pass


if __name__ == "__main__":
    (PROJECTS_DIR / "default").mkdir(parents=True, exist_ok=True)
    print("Capture server listening on http://127.0.0.1:9999")
    print(f"Active project: {get_active_project()['name']}")
    HTTPServer(("127.0.0.1", 9999), Handler).serve_forever()
