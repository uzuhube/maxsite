"""
GeoGuessr Solver — CDP Mode (100% accuracy, no proxy needed)

Connects to Steam's Chrome DevTools Protocol to intercept
GeoGuessr network traffic and extract exact coordinates.

Setup:
  1. Steam → GeoGuessr → Properties → Launch Options:
     --remote-debugging-port=34788 --remote-allow-origins=*
  2. pip install websocket-client requests Pillow
  3. python cdp_solver.py

How it works:
  - Connects to localhost:34788 (Steam's embedded Chromium)
  - Monitors network for Google Maps RPC responses
  - Extracts panorama IDs from responses
  - Resolves pano IDs to lat/lng via StreetViewService
  - Shows city/country in a transparent overlay
"""

import json
import re
import sys
import time
import threading
import webbrowser
import base64
from collections import deque

import requests

try:
    import websocket
except ImportError:
    print("[!] Missing: pip install websocket-client")
    sys.exit(1)

# ─── Configuration ───────────────────────────────────────────────────────────

CDP_PORT = 34788
CDP_TARGET_URL = f"http://localhost:{CDP_PORT}/json"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"

# Regex patterns for extracting panorama IDs from RPC responses
PANO_PATTERNS = [
    re.compile(r'\[2,\s*"([A-Za-z0-9_:\-]{16,96})"'),
    re.compile(r'\[2,\s*\\"([A-Za-z0-9_:\-]{16,96})\\"'),
    re.compile(r'(?i)(?:pano|panoid|pano_id|panoId)\\":\\"([A-Za-z0-9_:\-]{16,96})\\"'),
    re.compile(r'(?i)(?:pano|panoid|pano_id|panoId)":"([A-Za-z0-9_:\-]{16,96})"'),
]

# URLs that indicate Google Maps RPC traffic
MAPS_RPC_MARKERS = ["maps.googleapis.com/$rpc", "maps.googleapis.com"]


# ─── CDP Connection ──────────────────────────────────────────────────────────

