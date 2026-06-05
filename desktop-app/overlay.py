"""
Overlay window for GeoGuessr Solver.
Compact, transparent, always-on-top overlay that shows city/country.
Designed to float over the game without blocking the view.
"""

import tkinter as tk
import webbrowser
import threading
import requests


class ResultOverlay:
    """
    Compact transparent always-on-top overlay.
    Shows city/country name instead of raw coordinates.
    """

    def __init__(self, parent=None):
        if parent:
            self.root = tk.Toplevel(parent)
        else:
            self.root = tk.Tk()

        self.root.title("GeoSolver")
        self.root.geometry("280x90+30+30")
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.75)  # 75% opacity - semi-transparent
        self.root.overrideredirect(True)  # No window borders
        self.root.configure(bg="#000000")

        # Make window draggable
        self._drag_data = {"x": 0, "y": 0}
        self.root.bind("<ButtonPress-1>", self._start_drag)
        self.root.bind("<B1-Motion>", self._on_drag)
        # Right-click to close
        self.root.bind("<ButtonPress-3>", lambda e: self.hide())

        # Main frame with thin green border
        self.frame = tk.Frame(self.root, bg="#000000")
        self.frame.pack(fill="both", expand=True, padx=1, pady=1)
        self.frame.configure(highlightbackground="#00ff88", highlightthickness=1)

        # Location label (city/country) - large, prominent
        self.location_label = tk.Label(
            self.frame,
            text="⏳ Ожидание...",
            font=("Segoe UI", 14, "bold"),
            fg="#00ff88",
            bg="#000000",
            anchor="w",
            padx=10,
            pady=6,
        )
        self.location_label.pack(fill="x")

        # Subtitle (confidence + hint)
        self.subtitle_label = tk.Label(
            self.frame,
            text="Ctrl+Shift+G для сканирования",
            font=("Segoe UI", 9),
            fg="#888888",
            bg="#000000",
            anchor="w",
            padx=10,
            pady=(0, 6),
        )
        self.subtitle_label.pack(fill="x")

        # Maps link (subtle, bottom)
        self.maps_label = tk.Label(
            self.frame,
            text="",
            font=("Segoe UI", 9, "underline"),
            fg="#4da6ff",
            bg="#000000",
            cursor="hand2",
            anchor="w",
            padx=10,
            pady=(0, 4),
        )
        self.maps_label.pack(fill="x")

        self.coords = None
        self.root.withdraw()  # Start hidden

    def _start_drag(self, event):
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y

    def _on_drag(self, event):
        x = self.root.winfo_x() + event.x - self._drag_data["x"]
        y = self.root.winfo_y() + event.y - self._drag_data["y"]
        self.root.geometry(f"+{x}+{y}")

    def update(self, result: dict):
        """Update overlay with new result. Shows city/country prominently."""
        # If we have coordinates, do reverse geocoding to get city/country
        if result.get("lat") and result.get("lng"):
            self.coords = (result["lat"], result["lng"])
            # Show country from analysis immediately
            location_text = result.get("country", "Определение...")
            self.location_label.config(text=f"📍 {location_text}", fg="#00ff88")

            # Reverse geocode in background for more detail
            threading.Thread(
                target=self._reverse_geocode,
                args=(result["lat"], result["lng"]),
                daemon=True,
            ).start()

            # Subtitle with confidence
            confidence = result.get("confidence", 0)
            clues = result.get("clues", [])
            hint = clues[0] if clues else ""
            self.subtitle_label.config(
                text=f"Точность: {confidence}%  {hint[:30]}"
            )

            # Maps link
            self.maps_label.config(text="🗺️ Открыть на карте")
            self.maps_label.bind("<Button-1>", self._open_maps)

        elif result.get("country"):
            self.location_label.config(
                text=f"📍 {result['country']}", fg="#00ff88"
            )
            confidence = result.get("confidence", 0)
            self.subtitle_label.config(text=f"Точность: {confidence}%")
            self.maps_label.config(text="")
        else:
            self.location_label.config(text="❓ Не определено", fg="#ffcc00")
            self.subtitle_label.config(text="Попробуйте другой ракурс")
            self.maps_label.config(text="")

        self.show()

    def _reverse_geocode(self, lat, lng):
        """Reverse geocode coordinates to get city/country name."""
        try:
            resp = requests.get(
                f"https://nominatim.openstreetmap.org/reverse",
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
                # City/town
                city = (
                    addr.get("city")
                    or addr.get("town")
                    or addr.get("village")
                    or addr.get("municipality")
                )
                if city:
                    parts.append(city)
                # State/region
                state = addr.get("state")
                if state and state != city:
                    parts.append(state)
                # Country
                country = addr.get("country")
                if country:
                    parts.append(country)

                if parts:
                    location_text = ", ".join(parts)
                    # Update UI from main thread
                    self.root.after(
                        0,
                        lambda: self.location_label.config(
                            text=f"📍 {location_text}", fg="#00ff88"
                        ),
                    )
        except Exception:
            pass

    def _open_maps(self, event=None):
        if self.coords:
            url = f"https://www.google.com/maps?q={self.coords[0]},{self.coords[1]}"
            webbrowser.open(url)

    def show(self):
        self.root.deiconify()

    def hide(self):
        self.root.withdraw()

    def toggle(self):
        if self.root.winfo_viewable():
            self.hide()
        else:
            self.show()

    def set_opacity(self, value):
        """Set overlay opacity (0.0 - 1.0)."""
        self.root.attributes("-alpha", value)
