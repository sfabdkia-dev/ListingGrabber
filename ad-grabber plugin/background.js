// background.js
// Handles the Ctrl+Shift+G "grab now" shortcut — grabs the page without opening the popup.

const SERVER = "http://127.0.0.1:9999";

async function grabCurrentTab(tabId) {
  const { captureHtml } = await chrome.storage.local.get({ captureHtml: false });
  const [{ result: payload }] = await chrome.scripting.executeScript({
    target: { tabId },
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

  return res.ok;
}

chrome.commands.onCommand.addListener(async (command) => {
  if (command !== "grab_now") return;

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) return;

  try {
    const ok = await grabCurrentTab(tab.id);
    await chrome.action.setBadgeText({ text: ok ? "✓" : "ERR", tabId: tab.id });
    await chrome.action.setBadgeBackgroundColor({ color: ok ? "#2e7d32" : "#c62828", tabId: tab.id });
  } catch {
    await chrome.action.setBadgeText({ text: "ERR", tabId: tab.id });
    await chrome.action.setBadgeBackgroundColor({ color: "#c62828", tabId: tab.id });
  }

  setTimeout(() => chrome.action.setBadgeText({ text: "", tabId: tab.id }), 2000);
});
