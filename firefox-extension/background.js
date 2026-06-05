// GeoGuessr Solver - Background Script (Firefox)

const browserAPI = typeof browser !== "undefined" ? browser : chrome;
let latestCoords = null;

browserAPI.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "COORDS_UPDATE") {
    latestCoords = message.data;
    browserAPI.browserAction.setBadgeText({ text: "📍" });
    browserAPI.browserAction.setBadgeBackgroundColor({ color: "#00ff88" });
  }

  if (message.type === "GET_LATEST_COORDS") {
    sendResponse({ coords: latestCoords });
  }

  return true;
});

browserAPI.tabs.onActivated.addListener(() => {
  latestCoords = null;
  browserAPI.browserAction.setBadgeText({ text: "" });
});
