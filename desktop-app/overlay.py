"""
Overlay window for GeoGuessr Solver.
Shows results in an always-on-top transparent overlay.
"""

import tkinter as tk
import webbrowser


class ResultOverlay:
    """Always-on-top overlay window showing location results."""

    def __init__(self):
        self.root = tk.Toplevel()
        self.root.title("GeoSolver")
        self.root.geometry("300x180+50+50")
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#1a1a2e")
        self.root.overrideredirect(True)  # No window borders

        # Make window draggable
        self._drag_data = {"x": 0, "y": 0}
        self.root.bind("<ButtonPress-1>", self._start_drag)
        self.root.bind("<B1-Motion>", self._on_drag)

        # Content
        self.frame = tk.Frame(self.root, bg="#1a1a2e", relief="solid", bd=1)
        self.frame.pack(fill="both", expand=True)
        self.frame.configure(highlightbackground="#00ff88", highlightthickness=1)

        # Header
        header = tk.Frame(self.frame, bg="#0d1117")
        header.pack(fill="x")

        tk.Label(
            header,
            text="📍 GeoSolver",
            font=("Segoe UI", 11, "bold"),
            fg="#00ff88",
            bg="#0d1117",
            padx=8,
            pady=4,
        ).pack(side="left")

        # Close button
        close_btn = tk.Label(
            header,
            text="✕",
            font=("Segoe UI", 11),
            fg="#888",
            bg="#0d1117",
            cursor="hand2",
            padx=8,
            pady=4,
        )
        close_btn.pack(side="right")
        close_btn.bind("<Button-1>", lambda e: self.hide())

        # Content area
        self.content = tk.Label(
            self.frame,
            text="Ожидание...",
            font=("Courier New", 10),
            fg="#aaa",
            bg="#1a1a2e",
            justify="left",
            anchor="nw",
            wraplength=280,
            padx=8,
            pady=8,
        )
        self.content.pack(fill="both", expand=True)

        # Maps link
        self.maps_label = tk.Label(
            self.frame,
            text="",
            font=("Segoe UI", 9),
            fg="#4da6ff",
            bg="#1a1a2e",
            cursor="hand2",
            padx=8,
            pady=4,
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
        """Update overlay with new result."""
        lines = []

        if result.get("country"):
            lines.append(f"🌍 {result['country']}")
        if result.get("region"):
            lines.append(f"📍 {result['region']}")
        if result.get("confidence"):
            lines.append(f"📊 {result['confidence']}%")
        if result.get("lat") and result.get("lng"):
            lines.append(f"📐 {result['lat']:.4f}, {result['lng']:.4f}")
            self.coords = (result["lat"], result["lng"])
            self.maps_label.config(text="🗺️ Открыть в Maps")
            self.maps_label.bind("<Button-1>", self._open_maps)

        if lines:
            self.content.config(text="\n".join(lines), fg="#00ff88")
        else:
            self.content.config(text="Не определено", fg="#888")

        self.show()

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
