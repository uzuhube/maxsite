"""
GeoGuessr Solver — CDP Mode (100% accuracy, no proxy needed)

Connects to Steam's Chrome DevTools Protocol to intercept
GeoGuessr network traffic and extract exact coordinates.

Setup:
  1. Steam → GeoGuessr → Properties → Launch Options:
     --remote-debugging-port=34788 --remote-allow-origins=*
  2. pip install websocket-client requests Pillow
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
        self._responses = {}  # msg_id -> threading.Event
        self._response_data = {}  # msg_id -> result data
        self._rpc_requests = {}  # request_id -> url (max 20)
        self._resolved_panos = set()
        self._last_coords = None
        self._running = False
        self._connected = False
        self._network_log_count = 0
        self._coords_found_this_round = False  # Debounce: 1 result per round
        self._last_result_time = 0  # Debounce timer
        self._active_threads = 0  # Limit concurrent threads
        self._max_threads = 2

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
        # Force IPv4 127.0.0.1 (Windows blocks IPv6 localhost WebSocket)
        ws_url = self.ws_url.replace("localhost", "127.0.0.1")
        log("info", f"Подключение к: {ws_url[:80]}")

        self.ws = websocket.WebSocket()
        self.ws.settimeout(1.0)

        try:
            # Create a raw IPv4 socket first to avoid Windows permission issues
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)

            # Parse host:port from ws URL (ws://127.0.0.1:34788/devtools/...)
            import urllib.parse
            parsed = urllib.parse.urlparse(ws_url)
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or 34788

            sock.connect((host, port))
            sock.settimeout(1.0)

            # Connect websocket over the existing socket
            self.ws.connect(
                ws_url,
                socket=sock,
                suppress_origin=True,
                skip_utf8_validation=True,
            )
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
            error_str = str(e)
            if "10013" in error_str:
                log("err", f"Windows блокирует WebSocket соединение!")
                log("err", f"Решения:")
                log("err", f"  1. Запустите от имени администратора")
                log("err", f"  2. Отключите антивирус/файрвол временно")
                log("err", f"  3. Добавьте Python в исключения файрвола")
            else:
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

            # Log first 10 network responses for debugging
            if self._network_log_count < 10 and url and not url.startswith("data:"):
                self._network_log_count += 1
                maps_marker = " <MAPS>" if "maps.googleapis" in url else ""
                log("info", f"  NET [{self._network_log_count}]: {url[:70]}{maps_marker}")

            if self._is_maps_rpc(url):
                self._rpc_requests[request_id] = url
                log("data", f"Maps RPC: {url[:80]}")

        elif method == "Network.loadingFinished":
            request_id = params.get("requestId", "")
            if request_id in self._rpc_requests:
                del self._rpc_requests[request_id]
                # Skip if we already have coords for this round (debounce)
                if self._coords_found_this_round:
                    return
                # Limit concurrent processing threads
                if self._active_threads >= self._max_threads:
                    return
                self._active_threads += 1
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
        if "maps.googleapis.com/$rpc" in url:
            return True
        if "maps.googleapis.com" in url and (
            "SingleImageSearch" in url or
            "GeoPhotoService" in url or
            "GetMetadata" in url or
            "Streetview" in url or
            "$rpc" in url
        ):
            return True
        return False

    def _fetch_and_process_body(self, request_id):
        """Fetch response body and extract pano IDs."""
        try:
            if self._coords_found_this_round:
                return

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

            # Try direct coordinate extraction first (fastest)
            coords = self._extract_coords_direct(body)
            if coords:
                lat, lng = coords
                if self._validate_coords(lat, lng):
                    self._emit_coords(lat, lng)
                    return

            # Try pano IDs (only resolve first one)
            panos = self._extract_panos(body)
            if panos:
                pano_id = panos[0]
                if pano_id not in self._resolved_panos:
                    self._resolved_panos.add(pano_id)
                    log("data", f"Pano ID: {pano_id[:24]}...")
                    self._resolve_pano(pano_id)  # Run in same thread (no new thread)
        finally:
            self._active_threads = max(0, self._active_threads - 1)

    def _emit_coords(self, lat, lng):
        """Emit coordinates with debounce (max 1 per 3 seconds)."""
        now = time.time()
        if now - self._last_result_time < 3.0:
            return
        self._last_result_time = now
        self._coords_found_this_round = True
        self._last_coords = (lat, lng)
        log("ok", f"КООРДИНАТЫ: {lat:.6f}, {lng:.6f}")
        self.on_coords(lat, lng)
        # Reset debounce after 5 seconds (for next round)
        threading.Timer(5.0, self._reset_round).start()

    def _reset_round(self):
        """Allow new coordinates after round change."""
        self._coords_found_this_round = False
        # Clean up old data to prevent memory buildup
        if len(self._resolved_panos) > 50:
            self._resolved_panos.clear()
        if len(self._rpc_requests) > 20:
            self._rpc_requests.clear()
        if len(self._responses) > 10:
            # Clean stale responses
            stale = [k for k, v in self._responses.items() if v.is_set()]
            for k in stale:
                self._responses.pop(k, None)
                self._response_data.pop(k, None)

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
            self._emit_coords(lat, lng)

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

    # Priority (same as GeoHelper): iframe > page, game > any
    # Network traffic for Maps RPC happens in the IFRAME, not the page shell
    game_iframe = next((t for t in targets if t.get("type") == "iframe" and is_geo(t) and is_game(t) and has_ws(t)), None)
    game_page = next((t for t in targets if t.get("type") == "page" and is_geo(t) and is_game(t) and has_ws(t)), None)
    any_iframe = next((t for t in targets if t.get("type") == "iframe" and is_geo(t) and has_ws(t)), None)
    any_page = next((t for t in targets if t.get("type") == "page" and is_geo(t) and has_ws(t)), None)

    # Pick in priority order: game iframe > game page > any iframe > any page
    picked = game_iframe or game_page or any_iframe or any_page

    if picked:
        target_type = picked.get("type", "")
        target_url = picked.get("url", "")[:60]
        log("ok", f"Цель: [{target_type}] {target_url}")
    else:
        return None, "no_geoguessr"

    # Fix WebSocket URL: force 127.0.0.1 instead of localhost (Windows IPv6 fix)
    ws_url = picked.get("webSocketDebuggerUrl", "")
    ws_url = ws_url.replace("localhost", "127.0.0.1")
    picked["webSocketDebuggerUrl"] = ws_url

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


# ─── Map Tiles ────────────────────────────────────────────────────────────────

import math
import io

# Simple tile cache to avoid re-downloading
_tile_cache = {}  # (zoom, x, y) -> bytes
_tile_session = None


def _get_tile_session():
    global _tile_session
    if _tile_session is None:
        _tile_session = requests.Session()
        _tile_session.headers["User-Agent"] = "GeoSolver/2.0"
    return _tile_session


def fetch_map_tile(lat, lng, zoom, size=120):
    """Fetch a static map image from OSM tile server. Uses cache."""
    try:
        from PIL import Image, ImageDraw, ImageTk

        n = 2 ** zoom
        x_tile = int((lng + 180.0) / 360.0 * n)
        lat_rad = math.radians(lat)
        y_tile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)

        cache_key = (zoom, x_tile, y_tile)
        if cache_key in _tile_cache:
            tile_bytes = _tile_cache[cache_key]
        else:
            url = f"https://tile.openstreetmap.org/{zoom}/{x_tile}/{y_tile}.png"
            sess = _get_tile_session()
            resp = sess.get(url, timeout=4)
            if resp.status_code != 200:
                return None
            tile_bytes = resp.content
            # Cache (limit to 30 tiles)
            if len(_tile_cache) > 30:
                _tile_cache.clear()
            _tile_cache[cache_key] = tile_bytes

        tile = Image.open(io.BytesIO(tile_bytes)).convert("RGB")

        # Calculate pixel offset within tile
        x_frac = (lng + 180.0) / 360.0 * n - x_tile
        y_frac = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n - y_tile
        px = int(x_frac * 256)
        py = int(y_frac * 256)

        # Crop centered on the point
        half = size // 2
        padded = Image.new("RGB", (256 + size, 256 + size), (13, 13, 26))
        padded.paste(tile, (half, half))
        cropped = padded.crop((px, py, px + size, py + size))

        # Draw red marker
        draw = ImageDraw.Draw(cropped)
        cx, cy = size // 2, size // 2
        draw.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill="#ef4444", outline="#ffffff")

        return ImageTk.PhotoImage(cropped)
    except Exception as e:
        log("err", f"Карта z{zoom}: {e}")
        return None


# ─── GUI Overlay ──────────────────────────────────────────────────────────────

def create_overlay():
    """Create the overlay application with mini-maps."""
    import tkinter as tk

    class SolverApp:
        def __init__(self):
            self.root = tk.Tk()
            self.root.title("GeoSolver")
            self.root.geometry("410x280+50+50")
            self.root.attributes("-topmost", True)
            self.root.attributes("-alpha", 0.92)
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

            close_lbl = tk.Label(
                hdr, text="✕", font=("Segoe UI", 10),
                fg="#555", bg="#13132b", padx=8, cursor="hand2"
            )
            close_lbl.pack(side="right")
            close_lbl.bind("<Button-1>", lambda e: self._quit())

            # Location text
            self.loc_label = tk.Label(
                self.frame, text="Запуск...",
                font=("Segoe UI", 13, "bold"), fg="#e2e2ff",
                bg="#0d0d1a", anchor="w", padx=10, pady=4,
                wraplength=410, justify="left"
            )
            self.loc_label.pack(fill="x")

            # Coords + link row
            info_row = tk.Frame(self.frame, bg="#0d0d1a")
            info_row.pack(fill="x")

            self.coords_label = tk.Label(
                info_row, text="", font=("Consolas", 9),
                fg="#555577", bg="#0d0d1a", anchor="w", padx=10
            )
            self.coords_label.pack(side="left")

            self.maps_link = tk.Label(
                info_row, text="", font=("Segoe UI", 9, "underline"),
                fg="#7c3aed", bg="#0d0d1a", cursor="hand2", padx=10
            )
            self.maps_link.pack(side="right")
            self.maps_link.bind("<Button-1>", lambda e: self._open_maps())

            # Maps row (3 mini-maps: city, country, continent)
            maps_frame = tk.Frame(self.frame, bg="#0d0d1a")
            maps_frame.pack(fill="x", padx=6, pady=4)

            MAP_SIZE = 120

            # City map (zoom 12)
            city_col = tk.Frame(maps_frame, bg="#0d0d1a")
            city_col.pack(side="left", padx=2)
            tk.Label(city_col, text="Город", font=("Segoe UI", 8),
                     fg="#666", bg="#0d0d1a").pack()
            self.map_city = tk.Canvas(city_col, bg="#1a1a2e", width=MAP_SIZE, height=MAP_SIZE, highlightthickness=0)
            self.map_city.pack()

            # Country map (zoom 5)
            country_col = tk.Frame(maps_frame, bg="#0d0d1a")
            country_col.pack(side="left", padx=2)
            tk.Label(country_col, text="Страна", font=("Segoe UI", 8),
                     fg="#666", bg="#0d0d1a").pack()
            self.map_country = tk.Canvas(country_col, bg="#1a1a2e", width=MAP_SIZE, height=MAP_SIZE, highlightthickness=0)
            self.map_country.pack()

            # Continent map (zoom 2)
            cont_col = tk.Frame(maps_frame, bg="#0d0d1a")
            cont_col.pack(side="left", padx=2)
            tk.Label(cont_col, text="Континент", font=("Segoe UI", 8),
                     fg="#666", bg="#0d0d1a").pack()
            self.map_cont = tk.Canvas(cont_col, bg="#1a1a2e", width=MAP_SIZE, height=MAP_SIZE, highlightthickness=0)
            self.map_cont.pack()

            # Keep references to images (prevent GC)
            self._map_images = [None, None, None]

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

            # Stop old CDP if any
            if self.cdp:
                self.cdp.stop()

            self.cdp = CDPClient(ws_url, self._on_coords)
            self.cdp.start()

            # Monitor connection health
            self.root.after(3000, self._check_health)

        def _schedule_reconnect(self, delay_ms):
            self._reconnect_count += 1
            actual_delay = min(delay_ms * (1.2 ** min(self._reconnect_count, 8)), 8000)
            self.root.after(int(actual_delay), self._connect)

        def _check_health(self):
            """Check if CDP connection is still alive."""
            if not self.cdp or not self.cdp.connected:
                log("info", "Соединение потеряно, переподключение...")
                self._set_state("searching", "Переподключение...")
                if self.cdp:
                    self.cdp.stop()
                self.cdp = None
                self._reconnect_count = 0
                self.root.after(1500, self._connect)
            else:
                self.root.after(3000, self._check_health)

        def _on_coords(self, lat, lng):
            """Called from CDP thread when coordinates are found."""
            self.coords = (lat, lng)
            self.root.after(0, lambda: self._show_coords(lat, lng))

        def _show_coords(self, lat, lng):
            """Update UI with new coordinates."""
            self.coords_label.config(text=f"{lat:.5f}, {lng:.5f}")
            self.maps_link.config(text="Google Maps →")
            self.loc_label.config(text="Определяю...", fg="#a78bfa")

            # Geocode + load maps in background
            threading.Thread(
                target=self._do_geocode, args=(lat, lng), daemon=True
            ).start()
            threading.Thread(
                target=self._load_maps, args=(lat, lng), daemon=True
            ).start()

        def _do_geocode(self, lat, lng):
            location = reverse_geocode(lat, lng)
            self.root.after(0, lambda: self.loc_label.config(
                text=f"📍 {location}", fg="#e2e2ff"
            ))

        def _load_maps(self, lat, lng):
            """Load three map tiles in parallel."""
            import concurrent.futures

            zooms = [(12, self.map_city, 0), (5, self.map_country, 1), (2, self.map_cont, 2)]

            def load_one(zoom, widget, idx):
                img = fetch_map_tile(lat, lng, zoom)
                if img:
                    self._map_images[idx] = img
                    self.root.after(0, lambda w=widget, i=img: self._set_map(w, i))

            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
                for z, w, i in zooms:
                    pool.submit(load_one, z, w, i)

        def _set_map(self, canvas, img):
            """Set image on canvas widget."""
            canvas.delete("all")
            canvas.create_image(60, 60, image=img)

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
