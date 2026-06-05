"""
GeoGuessr Solver - Desktop Application
Auto location recognition for GeoGuessr (Steam/Browser)

Works by:
1. Capturing screen on hotkey press
2. Analyzing the image using OCR and visual heuristics
3. Showing estimated location in an overlay
"""

import sys
import threading
import tkinter as tk
from tkinter import ttk
import webbrowser

from capture import ScreenCapture
from analyzer import LocationAnalyzer
from overlay import ResultOverlay


class GeoGuessrSolver:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("GeoGuessr Solver")
        self.root.geometry("400x500")
        self.root.configure(bg="#1a1a2e")
        self.root.resizable(False, False)

        self.capture = ScreenCapture()
        self.analyzer = LocationAnalyzer()
        self.overlay = None
        self.is_running = False

        self._setup_ui()
        self._setup_hotkey()

    def _setup_ui(self):
        # Title
        title_frame = tk.Frame(self.root, bg="#1a1a2e")
        title_frame.pack(fill="x", padx=20, pady=(20, 10))

        tk.Label(
            title_frame,
            text="🌍 GeoGuessr Solver",
            font=("Segoe UI", 18, "bold"),
            fg="#00ff88",
            bg="#1a1a2e",
        ).pack(anchor="w")

        tk.Label(
            title_frame,
            text="Авто распознавание места (Steam/Browser)",
            font=("Segoe UI", 10),
            fg="#888",
            bg="#1a1a2e",
        ).pack(anchor="w")

        # Status
        status_frame = tk.Frame(self.root, bg="#2a2a3e", relief="flat")
        status_frame.pack(fill="x", padx=20, pady=10)

        self.status_label = tk.Label(
            status_frame,
            text="⏸️ Нажмите Start или используйте Ctrl+Shift+G",
            font=("Segoe UI", 11),
            fg="#aaa",
            bg="#2a2a3e",
            wraplength=340,
            pady=10,
            padx=10,
        )
        self.status_label.pack()

        # Controls
        ctrl_frame = tk.Frame(self.root, bg="#1a1a2e")
        ctrl_frame.pack(fill="x", padx=20, pady=10)

        self.start_btn = tk.Button(
            ctrl_frame,
            text="▶️ Start",
            font=("Segoe UI", 12, "bold"),
            fg="#000",
            bg="#00ff88",
            activebackground="#00cc66",
            relief="flat",
            cursor="hand2",
            command=self.toggle_capture,
            width=15,
            pady=8,
        )
        self.start_btn.pack(side="left", padx=(0, 5))

        self.scan_btn = tk.Button(
            ctrl_frame,
            text="📷 Scan Now",
            font=("Segoe UI", 12),
            fg="#fff",
            bg="#444",
            activebackground="#555",
            relief="flat",
            cursor="hand2",
            command=self.manual_scan,
            width=15,
            pady=8,
        )
        self.scan_btn.pack(side="right", padx=(5, 0))

        # Results
        results_frame = tk.LabelFrame(
            self.root,
            text="Результат",
            font=("Segoe UI", 11),
            fg="#888",
            bg="#1a1a2e",
            relief="flat",
        )
        results_frame.pack(fill="both", expand=True, padx=20, pady=10)

        self.result_text = tk.Text(
            results_frame,
            font=("Courier New", 11),
            fg="#00ff88",
            bg="#0d1117",
            relief="flat",
            height=8,
            wrap="word",
            padx=10,
            pady=10,
        )
        self.result_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.result_text.insert("1.0", "Ожидание сканирования...")
        self.result_text.config(state="disabled")

        # Actions
        action_frame = tk.Frame(self.root, bg="#1a1a2e")
        action_frame.pack(fill="x", padx=20, pady=(0, 10))

        self.maps_btn = tk.Button(
            action_frame,
            text="🗺️ Открыть в Google Maps",
            font=("Segoe UI", 10),
            fg="#4da6ff",
            bg="#1a3a5c",
            activebackground="#2a4a6c",
            relief="flat",
            cursor="hand2",
            command=self.open_maps,
            state="disabled",
        )
        self.maps_btn.pack(fill="x", pady=2)

        # Hotkey info
        tk.Label(
            self.root,
            text="Горячая клавиша: Ctrl+Shift+G",
            font=("Segoe UI", 9),
            fg="#555",
            bg="#1a1a2e",
        ).pack(pady=(0, 10))

        self.last_coords = None

    def _setup_hotkey(self):
        """Setup global hotkey listener."""
        from pynput import keyboard

        def on_activate():
            self.manual_scan()

        hotkey = keyboard.HotKey(
            keyboard.HotKey.parse("<ctrl>+<shift>+g"), on_activate
        )

        def on_press(key):
            hotkey.press(key)

        def on_release(key):
            hotkey.release(key)

        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.daemon = True
        listener.start()

    def toggle_capture(self):
        """Toggle auto-capture mode."""
        if self.is_running:
            self.is_running = False
            self.start_btn.config(text="▶️ Start", bg="#00ff88")
            self.status_label.config(text="⏸️ Остановлено", fg="#aaa")
        else:
            self.is_running = True
            self.start_btn.config(text="⏹️ Stop", bg="#ff4444")
            self.status_label.config(text="🔄 Авто-сканирование активно...", fg="#00ff88")
            self._auto_scan_loop()

    def _auto_scan_loop(self):
        """Auto scan every 3 seconds."""
        if not self.is_running:
            return
        self.manual_scan()
        self.root.after(3000, self._auto_scan_loop)

    def manual_scan(self):
        """Perform a single scan."""
        self.status_label.config(text="🔍 Сканирование...", fg="#ffcc00")
        threading.Thread(target=self._do_scan, daemon=True).start()

    def _do_scan(self):
        """Scan in background thread."""
        try:
            # Capture screen
            image = self.capture.grab_screen()

            # Analyze
            result = self.analyzer.analyze(image)

            # Update UI in main thread
            self.root.after(0, lambda: self._show_result(result))

        except Exception as e:
            self.root.after(
                0,
                lambda: self.status_label.config(
                    text=f"❌ Ошибка: {str(e)}", fg="#ff4444"
                ),
            )

    def _show_result(self, result):
        """Display analysis result."""
        self.result_text.config(state="normal")
        self.result_text.delete("1.0", "end")

        lines = []
        if result.get("country"):
            lines.append(f"Страна: {result['country']}")
        if result.get("region"):
            lines.append(f"Регион: {result['region']}")
        if result.get("city"):
            lines.append(f"Город: {result['city']}")
        if result.get("confidence"):
            lines.append(f"Уверенность: {result['confidence']}%")
        if result.get("clues"):
            lines.append(f"\nПодсказки:")
            for clue in result["clues"]:
                lines.append(f"  • {clue}")
        if result.get("lat") and result.get("lng"):
            lines.append(f"\nКоординаты: {result['lat']:.4f}, {result['lng']:.4f}")
            self.last_coords = (result["lat"], result["lng"])
            self.maps_btn.config(state="normal")

        if lines:
            self.result_text.insert("1.0", "\n".join(lines))
            self.status_label.config(text="✅ Анализ завершён", fg="#00ff88")
        else:
            self.result_text.insert("1.0", "Не удалось определить место.\nПопробуйте другой ракурс.")
            self.status_label.config(text="⚠️ Место не определено", fg="#ffcc00")

        self.result_text.config(state="disabled")

    def open_maps(self):
        """Open result in Google Maps."""
        if self.last_coords:
            url = f"https://www.google.com/maps?q={self.last_coords[0]},{self.last_coords[1]}"
            webbrowser.open(url)

    def run(self):
        """Start the application."""
        self.root.mainloop()


if __name__ == "__main__":
    app = GeoGuessrSolver()
    app.run()
