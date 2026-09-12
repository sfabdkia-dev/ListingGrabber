"""Facebook Marketplace Ad Database Viewer — project-aware edition.

On launch: auto-loads the last active project (or the root folder if data exists there).
Then opens a table UI with edit, delete, add-column, and project management.
"""

import json
import datetime
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from pathlib import Path

from parse_ad import parse_marketplace_ad

APP_DIR = Path(__file__).resolve().parent
CONFIG_FILE = APP_DIR / "active_project.json"    # shared with Capture_server.py
SETTINGS_FILE = APP_DIR / "app_settings.json"

HIDDEN_COLS = {"source_file"}
MAX_RECENT = 8


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


# ── database helpers ──────────────────────────────────────────────────────────

def load_records(db_path):
    """Load records, keeping the latest entry for each URL (in-place replacement)."""
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
                            records[url_index[url]] = rec  # replace with newer
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
    """Parse unprocessed captures, adding new ads or updating existing ones by URL."""
    processed = {r["source_file"] for r in records if "source_file" in r}
    new_records, log = [], []
    captures_dir = Path(captures_dir)
    if captures_dir.exists():
        for path in sorted(captures_dir.glob("*_capture.json")):
            if path.name in processed:
                continue
            try:
                ad = parse_marketplace_ad(str(path))
                ad["source_file"] = path.name
                url = ad.get("url")
                if url and url in url_index:
                    records[url_index[url]] = ad  # update existing record in-place
                    log.append(f"  ↻ {path.name}  →  updated '{ad.get('title', '(no title)')[:50]}'")
                else:
                    if url:
                        url_index[url] = len(records) + len(new_records)
                    new_records.append(ad)
                    log.append(f"  + {path.name}  →  {ad.get('title', '(no title)')[:55]}")
            except Exception as exc:
                log.append(f"  ! {path.name}  ERROR: {exc}")
    return new_records, log


# ── main application ──────────────────────────────────────────────────────────

class AdDatabaseApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Facebook Marketplace Ad Database")
        self.geometry("1300x720")
        self.minsize(800, 400)
        self.records = []
        self.columns = []
        self._sort_col = None
        self._sort_asc = True
        self._project_path = None
        self._project_name = None
        self._settings = load_settings()
        self._build_ui()
        self._auto_load_project()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self._build_menu()
        self._build_toolbar()
        self._build_table()
        self._build_statusbar()

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

        self.bind_all("<Control-n>", lambda e: self._new_project())
        self.bind_all("<Control-o>", lambda e: self._open_project())

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

    def _build_toolbar(self):
        bar = tk.Frame(self, bg="#2c2c2c", pady=4)
        bar.pack(fill=tk.X)

        btn = {"bg": "#444", "fg": "white", "relief": tk.FLAT,
               "padx": 10, "pady": 4, "cursor": "hand2", "font": ("Segoe UI", 9)}

        tk.Button(bar, text="⟳  Process New",  command=self._run_process,      **btn).pack(side=tk.LEFT, padx=(6, 2))
        ttk.Separator(bar, orient="vertical").pack(side=tk.LEFT, fill=tk.Y, padx=4)
        tk.Button(bar, text="＋  Add Column",   command=self._add_column,       **btn).pack(side=tk.LEFT, padx=2)
        tk.Button(bar, text="✎  Edit Cell",     command=self._edit_selected_cell, **btn).pack(side=tk.LEFT, padx=2)
        tk.Button(bar, text="🗑  Delete",        command=self._delete_selected,  **btn).pack(side=tk.LEFT, padx=2)
        ttk.Separator(bar, orient="vertical").pack(side=tk.LEFT, fill=tk.Y, padx=4)
        tk.Button(bar, text="💾  Save",          command=self._save,             **btn).pack(side=tk.LEFT, padx=2)

        self._project_label_var = tk.StringVar(value="No project — use File menu")
        tk.Label(bar, textvariable=self._project_label_var, bg="#2c2c2c",
                 fg="#aaa", font=("Segoe UI", 9), padx=10).pack(side=tk.RIGHT)

    def _build_table(self):
        frame = tk.Frame(self)
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

        self.tree.bind("<Double-1>", self._on_double_click)

    def _build_statusbar(self):
        bar = tk.Frame(self, bg="#f0f0f0", bd=1, relief=tk.SUNKEN)
        bar.pack(fill=tk.X, side=tk.BOTTOM)
        self.status_var = tk.StringVar(value="Open or create a project (File menu)")
        tk.Label(bar, textvariable=self.status_var, anchor=tk.W,
                 bg="#f0f0f0", font=("Segoe UI", 8), padx=6).pack(side=tk.LEFT)

    # ── project management ────────────────────────────────────────────────────

    def _auto_load_project(self):
        # 1. Try last active project from shared config
        if CONFIG_FILE.exists():
            try:
                cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                p = Path(cfg.get("path", ""))
                if p.exists():
                    self._load_project(p, silent=True)
                    return
            except Exception:
                pass

        # 2. Fall back to most recent in settings
        for r in self._settings.get("recent_projects", []):
            p = Path(r["path"])
            if p.exists():
                self._load_project(p, silent=True)
                return

        # 3. Fall back to default project if it already has data
        default_dir = APP_DIR / "projects" / "default"
        if (default_dir / "ads_database.jsonl").exists() or default_dir.exists():
            self._load_project(default_dir, silent=True)

    def _new_project(self):
        name = simpledialog.askstring("New Project", "Project name:", parent=self)
        if not name or not name.strip():
            return
        name = name.strip()
        folder = create_project_folder(name, APP_DIR / "projects")
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

        self.records, url_index = load_records(project_path / "ads_database.jsonl")

        new_recs, log = process_new_captures(self.records, url_index, project_path)
        if new_recs or log:
            self.records.extend(new_recs)
            save_records(self.records, project_path / "ads_database.jsonl")
            if not silent and log:
                messagebox.showinfo("New captures processed",
                                    f"Processed {len(log)} capture(s):\n\n" + "\n".join(log))

        self._rebuild_columns()
        self._refresh_table()
        self.title(f"Facebook Marketplace Ad Database — {name}")
        self._project_label_var.set(f"Project: {name}")
        self.status_var.set(
            f"{len(self.records)} records  |  {len(self.columns)} columns  |  {project_path}")

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
        self.tree.delete(*self.tree.get_children())
        self.tree["columns"] = self.columns

        wide = {"title": 220, "description": 260, "url": 200, "listed": 180, "location": 130}
        for col in self.columns:
            arrow = ("  ▲" if self._sort_asc else "  ▼") if self._sort_col == col else ""
            self.tree.heading(col, text=col.replace("_", " ").title() + arrow,
                              command=lambda c=col: self._sort_by(c))
            self.tree.column(col, width=wide.get(col, 110), minwidth=50, stretch=False)

        for i, rec in enumerate(self.records):
            values = [str(rec.get(col) or "") for col in self.columns]
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

    def _on_double_click(self, event):
        if self.tree.identify("region", event.x, event.y) != "cell":
            return
        row_id = self.tree.identify_row(event.y)
        col_id = self.tree.identify_column(event.x)
        if row_id and col_id:
            self._open_editor(int(row_id), int(col_id[1:]) - 1)

    def _edit_selected_cell(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Edit", "Select a row first.")
            return
        col_name = simpledialog.askstring(
            "Edit Column",
            f"Column to edit?\n\nAvailable: {', '.join(self.columns)}",
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
        tk.Button(bf, text="Save",   command=do_save,       width=10,
                  bg="#0078d4", fg="white", relief=tk.FLAT).pack(side=tk.LEFT)
        tk.Button(bf, text="Cancel", command=dlg.destroy,   width=10,
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
            messagebox.showwarning("Add Column", f"Column name invalid or already exists.")
            return
        for rec in self.records:
            rec.setdefault(name, None)
        self.columns.append(name)
        self._save()
        self._refresh_table()
        self.status_var.set(f"Column '{name}' added to all records.")

    # ── save ──────────────────────────────────────────────────────────────────

    def _save(self):
        if not self._project_path:
            return
        save_records(self.records, self._project_path / "ads_database.jsonl")
        self.status_var.set(f"Saved — {len(self.records)} records.")


if __name__ == "__main__":
    import sys
    app = AdDatabaseApp()
    if len(sys.argv) > 1:
        folder = Path(sys.argv[1])
        if folder.exists():
            app.after(0, lambda: app._load_project(folder))
    app.mainloop()
