"""
GeoGuessr Solver — CDP Mode (100% accuracy, no proxy needed)

Connects to Steam's Chrome DevTools Protocol to intercept
GeoGuessr network traffic and extract exact coordinates.

Setup:
  1. Steam → GeoGuessr → Properties → Launch Options:
     --remote-debugging-port=34788 --remote-allow-origins=*
  2. pip install websocket-client requests
  3. python cdp_solver.py
"""

import json
import re
import sys
import time
import threading
import webbrowser
import base64
import traceback

import requests

try:
    import websocket
except ImportError:
    print("[!] Нужно: pip install websocket-client")
    sys.exit(1)

# ─── Configuration ───────────────────────────────────────────────────────────

CDP_PORT = 34788
CDP_TARGET_URL = f"http://localhost:{CDP_PORT}/json"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"

# Panorama ID patterns (from GeoHelper's approach)
PANO_PATTERNS = [
    re.compile(r'\[2,\s*"([A-Za-z0-9_:\-]{16,96})"'),
    re.compile(r'\[2,\s*\\"([A-Za-z0-9_:\-]{16,96})\\"'),
    re.compile(r'(?i)(?:pano|panoid|pano_id|panoId)\\":\\"([A-Za-z0-9_:\-]{16,96})\\"'),
    re.compile(r'(?i)(?:pano|panoid|pano_id|panoId)":"([A-Za-z0-9_:\-]{16,96})"'),
]

# Direct coordinate patterns (backup)
COORD_PATTERNS = [
    re.compile(r'\[\[null,null,(-?\d+\.\d{4,}),(-?\d+\.\d{4,})\]'),
    re.compile(r'"lat"\s*:\s*(-?\d+\.\d{4,}).*?"lng"\s*:\s*(-?\d+\.\d{4,})'),
]


# ─── Logging ──────────────────────────────────────────────────────────────────

def log(level, msg):
    prefix = {"info": "[*]", "ok": "[+]", "err": "[!]", "data": "[>]"}
    print(f"{prefix.get(level, '[?]')} {msg}")


# ─── CDP Connection ──────────────────────────────────────────────────────────

