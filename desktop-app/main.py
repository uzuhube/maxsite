"""
GeoGuessr Solver - Desktop Application
Auto location recognition for GeoGuessr (Steam/Browser)

Works by:
1. Capturing screen on hotkey press
2. Analyzing the image using OCR and visual heuristics
3. Showing city/country in a transparent overlay on top of the game

Compatible with Python 3.14+
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
        self.root.geometry("380x420")
        self.root.configure(bg="#1a1a2e")
        self.root.resizable(False, False)

        self.capture = ScreenCapture()
        self.analyzer = LocationAnalyzer()
        self.overlay = None
        self.is_running = False
        self._mainloop_started = False

        self._setup_ui()
        self._create_overlay()

        # Delay hotkey setup until after mainloop starts
        self.root.after(100, self._setup_hotkey)

    def _create_overlay(self):
        """Create the transparent game overlay."""
        try:
            self.overlay = ResultOverlay(self.root)
        except Exception as e:
            print(f"Warning: overlay creation failed: {e}")

    def _setup_ui(self):
        # Title
        title_frame = tk.Frame(self.root, bg="#1a1a2e")
        title_frame.pack(fill="x", padx=20, pady=15)

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
            text="⏸️ Нажмите Start или Ctrl+Shift+G",
            font=("Segoe UI", 11),
            fg="#aaa",
            bg="#2a2a3e",
            wraplength=320,
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
            width=12,
            pady=8,
        )
        self.start_btn.pack(side="left", padx=5)

        self.scan_btn = tk.Button(
            ctrl_frame,
            text="📷 Scan",
            font=("Segoe UI", 12),
            fg="#fff",
            bg="#444",
            activebackground="#555",
            relief="flat",
            cursor="hand2",
            command=self.manual_scan,
            width=12,
            pady=8,
        )
        self.scan_btn.pack(side="right", padx=5)

        # Overlay controls
        overlay_frame = tk.Frame(self.root, bg="#1a1a2e")
        overlay_frame.pack(fill="x", padx=20, pady=5)

        tk.Label(
            overlay_frame,
            text="Прозрачность:",
            font=("Segoe UI", 9),
            fg="#888",
            bg="#1a1a2e",
        ).pack(side="left")

        self.opacity_scale = tk.Scale(
            overlay_frame,
            from_=30,
            to=100,
            orient="horizontal",
            length=140,
            bg="#1a1a2e",
            fg="#00ff88",
            troughcolor="#333",
            highlightthickness=0,
            command=self._on_opacity_change,
        )
        self.opacity_scale.set(75)
        self.opacity_scale.pack(side="right")

        self.overlay_btn = tk.Button(
            overlay_frame,
            text="👁",
            font=("Segoe UI", 10),
            fg="#fff",
            bg="#333",
            relief="flat",
            cursor="hand2",
            command=self._toggle_overlay,
            width=3,
        )
        self.overlay_btn.pack(side="right", padx=5)

        # Result display
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
            font=("Segoe UI", 11),
            fg="#00ff88",
            bg="#0d1117",
            relief="flat",
            height=6,
            wrap="word",
            padx=10,
            pady=10,
        )
        self.result_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.result_text.insert("1.0", "Ожидание сканирования...\n\nНажмите Start или Ctrl+Shift+G")
        self.result_text.config(state="disabled")

        # Footer
        footer = tk.Frame(self.root, bg="#1a1a2e")
        footer.pack(fill="x", padx=20, pady=8)

        tk.Label(
            footer,
            text="Ctrl+Shift+G — сканировать | ПКМ на оверлее — скрыть",
            font=("Segoe UI", 8),
            fg="#555",
            bg="#1a1a2e",
        ).pack()

        self.last_coords = None

    def _on_opacity_change(self, value):
        """Change overlay opacity."""
        if self.overlay:
            self.overlay.set_opacity(int(value) / 100.0)

    def _toggle_overlay(self):
        """Toggle overlay visibility."""
        if self.overlay:
            self.overlay.toggle()

    def _setup_hotkey(self):
        """Setup global hotkey listener (called after mainloop starts)."""
        self._mainloop_started = True
        try:
            from pynput import keyboard

            def on_activate():
                if self._mainloop_started:
                    self.root.after(0, self.manual_scan)

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
        except ImportError:
            self.status_label.config(
                text="⚠️ pynput не установлен — горячие клавиши отключены",
                fg="#ffcc00",
            )
        except Exception as e:
            print(f"Hotkey setup error: {e}")

    def toggle_capture(self):
        """Toggle auto-capture mode."""
        if self.is_running:
            self.is_running = False
            self.start_btn.config(text="▶️ Start", bg="#00ff88")
            self.status_label.config(text="⏸️ Остановлено", fg="#aaa")
        else:
            self.is_running = True
            self.start_btn.config(text="⏹️ Stop", bg="#ff4444")
            self.status_label.config(text="🔄 Авто-сканирование...", fg="#00ff88")
            self._auto_scan_loop()

    def _auto_scan_loop(self):
        """Auto scan every 3 seconds."""
        if not self.is_running:
            return
        self._do_scan_safe()
        self.root.after(3000, self._auto_scan_loop)

    def manual_scan(self):
        """Perform a single scan."""
        self.status_label.config(text="🔍 Сканирование...", fg="#ffcc00")
        self._do_scan_safe()

    def _do_scan_safe(self):
        """Run scan in background thread, safely update UI."""
        def worker():
            try:
                image = self.capture.grab_screen()
                result = self.analyzer.analyze(image)
                self.root.after(0, lambda: self._show_result(result))
            except Exception as e:
                error_msg = str(e).split("\n")[0][:60]
                self.root.after(
                    0,
                    lambda: self.status_label.config(
                        text=f"❌ {error_msg}", fg="#ff4444"
                    ),
                )

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def _show_result(self, result):
        """Display analysis result in both main window and overlay."""
        # Update overlay (shows city/country on top of game)
        if self.overlay:
            try:
                self.overlay.update(result)
            except Exception:
                pass

        # Update main window text
        self.result_text.config(state="normal")
        self.result_text.delete("1.0", "end")

        lines = []
        if result.get("country"):
            lines.append(f"📍 {result['country']}")
        if result.get("confidence"):
            lines.append(f"Точность: {result['confidence']}%")
        if result.get("clues"):
            lines.append("")
            for clue in result["clues"][:5]:
                lines.append(f"  • {clue}")

        if lines:
            self.result_text.insert("1.0", "\n".join(lines))
            self.status_label.config(text="✅ Место определено!", fg="#00ff88")
        else:
            self.result_text.insert("1.0", "Не удалось определить.\nПопробуйте другой ракурс.")
            self.status_label.config(text="⚠️ Не определено", fg="#ffcc00")

        self.result_text.config(state="disabled")

    def run(self):
        """Start the application."""
        self.root.mainloop()


if __name__ == "__main__":
    app = GeoGuessrSolver()
    app.run()
