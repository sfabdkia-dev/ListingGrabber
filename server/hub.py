"""Control Hub.

Single entry point for the whole tool:
  - Start / stop the capture server with live status indicator
  - Live capture log (polls the captures folder for new files)
  - Auto-process toggle (parse + add to DB as captures arrive)
  - Project switcher dropdown in the toolbar
  - Open current project folder in Explorer
  - Full ad database viewer with edit, delete, add/remove column, export
"""

import csv
import json
import socket
import subprocess
import sys
import datetime
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from parsers.parse_router import parse_capture

APP_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = APP_DIR / "active_project.json"
SETTINGS_FILE = APP_DIR / "app_settings.json"

HIDDEN_COLS = {"source_file"}
MAX_RECENT = 8
FOLDER_COL = "__folder__"

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 9999
POLL_MS = 1500          # server-status + capture-log poll interval


# ── settings / config helpers ─────────────────────────────────────────────────

def load_settings():
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"recent_projects": []}


def save_settings(settings):
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")


def write_active_config(name, project_path):
    project_path = Path(project_path)
    if project_path.name.lower() == "captures" and project_path.parent.exists():
        project_path = project_path.parent
    cfg = {
        "name": name,
        "path": str(project_path),
        "captures_dir": str(project_path),
        "database_file": str(project_path / "ads_database.jsonl"),
    }
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return cfg


def add_to_recent(settings, name, path):
    recent = [r for r in settings.get("recent_projects", []) if r["path"] != str(path)]
    recent.insert(0, {"name": name, "path": str(path)})
    settings["recent_projects"] = recent[:MAX_RECENT]
    save_settings(settings)


# ── project helpers ───────────────────────────────────────────────────────────

def project_name_from_folder(folder):
    meta = Path(folder) / "project.json"
    if meta.exists():
        try:
            return json.loads(meta.read_text(encoding="utf-8")).get("name", Path(folder).name)
        except Exception:
            pass
    return Path(folder).name