class CDPClient:
    """Synchronous CDP client using websocket-client with threading."""

    def __init__(self, ws_url, on_coords):
        self.ws_url = ws_url
        self.on_coords = on_coords
        self.ws = None
        self._msg_id = 0
        self._lock = threading.Lock()
        self._responses = {}  # msg_id -> threading.Event, result
        self._response_data = {}  # msg_id -> result data
        self._rpc_requests = {}  # request_id -> url
        self._resolved_panos = set()
        self._last_coords = None
        self._running = False
        self._connected = False

    @property
    def connected(self):
        return self._connected

    def start(self):
        """Start connection in background thread."""
        self._running = True
        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()

    def stop(self):
        self._running = False
        self._connected = False
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass

    def _next_id(self):
        with self._lock:
            self._msg_id += 1
            return self._msg_id

    def _send_command(self, method, params=None, timeout=10):
        """Send CDP command and wait for response."""
        if not self.ws or not self._connected:
            return None

        msg_id = self._next_id()
        event = threading.Event()
        self._responses[msg_id] = event
        self._response_data[msg_id] = None

        payload = json.dumps({"id": msg_id, "method": method, "params": params or {}})
        try:
            self.ws.send(payload)
        except Exception:
            self._responses.pop(msg_id, None)
            return None

        if event.wait(timeout=timeout):
            result = self._response_data.pop(msg_id, None)
            self._responses.pop(msg_id, None)
            return result
        else:
            self._responses.pop(msg_id, None)
            self._response_data.pop(msg_id, None)
            return None

    def _send_command_async(self, method, params=None):
        """Send CDP command without waiting for response (fire-and-forget)."""
        if not self.ws or not self._connected:
            return None

        msg_id = self._next_id()
        payload = json.dumps({"id": msg_id, "method": method, "params": params or {}})
        try:
            self.ws.send(payload)
        except Exception:
            pass
        return msg_id

    def _run(self):
        """Main WebSocket connection loop."""
        self.ws = websocket.WebSocket()
        self.ws.settimeout(1.0)

        try:
            self.ws.connect(self.ws_url)
            self._connected = True
            log("ok", "CDP WebSocket подключен")

            # Enable network monitoring
            self._send_command("Network.enable")
            log("info", "Network мониторинг включен")

            # Main read loop
            while self._running:
                try:
                    data = self.ws.recv()
                    if data:
                        self._handle_message(data)
                except websocket.WebSocketTimeoutException:
                    continue
                except websocket.WebSocketConnectionClosedException:
                    log("err", "WebSocket соединение закрыто")
                    break
                except Exception as e:
                    if self._running:
                        log("err", f"WebSocket ошибка: {e}")
                    break

        except Exception as e:
            log("err", f"Не удалось подключиться: {e}")
        finally:
            self._connected = False
            self._running = False

    def _handle_message(self, raw):
        """Process incoming CDP message."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return

        # Response to our command
        if "id" in data:
            msg_id = data["id"]
            if msg_id in self._responses:
                self._response_data[msg_id] = data.get("result")
                self._responses[msg_id].set()
            return

        # CDP Event
        method = data.get("method", "")
        params = data.get("params", {})

        if method == "Network.responseReceived":
            request_id = params.get("requestId", "")
            url = params.get("response", {}).get("url", "")
            if self._is_maps_rpc(url):
                self._rpc_requests[request_id] = url
                log("data", f"Maps RPC: {url[:80]}")

        elif method == "Network.loadingFinished":
            request_id = params.get("requestId", "")
            if request_id in self._rpc_requests:
                del self._rpc_requests[request_id]
                # Fetch body in background
                threading.Thread(
                    target=self._fetch_and_process_body,
                    args=(request_id,),
                    daemon=True,
                ).start()

        elif method == "Network.loadingFailed":
            request_id = params.get("requestId", "")
            self._rpc_requests.pop(request_id, None)

    def _is_maps_rpc(self, url):
        """Check if URL is a Google Maps RPC request."""
        return (
            "maps.googleapis.com/$rpc" in url
            or "maps.googleapis.com" in url
            and ("SingleImageSearch" in url or "GeoPhotoService" in url or "$rpc" in url)
        )

    def _fetch_and_process_body(self, request_id):
        """Fetch response body and extract pano IDs."""
        result = self._send_command(
            "Network.getResponseBody",
            {"requestId": request_id},
            timeout=5,
        )
        if not result:
            return

        body = result.get("body", "")
        if result.get("base64Encoded"):
            try:
                body = base64.b64decode(body).decode("utf-8", errors="ignore")
            except Exception:
                return

        if not body:
            return

        # Try to extract pano IDs
        panos = self._extract_panos(body)
        if panos:
            log("data", f"Найдено {len(panos)} pano ID: {panos[0][:20]}...")
            for pano_id in panos[:3]:
                if pano_id not in self._resolved_panos:
                    self._resolved_panos.add(pano_id)
                    threading.Thread(
                        target=self._resolve_pano,
                        args=(pano_id,),
                        daemon=True,
                    ).start()

        # Also try direct coordinate extraction
        coords = self._extract_coords_direct(body)
        if coords:
            lat, lng = coords
            if self._validate_coords(lat, lng):
                log("ok", f"Координаты из тела: {lat:.5f}, {lng:.5f}")
                self._last_coords = (lat, lng)
                self.on_coords(lat, lng)

    def _extract_panos(self, text):
        """Extract panorama IDs from response text."""
        seen = set()
        panos = []
        for pattern in PANO_PATTERNS:
            for match in pattern.finditer(text):
                pano_id = match.group(1)
                if pano_id not in seen:
                    seen.add(pano_id)
                    panos.append(pano_id)
        return panos

    def _extract_coords_direct(self, text):
        """Try to extract coordinates directly from response body."""
        for pattern in COORD_PATTERNS:
            match = pattern.search(text)
            if match:
                try:
                    lat = float(match.group(1))
                    lng = float(match.group(2))
                    if self._validate_coords(lat, lng):
                        return (lat, lng)
                except (ValueError, IndexError):
                    continue
        return None

    def _resolve_pano(self, pano_id):
        """Resolve panorama ID to coordinates via StreetViewService."""
        escaped = json.dumps(pano_id)
        script = f"""
