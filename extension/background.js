// background.js
// Handles the Ctrl+Shift+U "grab now" shortcut - grabs the page without opening the popup.

const SERVER = "http://127.0.0.1:9999";

const SUPPORTED_PATTERNS = [
  { label: "Facebook Marketplace", test: url => /facebook\.com\/marketplace\/item\//i.test(url) },
  { label: "Amazon product",       test: url => /amazon\.[a-z.]+/i.test(url) && /\/dp\/|\/gp\/product\//i.test(url) },
];

function getSupportedSite(url) {
  return SUPPORTED_PATTERNS.find(p => p.test(url)) || null;
}

function notify(title, message) {
  chrome.notifications.create({
    type: "basic",
    iconUrl: "icons/icon48.png",
    title,
    message,
  });
}

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

  if (!getSupportedSite(tab.url || "")) {
    notify("Listing Grabber", "Not a supported page.\nOpen the product page of a supported website.");
    return;
  }

  try {
    const ok = await grabCurrentTab(tab.id);
    await chrome.action.setBadgeText({ text: ok ? "" : "ERR", tabId: tab.id });
    await chrome.action.setBadgeBackgroundColor({ color: ok ? "#2e7d32" : "#c62828", tabId: tab.id });
  } catch (e) {
    await chrome.action.setBadgeText({ text: "ERR", tabId: tab.id });
    await chrome.action.setBadgeBackgroundColor({ color: "#c62828", tabId: tab.id });
  }

  setTimeout(() => chrome.action.setBadgeText({ text: "", tabId: tab.id }), 2000);
});
