const SERVER = "http://127.0.0.1:9999";

const dot            = document.getElementById("dot");
const serverText     = document.getElementById("server-text");
const projectSelect  = document.getElementById("project-select");
const capturesPath   = document.getElementById("captures-path");
const refreshBtn     = document.getElementById("refresh-btn");
const grabBtn        = document.getElementById("grab-btn");
const statusBar      = document.getElementById("status");
const captureHtmlToggle = document.getElementById("capture-html-toggle");
const addToggle      = document.getElementById("add-toggle");
const addPanel       = document.getElementById("add-panel");
const folderInput    = document.getElementById("folder-path-input");
const openFolderBtn  = document.getElementById("open-folder-btn");
const newNameInput   = document.getElementById("new-name-input");
const createBtn      = document.getElementById("create-btn");
const newProjectHint = document.getElementById("new-project-hint");

let serverOnline = false;
let defaultProjectsPath = "";

function setStatus(msg, type = "") {
  statusBar.textContent = msg;
  statusBar.className = "status-bar" + (type ? " " + type : "");
}

function clearStatusAfter(ms = 3500) {
  setTimeout(() => setStatus(""), ms);
}

// -- collapsible toggles -------------------------------------------------------

addToggle.addEventListener("click", () => {
  addToggle.classList.toggle("open");
  addPanel.classList.toggle("open");
});

document.getElementById("html-toggle").addEventListener("click", () => {
  document.getElementById("html-toggle").classList.toggle("open");
  document.getElementById("html-panel").classList.toggle("open");
});

// -- load current project + recent list ---------------------------------------

async function loadState() {
  try {
    const [statusRes, projectsRes] = await Promise.all([
      fetch(SERVER),
      fetch(SERVER + "/projects"),
    ]);
    const active = await statusRes.json();
    const { recent_projects } = await projectsRes.json();

    dot.className = "dot green";
    serverText.textContent = "Server running";
    serverOnline = true;
    grabBtn.disabled = false;

    // Derive default projects parent from active project path for the hint
    defaultProjectsPath = (active.path || "").replace(/[/\\][^/\\]+$/, "") + "/projects";
    newProjectHint.textContent = "Will be created in: " + defaultProjectsPath + "/<name>";

    populateDropdown(active, recent_projects);
    capturesPath.textContent = active.captures_dir || "-";

  } catch (e) {
    dot.className = "dot red";
    serverText.textContent = "Server not running - open the Launch_Hub shortcut";
    serverOnline = false;
    grabBtn.disabled = true;
    projectSelect.disabled = true;
    projectSelect.innerHTML = '<option value="">-</option>';
    capturesPath.textContent = "-";
  }
}

function populateDropdown(active, projects) {
  projectSelect.innerHTML = "";
  projectSelect.disabled = false;
  const seen = new Set();

  if (active && active.path) {
    projectSelect.appendChild(new Option(active.name || "Default", active.path, true, true));
    seen.add(active.path);
  }
  for (const r of (projects || [])) {
    if (!seen.has(r.path)) {
      projectSelect.appendChild(new Option(r.name, r.path));
      seen.add(r.path);
    }
  }
}

// -- refresh: rescan the projects folder on demand ----------------------------

refreshBtn.addEventListener("click", async () => {
  if (!serverOnline) return;
  refreshBtn.disabled = true;
  refreshBtn.classList.add("spinning");
  setStatus("Rescanning projects folder...");
  try {
    const [statusRes, scanRes] = await Promise.all([
      fetch(SERVER),
      fetch(SERVER + "/scan-projects"),
    ]);
    const active = await statusRes.json();
    const { recent_projects } = await scanRes.json();
    populateDropdown(active, recent_projects);
    setStatus(` Found ${recent_projects.length} project(s)`, "ok");
  } catch (e) {
    setStatus("X " + e.message, "err");
  } finally {
    refreshBtn.classList.remove("spinning");
    refreshBtn.disabled = false;
    clearStatusAfter();
  }
});

// -- switch project via dropdown -----------------------------------------------