class CDPConnection:
    """Manages WebSocket connection to Chrome DevTools Protocol."""

    def __init__(self, ws_url, on_coords_callback):
        self.ws_url = ws_url
        self.on_coords = on_coords_callback
        self.ws = None
        self.msg_id = 0
        self.pending = {}
        self.rpc_requests = {}  # request_id -> url
        self.last_coords = None
        self.resolved_panos = set()
        self.pano_queue = deque()
        self._lock = threading.Lock()
        self._running = False

    def connect(self):
        """Connect and start listening."""
        self._running = True
        self.ws = websocket.WebSocketApp(
            self.ws_url,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
            on_open=self._on_open,
        )
        self.ws.run_forever()

    def stop(self):
        self._running = False
        if self.ws:
            self.ws.close()

    def _send(self, method, params=None):
        """Send a CDP command and return its ID."""
        with self._lock:
            self.msg_id += 1
            msg_id = self.msg_id
        msg = {"id": msg_id, "method": method, "params": params or {}}
        self.ws.send(json.dumps(msg))
        return msg_id

    def _on_open(self, ws):
        """Enable network monitoring."""
        self._send("Network.enable")
        # Check if Google Maps is ready
        threading.Thread(target=self._prewarm_google_maps, daemon=True).start()

    def _on_error(self, ws, error):
        pass

    def _on_close(self, ws, close_code, close_msg):
        self._running = False

    def _on_message(self, ws, message):
        """Handle incoming CDP messages."""
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return

        # Response to our command
        if "id" in data:
            msg_id = data["id"]
            if msg_id in self.pending:
                callback = self.pending.pop(msg_id)
                callback(data.get("result", {}))
            return

        # Event from CDP
        method = data.get("method", "")
        params = data.get("params", {})

        if method == "Network.responseReceived":
            self._handle_response(params)
        elif method == "Network.loadingFinished":
            self._handle_loading_finished(params)
        elif method == "Network.loadingFailed":
            request_id = params.get("requestId", "")
            self.rpc_requests.pop(request_id, None)

    def _handle_response(self, params):
        """Remember RPC responses for later body fetching."""
        request_id = params.get("requestId", "")
        response = params.get("response", {})
        url = response.get("url", "")

        if any(marker in url for marker in MAPS_RPC_MARKERS):
            self.rpc_requests[request_id] = url

    def _handle_loading_finished(self, params):
        """Fetch body of completed RPC requests."""
        request_id = params.get("requestId", "")
        if request_id not in self.rpc_requests:
            return
        del self.rpc_requests[request_id]

        # Fetch response body
        def on_body(result):
            body = result.get("body", "")
            if result.get("base64Encoded"):
                try:
                    body = base64.b64decode(body).decode("utf-8", errors="ignore")
                except Exception:
                    return
            if body:
                self._extract_and_resolve_panos(body)

        msg_id = self._send("Network.getResponseBody", {"requestId": request_id})
        self.pending[msg_id] = on_body

    def _extract_and_resolve_panos(self, text):
        """Extract panorama IDs from response text."""
        seen = set()
        panos = []
        for pattern in PANO_PATTERNS:
            for match in pattern.finditer(text):
                pano_id = match.group(1)
                if pano_id not in seen and pano_id not in self.resolved_panos:
                    seen.add(pano_id)
                    panos.append(pano_id)

        if panos:
            # Resolve first new pano
            for pano in panos[:3]:
                threading.Thread(
                    target=self._resolve_pano, args=(pano,), daemon=True
                ).start()

    def _resolve_pano(self, pano_id):
        """Resolve a panorama ID to coordinates using StreetViewService."""
        if pano_id in self.resolved_panos:
            return
        self.resolved_panos.add(pano_id)

        # Build JavaScript to resolve pano
        escaped_pano = json.dumps(pano_id)
        script = f"""new Promise(resolve => {{
  try {{
    if (!window.google || !window.google.maps || !window.google.maps.StreetViewService) {{
      resolve(JSON.stringify({{ error: 'GOOGLE_MAPS_NOT_READY' }}));
      return;
    }}
    const sv = new window.google.maps.StreetViewService();
    sv.getPanorama({{ pano: {escaped_pano} }}, (data, status) => {{
      if (status === 'OK' && data && data.location && data.location.latLng) {{
        resolve(JSON.stringify({{
          lat: data.location.latLng.lat(),
          lng: data.location.latLng.lng(),
          description: data.location.description || ''
        }}));
      }} else {{
        resolve(JSON.stringify({{ error: status || 'NO_DATA' }}));
      }}
    }});
  }} catch (err) {{
    resolve(JSON.stringify({{ error: err.message }}));
  }}
}})"""

        # Send evaluate command
        result_event = threading.Event()
        result_data = [None]

        def on_result(result):
            value = result.get("result", {}).get("value", "")
            result_data[0] = value
            result_event.set()

        msg_id = self._send(
            "Runtime.evaluate",
            {
                "expression": script,
                "returnByValue": True,
                "awaitPromise": True,
            },
        )
        self.pending[msg_id] = on_result

        # Wait for result (max 5 seconds)
        if result_event.wait(timeout=5):
            raw = result_data[0]
            if raw:
                try:
                    data = json.loads(raw)
                    if "lat" in data and "lng" in data:
                        lat, lng = data["lat"], data["lng"]
                        if self._is_valid_coords(lat, lng):
                            self.last_coords = (lat, lng)
                            self.on_coords(lat, lng, data.get("description", ""))
                except (json.JSONDecodeError, KeyError):
                    pass

    def _is_valid_coords(self, lat, lng):
        """Validate coordinates."""
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            return False
        if lat == 0 and lng == 0:
            return False
        # Check if significantly different from last position
        if self.last_coords:
            prev_lat, prev_lng = self.last_coords
            if abs(lat - prev_lat) < 0.0001 and abs(lng - prev_lng) < 0.0001:
                return False
        return True

    def _prewarm_google_maps(self):
        """Check if Google Maps is loaded in the page."""
        time.sleep(1)
        script = "Boolean(window.google && window.google.maps && window.google.maps.StreetViewService)"
        for _ in range(10):
            try:
                msg_id = self._send(
                    "Runtime.evaluate",
                    {"expression": script, "returnByValue": True},
                )
                time.sleep(0.5)
            except Exception:
                time.sleep(1)


# ─── Target Discovery ────────────────────────────────────────────────────────

