"""
GeoGuessr Solver - Proxy Mode (100% accuracy for Steam)

Launches a local HTTPS proxy that intercepts GeoGuessr traffic
and shows exact coordinates in an overlay on top of the game.

Usage:
    python proxy_solver.py

Requirements:
    pip install mitmproxy requests Pillow
    + Install mitmproxy CA certificate (see README)
"""

import os
import sys
import json
import time
import threading
import subprocess
import tkinter as tk
import webbrowser
import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
COORDS_FILE = os.path.join(SCRIPT_DIR, ".coords.json")
ADDON_SCRIPT = os.path.join(SCRIPT_DIR, "proxy_addon.py")
PROXY_PORT = 8082


class ProxyOverlay:
    """Transparent overlay showing intercepted location."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("GeoGuessr Solver - Proxy")
        self.root.geometry("320x120+30+30")
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.80)
        self.root.overrideredirect(True)
        self.root.configure(bg="#000000")

        # Draggable
        self._drag_data = {"x": 0, "y": 0}
        self.root.bind("<ButtonPress-1>", self._start_drag)
        self.root.bind("<B1-Motion>", self._on_drag)
        self.root.bind("<ButtonPress-3>", lambda e: self.root.destroy())

        # Frame
        self.frame = tk.Frame(self.root, bg="#000000")
        self.frame.pack(fill="both", expand=True, padx=1, pady=1)
        self.frame.configure(highlightbackground="#00ff88", highlightthickness=2)

        # Header
        self.header = tk.Label(
            self.frame,
            text="🌍 GeoGuessr Solver [PROXY]",
            font=("Segoe UI", 10, "bold"),
            fg="#00ff88",
            bg="#000000",
            anchor="w",
            padx=8,
            pady=4,
        )
        self.header.pack(fill="x")

        # Location
        self.location_label = tk.Label(
            self.frame,
            text="⏳ Ожидание координат...",
            font=("Segoe UI", 14, "bold"),
            fg="#ffffff",
            bg="#000000",
            anchor="w",
            padx=8,
            pady=4,
        )
        self.location_label.pack(fill="x")

        # Subtitle
        self.subtitle = tk.Label(
            self.frame,
            text="Прокси активен на порту 8082",
            font=("Segoe UI", 9),
            fg="#888888",
            bg="#000000",
            anchor="w",
            padx=8,
            pady=2,
        )
        self.subtitle.pack(fill="x")

        # Maps link
        self.maps_label = tk.Label(
            self.frame,
            text="",
            font=("Segoe UI", 9, "underline"),
            fg="#4da6ff",
            bg="#000000",
            cursor="hand2",
            anchor="w",
            padx=8,
            pady=2,
        )
        self.maps_label.pack(fill="x")

        self.coords = None
        self.last_modified = 0

        # Start polling for coords
        self._poll_coords()

    def _start_drag(self, event):
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y

    def _on_drag(self, event):
        x = self.root.winfo_x() + event.x - self._drag_data["x"]
        y = self.root.winfo_y() + event.y - self._drag_data["y"]
        self.root.geometry(f"+{x}+{y}")

    def _poll_coords(self):
        """Check coords file every 500ms for new coordinates."""
        try:
            if os.path.exists(COORDS_FILE):
                mtime = os.path.getmtime(COORDS_FILE)
                if mtime > self.last_modified:
                    self.last_modified = mtime
                    with open(COORDS_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    lat = data.get("lat")
                    lng = data.get("lng")
                    if lat and lng:
                        self.coords = (lat, lng)
                        self.location_label.config(text=f"📍 {lat:.5f}, {lng:.5f}")
                        self.maps_label.config(text="🗺️ Открыть на карте")
                        self.maps_label.bind("<Button-1>", self._open_maps)
                        # Reverse geocode
                        threading.Thread(
                            target=self._reverse_geocode,
                            args=(lat, lng),
                            daemon=True,
                        ).start()
        except Exception:
            pass

        self.root.after(500, self._poll_coords)

    def _reverse_geocode(self, lat, lng):
        """Get city/country name from coordinates."""
        try:
            resp = requests.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={
                    "lat": lat,
                    "lon": lng,
                    "format": "json",
                    "zoom": 10,
                    "accept-language": "ru",
                },
                headers={"User-Agent": "GeoGuessrSolver/1.0"},
                timeout=5,
            )
            data = resp.json()

            if data.get("address"):
                addr = data["address"]
                parts = []
                city = (
                    addr.get("city")
                    or addr.get("town")
                    or addr.get("village")
                    or addr.get("municipality")
                )
                if city:
                    parts.append(city)
                state = addr.get("state")
                if state and state != city:
                    parts.append(state)
                country = addr.get("country")
                if country:
                    parts.append(country)

                if parts:
                    location_text = ", ".join(parts)
                    self.root.after(
                        0,
                        lambda t=location_text: self.location_label.config(
                            text=f"📍 {t}", fg="#00ff88"
                        ),
                    )
                    self.root.after(
                        0,
                        lambda: self.subtitle.config(
                            text=f"{lat:.4f}, {lng:.4f}"
                        ),
                    )
        except Exception:
            pass

    def _open_maps(self, event=None):
        if self.coords:
            url = f"https://www.google.com/maps?q={self.coords[0]},{self.coords[1]}"
            webbrowser.open(url)

    def run(self):
        self.root.mainloop()


def check_mitmproxy():
    """Check if mitmproxy is installed."""
    try:
        result = subprocess.run(
            ["mitmdump", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def start_proxy():
    """Start mitmproxy in background with our addon."""
    cmd = [
        "mitmdump",
        "--listen-port", str(PROXY_PORT),
        "--set", "stream_large_bodies=1",
        "--scripts", ADDON_SCRIPT,
        "--quiet",
    ]

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    return process


def show_setup_window():
    """Show setup instructions if mitmproxy is not installed."""
    root = tk.Tk()
    root.title("GeoGuessr Solver - Настройка")
    root.geometry("500x400")
    root.configure(bg="#1a1a2e")

    tk.Label(
        root,
        text="🌍 GeoGuessr Solver - Настройка прокси",
        font=("Segoe UI", 14, "bold"),
        fg="#00ff88",
        bg="#1a1a2e",
    ).pack(pady=15)

    instructions = """
