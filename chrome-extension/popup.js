// GeoGuessr Solver - Popup Script

document.addEventListener("DOMContentLoaded", () => {
  const statusEl = document.getElementById("status");
  const coordsSection = document.getElementById("coords-section");
  const latEl = document.getElementById("lat");
  const lngEl = document.getElementById("lng");
  const countryEl = document.getElementById("country");
  const mapsLink = document.getElementById("maps-link");
  const copyBtn = document.getElementById("copy-btn");
  const toggleOverlay = document.getElementById("toggle-overlay");

  let currentCoords = null;

  function updateUI(coords) {
    if (!coords) {
      statusEl.className = "status waiting";
      statusEl.textContent = "Ожидание... Откройте игру GeoGuessr";
      coordsSection.style.display = "none";
      return;
    }

    currentCoords = coords;
    statusEl.className = "status found";
    statusEl.textContent = "✓ Координаты найдены!";
    coordsSection.style.display = "block";
    latEl.textContent = coords.lat.toFixed(6);
    lngEl.textContent = coords.lng.toFixed(6);
    mapsLink.href = `https://www.google.com/maps?q=${coords.lat},${coords.lng}`;

    // Reverse geocode for country name
    reverseGeocode(coords.lat, coords.lng);
  }

  async function reverseGeocode(lat, lng) {
    try {
      const response = await fetch(
        `https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lng}&format=json&zoom=5`
      );
      const data = await response.json();
      if (data.address) {
        const parts = [];
        if (data.address.country) parts.push(data.address.country);
        if (data.address.state) parts.push(data.address.state);
        if (data.address.city || data.address.town)
          parts.push(data.address.city || data.address.town);

        if (parts.length > 0) {
          countryEl.textContent = parts.reverse().join(", ");
          countryEl.style.display = "block";
        }
      }
    } catch (e) {
      // Reverse geocoding failed, not critical
    }
  }

  // Get coords from content script
  function fetchCoords() {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs[0]?.url?.includes("geoguessr.com")) {
        chrome.tabs.sendMessage(
          tabs[0].id,
          { type: "GET_COORDS" },
          (response) => {
            if (chrome.runtime.lastError) {
              // Content script not loaded yet
              return;
            }
            if (response?.coords) {
              updateUI(response.coords);
            }
          }
        );
      } else {
        statusEl.className = "status waiting";
        statusEl.textContent = "Откройте GeoGuessr для начала";
      }
    });

    // Also check background for latest coords
    chrome.runtime.sendMessage(
      { type: "GET_LATEST_COORDS" },
      (response) => {
        if (response?.coords) {
          updateUI(response.coords);
        }
      }
    );
  }

  // Copy coordinates
  copyBtn.addEventListener("click", () => {
    if (currentCoords) {
      navigator.clipboard.writeText(
        `${currentCoords.lat}, ${currentCoords.lng}`
      );
      copyBtn.textContent = "✓ Скопировано!";
      setTimeout(() => {
        copyBtn.textContent = "📋 Копировать координаты";
      }, 2000);
    }
  });

  // Toggle overlay
  toggleOverlay.addEventListener("click", () => {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs[0]) {
        chrome.tabs.sendMessage(tabs[0].id, { type: "TOGGLE_OVERLAY" });
      }
    });
  });

  // Initial fetch and poll
  fetchCoords();
  setInterval(fetchCoords, 2000);

  // Listen for updates from background
  chrome.runtime.onMessage.addListener((message) => {
    if (message.type === "COORDS_UPDATE") {
      updateUI(message.data);
    }
  });
});