def find_geoguessr_target():
    """Find GeoGuessr page in CDP targets."""
    try:
        resp = requests.get(CDP_TARGET_URL, timeout=4)
    except requests.ConnectionError:
        return None, "not_running"
    except requests.Timeout:
        return None, "timeout"

    text = resp.text
    if "WebSockets request was expected" in text or "400 Bad Request" in text:
        return None, "missing_origins"

    try:
        targets = resp.json()
    except json.JSONDecodeError:
        return None, "missing_origins"

    # Priority: game iframe > game page > any geoguessr
    def is_geo(t):
        url = t.get("url", "")
        title = t.get("title", "")
        return "geoguessr.com" in url or "GeoGuessr" in title

    def is_game(t):
        url = t.get("url", "").lower()
        return any(x in url for x in ["/game", "/duels", "/battle", "/challenge", "/quiz", "/play"])

    game_targets = [t for t in targets if is_geo(t) and is_game(t) and t.get("webSocketDebuggerUrl")]
    geo_targets = [t for t in targets if is_geo(t) and t.get("webSocketDebuggerUrl")]

    # Prefer iframe type for game
    for t in game_targets:
        if t.get("type") == "iframe":
            return t, "ok"
    for t in game_targets:
        if t.get("type") == "page":
            return t, "ok"
    for t in geo_targets:
        return t, "ok"

    return None, "no_geoguessr"


# ─── Reverse Geocoding ────────────────────────────────────────────────────────

def reverse_geocode(lat, lng):
    """Get city/country from coordinates via Nominatim."""
    try:
        resp = requests.get(
            NOMINATIM_URL,
            params={
                "lat": lat,
                "lon": lng,
                "format": "json",
                "zoom": 10,
                "accept-language": "ru",
            },
            headers={"User-Agent": "GeoGuessrSolver/2.0"},
            timeout=5,
        )
        data = resp.json()
        addr = data.get("address", {})

        parts = []
        city = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("municipality")
        if city:
            parts.append(city)
        state = addr.get("state")
        if state and state != city:
            parts.append(state)
        country = addr.get("country")
        if country:
            parts.append(country)

        return ", ".join(parts) if parts else None
    except Exception:
        return None


# ─── GUI Overlay ──────────────────────────────────────────────────────────────