def create_project_folder(name, parent_dir):
    folder = Path(parent_dir) / name
    folder.mkdir(parents=True, exist_ok=True)
    meta = {"name": name, "created": datetime.datetime.now().isoformat()}
    (folder / "project.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return folder


def discover_all_projects(settings):
    """Merge recent list with on-disk scan of PROJECTS_DIR, skipping missing folders."""
    recent = [r for r in settings.get("recent_projects", []) if Path(r["path"]).is_dir()]
    recent_paths = {r["path"] for r in recent}
    discovered = []
    projects_dir = APP_DIR / "My projects"
    if projects_dir.exists():
        for d in sorted(projects_dir.iterdir()):
            if not d.is_dir() or str(d) in recent_paths:
                continue
            name = project_name_from_folder(d)
            discovered.append({"name": name, "path": str(d)})
    return recent + discovered


# ── database helpers ──────────────────────────────────────────────────────────

def load_records(db_path):
    records, url_index = [], {}
    db_path = Path(db_path)
    if db_path.exists():
        with open(db_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rec = json.loads(line)
                        url = rec.get("url")
                        if url and url in url_index:
                            records[url_index[url]] = rec
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


def process_new_captures(records, url_index, captures_dir):
    processed = {r["source_file"] for r in records if "source_file" in r}
    new_records, log = [], []
    captures_dir = Path(captures_dir)
    if captures_dir.exists():
        for path in sorted(captures_dir.glob("*_capture.json")):
            if path.name in processed:
                continue
            try:
                ad = parse_capture(str(path))
                ad["source_file"] = path.name
                url = ad.get("url")
                if url and url in url_index:
                    records[url_index[url]] = ad
                    log.append(f"  ↻ {path.name}  →  updated '{ad.get('title', '(no title)')[:50]}'")
                else:
                    if url:
                        url_index[url] = len(records) + len(new_records)
                    new_records.append(ad)
                    log.append(f"  + {path.name}  →  {ad.get('title', '(no title)')[:55]}")
            except Exception as exc:
                log.append(f"  ! {path.name}  ERROR: {exc}")
    return new_records, log


# ── server helpers ────────────────────────────────────────────────────────────

def is_server_running():
    try:
        with socket.create_connection((SERVER_HOST, SERVER_PORT), timeout=0.3):
            return True
    except OSError:
        return False


def start_server():
    subprocess.Popen(
        ["cmd", "/c", "start", "Capture Server",
         "powershell", "-NoExit", "-Command",
         f"Set-Location '{APP_DIR}'; python server/capture_server.py"],
        cwd=str(APP_DIR),
        creationflags=subprocess.DETACHED_PROCESS,
    )


def stop_server():
    subprocess.run(
        ["taskkill", "/F", "/FI", "WINDOWTITLE eq Capture Server"],
        capture_output=True,
    )


# ── main application ──────────────────────────────────────────────────────────

class AdDatabaseApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Control Hub")
        self.geometry("1340x780")
        self.minsize(900, 500)
        self.records = []
        self.columns = []
        self._visible_columns = []
        self._sort_col = None
        self._sort_asc = True
        self._project_path = None
        self._project_name = None
        self._settings = load_settings()
        self._auto_process_var = tk.BooleanVar(value=True)
        self._seen_captures: set = set()   # filenames seen by the log poller
        self._build_ui()
        self._auto_load_project()
        self._poll()   # start polling loop

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        self._build_menu()
        self._build_server_panel()
        self._build_toolbar()
        self._build_table(self)
        self._build_statusbar()
        self._build_log_window()

    def _build_menu(self):
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New Project…",  accelerator="Ctrl+N", command=self._new_project)
        file_menu.add_command(label="Open Project…", accelerator="Ctrl+O", command=self._open_project)
        file_menu.add_separator()
        self._recent_menu = tk.Menu(file_menu, tearoff=0)
        file_menu.add_cascade(label="Recent Projects", menu=self._recent_menu)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.quit)

        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=view_menu)
        view_menu.add_command(label="Capture Log",
                              accelerator="Ctrl+L",
                              command=self._show_log_window)

        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(
            label="Project Repository",
            command=lambda: webbrowser.open("https://github.com/sfabdkia-dev/Semi-autoPageGrabber"),
        )

        self.bind_all("<Control-n>", lambda e: self._new_project())
        self.bind_all("<Control-o>", lambda e: self._open_project())
        self.bind_all("<Control-l>", lambda e: self._show_log_window())
        self._refresh_recent_menu()

    def _refresh_recent_menu(self):
        self._recent_menu.delete(0, tk.END)
        recent = self._settings.get("recent_projects", [])
        if not recent:
            self._recent_menu.add_command(label="(none)", state=tk.DISABLED)
            return
        for r in recent:
            self._recent_menu.add_command(
                label=f"{r['name']}  —  {r['path']}",
                command=lambda p=r["path"]: self._load_project(Path(p)),
            )

    def _build_server_panel(self):
        panel = tk.Frame(self, bg="#1a1a2e", pady=6)
        panel.pack(fill=tk.X)

        # Status indicator dot
        self._status_canvas = tk.Canvas(panel, width=14, height=14,
                                        bg="#1a1a2e", highlightthickness=0)
        self._status_canvas.pack(side=tk.LEFT, padx=(10, 4))
        self._status_dot = self._status_canvas.create_oval(2, 2, 12, 12, fill="#555", outline="")

        self._server_status_var = tk.StringVar(value="Server: checking…")
        tk.Label(panel, textvariable=self._server_status_var, bg="#1a1a2e",
                 fg="#ccc", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 12))

        sbtn = {"bg": "#2e4057", "fg": "white", "relief": tk.FLAT,
                "padx": 10, "pady": 3, "cursor": "hand2", "font": ("Segoe UI", 9)}

        self._start_btn = tk.Button(panel, text="▶  Start Server", command=self._start_server, **sbtn)
        self._start_btn.pack(side=tk.LEFT, padx=2)

        self._stop_btn = tk.Button(panel, text="■  Stop Server", command=self._stop_server, **sbtn)
        self._stop_btn.pack(side=tk.LEFT, padx=2)

        ttk.Separator(panel, orient="vertical").pack(side=tk.LEFT, fill=tk.Y, padx=8)

        tk.Checkbutton(
            panel, text="Auto-process captures", variable=self._auto_process_var,
            bg="#1a1a2e", fg="#ccc", selectcolor="#333",
            activebackground="#1a1a2e", activeforeground="white",
            font=("Segoe UI", 9),
        ).pack(side=tk.LEFT, padx=4)

        tk.Label(panel, text="Port 9999", bg="#1a1a2e",
                 fg="#555", font=("Segoe UI", 8)).pack(side=tk.RIGHT, padx=10)

    def _build_toolbar(self):
        bar = tk.Frame(self, bg="#2c2c2c", pady=4)
        bar.pack(fill=tk.X)

        btn = {"bg": "#444", "fg": "white", "relief": tk.FLAT,
               "padx": 10, "pady": 4, "cursor": "hand2", "font": ("Segoe UI", 9)}

        tk.Button(bar, text="⟳  Refresh",  command=self._run_process,       **btn).pack(side=tk.LEFT, padx=(6, 2))
        ttk.Separator(bar, orient="vertical").pack(side=tk.LEFT, fill=tk.Y, padx=4)
        tk.Button(bar, text="＋  Add Column",    command=self._add_column,          **btn).pack(side=tk.LEFT, padx=2)
        tk.Button(bar, text="✏  Edit Columns",   command=self._edit_columns,        **btn).pack(side=tk.LEFT, padx=2)
        tk.Button(bar, text="🗑  Delete",         command=self._delete_selected,     **btn).pack(side=tk.LEFT, padx=2)
        ttk.Separator(bar, orient="vertical").pack(side=tk.LEFT, fill=tk.Y, padx=4)
        tk.Button(bar, text="💾  Save",           command=self._save,                **btn).pack(side=tk.LEFT, padx=2)
        tk.Button(bar, text="📤  Export CSV",     command=self._export_csv,          **btn).pack(side=tk.LEFT, padx=2)
        ttk.Separator(bar, orient="vertical").pack(side=tk.LEFT, fill=tk.Y, padx=4)
        tk.Button(bar, text="📁  Open Folder",    command=self._open_project_folder, **btn).pack(side=tk.LEFT, padx=2)

        # Project switcher dropdown (right side of toolbar)
        right = tk.Frame(bar, bg="#2c2c2c")
        right.pack(side=tk.RIGHT, padx=6)

        tk.Label(right, text="Project:", bg="#2c2c2c", fg="#aaa",
                 font=("Segoe UI", 9)).pack(side=tk.LEFT)

        self._project_combo_var = tk.StringVar()
        self._project_combo = ttk.Combobox(
            right, textvariable=self._project_combo_var,
            state="readonly", width=28, font=("Segoe UI", 9),
        )
        self._project_combo.pack(side=tk.LEFT, padx=(4, 0))
        self._project_combo.bind("<<ComboboxSelected>>", self._on_project_combo_select)
        self._combo_projects = []
        self._refresh_project_combo()

    def _build_log_window(self):
        """Create the capture log as a detached Toplevel, hidden by default."""
        win = tk.Toplevel(self)
        win.title("Capture Log")
        win.geometry("680x400")
        win.resizable(True, True)
        win.withdraw()   # hidden until the user opens it
        win.protocol("WM_DELETE_WINDOW", win.withdraw)  # close hides, not destroys
        self._log_win = win

        tk.Label(win, text="Capture Log", font=("Segoe UI", 10, "bold"),
                 padx=10, pady=6, anchor=tk.W).pack(fill=tk.X)

        self._log_text = tk.Text(
            win, bg="#1e1e1e", fg="#c8e6c9", insertbackground="white",
            font=("Consolas", 9), relief=tk.FLAT, state=tk.DISABLED,
            wrap=tk.WORD, padx=8, pady=6,
        )
        log_vsb = ttk.Scrollbar(win, orient="vertical", command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=log_vsb.set)
        log_vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._log_text.pack(fill=tk.BOTH, expand=True)

        tk.Button(
            win, text="Clear log", bg="#2c2c2c", fg="#aaa",
            relief=tk.FLAT, font=("Segoe UI", 8), cursor="hand2",
            command=self._clear_log,
        ).pack(fill=tk.X)

    def _show_log_window(self):
        self._log_win.deiconify()
        self._log_win.lift()

    def _build_table(self, parent):
        frame = tk.Frame(parent)
        frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=(4, 0))

        self.tree = ttk.Treeview(frame, selectmode="extended", show="headings")
        vsb = ttk.Scrollbar(frame, orient="vertical",   command=self.tree.yview)
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side=tk.RIGHT,  fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree.pack(fill=tk.BOTH, expand=True)

        style = ttk.Style()
        style.configure("Treeview",         rowheight=24, font=("Segoe UI", 9))
        style.configure("Treeview.Heading",               font=("Segoe UI", 9, "bold"))
        style.map("Treeview", background=[("selected", "#0078d4")])

        self.tree.bind("<ButtonRelease-1>", self._on_single_click)
        self.tree.bind("<Double-1>",        self._on_double_click)

    def _build_statusbar(self):
        bar = tk.Frame(self, bg="#f0f0f0", bd=1, relief=tk.SUNKEN)
        bar.pack(fill=tk.X, side=tk.BOTTOM)
        self.status_var = tk.StringVar(value="Open or create a project (File menu)")
        tk.Label(bar, textvariable=self.status_var, anchor=tk.W,
                 bg="#f0f0f0", font=("Segoe UI", 8), padx=6).pack(side=tk.LEFT)

    # ── polling loop ──────────────────────────────────────────────────────────

    def _poll(self):
        self._poll_server_status()
        self._poll_captures()
        self.after(POLL_MS, self._poll)

    def _poll_server_status(self):
        running = is_server_running()
        if running:
            self._status_canvas.itemconfig(self._status_dot, fill="#4caf50")
            self._server_status_var.set("Server: running")
            self._start_btn.config(state=tk.DISABLED)
            self._stop_btn.config(state=tk.NORMAL)
        else:
            self._status_canvas.itemconfig(self._status_dot, fill="#e53935")
            self._server_status_var.set("Server: stopped")
            self._start_btn.config(state=tk.NORMAL)
            self._stop_btn.config(state=tk.DISABLED)

    def _poll_captures(self):
        if not self._project_path or not self._project_path.exists():
            return

        new_files = []
        for path in sorted(self._project_path.glob("*_capture.json")):
            if path.name not in self._seen_captures:
                self._seen_captures.add(path.name)
                new_files.append(path)

        if not new_files:
            return

        for path in new_files:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                url = data.get("url", "")[:70]
                ts = datetime.datetime.now().strftime("%H:%M:%S")
                self._log(f"[{ts}] {path.name}\n  {url}\n")
            except Exception:
                self._log(f"  {path.name}\n")

        if self._auto_process_var.get():
            _, url_index = load_records(self._project_path / "ads_database.jsonl")
            new_recs, log_lines = process_new_captures(self.records, url_index, self._project_path)
            if new_recs:
                self.records.extend(new_recs)
                save_records(self.records, self._project_path / "ads_database.jsonl")
                self._rebuild_columns()
                self._refresh_table()
                self.status_var.set(
                    f"Auto-processed {len(new_recs)} new capture(s). Total: {len(self.records)}")
                for line in log_lines:
                    self._log(f"  ✓ {line.strip()}\n")

    def _log(self, text):
        self._log_text.config(state=tk.NORMAL)
        self._log_text.insert(tk.END, text)
        self._log_text.see(tk.END)
        self._log_text.config(state=tk.DISABLED)

    def _clear_log(self):
        self._log_text.config(state=tk.NORMAL)
        self._log_text.delete("1.0", tk.END)
        self._log_text.config(state=tk.DISABLED)

    # ── server controls ───────────────────────────────────────────────────────

    def _start_server(self):
        self._log(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Starting capture server…\n")
        start_server()

    def _stop_server(self):
        self._log(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Stopping capture server…\n")
        stop_server()

    # ── project combo ─────────────────────────────────────────────────────────

    def _refresh_project_combo(self):
        all_projects = discover_all_projects(self._settings)
        names = [f"{p['name']}  ({Path(p['path']).name})" for p in all_projects]
        self._project_combo["values"] = names
        self._combo_projects = all_projects

        if self._project_path:
            for i, p in enumerate(all_projects):
                if p["path"] == str(self._project_path):
                    self._project_combo.current(i)
                    break

    def _on_project_combo_select(self, event):
        idx = self._project_combo.current()
        if idx < 0 or idx >= len(self._combo_projects):
            return
        chosen = self._combo_projects[idx]
        self._load_project(Path(chosen["path"]))

    # ── project management ────────────────────────────────────────────────────

    def _auto_load_project(self):
        if CONFIG_FILE.exists():
            try:
                cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                p = Path(cfg.get("path", ""))
                if p.exists():
                    self._load_project(p, silent=True)
                    return
            except Exception:
                pass

        for r in self._settings.get("recent_projects", []):
            p = Path(r["path"])
            if p.exists():
                self._load_project(p, silent=True)
                return

        default_dir = APP_DIR / "My projects" / "default"
        if (default_dir / "ads_database.jsonl").exists() or default_dir.exists():
            self._load_project(default_dir, silent=True)

    def _new_project(self):
        name = simpledialog.askstring("New Project", "Project name:", parent=self)
        if not name or not name.strip():
            return
        name = name.strip()
        folder = create_project_folder(name, APP_DIR / "My projects")
        self._load_project(folder)

    def _open_project(self):
        folder = filedialog.askdirectory(title="Select project folder", parent=self)
        if folder:
            self._load_project(Path(folder))

    def _load_project(self, project_path, silent=False):
        project_path = Path(project_path)
        if not project_path.exists():
            if not silent:
                messagebox.showerror("Open Project", f"Folder not found:\n{project_path}")
            return

        project_path.mkdir(parents=True, exist_ok=True)
        name = project_name_from_folder(project_path)

        self._project_path = project_path
        self._project_name = name

        write_active_config(name, project_path)
        add_to_recent(self._settings, name, project_path)
        self._refresh_recent_menu()
        self._refresh_project_combo()

        self.records, url_index = load_records(project_path / "ads_database.jsonl")

        # Seed seen-captures so the poller only fires on files that arrive after this point
        self._seen_captures = {p.name for p in project_path.glob("*_capture.json")}

        new_recs, log = process_new_captures(self.records, url_index, project_path)
        if new_recs or log:
            self.records.extend(new_recs)
            save_records(self.records, project_path / "ads_database.jsonl")
            if not silent and log:
                messagebox.showinfo("New captures processed",
                                    f"Processed {len(log)} capture(s):\n\n" + "\n".join(log))

        self._rebuild_columns()
        self._refresh_table()
        self.title(f"Control Hub — {name}")
        self.status_var.set(
            f"{len(self.records)} records  |  {len(self.columns)} columns  |  {project_path}")

    def _open_project_folder(self):
        if not self._project_path:
            messagebox.showinfo("No Project", "Open or create a project first.")
            return
        subprocess.Popen(["explorer", str(self._project_path)])

    # ── data processing ───────────────────────────────────────────────────────

    def _run_process(self):
        if not self._project_path:
            messagebox.showinfo("No Project", "Open or create a project first.")
            return
        _, url_index = load_records(self._project_path / "ads_database.jsonl")
        new_recs, log = process_new_captures(self.records, url_index, self._project_path)
        if not new_recs and not log:
            messagebox.showinfo("Process New", "No new capture files found.")
            return
        self.records.extend(new_recs)
        save_records(self.records, self._project_path / "ads_database.jsonl")
        self._rebuild_columns()
        self._refresh_table()
        self.status_var.set(f"Added {len(new_recs)} new record(s). Total: {len(self.records)}")

    def _rebuild_columns(self):
        seen, cols = set(), []
        for r in self.records:
            for k in r:
                if k not in seen and k not in HIDDEN_COLS:
                    seen.add(k)
                    cols.append(k)
        self.columns = cols

    def _refresh_table(self):
        hidden = self._get_hidden_columns()
        self._visible_columns = [c for c in self.columns if c not in hidden]

        self.tree.delete(*self.tree.get_children())
        self.tree["columns"] = [FOLDER_COL] + self._visible_columns

        self.tree.heading(FOLDER_COL, text="")
        self.tree.column(FOLDER_COL, width=28, minwidth=28, stretch=False, anchor="center")

        wide = {"title": 220, "description": 260, "url": 200, "listed": 180, "location": 130}
        for col in self._visible_columns:
            arrow = ("  ▲" if self._sort_asc else "  ▼") if self._sort_col == col else ""
            self.tree.heading(col, text=col.replace("_", " ").title() + arrow,
                              command=lambda c=col: self._sort_by(c))
            self.tree.column(col, width=wide.get(col, 110), minwidth=50, stretch=False)

        for i, rec in enumerate(self.records):
            values = ["📂"] + [str(rec.get(col) or "") for col in self._visible_columns]
            self.tree.insert("", tk.END, iid=str(i), values=values,
                             tags=("even" if i % 2 == 0 else "odd",))

        self.tree.tag_configure("even", background="#f7f7f7")
        self.tree.tag_configure("odd",  background="#ffffff")

    def _sort_by(self, col):
        self._sort_asc = not self._sort_asc if self._sort_col == col else True
        self._sort_col = col
        self.records.sort(key=lambda r: str(r.get(col) or "").lower(), reverse=not self._sort_asc)
        self._refresh_table()

    # ── editing ───────────────────────────────────────────────────────────────

    def _on_single_click(self, event):
        if self.tree.identify("region", event.x, event.y) != "cell":
            return
        col_id = self.tree.identify_column(event.x)
        if not col_id or int(col_id[1:]) != 1:
            return
        row_id = self.tree.identify_row(event.y)
        if row_id:
            self._open_source_folder(int(row_id))

    def _on_double_click(self, event):
        if self.tree.identify("region", event.x, event.y) != "cell":
            return
        row_id = self.tree.identify_row(event.y)
        col_id = self.tree.identify_column(event.x)
        if not row_id or not col_id:
            return
        col_pos = int(col_id[1:])
        if col_pos == 1:
            return
        visible_col_index = col_pos - 2
        col_name = self._visible_columns[visible_col_index]
        all_col_index = self.columns.index(col_name)
        if col_name == "url":
            url = self.records[int(row_id)].get("url", "")
            if url:
                webbrowser.open(url)
        else:
            self._open_editor(int(row_id), all_col_index)

    def _open_source_folder(self, rec_index):
        if not self._project_path:
            return
        rec = self.records[rec_index]
        source_file = rec.get("source_file")
        if source_file:
            path = self._project_path / source_file
            if path.exists():
                subprocess.Popen(["explorer", "/select,", str(path)])
                return
        subprocess.Popen(["explorer", str(self._project_path)])

    def _edit_selected_cell(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Edit", "Select a row first.")
            return
        col_name = simpledialog.askstring(
            "Edit Column",
            f"Column to edit?\n\nAvailable: {', '.join(self._visible_columns)}",
            parent=self)
        if col_name and col_name in self.columns:
            self._open_editor(int(sel[0]), self.columns.index(col_name))

    def _open_editor(self, rec_index, col_index):
        col_name = self.columns[col_index]
        current = str(self.records[rec_index].get(col_name) or "")

        dlg = tk.Toplevel(self)
        dlg.title(f"Edit — {col_name.replace('_', ' ').title()}")
        dlg.geometry("520x280")
        dlg.resizable(True, True)
        dlg.grab_set()
        dlg.transient(self)

        tk.Label(dlg, text=col_name.replace("_", " ").title(),
                 font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, padx=12, pady=(10, 2))

        frm = tk.Frame(dlg)
        frm.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)
        txt = tk.Text(frm, wrap=tk.WORD, font=("Segoe UI", 9), relief=tk.SOLID, bd=1)
        txt.pack(fill=tk.BOTH, expand=True)
        txt.insert("1.0", current)
        txt.focus_set()

        def do_save():
            val = txt.get("1.0", tk.END).strip()
            self.records[rec_index][col_name] = val or None
            self._refresh_table()
            self.status_var.set(f"Row {rec_index} · '{col_name}' updated (unsaved — press Save)")
            dlg.destroy()

        bf = tk.Frame(dlg)
        bf.pack(fill=tk.X, padx=12, pady=8)
        tk.Button(bf, text="Save",   command=do_save,     width=10,
                  bg="#0078d4", fg="white", relief=tk.FLAT).pack(side=tk.LEFT)
        tk.Button(bf, text="Cancel", command=dlg.destroy, width=10,
                  relief=tk.FLAT).pack(side=tk.LEFT, padx=6)
        dlg.bind("<Return>", lambda e: do_save())
        dlg.bind("<Escape>", lambda e: dlg.destroy())

    # ── delete ────────────────────────────────────────────────────────────────

    def _delete_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Delete", "Select one or more rows first.")
            return
        if not messagebox.askyesno("Delete", f"Permanently delete {len(sel)} record(s)?"):
            return
        for i in sorted([int(s) for s in sel], reverse=True):
            self.records.pop(i)
        self._save()
        self._rebuild_columns()
        self._refresh_table()
        self.status_var.set(f"Deleted {len(sel)} record(s). {len(self.records)} remaining.")

    # ── add column ────────────────────────────────────────────────────────────

    def _add_column(self):
        if not self._project_path:
            messagebox.showinfo("No Project", "Open or create a project first.")
            return
        name = simpledialog.askstring("Add Column", "New column name:", parent=self)
        if not name:
            return
        name = name.strip().lower().replace(" ", "_")
        if not name or name in self.columns or name in HIDDEN_COLS:
            messagebox.showwarning("Add Column", "Column name invalid or already exists.")
            return
        for rec in self.records:
            rec.setdefault(name, None)
        self.columns.append(name)
        self._save()
        self._refresh_table()
        self.status_var.set(f"Column '{name}' added to all records.")

    # ── column visibility helpers ──────────────────────────────────────────────

    def _get_hidden_columns(self):
        if not self._project_path:
            return set()
        key = str(self._project_path)
        return set(self._settings.get("column_visibility", {}).get(key, []))

    def _set_hidden_columns(self, hidden_set):
        if not self._project_path:
            return
        key = str(self._project_path)
        if "column_visibility" not in self._settings:
            self._settings["column_visibility"] = {}
        self._settings["column_visibility"][key] = sorted(hidden_set)
        save_settings(self._settings)

    # ── edit columns ──────────────────────────────────────────────────────────

    def _edit_columns(self):
        if not self._project_path:
            messagebox.showinfo("No Project", "Open or create a project first.")
            return
        if not self.columns:
            messagebox.showinfo("Edit Columns", "No columns to edit.")
            return

        hidden = self._get_hidden_columns()

        dlg = tk.Toplevel(self)
        dlg.title("Edit Columns")
        dlg.geometry("360x460")
        dlg.resizable(False, True)
        dlg.grab_set()
        dlg.transient(self)

        tk.Label(dlg, text="Toggle column visibility:",
                 font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, padx=12, pady=(10, 2))
        tk.Label(dlg, text="Checked = visible in table. Settings are saved automatically.",
                 font=("Segoe UI", 8), fg="#777").pack(anchor=tk.W, padx=12, pady=(0, 6))

        scroll_frame = tk.Frame(dlg)
        scroll_frame.pack(fill=tk.BOTH, expand=True, padx=12)

        canvas = tk.Canvas(scroll_frame, bd=0, highlightthickness=0)
        vsb = ttk.Scrollbar(scroll_frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        inner = tk.Frame(canvas)
        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(inner_id, width=e.width))

        check_vars = {}
        for col in self.columns:
            var = tk.BooleanVar(value=(col not in hidden))
            check_vars[col] = var
            tk.Checkbutton(
                inner, text=col.replace("_", " ").title(), variable=var,
                font=("Segoe UI", 9), anchor=tk.W,
            ).pack(fill=tk.X, padx=4, pady=1)

        def select_all():
            for v in check_vars.values():
                v.set(True)

        def select_none():
            for v in check_vars.values():
                v.set(False)

        sel_frame = tk.Frame(dlg)
        sel_frame.pack(fill=tk.X, padx=12, pady=(4, 0))
        tk.Button(sel_frame, text="Show All", command=select_all,
                  font=("Segoe UI", 8), relief=tk.FLAT, bg="#e0e0e0").pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(sel_frame, text="Hide All", command=select_none,
                  font=("Segoe UI", 8), relief=tk.FLAT, bg="#e0e0e0").pack(side=tk.LEFT)

        def do_apply():
            new_hidden = {col for col, var in check_vars.items() if not var.get()}
            if new_hidden == hidden:
                dlg.destroy()
                return
            if not new_hidden and len(new_hidden) == len(self.columns):
                messagebox.showwarning("Edit Columns", "At least one column must be visible.", parent=dlg)
                return
            self._set_hidden_columns(new_hidden)
            self._refresh_table()
            shown = len(self.columns) - len(new_hidden)
            self.status_var.set(f"Showing {shown} of {len(self.columns)} columns.")
            dlg.destroy()

        bf = tk.Frame(dlg)
        bf.pack(fill=tk.X, padx=12, pady=8)
        tk.Button(bf, text="Apply", command=do_apply, width=10,
                  bg="#0078d4", fg="white", relief=tk.FLAT).pack(side=tk.LEFT)
        tk.Button(bf, text="Cancel", command=dlg.destroy, width=10,
                  relief=tk.FLAT).pack(side=tk.LEFT, padx=6)
        dlg.bind("<Escape>", lambda e: dlg.destroy())

    # ── export CSV ────────────────────────────────────────────────────────────

    def _export_csv(self):
        if not self.records:
            messagebox.showinfo("Export CSV", "No records to export.")
            return
        path = filedialog.asksaveasfilename(
            title="Export as CSV",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=f"{self._project_name or 'ads'}_export.csv",
            parent=self,
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=self.columns, extrasaction="ignore")
                writer.writeheader()
                for rec in self.records:
                    writer.writerow({col: rec.get(col) or "" for col in self.columns})
            self.status_var.set(f"Exported {len(self.records)} records to {Path(path).name}")
        except Exception as exc:
            messagebox.showerror("Export CSV", f"Failed to save:\n{exc}")

    # ── save ──────────────────────────────────────────────────────────────────

    def _save(self):
        if not self._project_path:
            return
        save_records(self.records, self._project_path / "ads_database.jsonl")
        self.status_var.set(f"Saved — {len(self.records)} records.")


if __name__ == "__main__":
    app = AdDatabaseApp()
    if len(sys.argv) > 1:
        folder = Path(sys.argv[1])
        if folder.exists():
            app.after(0, lambda: app._load_project(folder))
    app.mainloop()
