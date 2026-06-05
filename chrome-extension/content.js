// GeoGuessr Solver - Content Script
// Extracts location coordinates from Google Street View on GeoGuessr pages

(function () {
  "use strict";

  let lastCoords = null;
  let overlay = null;

  // Method 1: Hook into Google Maps API coverage/panorama requests
  function hookXHR() {
    const originalOpen = XMLHttpRequest.prototype.open;
    const originalSend = XMLHttpRequest.prototype.send;

    XMLHttpRequest.prototype.open = function (method, url, ...args) {
      this._url = url;
      return originalOpen.call(this, method, url, ...args);
    };

    XMLHttpRequest.prototype.send = function (...args) {
      this.addEventListener("load", function () {
        try {
          if (this._url && isGoogleMapsRequest(this._url)) {
            parseResponse(this.responseText, this._url);
          }
        } catch (e) {
          // Silent fail
        }
      });
      return originalSend.call(this, ...args);
    };
  }

  // Method 2: Hook fetch API
  function hookFetch() {
    const originalFetch = window.fetch;
    window.fetch = function (...args) {
      const url = typeof args[0] === "string" ? args[0] : args[0]?.url || "";
      const promise = originalFetch.apply(this, args);

      if (isGoogleMapsRequest(url)) {
        promise
          .then((response) => response.clone().text())
          .then((text) => {
            parseResponse(text, url);
          })
          .catch(() => {});
      }

      return promise;
    };
  }

  // Method 3: Monitor Google Maps objects directly
  function pollGoogleMaps() {
    setInterval(() => {
      try {
        // Try to find the panorama element and extract position
        const coords = extractFromDOM();
        if (coords && coordsChanged(coords)) {
          lastCoords = coords;
          updateOverlay(coords);
          sendToPopup(coords);
        }
      } catch (e) {
        // Silent fail
      }
    }, 1000);
  }

  function isGoogleMapsRequest(url) {
    return (
      url.includes("maps.googleapis.com") ||
      url.includes("google.com/maps") ||
      url.includes("cbk0.google.com") ||
      url.includes("geo0.ggpht.com") ||
      url.includes("streetviewpixels") ||
      url.includes("GeoPhotoService") ||
      url.includes("SingleImageSearch")
    );
  }

  function parseResponse(text, url) {
    if (!text) return;

    // Pattern 1: Look for coordinate arrays [lat, lng] in response
    // Google Maps responses often contain coordinates in arrays
    const coordPatterns = [
      /\[\[null,null,(-?\d+\.\d+),(-?\d+\.\d+)\]/g,
      /\[(-?\d+\.\d{4,}),(-?\d+\.\d{4,})\]/g,
      /"lat"\s*:\s*(-?\d+\.\d+).*?"lng"\s*:\s*(-?\d+\.\d+)/g,
      /ll=(-?\d+\.\d+),(-?\d+\.\d+)/g,
    ];

    for (const pattern of coordPatterns) {
      let match;
      while ((match = pattern.exec(text)) !== null) {
        const lat = parseFloat(match[1]);
        const lng = parseFloat(match[2]);

        if (isValidCoord(lat, lng)) {
          const coords = { lat, lng };
          if (coordsChanged(coords)) {
            lastCoords = coords;
            updateOverlay(coords);
            sendToPopup(coords);
          }
          return;
        }
      }
    }

    // Pattern 2: Search in protobuf-like response (common in Google APIs)
    try {
      const numbers = text.match(/-?\d+\.\d{5,}/g);
      if (numbers && numbers.length >= 2) {
        for (let i = 0; i < numbers.length - 1; i++) {
          const lat = parseFloat(numbers[i]);
          const lng = parseFloat(numbers[i + 1]);
          if (isValidCoord(lat, lng)) {
            const coords = { lat, lng };
            if (coordsChanged(coords)) {
              lastCoords = coords;
              updateOverlay(coords);
              sendToPopup(coords);
            }
            return;
          }
        }
      }
    } catch (e) {
      // Silent fail
    }
  }

  function extractFromDOM() {
    // Try to extract coordinates from various GeoGuessr page elements
    // Method A: Check for Google Maps script variables
    const scripts = document.querySelectorAll("script");
    for (const script of scripts) {
      const content = script.textContent;
      if (content.includes("google.maps") || content.includes("LatLng")) {
        const match = content.match(
          /LatLng\((-?\d+\.\d+),\s*(-?\d+\.\d+)\)/
        );
        if (match) {
          return { lat: parseFloat(match[1]), lng: parseFloat(match[2]) };
        }
      }
    }

    // Method B: Check meta tags or data attributes
    const metaTags = document.querySelectorAll(
      'meta[content*="geo"], [data-lat], [data-lng]'
    );
    for (const tag of metaTags) {
      const lat = tag.getAttribute("data-lat");
      const lng = tag.getAttribute("data-lng");
      if (lat && lng) {
        return { lat: parseFloat(lat), lng: parseFloat(lng) };
      }
    }

    // Method C: Look for canvas/iframe with Google Maps
    const iframes = document.querySelectorAll("iframe");
    for (const iframe of iframes) {
      const src = iframe.src || "";
      const match = src.match(
        /[@!](-?\d+\.\d+)[,!](-?\d+\.\d+)|center=(-?\d+\.\d+),(-?\d+\.\d+)/
      );
      if (match) {
        const lat = parseFloat(match[1] || match[3]);
        const lng = parseFloat(match[2] || match[4]);
        if (isValidCoord(lat, lng)) {
          return { lat, lng };
        }
      }
    }

    return null;
  }

  function isValidCoord(lat, lng) {
    return (
      lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180 && lat !== 0 && lng !== 0
    );
  }

  function coordsChanged(newCoords) {
    if (!lastCoords) return true;
    return (
      Math.abs(newCoords.lat - lastCoords.lat) > 0.0001 ||
      Math.abs(newCoords.lng - lastCoords.lng) > 0.0001
    );
  }

  function createOverlay() {
    if (overlay) return overlay;

    overlay = document.createElement("div");
    overlay.id = "geoguessr-solver-overlay";
    overlay.style.cssText = `
      position: fixed;
      top: 10px;
      right: 10px;
      background: rgba(0, 0, 0, 0.85);
      color: #00ff88;
      padding: 12px 16px;
      border-radius: 8px;
      font-family: 'Courier New', monospace;
      font-size: 14px;
      z-index: 999999;
      min-width: 250px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.5);
      border: 1px solid #00ff88;
      cursor: move;
      user-select: none;
      display: none;
    `;

    // Make draggable
    let isDragging = false;
    let offsetX, offsetY;
    overlay.addEventListener("mousedown", (e) => {
      isDragging = true;
      offsetX = e.clientX - overlay.offsetLeft;
      offsetY = e.clientY - overlay.offsetTop;
    });
    document.addEventListener("mousemove", (e) => {
      if (isDragging) {
        overlay.style.left = e.clientX - offsetX + "px";
        overlay.style.right = "auto";
        overlay.style.top = e.clientY - offsetY + "px";
      }
    });
    document.addEventListener("mouseup", () => {
      isDragging = false;
    });

    document.body.appendChild(overlay);
    return overlay;
  }

  function updateOverlay(coords) {
    const ov = createOverlay();
    const country = guessCountryFromPage();
    const mapsLink = `https://www.google.com/maps?q=${coords.lat},${coords.lng}`;

    ov.innerHTML = `
      <div style="margin-bottom: 6px; font-weight: bold; color: #fff; font-size: 16px;">
        📍 GeoGuessr Solver
      </div>
      <div style="margin-bottom: 4px;">
        <span style="color: #aaa;">Lat:</span> ${coords.lat.toFixed(6)}
      </div>
      <div style="margin-bottom: 4px;">
        <span style="color: #aaa;">Lng:</span> ${coords.lng.toFixed(6)}
      </div>
      ${country ? `<div style="margin-bottom: 4px; color: #ffcc00;">${country}</div>` : ""}
      <div style="margin-top: 8px;">
        <a href="${mapsLink}" target="_blank" style="color: #00aaff; text-decoration: none; font-size: 12px;">
          🗺️ Open in Google Maps
        </a>
      </div>
    `;
    ov.style.display = "block";
  }

  function guessCountryFromPage() {
    // Try to extract any country hints from the page
    try {
      const text = document.body.innerText;
      // Check for round info elements
      const roundInfo = document.querySelector(
        '[class*="round-info"], [class*="country"], [data-qa="round-info"]'
      );
      if (roundInfo) {
        return roundInfo.textContent.trim();
      }
    } catch (e) {
      // Silent
    }
    return null;
  }

  function sendToPopup(coords) {
    chrome.runtime.sendMessage({
      type: "COORDS_UPDATE",
      data: coords,
    });
  }

  // Listen for messages from popup
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === "GET_COORDS") {
      sendResponse({ coords: lastCoords });
    }
    if (message.type === "TOGGLE_OVERLAY") {
      if (overlay) {
        overlay.style.display =
          overlay.style.display === "none" ? "block" : "none";
      }
    }
  });

  // Initialize
  function init() {
    // Inject hooks via page script to access page's JS context
    const script = document.createElement("script");
    script.textContent = `
      (function() {
        // Hook into XMLHttpRequest
        const origOpen = XMLHttpRequest.prototype.open;
        const origSend = XMLHttpRequest.prototype.send;
        
        XMLHttpRequest.prototype.open = function(method, url) {
          this.__url = url;
          return origOpen.apply(this, arguments);
        };
        
        XMLHttpRequest.prototype.send = function() {
          this.addEventListener('load', function() {
            if (this.__url && (
              this.__url.includes('maps.googleapis.com') ||
              this.__url.includes('cbk0.google.com') ||
              this.__url.includes('GeoPhotoService') ||
              this.__url.includes('SingleImageSearch') ||
              this.__url.includes('streetviewpixels')
            )) {
              window.postMessage({
                type: '__GEOSOLVER_XHR__',
                url: this.__url,
                response: this.responseText
              }, '*');
            }
          });
          return origSend.apply(this, arguments);
        };

        // Hook fetch
        const origFetch = window.fetch;
        window.fetch = function() {
          const url = typeof arguments[0] === 'string' ? arguments[0] : (arguments[0]?.url || '');
          const result = origFetch.apply(this, arguments);
          
          if (url.includes('maps.googleapis.com') ||
              url.includes('cbk0.google.com') ||
              url.includes('GeoPhotoService') ||
              url.includes('SingleImageSearch')) {
            result.then(r => r.clone().text()).then(text => {
              window.postMessage({
                type: '__GEOSOLVER_XHR__',
                url: url,
                response: text
              }, '*');
            }).catch(() => {});
          }
          
          return result;
        };

        // Try to access Google Maps Panorama object directly
        setInterval(() => {
          try {
            if (window.google && window.google.maps) {
              const svs = document.querySelector('[class*="streetview"], canvas, .widget-scene');
              if (svs) {
                // Look for __gm property on map elements
                const mapElements = document.querySelectorAll('[__gm]');
                for (const el of mapElements) {
                  const map = el.__gm?.map;
                  if (map) {
                    const sv = map.getStreetView?.();
                    if (sv) {
                      const pos = sv.getPosition?.();
                      if (pos) {
                        window.postMessage({
                          type: '__GEOSOLVER_DIRECT__',
                          lat: pos.lat(),
                          lng: pos.lng()
                        }, '*');
                      }
                    }
                  }
                }
              }
            }
          } catch(e) {}
        }, 2000);
      })();
    `;
    document.documentElement.appendChild(script);
    script.remove();

    // Listen for messages from injected script
    window.addEventListener("message", (event) => {
      if (event.data.type === "__GEOSOLVER_XHR__") {
        parseResponse(event.data.response, event.data.url);
      }
      if (event.data.type === "__GEOSOLVER_DIRECT__") {
        const coords = { lat: event.data.lat, lng: event.data.lng };
        if (isValidCoord(coords.lat, coords.lng) && coordsChanged(coords)) {
          lastCoords = coords;
          updateOverlay(coords);
          sendToPopup(coords);
        }
      }
    });

    // Also poll DOM
    pollGoogleMaps();
  }

  // Start when page is ready
  if (document.readyState === "complete") {
    init();
  } else {
    window.addEventListener("load", init);
  }
})();