projectSelect.addEventListener("change", async () => {
  const path = projectSelect.value;
  if (!path) return;
  setStatus("Switching project...");
  try {
    const res  = await fetch(SERVER + "/set-project", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    const data = await res.json();
    if (data.ok) {
      capturesPath.textContent = data.captures_dir || "-";
      setStatus(` Switched to "${data.name}"`, "ok");
    } else {
      setStatus("X " + (data.error || "Failed"), "err");
    }
  } catch (e) {
    setStatus("X " + e.message, "err");
  }
  clearStatusAfter();
});

// -- open existing folder ------------------------------------------------------

openFolderBtn.addEventListener("click", async () => {
  const path = folderInput.value.trim();
  if (!path) { setStatus("X Enter a folder path first", "err"); clearStatusAfter(); return; }

  setStatus("Opening folder...");
  try {
    const res  = await fetch(SERVER + "/set-project", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    const data = await res.json();
    if (data.ok) {
      capturesPath.textContent = data.captures_dir || "-";
      folderInput.value = "";
      // Add to dropdown if not already there
      if (![...projectSelect.options].some(o => o.value === data.path)) {
        const opt = new Option(data.name, data.path);
        projectSelect.insertBefore(opt, projectSelect.firstChild);
      }
      projectSelect.value = data.path;
      setStatus(` Opened "${data.name}"`, "ok");
      addToggle.classList.remove("open");
      addPanel.classList.remove("open");
    } else {
      setStatus("X " + (data.error || "Folder not found"), "err");
    }
  } catch (e) {
    setStatus("X " + e.message, "err");
  }
  clearStatusAfter();
});

folderInput.addEventListener("keydown", e => { if (e.key === "Enter") openFolderBtn.click(); });

// -- create new project --------------------------------------------------------

createBtn.addEventListener("click", async () => {
  const name = newNameInput.value.trim();
  if (!name) { setStatus("X Enter a project name", "err"); clearStatusAfter(); return; }

  createBtn.disabled = true;
  setStatus("Creating project...");
  try {
    const res  = await fetch(SERVER + "/new-project", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    const data = await res.json();
    if (data.ok) {
      capturesPath.textContent = data.captures_dir || "-";
      newNameInput.value = "";
      // Add to dropdown and select it
      if (![...projectSelect.options].some(o => o.value === data.path)) {
        const opt = new Option(data.name, data.path);
        projectSelect.insertBefore(opt, projectSelect.firstChild);
      }
      projectSelect.value = data.path;
      setStatus(` Created "${data.name}"`, "ok");
      addToggle.classList.remove("open");
      addPanel.classList.remove("open");
    } else {
      setStatus("X " + (data.error || "Failed"), "err");
    }
  } catch (e) {
    setStatus("X " + e.message, "err");
  } finally {
    createBtn.disabled = false;
  }
  clearStatusAfter(4000);
});

newNameInput.addEventListener("keydown", e => { if (e.key === "Enter") createBtn.click(); });

// -- URL validation -----------------------------------------------------------

const SUPPORTED_PATTERNS = [
  { label: "Facebook Marketplace", test: url => /facebook\.com\/marketplace\/item\//i.test(url) },
  { label: "Amazon product",       test: url => /amazon\.[a-z.]+/i.test(url) && /\/dp\/|\/gp\/product\//i.test(url) },
];

function getSupportedSite(url) {
  return SUPPORTED_PATTERNS.find(p => p.test(url)) || null;
}

// -- grab page ----------------------------------------------------------------

grabBtn.addEventListener("click", async () => {
  grabBtn.disabled = true;
  setStatus("Grabbing page...");
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    if (!getSupportedSite(tab.url || "")) {
      setStatus("X Not a supported page. Open the product page of a supported website.", "err");
      clearStatusAfter(5000);
      grabBtn.disabled = false;
      return;
    }

    const { captureHtml } = await chrome.storage.local.get({ captureHtml: false });
    const [{ result: payload }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: (includeHtml) => ({
        url: location.href,
        title: document.title,
        capturedAt: new Date().toISOString(),
        ...(includeHtml ? { html: document.documentElement.outerHTML } : {}),
        text: document.body.innerText.slice(0, 20000),
      }),
      args: [captureHtml],
    });
    const res = await fetch(SERVER, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (res.ok) {
      setStatus(" Page captured!", "ok");
    } else {
      throw new Error("Server returned " + res.status);
    }
  } catch (e) {
    setStatus("X " + e.message, "err");
  } finally {
    grabBtn.disabled = false;
    clearStatusAfter(4000);
  }
});

// -- capture-html toggle -------------------------------------------------------

chrome.storage.local.get({ captureHtml: false }, ({ captureHtml }) => {
  captureHtmlToggle.checked = captureHtml;
});

captureHtmlToggle.addEventListener("change", () => {
  chrome.storage.local.set({ captureHtml: captureHtmlToggle.checked });
});

// -- init ----------------------------------------------------------------------

loadState();
