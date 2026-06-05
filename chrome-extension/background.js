// GeoGuessr Solver - Background Service Worker

let latestCoords = null;

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "COORDS_UPDATE") {
    latestCoords = message.data;
    // Update badge
    chrome.action.setBadgeText({ text: "📍" });
    chrome.action.setBadgeBackgroundColor({ color: "#00ff88" });
  }

  if (message.type === "GET_LATEST_COORDS") {
    sendResponse({ coords: latestCoords });
  }

  return true;
});

// Clear badge when tab changes
chrome.tabs.onActivated.addListener(() => {
  latestCoords = null;
  chrome.action.setBadgeText({ text: "" });
});