(function() {{
  try {{
    if (!window.google || !window.google.maps || !window.google.maps.StreetViewService) {{
      return JSON.stringify({{error: 'MAPS_NOT_READY'}});
    }}
    return new Promise(function(resolve) {{
      var sv = new window.google.maps.StreetViewService();
      sv.getPanorama({{pano: {escaped}}}, function(data, status) {{
        if (status === 'OK' && data && data.location && data.location.latLng) {{
          resolve(JSON.stringify({{
            lat: data.location.latLng.lat(),
            lng: data.location.latLng.lng(),
            desc: data.location.description || ''
          }}));
        }} else {{
          resolve(JSON.stringify({{error: status || 'NO_DATA'}}));
        }}
      }});
    }});
  }} catch(e) {{
    return JSON.stringify({{error: e.message}});
  }}
}})()"""

        result = self._send_command(
            "Runtime.evaluate",
            {
                "expression": script,
                "returnByValue": True,
                "awaitPromise": True,
            },
            timeout=8,
        )

        if not result:
            log("err", f"Pano resolve timeout: {pano_id[:20]}")
            return

        raw_value = ""
        res = result.get("result", {})
        if res.get("type") == "string":
            raw_value = res.get("value", "")
        elif res.get("value"):
            raw_value = str(res.get("value", ""))

        if not raw_value:
            # Try exceptionDetails
            exc = result.get("exceptionDetails")
            if exc:
                log("err", f"JS ошибка: {exc.get('text', 'unknown')}")
            return

        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError:
            log("err", f"Не удалось разобрать ответ: {raw_value[:60]}")
            return

        if "error" in parsed:
            error = parsed["error"]
            if error == "MAPS_NOT_READY":
                log("info", "Google Maps ещё не загружен в игре")
                # Remove from resolved so we can retry later
                self._resolved_panos.discard(pano_id)
            else:
                log("info", f"Pano resolve: {error}")
            return

        lat = parsed.get("lat")
        lng = parsed.get("lng")
        if lat is not None and lng is not None and self._validate_coords(lat, lng):
            log("ok", f"КООРДИНАТЫ: {lat:.6f}, {lng:.6f}")
            self._last_coords = (lat, lng)
            self.on_coords(lat, lng)

    def _validate_coords(self, lat, lng):
        """Check if coordinates are valid and different from last."""
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            return False
        if lat == 0 and lng == 0:
            return False
        if self._last_coords:
            prev_lat, prev_lng = self._last_coords
            if abs(lat - prev_lat) < 0.0001 and abs(lng - prev_lng) < 0.0001:
                return False
        return True


# ─── Target Discovery ────────────────────────────────────────────────────────

def find_target():
    """Find the best CDP target for GeoGuessr."""
    try:
        resp = requests.get(CDP_TARGET_URL, timeout=4)
    except requests.ConnectionError:
        return None, "not_running"
    except requests.Timeout:
        return None, "timeout"

    text = resp.text.strip()

    # Check for missing --remote-allow-origins=*
    if "WebSockets request was expected" in text or "400 Bad Request" in text:
        return None, "missing_origins"

    try:
        targets = resp.json()
    except (json.JSONDecodeError, ValueError):
        return None, "missing_origins"

    if not isinstance(targets, list):
        return None, "invalid_response"

    log("info", f"Найдено {len(targets)} CDP targets")

    # Log all targets for debugging
    for t in targets:
        title = t.get("title", "")[:40]
        url = t.get("url", "")[:60]
        ttype = t.get("type", "")
        has_ws = bool(t.get("webSocketDebuggerUrl"))
        log("info", f"  [{ttype}] {title or url} {'(ws)' if has_ws else ''}")

    def is_geo(t):
        url = t.get("url", "").lower()
        title = t.get("title", "").lower()
        return "geoguessr" in url or "geoguessr" in title

    def is_game(t):
        url = t.get("url", "").lower()
        return any(x in url for x in [
            "/game/", "/duels/", "/battle/", "/challenge/",
            "/quiz/", "/play/", "/game?", "/round"
        ])

    def has_ws(t):
        return bool(t.get("webSocketDebuggerUrl"))

    # Priority: game page/iframe > any geoguessr page > any page with ws
    game_geo = [t for t in targets if is_geo(t) and is_game(t) and has_ws(t)]
    any_geo = [t for t in targets if is_geo(t) and has_ws(t)]
    any_page = [t for t in targets if t.get("type") == "page" and has_ws(t)]

    # Pick the best target
    picked = None
    if game_geo:
        picked = game_geo[0]
        log("ok", f"Цель: игровая страница GeoGuessr")
    elif any_geo:
        picked = any_geo[0]
        log("ok", f"Цель: страница GeoGuessr")
    elif any_page:
        # Even non-geoguessr pages might be useful if it's the only game page
        picked = any_page[0]
        log("info", f"Цель: {picked.get('title', picked.get('url', ''))[:50]}")

    if not picked:
        return None, "no_geoguessr"

    return picked, "ok"


# ─── Reverse Geocoding ────────────────────────────────────────────────────────

def reverse_geocode(lat, lng):
    """Get city/country name from coordinates."""
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
            headers={"User-Agent": "GeoSolver/2.0"},
            timeout=5,
        )
        data = resp.json()
        addr = data.get("address", {})
        parts = []
        city = (
            addr.get("city") or addr.get("town") or
            addr.get("village") or addr.get("municipality")
        )
        if city:
            parts.append(city)
        state = addr.get("state")
        if state and state != city:
            parts.append(state)
        country = addr.get("country")
        if country:
            parts.append(country)
        return ", ".join(parts) if parts else f"{lat:.4f}, {lng:.4f}"
    except Exception:
        return f"{lat:.4f}, {lng:.4f}"


# ─── GUI Overlay ──────────────────────────────────────────────────────────────

def create_overlay():
    """Create the overlay application."""
    import tkinter as tk

    class SolverApp:
        def __init__(self):
            self.root = tk.Tk()
            self.root.title("GeoSolver")
            self.root.geometry("380x130+50+50")
            self.root.attributes("-topmost", True)
            self.root.attributes("-alpha", 0.90)
            self.root.overrideredirect(True)
            self.root.configure(bg="#0d0d1a")

            # Dragging
            self._dx = 0
            self._dy = 0
            self.root.bind("<ButtonPress-1>", self._drag_start)
            self.root.bind("<B1-Motion>", self._drag_move)

            # Main frame
            self.frame = tk.Frame(self.root, bg="#0d0d1a")
            self.frame.pack(fill="both", expand=True, padx=2, pady=2)
            self.frame.configure(highlightbackground="#7c3aed", highlightthickness=2)

            # Header
            hdr = tk.Frame(self.frame, bg="#13132b")
            hdr.pack(fill="x")

            self.dot = tk.Label(hdr, text="●", font=("Arial", 9), fg="#ef4444", bg="#13132b")
            self.dot.pack(side="left", padx=6)

            tk.Label(
                hdr, text="GeoSolver", font=("Segoe UI", 9, "bold"),
                fg="#a78bfa", bg="#13132b"
            ).pack(side="left")

            self.status_text = tk.Label(
                hdr, text="", font=("Segoe UI", 8),
                fg="#666", bg="#13132b"
            ).pack(side="left", padx=8)

            close_lbl = tk.Label(
                hdr, text="✕", font=("Segoe UI", 10),
                fg="#555", bg="#13132b", padx=8, cursor="hand2"
            )
            close_lbl.pack(side="right")
            close_lbl.bind("<Button-1>", lambda e: self._quit())

            # Location
            self.loc_label = tk.Label(
                self.frame, text="Запуск...",
                font=("Segoe UI", 14, "bold"), fg="#e2e2ff",
                bg="#0d0d1a", anchor="w", padx=10, pady=6,
                wraplength=360, justify="left"
            )
            self.loc_label.pack(fill="x")

            # Coords + link
            bottom = tk.Frame(self.frame, bg="#0d0d1a")
            bottom.pack(fill="x")

            self.coords_label = tk.Label(
                bottom, text="", font=("Consolas", 9),
                fg="#555577", bg="#0d0d1a", anchor="w", padx=10
            )
            self.coords_label.pack(side="left")

            self.maps_link = tk.Label(
                bottom, text="", font=("Segoe UI", 9, "underline"),
                fg="#7c3aed", bg="#0d0d1a", cursor="hand2", padx=10
            )
            self.maps_link.pack(side="right")
            self.maps_link.bind("<Button-1>", lambda e: self._open_maps())

            # State
            self.coords = None
            self.cdp = None
            self._reconnect_count = 0

            # Start connection loop
            self.root.after(300, self._connect)

        def _drag_start(self, e):
            self._dx = e.x
            self._dy = e.y

        def _drag_move(self, e):
            x = self.root.winfo_x() + e.x - self._dx
            y = self.root.winfo_y() + e.y - self._dy
            self.root.geometry(f"+{x}+{y}")

        def _quit(self):
            if self.cdp:
                self.cdp.stop()
            self.root.destroy()

        def _set_state(self, state, text):
            colors = {
                "connected": "#22c55e",
                "searching": "#f59e0b",
                "error": "#ef4444",
            }
            self.dot.config(fg=colors.get(state, "#666"))
            self.loc_label.config(text=text, fg="#888899")
            self.coords_label.config(text="")
            self.maps_link.config(text="")

        def _connect(self):
            """Try to find and connect to GeoGuessr."""
            self._set_state("searching", "Поиск GeoGuessr...")

            target, status = find_target()

            if status == "not_running":
                self._set_state("error", "Steam не запущен или нет флагов CDP")
                self._schedule_reconnect(4000)
                return
            elif status == "missing_origins":
                self._set_state("error", "Нужен флаг --remote-allow-origins=*")
                self._schedule_reconnect(4000)
                return
            elif status == "no_geoguessr":
                self._set_state("searching", "Откройте GeoGuessr в Steam")
                self._schedule_reconnect(2000)
                return
            elif status != "ok":
                self._set_state("error", f"Ошибка: {status}")
                self._schedule_reconnect(3000)
                return

            # Connect to target
            ws_url = target.get("webSocketDebuggerUrl", "")
            if not ws_url:
                self._set_state("error", "Нет WebSocket URL")
                self._schedule_reconnect(3000)
                return

            self._set_state("connected", "Подключено! Ожидание раунда...")
            self._reconnect_count = 0

            self.cdp = CDPClient(ws_url, self._on_coords)
            self.cdp.start()

            # Monitor connection health
            self.root.after(3000, self._check_health)

        def _schedule_reconnect(self, delay_ms):
            self._reconnect_count += 1
            # Exponential backoff up to 10s
            actual_delay = min(delay_ms * (1.5 ** min(self._reconnect_count, 5)), 10000)
            self.root.after(int(actual_delay), self._connect)

        def _check_health(self):
            """Check if CDP connection is still alive."""
            if not self.cdp or not self.cdp.connected:
                log("info", "Соединение потеряно, переподключение...")
                self._set_state("searching", "Переподключение...")
                self.cdp = None
                self.root.after(2000, self._connect)
            else:
                self.root.after(5000, self._check_health)

        def _on_coords(self, lat, lng):
            """Called from CDP thread when coordinates are found."""
            self.coords = (lat, lng)
            self.root.after(0, lambda: self._show_coords(lat, lng))

        def _show_coords(self, lat, lng):
            """Update UI with new coordinates."""
            self.coords_label.config(text=f"{lat:.5f}, {lng:.5f}")
            self.maps_link.config(text="Google Maps →")
            self.loc_label.config(text="Определяю город...", fg="#a78bfa")

            # Geocode in background
            threading.Thread(
                target=self._do_geocode, args=(lat, lng), daemon=True
            ).start()

        def _do_geocode(self, lat, lng):
            location = reverse_geocode(lat, lng)
            self.root.after(0, lambda: self.loc_label.config(
                text=f"📍 {location}", fg="#e2e2ff"
            ))

        def _open_maps(self):
            if self.coords:
                webbrowser.open(
                    f"https://www.google.com/maps/@{self.coords[0]},{self.coords[1]},14z"
                )

        def run(self):
            self.root.mainloop()

    return SolverApp()


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print()
    print("  ╔═══════════════════════════════════════════╗")
    print("  ║  GeoSolver — CDP Mode (100% accuracy)    ║")
    print("  ╚═══════════════════════════════════════════╝")
    print()
    print("  Настройка Steam:")
    print("  GeoGuessr → Свойства → Параметры запуска:")
    print("  --remote-debugging-port=34788 --remote-allow-origins=*")
    print()
    print("  ЛКМ — перетащить | ПКМ или ✕ — закрыть")
    print()
    print("─" * 50)
    print()

    app = create_overlay()
    app.run()


if __name__ == "__main__":
    main()