❌ mitmproxy не найден!

Для 100% точного определения координат в Steam
нужно установить mitmproxy:

1. Скачай: https://mitmproxy.org/
   или: pip install mitmproxy

2. Установи сертификат:
   - Запусти: mitmdump
   - Открой: http://mitm.it
   - Скачай и установи сертификат для Windows

3. Настрой прокси в Windows:
   Параметры → Сеть → Прокси →
   Адрес: 127.0.0.1  Порт: 8082

4. Запусти снова: python proxy_solver.py
"""

    text = tk.Text(
        root,
        font=("Consolas", 10),
        fg="#eee",
        bg="#0d1117",
        relief="flat",
        wrap="word",
        padx=15,
        pady=15,
    )
    text.pack(fill="both", expand=True, padx=20, pady=10)
    text.insert("1.0", instructions)
    text.config(state="disabled")

    def open_mitmproxy_site():
        webbrowser.open("https://mitmproxy.org/")

    tk.Button(
        root,
        text="📥 Открыть сайт mitmproxy",
        font=("Segoe UI", 11),
        fg="#000",
        bg="#00ff88",
        relief="flat",
        cursor="hand2",
        command=open_mitmproxy_site,
        pady=8,
    ).pack(fill="x", padx=20, pady=10)

    root.mainloop()


def main():
    # Clean old coords file
    if os.path.exists(COORDS_FILE):
        os.remove(COORDS_FILE)

    # Check mitmproxy
    if not check_mitmproxy():
        show_setup_window()
        return

    # Start proxy in background
    print(f"[*] Starting proxy on port {PROXY_PORT}...")
    proxy_process = start_proxy()
    time.sleep(1)

    # Check if proxy started
    if proxy_process.poll() is not None:
        print("[!] Failed to start proxy. Check if port 8082 is free.")
        show_setup_window()
        return

    print(f"[*] Proxy running on 127.0.0.1:{PROXY_PORT}")
    print("[*] Configure Windows proxy: 127.0.0.1:8082")
    print("[*] Overlay started. Right-click to close.")
    print()

    # Start overlay
    try:
        overlay = ProxyOverlay()
        overlay.run()
    finally:
        proxy_process.terminate()
        if os.path.exists(COORDS_FILE):
            os.remove(COORDS_FILE)
        print("[*] Proxy stopped.")


if __name__ == "__main__":
    main()