def create_overlay():
    """Create the main overlay window."""
    import tkinter as tk

    class SolverOverlay:
        def __init__(self):
            self.root = tk.Tk()
            self.root.title("GeoSolver")
            self.root.geometry("360x140+50+50")
            self.root.attributes("-topmost", True)
            self.root.attributes("-alpha", 0.88)
            self.root.overrideredirect(True)
            self.root.configure(bg="#0f0f1a")

            # Dragging
            self._drag_x = 0
            self._drag_y = 0
            self.root.bind("<ButtonPress-1>", self._start_drag)
            self.root.bind("<B1-Motion>", self._on_drag)
            self.root.bind("<ButtonPress-3>", lambda e: self._quit())

            # Main frame with border
            self.frame = tk.Frame(self.root, bg="#0f0f1a")
            self.frame.pack(fill="both", expand=True, padx=2, pady=2)
            self.frame.configure(highlightbackground="#6c3bff", highlightthickness=2)

            # Header bar
            header_frame = tk.Frame(self.frame, bg="#161625")
            header_frame.pack(fill="x")

            self.status_dot = tk.Label(
                header_frame,
                text="●",
                font=("Segoe UI", 8),
                fg="#ff4444",
                bg="#161625",
                padx=6,
            )
            self.status_dot.pack(side="left")

            self.header = tk.Label(
                header_frame,
                text="GeoSolver",
                font=("Segoe UI", 9, "bold"),
                fg="#a78bfa",
                bg="#161625",
                anchor="w",
            )
            self.header.pack(side="left", fill="x", expand=True)

            close_btn = tk.Label(
                header_frame,
                text="✕",
                font=("Segoe UI", 9),
                fg="#666",
                bg="#161625",
                padx=8,
                cursor="hand2",
            )
            close_btn.pack(side="right")
            close_btn.bind("<Button-1>", lambda e: self._quit())

            # Location display
            self.location_label = tk.Label(
                self.frame,
                text="Ожидание подключения...",
                font=("Segoe UI", 15, "bold"),
                fg="#ffffff",
                bg="#0f0f1a",
                anchor="w",
                padx=10,
                pady=6,
                wraplength=340,
                justify="left",
            )
            self.location_label.pack(fill="x")

            # Coords subtitle
            self.coords_label = tk.Label(
                self.frame,
                text="",
                font=("Consolas", 9),
                fg="#666688",
                bg="#0f0f1a",
                anchor="w",
                padx=10,
                pady=2,
            )
            self.coords_label.pack(fill="x")

            # Maps link
            self.maps_label = tk.Label(
                self.frame,
                text="",
                font=("Segoe UI", 9, "underline"),
                fg="#6c3bff",
                bg="#0f0f1a",
                cursor="hand2",
                anchor="w",
                padx=10,
                pady=2,
            )
            self.maps_label.pack(fill="x")

            self.coords = None
            self.cdp_thread = None
            self.cdp = None

            # Start CDP connection loop
            self.root.after(500, self._connect_loop)

        def _start_drag(self, event):
            self._drag_x = event.x
            self._drag_y = event.y

        def _on_drag(self, event):
            x = self.root.winfo_x() + event.x - self._drag_x
            y = self.root.winfo_y() + event.y - self._drag_y
            self.root.geometry(f"+{x}+{y}")

        def _quit(self):
            if self.cdp:
                self.cdp.stop()
            self.root.destroy()

        def _connect_loop(self):
            """Try to connect to CDP."""
            target, status = find_geoguessr_target()

            if status == "not_running":
                self._set_status("disconnected", "Steam не запущен или нет флагов CDP")
                self.root.after(3000, self._connect_loop)
                return
            elif status == "missing_origins":
                self._set_status("error", "Добавьте --remote-allow-origins=*")
                self.root.after(3000, self._connect_loop)
                return
            elif status == "no_geoguessr":
                self._set_status("waiting", "Запустите GeoGuessr в Steam")
                self.root.after(2000, self._connect_loop)
                return
            elif status == "timeout":
                self._set_status("disconnected", "Таймаут подключения к CDP")
                self.root.after(3000, self._connect_loop)
                return

            # Connected!
            ws_url = target.get("webSocketDebuggerUrl", "")
            title = target.get("title", "") or target.get("url", "")
            self._set_status("connected", f"Подключено: {title[:40]}")

            self.cdp = CDPConnection(ws_url, self._on_coords_found)
            self.cdp_thread = threading.Thread(target=self.cdp.connect, daemon=True)
            self.cdp_thread.start()

            # Monitor connection
            self.root.after(5000, self._check_connection)

        def _check_connection(self):
            """Check if CDP is still connected."""
            if self.cdp and not self.cdp._running:
                self._set_status("disconnected", "Соединение потеряно")
                self.cdp = None
                self.root.after(3000, self._connect_loop)
            else:
                self.root.after(5000, self._check_connection)

        def _on_coords_found(self, lat, lng, description=""):
            """Called from CDP thread when coords are found."""
            self.coords = (lat, lng)
            # Update UI from main thread
            self.root.after(0, lambda: self._update_location(lat, lng, description))

        def _update_location(self, lat, lng, description=""):
            """Update overlay with new location."""
            self.coords_label.config(text=f"{lat:.5f}, {lng:.5f}")
            self.maps_label.config(text="🗺 Открыть Google Maps")
            self.maps_label.bind("<Button-1>", lambda e: self._open_maps())

            if description:
                self.location_label.config(text=f"📍 {description}", fg="#e0e0ff")
            else:
                self.location_label.config(text="📍 Определяю...", fg="#aaaacc")

            # Reverse geocode in background
            threading.Thread(
                target=self._geocode, args=(lat, lng), daemon=True
            ).start()

        def _geocode(self, lat, lng):
            """Reverse geocode and update label."""
            location = reverse_geocode(lat, lng)
            if location:
                self.root.after(
                    0, lambda: self.location_label.config(text=f"📍 {location}", fg="#e0e0ff")
                )

        def _open_maps(self):
            if self.coords:
                url = f"https://www.google.com/maps?q={self.coords[0]},{self.coords[1]}"
                webbrowser.open(url)

        def _set_status(self, state, text):
            """Update status indicator."""
            colors = {
                "connected": "#00ff88",
                "waiting": "#ffaa00",
                "disconnected": "#ff4444",
                "error": "#ff4444",
            }
            self.status_dot.config(fg=colors.get(state, "#888"))
            self.location_label.config(text=text, fg="#888899")
            self.coords_label.config(text="")
            self.maps_label.config(text="")

        def run(self):
            self.root.mainloop()

    return SolverOverlay()


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 50)
    print("  GeoSolver — CDP Mode (100% accuracy)")
    print("=" * 50)
    print()
    print("Настройка Steam:")
    print("  GeoGuessr → Свойства → Параметры запуска:")
    print("  --remote-debugging-port=34788 --remote-allow-origins=*")
    print()
    print("Управление:")
    print("  ЛКМ — перетащить оверлей")
    print("  ПКМ — закрыть")
    print()

    overlay = create_overlay()
    overlay.run()


if __name__ == "__main__":
    main()
